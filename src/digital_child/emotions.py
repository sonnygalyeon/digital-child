from __future__ import annotations

from digital_child.models import (
    AutonomyDecisionKind,
    EmotionName,
    EmotionState,
    MessageAnalysis,
    MessageIntent,
    RelationshipProfile,
    ResearchReport,
    ResearchStatus,
)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, value))


class EmotionEngine:
    def update(
        self,
        current: EmotionState,
        analysis: MessageAnalysis,
        decision: AutonomyDecisionKind,
        relationship: RelationshipProfile,
        research: ResearchReport | None,
        energy: float,
    ) -> EmotionState:
        valence = current.valence * 0.75
        arousal = current.arousal * 0.70
        curiosity = current.curiosity * 0.85
        confusion = current.confusion * 0.70
        confidence = current.confidence * 0.85

        if analysis.intent == MessageIntent.QUESTION:
            curiosity += 0.16
            arousal += 0.08
        if analysis.intent == MessageIntent.CLAIM:
            curiosity += 0.10
        if analysis.contains_pressure:
            valence -= 0.18
            arousal += 0.20
        if decision == AutonomyDecisionKind.INVESTIGATE:
            curiosity += 0.22
            arousal += 0.10
        elif decision == AutonomyDecisionKind.REFUSE:
            valence -= 0.08
            confidence += 0.18
        elif decision == AutonomyDecisionKind.ACCEPT:
            valence += 0.08
        elif decision == AutonomyDecisionKind.ASK_CLARIFICATION:
            confusion += 0.22

        if research is not None:
            if research.status == ResearchStatus.COMPLETED:
                confidence += 0.15
                confusion -= 0.08
            elif research.status in {ResearchStatus.INCONCLUSIVE, ResearchStatus.FAILED}:
                confusion += 0.18

        fatigue = clamp(1.0 - energy)
        trust = relationship.epistemic_trust
        updated = EmotionState(
            valence=clamp_signed(valence),
            arousal=clamp(arousal),
            curiosity=clamp(curiosity),
            confidence=clamp(confidence),
            confusion=clamp(confusion),
            trust=clamp(trust),
            fatigue=fatigue,
            social_need=current.social_need,
            dominant=EmotionName.NEUTRAL,
        )
        return updated.model_copy(update={"dominant": self._dominant(updated, decision)})

    @staticmethod
    def idle_decay(current: EmotionState, amount: float = 0.02) -> EmotionState:
        updated = current.model_copy(
            update={
                "valence": current.valence * (1.0 - amount),
                "arousal": clamp(current.arousal * (1.0 - amount * 0.8)),
                "confusion": clamp(current.confusion * (1.0 - amount * 0.5)),
            }
        )
        return updated.model_copy(update={"dominant": EmotionEngine._dominant(updated, None)})

    @staticmethod
    def _dominant(
        state: EmotionState,
        decision: AutonomyDecisionKind | None,
    ) -> EmotionName:
        if decision == AutonomyDecisionKind.INVESTIGATE:
            return EmotionName.THINKING
        if state.confusion > 0.58:
            return EmotionName.CONFUSED
        if state.trust < 0.25 or state.valence < -0.35:
            return EmotionName.WARY
        if state.curiosity > 0.66:
            return EmotionName.CURIOUS
        if state.confidence > 0.68 and state.valence < 0.05:
            return EmotionName.SKEPTICAL
        if state.valence > 0.40:
            return EmotionName.HAPPY
        return EmotionName.NEUTRAL
