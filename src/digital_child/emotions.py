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
from digital_child.psychology_models import (
    DevelopmentalDynamics,
    PsychologyState,
    SituationAppraisal,
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
        appraisal: SituationAppraisal | None = None,
        development: DevelopmentalDynamics | None = None,
        psychology: PsychologyState | None = None,
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
        if appraisal is not None and development is not None and psychology is not None:
            traits, mood = psychology.character, psychology.mood
            regulation = clamp(
                development.regulation * (0.65 + traits.flexibility * 0.35) * (0.75 + energy * 0.25)
            )
            inertia = 0.35 + regulation * 0.4
            updated.valence = clamp_signed(
                current.valence * inertia
                + updated.valence * (1 - inertia)
                + appraisal.support * 0.13
                - appraisal.hostility * 0.25
                + mood.valence * 0.12
                + appraisal.memory_resonance * 0.07
            )
            updated.arousal = clamp(
                updated.arousal
                + appraisal.reactance * 0.18
                + appraisal.hostility * 0.18
                - regulation * 0.025
            )
            updated.curiosity = clamp(
                updated.curiosity
                + traits.openness * appraisal.novelty * 0.12
                - appraisal.overload * 0.1
            )
            updated.trust = clamp(
                relationship.epistemic_trust * 0.50
                + relationship.affective_trust * 0.30
                + mood.social_safety * 0.20
            )
            updated.confusion = clamp(
                updated.confusion + appraisal.complexity * (1 - development.reflection) * 0.12
            )
            updated.frustration = clamp(
                current.frustration * 0.68
                + appraisal.reactance
                * 0.40
                * (0.65 + traits.emotional_sensitivity * 0.35)
                * (1 - regulation * 0.45)
            )
            updated.anxiety = clamp(
                current.anxiety * 0.78
                + (
                    appraisal.uncertainty * (1 - development.uncertainty_tolerance)
                    + appraisal.hostility * 0.5
                    + appraisal.recalled_threat * 0.2
                )
                * 0.28
                * (1 - regulation * 0.35)
            )
            updated.sadness = clamp(
                current.sadness * 0.85
                + appraisal.hostility * development.attachment * 0.20
                - appraisal.support * 0.08
            )
            updated.affection = clamp(
                current.affection * 0.86 + appraisal.support * relationship.affective_trust * 0.20
            )
            updated.pride = clamp(
                current.pride * 0.92 + max(0.0, psychology.self_model.efficacy - 0.3) * 0.05
            )
            updated.boredom = clamp(current.boredom * 0.65 + appraisal.boredom * 0.35)
            updated.regulation = regulation
        return updated.model_copy(update={"dominant": self._dominant(updated, decision)})

    @staticmethod
    def idle_decay(current: EmotionState, amount: float = 0.02) -> EmotionState:
        updated = current.model_copy(
            update={
                "valence": current.valence * (1.0 - amount),
                "arousal": clamp(current.arousal * (1.0 - amount * 0.8)),
                "confusion": clamp(current.confusion * (1.0 - amount * 0.5)),
                "frustration": clamp(current.frustration * (1.0 - amount)),
                "anxiety": clamp(current.anxiety * (1.0 - amount * 0.6)),
                "sadness": clamp(current.sadness * (1.0 - amount * 0.3)),
                "affection": clamp(current.affection * (1.0 - amount * 0.2)),
                "pride": clamp(current.pride * (1.0 - amount * 0.3)),
                "boredom": clamp(current.boredom * (1.0 - amount * 0.5)),
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
        if state.frustration > 0.45:
            return EmotionName.FRUSTRATED
        if state.anxiety > 0.40:
            return EmotionName.ANXIOUS
        if state.sadness > 0.38:
            return EmotionName.SAD
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
        if state.affection > 0.42:
            return EmotionName.AFFECTIONATE
        if state.pride > 0.38:
            return EmotionName.PROUD
        if state.boredom > 0.42:
            return EmotionName.BORED
        return EmotionName.NEUTRAL
