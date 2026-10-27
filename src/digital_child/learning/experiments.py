from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from digital_child.domain.models import StrictModel
from digital_child.infrastructure.repository import SQLiteRepository
from digital_child.learning.competence import CompetenceModel

ExperimentKind = Literal["balance", "transfer", "noise", "conditional", "reversal"]
EXPERIMENT_KINDS: tuple[ExperimentKind, ...] = (
    "balance",
    "transfer",
    "noise",
    "conditional",
    "reversal",
)


class Demonstration(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    person_id: str = "local-user"
    kind: ExperimentKind = "balance"
    context: Literal["default", "blue", "amber"] = "default"
    before: int = Field(ge=-1000, le=1000)
    action: Literal["left", "right"]
    after: int = Field(ge=-1000, le=1000)
    explanation: str = Field(default="", max_length=1000)
    inferred_sign: int = 1
    status: str = "unverified_hypothesis"
    checked_trials: list[str] = Field(default_factory=list, max_length=20)
    matched_contexts: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def derive_rule(self) -> Demonstration:
        scale = 2 if self.kind == "transfer" else 1
        delta = (self.after - self.before) * (1 if self.action == "right" else -1)
        if abs(delta) != scale:
            raise ValueError("Пример должен показывать один шаг среды (transfer: 2, остальные: 1)")
        if (self.kind == "conditional") != (self.context != "default"):
            raise ValueError("Для conditional нужен контекст blue или amber; иначе default")
        self.inferred_sign = delta // scale
        return self


class ExperimentChoice(StrictModel):
    kind: ExperimentKind
    expected_information_gain: float
    reason: str


class ExperimentTrial(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: ExperimentKind
    before: int
    action: Literal["left", "right"]
    predicted_after: float
    actual_after: int
    prediction_error: float = Field(ge=0)
    success: bool
    reward: float = Field(ge=-1, le=1)
    model_sign_before: int
    learned_sign_after: int
    episode_id: str | None = None
    autonomous: bool = False
    explanation: str
    context: str = "default"
    noise: int = 0
    predicted_success: float = 0.5
    demonstration_id: str | None = None
    selection_reason: str = "Ручной выбор среды"
    expected_information_gain: float = 0.0


class ExperimentEnvironment:
    """Closed causal world; no shell, files, messages or external tool calls."""

    def __init__(self, repository: SQLiteRepository, subject_id: str) -> None:
        self.repository, self.subject_id = repository, subject_id

    def history(self, limit: int = 20) -> list[ExperimentTrial]:
        return [
            ExperimentTrial.model_validate(item)
            for item in self.repository.list_features("experiment", self.subject_id, limit)
        ]

    def prepare(self, kind: ExperimentKind, now: datetime, autonomous: bool) -> ExperimentTrial:
        history = self.history(500)
        related = [item for item in history if item.kind == kind]
        seed = hashlib.blake2b(self.subject_id.encode(), digest_size=2).digest()
        actual_sign = 1 if seed[0] % 2 else -1
        scale = 1 if kind == "balance" else 2
        if kind not in {"balance", "transfer"}:
            scale = 1
        context = "default"
        if kind == "conditional":
            context = "blue" if len(related) % 2 == 0 else "amber"
            actual_sign *= 1 if context == "blue" else -1
        if kind == "reversal":
            actual_sign *= 1 if (len(related) // 4) % 2 == 0 else -1
        family = {"balance", "transfer"} if kind in {"balance", "transfer"} else {kind}
        evidence = [
            item
            for item in history
            if item.kind in family
            and item.context == context
            and item.learned_sign_after in {-1, 1}
        ]
        known_sign = evidence[0].learned_sign_after if evidence else 1
        demo = next(
            (
                item
                for item in self.demonstrations()
                if item.kind in family
                and item.context == context
                and item.status not in {"contradicted", "transferred"}
            ),
            None,
        )
        if demo is not None:
            known_sign = demo.inferred_sign
        # Transfer changes the distance/step scale while preserving causal direction.
        before = (1 if (len(related) + seed[1]) % 2 else -1) * scale * (2 + len(related) % 3)
        wanted_delta = -1 if before > 0 else 1
        action: Literal["left", "right"] = "right" if wanted_delta * known_sign > 0 else "left"
        action_sign = 1 if action == "right" else -1
        prediction = before + action_sign * known_sign * scale
        noise = ((len(related) + seed[1]) % 3 - 1) if kind == "noise" else 0
        actual = before + action_sign * actual_sign * scale + noise
        success = abs(actual) < abs(before)
        return ExperimentTrial(
            kind=kind,
            created_at=now,
            before=before,
            action=action,
            predicted_after=float(prediction),
            actual_after=actual,
            prediction_error=abs(prediction - actual) / (2 * scale),
            success=success,
            reward=0.7 if success else -0.35,
            model_sign_before=known_sign,
            learned_sign_after=(
                1
                if (actual - before) * action_sign > 0
                else -1
                if (actual - before) * action_sign < 0
                else known_sign
            ),
            autonomous=autonomous,
            explanation="Сравнен прогноз с наблюдением закрытой среды; "
            "модель использует только прежние наблюдения и помеченные гипотезы.",
            context=context,
            noise=noise,
            demonstration_id=None if demo is None else demo.id,
        )

    def save(self, trial: ExperimentTrial) -> None:
        self.repository.save_feature(
            "experiment", trial.id, self.subject_id, trial.model_dump(mode="json")
        )
        if trial.demonstration_id:
            row = self.repository.load_feature(
                "demonstration", trial.demonstration_id, self.subject_id
            )
            if row is not None:
                demo = Demonstration.model_validate(row)
                demo.checked_trials = (demo.checked_trials + [trial.id])[-20:]
                if trial.prediction_error > 0:
                    demo.status = "inconclusive_noise" if trial.kind == "noise" else "contradicted"
                else:
                    key = trial.kind + ":" + trial.context + ":" + str(abs(trial.before))
                    demo.matched_contexts = list(dict.fromkeys(demo.matched_contexts + [key]))[-10:]
                    demo.status = (
                        "transferred" if len(demo.matched_contexts) >= 2 else "matched_once"
                    )
                self.repository.save_feature(
                    "demonstration", demo.id, self.subject_id, demo.model_dump(mode="json")
                )

    def demonstrate(self, example: Demonstration) -> Demonstration:
        # Human observations propose a rule; they do not grant DEU or skill mastery.
        example = example.model_copy(
            update={
                "id": str(uuid4()),
                "status": "unverified_hypothesis",
                "checked_trials": [],
                "matched_contexts": [],
            }
        )
        self.repository.save_feature(
            "demonstration", example.id, self.subject_id, example.model_dump(mode="json")
        )
        return example

    def demonstrations(self) -> list[Demonstration]:
        return [
            Demonstration.model_validate(item)
            for item in self.repository.list_features("demonstration", self.subject_id, 100)
        ]

    def curriculum(self, competence: CompetenceModel | None = None) -> list[ExperimentChoice]:
        history = self.history(500)
        choices = []
        for kind in EXPERIMENT_KINDS:
            trials = [item for item in history if item.kind == kind]
            prerequisites: tuple[ExperimentKind, ...] = ()
            if kind == "transfer":
                prerequisites = ("balance",)
            elif kind in {"noise", "conditional", "reversal"}:
                prerequisites = ("balance", "transfer")
            if any(
                sum(item.kind == need and item.prediction_error == 0 for item in history) < 2
                for need in prerequisites
            ):
                continue
            target = {"balance": 2, "transfer": 2, "noise": 6, "conditional": 6, "reversal": 10}[
                kind
            ]
            if len(trials) >= max(20, target) or (
                len(trials) >= target
                and (kind == "noise" or all(item.prediction_error == 0 for item in trials[:2]))
            ):
                continue
            uncertainty = 1 / (1 + len(trials)) ** 0.5
            estimate = None if competence is None else competence.get("experiment:" + kind)
            if estimate is not None:
                uncertainty = estimate.uncertainty
            recent_error = sum(item.prediction_error for item in trials[:3]) / max(
                1, len(trials[:3])
            )
            gain = min(1.0, 0.65 * uncertainty + 0.35 * min(1.0, recent_error))
            if estimate is not None and estimate.calibration_error is not None:
                gain = min(1.0, gain + 0.15 * estimate.calibration_error)
            if kind == "conditional" and len({item.context for item in trials}) < 2:
                gain = min(1.0, gain + 0.15)
            choices.append(
                ExperimentChoice(
                    kind=kind,
                    expected_information_gain=gain,
                    reason=f"{kind}: наблюдений {len(trials)}, неопределённость {uncertainty:.2f}, "
                    f"недавняя ошибка {recent_error:.2f}; проверить оставшийся пробел.",
                )
            )
        return sorted(choices, key=lambda item: item.expected_information_gain, reverse=True)
