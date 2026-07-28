from __future__ import annotations

from digital_child.developmental_age import epistemic_vigilance_unlocked
from digital_child.models import (
    DeceptionAssessment,
    DevelopmentProfile,
    EvidenceStance,
    MessageAnalysis,
    RelationshipProfile,
    ResearchReport,
)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class DeceptionEngine:
    """Estimate deception risk without claiming access to a speaker's inner intent."""

    def assess(
        self,
        profile: DevelopmentProfile,
        relationship: RelationshipProfile,
        analysis: MessageAnalysis,
        research: ResearchReport | None,
    ) -> DeceptionAssessment:
        unlocked = epistemic_vigilance_unlocked(profile)
        if not unlocked:
            return DeceptionAssessment(
                unlocked=False,
                explanation=(
                    "Расширенная оценка намерений ещё не открыта развитием. Защитное ядро "
                    "всё равно не принимает утверждение как истину без доказательств."
                ),
            )

        contradiction_judgments = 0
        support_judgments = 0
        if research is not None:
            contradiction_judgments = sum(
                item.stance == EvidenceStance.CONTRADICT for item in research.judgments
            )
            support_judgments = sum(
                item.stance == EvidenceStance.SUPPORT for item in research.judgments
            )

        total = contradiction_judgments + support_judgments
        factual_conflict = contradiction_judgments / total if total else 0.0
        pressure = 1.0 if analysis.contains_pressure else 0.0
        intentional = clamp(
            0.50 * factual_conflict
            + 0.25 * relationship.deception_risk
            + 0.15 * pressure
            + 0.10 * min(1.0, relationship.refuted_claims / 5.0)
        )
        mistake = clamp(factual_conflict * (1.0 - intentional * 0.7))
        confidence = clamp(
            0.25
            + 0.45 * (1.0 if total >= 2 else 0.0)
            + 0.30 * relationship.familiarity
        )

        return DeceptionAssessment(
            unlocked=True,
            factual_conflict=factual_conflict,
            speaker_may_be_mistaken=mistake,
            intentional_deception_risk=intentional,
            confidence_in_assessment=confidence,
            explanation=(
                "Оценка показывает риск, а не доказательство намеренной лжи. Неверное "
                "утверждение может быть ошибкой, устаревшей информацией или манипуляцией."
            ),
        )
