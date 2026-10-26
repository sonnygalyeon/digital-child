from __future__ import annotations

import math
from datetime import UTC, datetime

from digital_child.config import env_float
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
        now: datetime | None = None,
        episode_id: str | None = None,
    ) -> EmotionState:
        now = now or datetime.now(UTC)
        current = self.advance(current, now)
        valence, arousal = current.valence, current.arousal
        curiosity, confusion, confidence = current.curiosity, current.confusion, current.confidence

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
        updated = current.model_copy(
            update=dict(
                valence=clamp_signed(valence),
                arousal=clamp(arousal),
                curiosity=clamp(curiosity),
                confidence=clamp(confidence),
                confusion=clamp(confusion),
                trust=clamp(trust),
                fatigue=fatigue,
                social_need=current.social_need,
            )
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
                current.frustration
                + appraisal.reactance
                * 0.40
                * (0.65 + traits.emotional_sensitivity * 0.35)
                * (1 - regulation * 0.45)
            )
            updated.anxiety = clamp(
                current.anxiety
                + (
                    appraisal.uncertainty * (1 - development.uncertainty_tolerance)
                    + appraisal.hostility * 0.5
                    + appraisal.recalled_threat * 0.2
                )
                * 0.28
                * (1 - regulation * 0.35)
            )
            updated.sadness = clamp(
                current.sadness
                + appraisal.hostility * development.attachment * 0.20
                - appraisal.support * 0.08
            )
            updated.affection = clamp(
                current.affection + appraisal.support * relationship.affective_trust * 0.20
            )
            updated.pride = current.pride
            updated.boredom = clamp(current.boredom * 0.65 + appraisal.boredom * 0.35)
            updated.regulation = regulation
        if psychology is not None:
            updated.longing = psychology.mood.social_longing
            updated.boredom = max(updated.boredom, psychology.mood.absence_boredom)
        reason = f"message:{analysis.intent.value}; decision:{decision.value}"
        if analysis.contains_pressure:
            reason += "; pressure"
        return self._settle(current, updated, decision, now, reason, episode_id)

    @staticmethod
    def social_idle(
        current: EmotionState, psychology: PsychologyState, now: datetime | None = None
    ) -> EmotionState:
        now = now or datetime.now(UTC)
        current = EmotionEngine.advance(current, now)
        mood = psychology.mood
        updated = current.model_copy(
            update={
                "longing": mood.social_longing,
                "boredom": max(current.boredom, mood.absence_boredom),
                "social_need": max(current.social_need, mood.social_longing),
                "valence": clamp_signed(
                    current.valence + current.longing * 0.12 - mood.social_longing * 0.12
                ),
            }
        )
        return EmotionEngine._settle(current, updated, None, now, "social_absence")

    @staticmethod
    def idle_decay(
        current: EmotionState, amount: float = 0.02, now: datetime | None = None
    ) -> EmotionState:
        now = now or datetime.now(UTC)
        current = EmotionEngine.advance(current, now)
        amount = clamp(amount)
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
        return EmotionEngine._settle(current, updated, None, now, "resource_recovery")

    @staticmethod
    def advance(current: EmotionState, now: datetime) -> EmotionState:
        now = now.replace(tzinfo=UTC) if now.tzinfo is None else now
        previous = current.updated_at
        if previous is not None and previous.tzinfo is None:
            previous = previous.replace(tzinfo=UTC)
        elapsed = 0.0 if previous is None else max(0.0, (now - previous).total_seconds())
        effective_now = max(now, previous) if previous else now
        half_life = max(30.0, env_float("DIGITAL_CHILD_EMOTION_HALF_LIFE_SECONDS", 900.0))
        baselines = {
            "valence": 0.0,
            "arousal": 0.25,
            "curiosity": 0.5,
            "confidence": 0.35,
            "confusion": 0.15,
            "frustration": 0.0,
            "anxiety": 0.0,
            "sadness": 0.0,
            "affection": 0.0,
            "pride": 0.0,
            "boredom": 0.0,
        }
        values: dict[str, object] = {"updated_at": effective_now}
        for name, baseline in baselines.items():
            slower = 3.0 if name == "affection" else 2.0 if name in {"pride", "sadness"} else 1.0
            retention = math.exp(-math.log(2) * elapsed / (half_life * slower))
            values[name] = baseline + (getattr(current, name) - baseline) * retention
        updated = current.model_copy(update=values)
        return EmotionEngine._settle(current, updated, None, effective_now, "elapsed_time")

    @staticmethod
    def apply_outcome(
        current: EmotionState,
        outcome_id: str,
        progress: float,
        confidence: float,
        now: datetime,
        episode_id: str | None = None,
    ) -> EmotionState:
        current = EmotionEngine.advance(current, now)
        if current.last_achievement_id == outcome_id:
            return current
        effect = max(-1.0, min(1.0, progress)) * clamp(confidence)
        updated = current.model_copy(
            update={
                "pride": clamp(current.pride + max(0.0, effect) * 0.04),
                "confidence": clamp(current.confidence + effect * 0.03),
                "frustration": clamp(current.frustration + max(0.0, -effect) * 0.04),
                "valence": clamp_signed(current.valence + effect * 0.035),
                "last_achievement_id": outcome_id,
            }
        )
        return EmotionEngine._settle(
            current, updated, None, now, "observed_outcome:" + outcome_id, episode_id
        )

    @staticmethod
    def _strength(state: EmotionState, name: EmotionName) -> float:
        def strength(value: float, threshold: float) -> float:
            return max(0.0, 1 + (value - threshold) / (1 - threshold))

        strengths = {
            EmotionName.FRUSTRATED: strength(state.frustration, 0.45),
            EmotionName.ANXIOUS: strength(state.anxiety, 0.40),
            EmotionName.SAD: strength(state.sadness, 0.38),
            EmotionName.CONFUSED: strength(state.confusion, 0.58),
            EmotionName.WARY: max(strength(1 - state.trust, 0.75), strength(-state.valence, 0.35)),
            EmotionName.MISSING_CONTACT: strength(state.longing, 0.12),
            EmotionName.BORED: strength(state.boredom, 0.42),
            EmotionName.CURIOUS: strength(state.curiosity, 0.66),
            EmotionName.SKEPTICAL: strength(state.confidence, 0.68)
            if state.valence < 0.05
            else 0.0,
            EmotionName.HAPPY: strength(state.valence, 0.40),
            EmotionName.AFFECTIONATE: strength(state.affection, 0.42),
            EmotionName.PROUD: strength(state.pride, 0.38),
        }
        return strengths.get(name, 0.0)

    @staticmethod
    def _settle(
        current: EmotionState,
        updated: EmotionState,
        decision: AutonomyDecisionKind | None,
        now: datetime,
        reason: str,
        episode_id: str | None = None,
    ) -> EmotionState:
        candidate = EmotionEngine._dominant(updated, decision)
        if candidate == current.dominant:
            return updated.model_copy(
                update={
                    "pending_dominant": None,
                    "pending_since": None,
                    "pending_episode_id": None,
                    "pending_reason": "",
                }
            )
        strength = EmotionEngine._strength(updated, candidate)
        old_strength = EmotionEngine._strength(updated, current.dominant)
        margin = max(0.0, env_float("DIGITAL_CHILD_EMOTION_SWITCH_MARGIN", 0.15))
        forced = candidate == EmotionName.THINKING or current.dominant == EmotionName.THINKING
        if not forced and old_strength >= 0.8 and strength < old_strength + margin:
            return updated.model_copy(
                update={
                    "pending_dominant": None,
                    "pending_since": None,
                    "pending_episode_id": None,
                    "pending_reason": "",
                }
            )
        pending_since = current.pending_since if current.pending_dominant == candidate else now
        pending_since = pending_since or now
        pending_reason = current.pending_reason if current.pending_dominant == candidate else reason
        pending_episode = (
            current.pending_episode_id if current.pending_dominant == candidate else episode_id
        )
        since = current.dominant_since or now
        hold = max(0.0, env_float("DIGITAL_CHILD_EMOTION_MIN_HOLD_SECONDS", 8.0))
        settle = max(0.0, env_float("DIGITAL_CHILD_EMOTION_SETTLE_SECONDS", 3.0))
        ready = (now - pending_since).total_seconds() >= settle and (
            now - since
        ).total_seconds() >= hold
        if forced or strength >= 1.85 or ready:
            return updated.model_copy(
                update={
                    "dominant": candidate,
                    "dominant_since": now,
                    "dominant_reason": pending_reason,
                    "dominant_episode_id": pending_episode,
                    "pending_dominant": None,
                    "pending_since": None,
                    "pending_reason": "",
                    "pending_episode_id": None,
                }
            )
        return updated.model_copy(
            update={
                "dominant_since": since,
                "pending_dominant": candidate,
                "pending_since": pending_since,
                "pending_reason": pending_reason,
                "pending_episode_id": pending_episode,
            }
        )

    @staticmethod
    def _dominant(
        state: EmotionState,
        decision: AutonomyDecisionKind | None,
    ) -> EmotionName:
        if decision == AutonomyDecisionKind.INVESTIGATE:
            return EmotionName.THINKING
        candidates = [name for name in EmotionName if EmotionEngine._strength(state, name) >= 1.0]
        return (
            max(candidates, key=lambda name: EmotionEngine._strength(state, name))
            if candidates
            else EmotionName.NEUTRAL
        )
