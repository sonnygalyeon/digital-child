from __future__ import annotations

import math

from pydantic import Field

from digital_child.domain.models import StrictModel
from digital_child.infrastructure.repository import SQLiteRepository


class SkillEstimate(StrictModel):
    skill: str
    samples: int = Field(default=0, ge=0)
    successes: float = Field(default=0, ge=0)
    squared_error: float = Field(default=0, ge=0)
    recent: list[float] = Field(default_factory=list, max_length=12)

    @property
    def confidence(self) -> float:
        if not self.samples:
            return 0.5
        # A small prior and recent outcomes prevent early certainty and allow drift.
        posterior = (1 + self.successes) / (2 + self.samples)
        recent = (1 + sum(self.recent)) / (2 + len(self.recent))
        return min(0.95, max(0.05, 0.4 * posterior + 0.6 * recent))

    @property
    def uncertainty(self) -> float:
        return 1 / math.sqrt(1 + self.samples)

    @property
    def calibration_error(self) -> float | None:
        return self.squared_error / self.samples if self.samples else None

    def diagnostic(self) -> dict[str, object]:
        return {
            **self.model_dump(),
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "brier_score": self.calibration_error,
        }


class CompetenceModel:
    def __init__(self, repository: SQLiteRepository, subject_id: str) -> None:
        self.repository, self.subject_id = repository, subject_id

    def get(self, skill: str) -> SkillEstimate:
        saved = self.repository.load_feature("competence", skill, self.subject_id)
        return SkillEstimate.model_validate(saved) if saved else SkillEstimate(skill=skill)

    def record(self, skill: str, outcome_id: str, success: float, predicted: float) -> None:
        key = skill + ":" + outcome_id
        with self.repository.transaction():
            if self.repository.load_feature("competence_outcome", key, self.subject_id):
                return
            estimate = self.get(skill)
            success, predicted = max(0.0, min(1.0, success)), max(0.0, min(1.0, predicted))
            estimate.samples += 1
            estimate.successes += success
            estimate.squared_error += (predicted - success) ** 2
            estimate.recent = (estimate.recent + [success])[-12:]
            self.repository.save_feature(
                "competence", skill, self.subject_id, estimate.model_dump(mode="json")
            )
            self.repository.save_feature(
                "competence_outcome",
                key,
                self.subject_id,
                {"success": success, "prediction": predicted},
            )

    def diagnostics(self) -> list[dict[str, object]]:
        return [
            SkillEstimate.model_validate(item).diagnostic()
            for item in self.repository.list_features("competence", self.subject_id, 100)
        ]

    def guidance(self, skills: list[str]) -> str:
        lines = []
        for skill in skills[:3]:
            estimate = self.get(skill)
            if not estimate.samples:
                lines.append(f"{skill}: наблюдаемых попыток нет; не заявляй освоенный навык.")
            else:
                lines.append(
                    f"{skill}: {estimate.samples} попыток, оценка успеха "
                    f"{estimate.confidence:.2f}, неопределённость {estimate.uncertainty:.2f}. "
                    + (
                        "Предложи небольшой проверяемый шаг или уточнение условий."
                        if estimate.confidence < 0.65 or estimate.samples < 4
                        else "Навык имеет наблюдаемые подтверждения в указанной среде."
                    )
                )
        return " ".join(lines) + " Эти оценки не являются вероятностью истинности любого ответа."
