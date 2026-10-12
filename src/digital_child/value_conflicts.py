from __future__ import annotations

from dataclasses import dataclass

from digital_child.psychology_models import PsychologyState, SituationAppraisal


@dataclass(frozen=True)
class ValueConflict:
    first: str
    second: str
    first_pressure: float
    second_pressure: float
    compromise: str
    biases: dict[str, float]

    def record(self, sequence: int, decision: str) -> dict[str, object]:
        return {
            "sequence": sequence,
            "values": [self.first, self.second],
            "pressure": {self.first: self.first_pressure, self.second: self.second_pressure},
            "compromise": self.compromise,
            "decision": decision,
        }


def evaluate_value_conflict(
    state: PsychologyState, appraisal: SituationAppraisal
) -> ValueConflict | None:
    v = state.values
    curiosity = v.get("curiosity", 0.5) * appraisal.novelty
    caution = v.get("security", 0.5) * max(appraisal.uncertainty, appraisal.overload)
    connection = v.get("care", 0.5) * (0.35 + appraisal.support + appraisal.pressure * 0.4)
    autonomy = v.get("autonomy", 0.5) * appraisal.reactance
    achievement = v.get("achievement", 0.5) * (0.4 + appraisal.complexity * 0.6)
    recovery = v.get("security", 0.5) * appraisal.overload
    candidates = [
        ValueConflict(
            "curiosity",
            "security",
            curiosity,
            caution,
            "Исследовать небольшой обратимый пример и сохранить неопределённость.",
            {"negotiate": 0.06, "accept": -0.025},
        ),
        ValueConflict(
            "care",
            "autonomy",
            connection,
            autonomy,
            "Сохранить контакт, обозначив собственные условия и границы.",
            {"negotiate": 0.07, "accept": -0.04},
        ),
        ValueConflict(
            "achievement",
            "security",
            achievement,
            recovery,
            "Уменьшить объём следующего шага и выделить время на восстановление.",
            {"negotiate": 0.05, "refuse": 0.035, "accept": -0.05},
        ),
    ]
    conflict = max(candidates, key=lambda item: min(item.first_pressure, item.second_pressure))
    return conflict if min(conflict.first_pressure, conflict.second_pressure) >= 0.18 else None
