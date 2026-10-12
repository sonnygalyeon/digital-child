from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from digital_child.config import env_bool, env_float, env_int
from digital_child.interest_catalog import (
    DISCUSSION_GUIDANCE,
    discussion_orientation,
    preferred_interests,
)
from digital_child.models import ConversationMessage, DevelopmentProfile, MessageIntent
from digital_child.psychology_models import PsychologyState


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def elapsed_seconds(now: datetime, previous: datetime) -> float:
    # Moving the system clock backwards cannot manufacture a long absence.
    return max(0.0, (utc(now) - utc(previous)).total_seconds())


@dataclass(frozen=True)
class InitiativeSettings:
    enabled: bool
    poll_seconds: float
    discussion_delay: float
    cooldown: float
    interest_delay: float
    reconnect_cooldown: float
    max_unanswered: int

    @classmethod
    def from_environment(cls) -> InitiativeSettings:
        return cls(
            enabled=env_bool("DIGITAL_CHILD_INITIATIVE_ENABLED", True),
            poll_seconds=max(5.0, env_float("DIGITAL_CHILD_INITIATIVE_POLL_SECONDS", 15.0)),
            discussion_delay=max(30.0, env_float("DIGITAL_CHILD_DISCUSSION_DELAY_SECONDS", 120.0)),
            cooldown=max(60.0, env_float("DIGITAL_CHILD_INITIATIVE_COOLDOWN_SECONDS", 900.0)),
            interest_delay=max(300.0, env_float("DIGITAL_CHILD_INTEREST_DELAY_SECONDS", 3600.0)),
            reconnect_cooldown=max(
                3600.0, env_float("DIGITAL_CHILD_RECONNECT_COOLDOWN_SECONDS", 86400.0)
            ),
            max_unanswered=max(1, min(2, env_int("DIGITAL_CHILD_MAX_UNANSWERED_INITIATIVES", 2))),
        )


@dataclass(frozen=True)
class InitiativePlan:
    person_id: str
    kind: Literal["reconnect", "discussion", "interest", "verification"]
    source: ConversationMessage
    topic: str
    angle: str
    score: float
    reason: str
    orientation: str
    guidance: tuple[str, ...]


class InitiativePlanner:
    def choose(
        self,
        state: PsychologyState,
        profile: DevelopmentProfile,
        latest_inputs: list[ConversationMessage],
        *,
        now: datetime,
        settings: InitiativeSettings,
        energy: float,
    ) -> InitiativePlan | None:
        if not settings.enabled or not state.initiative_enabled or energy < 0.12:
            return None
        choices = preferred_interests(state, profile, 32)
        if not choices:
            return None
        orientation = discussion_orientation(state, profile)
        candidates: list[InitiativePlan] = []
        for source in latest_inputs:
            social = state.relationships.get(source.person_id)
            if social is None or not social.initiative_allowed:
                continue
            if social.quiet_until is not None and utc(now) < utc(social.quiet_until):
                continue
            if social.unanswered_initiatives >= settings.max_unanswered:
                continue
            if social.conflict_load > 0.75 or social.felt_safety < 0.15:
                continue
            if social.last_initiative_attempt_at is not None:
                if elapsed_seconds(now, social.last_initiative_attempt_at) < min(
                    settings.cooldown, 300
                ):
                    continue
            if social.last_initiative_at is not None:
                if elapsed_seconds(now, social.last_initiative_at) < settings.cooldown:
                    continue
            silence = elapsed_seconds(now, source.created_at)
            interest = next(
                (item for item in choices if item.topic not in social.recent_initiative_topics),
                choices[0],
            )
            common = (
                "Напиши короткую самостоятельную реплику из 1–3 предложений.",
                "Не требуй ответа, не упрекай за отсутствие и не изображай события вне памяти.",
                "Вопрос уместен, но не обязателен: можно предложить мысль или свою точку зрения.",
            )
            if silence > 86400:
                # In a single absence, repeated contact has a separate daily cooldown.
                if social.last_initiative_at is not None and social.unanswered_initiatives:
                    if (
                        elapsed_seconds(now, social.last_initiative_at)
                        < settings.reconnect_cooldown
                    ):
                        continue
                candidates.append(
                    InitiativePlan(
                        source.person_id,
                        "reconnect",
                        source,
                        interest.topic,
                        interest.angle,
                        0.65 + social.longing * 0.20 + state.character.sociability * 0.10,
                        "Прошло больше суток без реплики собеседника; "
                        "возникло желание восстановить контакт.",
                        orientation,
                        common
                        + (
                            "Можно кратко сказать, что тебе не хватает общения, "
                            "и предложить значимую тему.",
                        ),
                    )
                )
                continue
            if social.unanswered_initiatives:
                # Wait for a response; reserve a second message for a later-day reconnect.
                continue
            if (
                settings.discussion_delay <= silence <= 6 * 3600
                and social.last_discussion_message_id != source.id
                and source.intent
                in {
                    MessageIntent.OPINION,
                    MessageIntent.QUESTION,
                    MessageIntent.CLAIM,
                    MessageIntent.REQUEST,
                }
            ):
                candidates.append(
                    InitiativePlan(
                        source.person_id,
                        "discussion",
                        source,
                        source.content[:160],
                        DISCUSSION_GUIDANCE[orientation],
                        0.60 + state.character.openness * 0.15,
                        "Есть возможность самостоятельно развить недавнюю дискуссию.",
                        orientation,
                        common
                        + (
                            DISCUSSION_GUIDANCE[orientation],
                            "Добавь новую мысль, а не повторяй предыдущий ответ "
                            "или уже заданный вопрос.",
                        ),
                    )
                )
            elif silence >= settings.interest_delay:
                candidates.append(
                    InitiativePlan(
                        source.person_id,
                        "interest",
                        source,
                        interest.topic,
                        interest.angle,
                        0.45 + interest.strength * 0.15 + state.character.sociability * 0.10,
                        "Личный интерес стал поводом предложить тему без внешнего вопроса.",
                        orientation,
                        common
                        + (
                            "Объясни, что именно тебе интересно в теме; "
                            "не выдавай интерес за установленный факт.",
                        ),
                    )
                )
        return max(
            candidates,
            key=lambda item: (item.score, -utc(item.source.created_at).timestamp(), item.person_id),
            default=None,
        )
