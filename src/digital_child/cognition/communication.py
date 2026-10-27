from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field

from digital_child.domain.models import StrictModel
from digital_child.infrastructure.config import env_int
from digital_child.infrastructure.repository import SQLiteRepository
from digital_child.psychology.appraisal import topic_tokens


class CommunicationPreferences(StrictModel):
    initiative_enabled: bool = True
    frequency: Literal["low", "normal", "high"] = "normal"
    reply_length: Literal["short", "normal", "detailed"] = "normal"
    quiet_enabled: bool = False
    quiet_start: int = Field(default=22, ge=0, le=23)
    quiet_end: int = Field(default=8, ge=0, le=23)
    utc_offset_minutes: int = Field(default=0, ge=-720, le=840)
    blocked_topics: list[str] = Field(default_factory=list, max_length=40)
    topic_snoozes: dict[str, datetime] = Field(default_factory=dict, max_length=32)

    def quiet(self, now: datetime) -> bool:
        hour = (now + timedelta(minutes=self.utc_offset_minutes)).hour
        if not self.quiet_enabled:
            return False
        if self.quiet_start == self.quiet_end:
            return True
        if self.quiet_start < self.quiet_end:
            return self.quiet_start <= hour < self.quiet_end
        return hour >= self.quiet_start or hour < self.quiet_end

    def allows_topic(self, topic: str, now: datetime) -> bool:
        tokens = set(topic_tokens(topic))
        blocked = self.blocked_topics + [
            key for key, until in self.topic_snoozes.items() if until > now
        ]
        return not any(
            key.casefold() in topic.casefold() or bool(tokens & set(topic_tokens(key)))
            for key in blocked
            if key.strip()
        )

    @property
    def cooldown_scale(self) -> float:
        return {"low": 4.0, "normal": 1.0, "high": 0.5}[self.frequency]

    @property
    def reply_chars(self) -> int:
        return {"short": 700, "normal": 2400, "detailed": 8000}[self.reply_length]


class CommunicationSettings:
    def __init__(self, repository: SQLiteRepository, subject_id: str) -> None:
        self.repository, self.subject_id = repository, subject_id

    def get(self, person_id: str) -> CommunicationPreferences:
        saved = self.repository.load_feature("communication", person_id, self.subject_id)
        return (
            CommunicationPreferences.model_validate(saved)
            if saved is not None
            else (
                CommunicationPreferences(
                    utc_offset_minutes=max(
                        -720, min(840, env_int("DIGITAL_CHILD_UTC_OFFSET_MINUTES", 0))
                    )
                )
            )
        )

    def update(self, person_id: str, patch: dict[str, object]) -> CommunicationPreferences:
        allowed = set(CommunicationPreferences.model_fields) - {"topic_snoozes"}
        if not set(patch) <= allowed:
            raise ValueError("Неизвестная настройка общения")
        preferences = CommunicationPreferences.model_validate(
            {
                **self.get(person_id).model_dump(),
                **patch,
            }
        )
        preferences.blocked_topics = [
            topic.strip()[:120] for topic in preferences.blocked_topics if topic.strip()
        ]
        self._save(person_id, preferences)
        return preferences

    def snooze_topic(self, person_id: str, topic: str, now: datetime) -> None:
        if not topic.strip():
            raise ValueError("Укажите тему, к которой не стоит возвращаться")
        preferences = self.get(person_id)
        snoozes = {key: until for key, until in preferences.topic_snoozes.items() if until > now}
        snoozes[topic.strip()[:120]] = now + timedelta(days=7)
        preferences.topic_snoozes = dict(list(snoozes.items())[-32:])
        self._save(person_id, preferences)

    def _save(self, person_id: str, preferences: CommunicationPreferences) -> None:
        self.repository.save_feature(
            "communication", person_id, self.subject_id, preferences.model_dump(mode="json")
        )
