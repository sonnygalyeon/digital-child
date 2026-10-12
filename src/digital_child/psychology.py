from __future__ import annotations

import hashlib
import math
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from digital_child.appraisal import appraise_situation, clamp, overlap, situation_cue, topic_tokens
from digital_child.behavior import choose_behavior
from digital_child.behavioral_development import developmental_dynamics
from digital_child.experiments import ExperimentTrial
from digital_child.initiative import InitiativePlan, elapsed_seconds, utc
from digital_child.interest_catalog import (
    THEMES,
    developmental_interest_weights,
    preferred_interests,
)
from digital_child.models import (
    AutonomyDecision,
    ConversationMessage,
    DeferredVerification,
    DevelopmentProfile,
    Episode,
    IdentityProfile,
    MessageAnalysis,
    Observation,
    RelationshipProfile,
    ResearchReport,
    ResearchStatus,
    ResourceBudget,
)
from digital_child.psychology_models import (
    AffectiveMemory,
    BehavioralCommitment,
    BehaviorTrace,
    CharacterTraits,
    DevelopmentalDynamics,
    GoalBehaviorPolicy,
    LearnedHabit,
    PersonalInterest,
    PsychologyState,
    SituationAppraisal,
    SocialExperience,
)
from digital_child.storage import SQLiteRepository


@dataclass(frozen=True)
class BehaviorEvaluation:
    decision: AutonomyDecision
    trace: BehaviorTrace
    development: DevelopmentalDynamics
    psychology: PsychologyState
    affective_trust_delta: float


class PsychologyEngine:
    """Persistent developmental simulation: every lasting change has an experience source."""

    def __init__(
        self,
        repository: SQLiteRepository,
        identity: IdentityProfile,
        profile: DevelopmentProfile,
    ) -> None:
        self.repository = repository
        self._lock = threading.RLock()
        saved = repository.load_psychology()
        if saved is not None and saved.subject_id != identity.id:
            raise ValueError(
                "Psychology belongs to another identity; explicit operator reset is required"
            )
        if saved is None:
            seed = hashlib.blake2b(identity.id.encode(), digest_size=16).hexdigest()
            traits = CharacterTraits(
                **{
                    name: 0.28 + 0.44 * self._seed_value(seed, name)
                    for name in CharacterTraits.model_fields
                }
            )
            self.state = PsychologyState(
                subject_id=identity.id,
                seed=seed,
                temperament=traits,
                character=traits.model_copy(deep=True),
                developmental_stage=profile.stage,
                values={
                    name: 0.40 + 0.30 * self._seed_value(seed, f"value:{name}")
                    for name in (
                        "curiosity",
                        "truth",
                        "autonomy",
                        "care",
                        "fairness",
                        "achievement",
                        "security",
                        "creativity",
                    )
                },
            )
            self.state.reflections.append(
                "Начальные особенности субъекта зафиксированы; "
                "дальнейшие изменения связываются с опытом."
            )
            self._save()
        else:
            self.state = saved
        self._refresh_developmental_interests(profile)
        self.sync_contacts(repository.latest_user_messages())
        self.update_absence(profile, datetime.now(UTC))
        self._save()

    def _refresh_developmental_interests(self, profile: DevelopmentProfile) -> None:
        weights = developmental_interest_weights(profile)
        for theme in THEMES:
            interest = self.state.interests.get(theme.title)
            if interest is None:
                interest = PersonalInterest(
                    topic=theme.title,
                    origin="developmental",
                    introduced_stage=profile.stage,
                    attraction=0.35
                    + 0.3 * self._seed_value(self.state.seed, f"interest:{theme.title}"),
                    last_sequence=self.repository.current_sequence(),
                )
                self.state.interests[theme.title] = interest
            interest.developmental_weight = weights[theme.title]

    def sync_contacts(
        self, messages: list[ConversationMessage], defaults: dict[str, bool] | None = None
    ) -> None:
        with self._lock:
            changed = False
            for message in messages:
                social = self.state.relationships.get(message.person_id)
                if social is None:
                    relationship = self.repository.load_relationship(message.person_id)
                    social = SocialExperience(
                        person_id=message.person_id,
                        initiative_allowed=True
                        if defaults is None
                        else defaults.get(message.person_id, True),
                        warmth=0.35 if relationship is None else relationship.affective_trust,
                    )
                    self.state.relationships[message.person_id] = social
                if social.last_contact_message_id == message.id:
                    continue
                social.last_contact_at = utc(message.created_at)
                social.last_contact_message_id = message.id
                social.unanswered_initiatives = 0
                social.longing = 0.0
                social.quiet_until = None
                text = message.content.strip().lower()
                if re.match(
                    r"^(пожалуйста[, ]+)?не (пиши (мне )?(первым|сама?)(?:\b)|"
                    r"начинай разговор|напоминай о себе)",
                    text,
                ):
                    social.initiative_allowed = False
                elif re.match(
                    r"^(можешь писать|пиши мне первым|можешь начинать разговор|пиши сам)", text
                ):
                    social.initiative_allowed = True
                elif re.match(r"^(я занят|я занята|давай позже|поговорим позже)", text):
                    social.quiet_until = utc(message.created_at) + timedelta(hours=4)
                elif re.match(r"^(пока[.! ]*$|до свидания|спокойной ночи)", text):
                    social.quiet_until = utc(message.created_at) + timedelta(hours=12)
                changed = True
            if changed:
                self._save()

    def update_absence(self, profile: DevelopmentProfile, now: datetime) -> bool:
        """Clock-based feeling, without developmental experience or character reinforcement."""
        with self._lock:
            previous = self.state.mood.model_copy()
            development = developmental_dynamics(profile)
            boredom = 0.0
            for social in self.state.relationships.values():
                if social.last_contact_at is None:
                    continue
                overdue_hours = max(0.0, elapsed_seconds(now, social.last_contact_at) / 3600 - 24)
                intensity = 1 - math.exp(-overdue_hours / 24)
                social.longing = clamp(
                    intensity
                    * (
                        0.25
                        + development.attachment * self.state.character.attachment_need * 0.45
                        + social.warmth * 0.25
                    )
                )
                boredom = max(
                    boredom, intensity * (0.4 + self.state.character.novelty_seeking * 0.3)
                )
            mood = self.state.mood
            mood.social_longing = max(
                (s.longing for s in self.state.relationships.values()), default=0.0
            )
            mood.absence_boredom = boredom
            penalty = mood.social_longing * 0.12
            mood.valence = max(
                -1.0, min(1.0, mood.valence + mood.absence_valence_penalty - penalty)
            )
            mood.absence_valence_penalty = penalty
            changed = any(
                round(getattr(previous, name), 3) != round(getattr(mood, name), 3)
                for name in ("social_longing", "absence_boredom", "valence")
            )
            if changed:
                self._save()
            return changed

    def record_initiative_attempt(self, person_id: str, now: datetime) -> None:
        with self._lock:
            self.state.relationships[person_id].last_initiative_attempt_at = now
            self._save()

    def record_initiative(
        self, plan: InitiativePlan, now: datetime, *, persist: bool = True
    ) -> None:
        with self._lock:
            social = self.state.relationships[plan.person_id]
            social.last_initiative_at = now
            social.unanswered_initiatives += 1
            social.recent_initiative_topics = [
                topic for topic in social.recent_initiative_topics if topic != plan.topic
            ]
            social.recent_initiative_topics = (social.recent_initiative_topics + [plan.topic])[-8:]
            if plan.kind == "discussion":
                social.last_discussion_message_id = plan.source.id
            if persist:
                self._save()

    def commit_initiative(
        self,
        plan: InitiativePlan,
        message: ConversationMessage,
        budget: ResourceBudget,
        verification: DeferredVerification | None = None,
    ) -> None:
        with self._lock:
            previous = self.state.model_copy(deep=True)
            try:
                self.record_initiative(plan, message.created_at, persist=False)
                self.repository.save_initiative(message, self.state, budget, verification)
            except Exception:
                self.state = previous
                raise

    def skip_discussion(self, person_id: str, message_id: str) -> None:
        with self._lock:
            self.state.relationships[person_id].last_discussion_message_id = message_id
            self._save()

    def set_initiative_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.state.initiative_enabled = enabled
            self._save()

    def set_contact_initiative(self, person_id: str, enabled: bool) -> None:
        with self._lock:
            social = self.state.relationships.get(person_id)
            if social is not None:
                social.initiative_allowed = enabled
                self._save()

    @staticmethod
    def _seed_value(seed: str, name: str) -> float:
        digest = hashlib.blake2b(f"{seed}:{name}".encode(), digest_size=8).digest()
        return int.from_bytes(digest, "big") / (2**64 - 1)

    def snapshot(self) -> PsychologyState:
        with self._lock:
            return self.state.model_copy(deep=True)

    def evaluate(
        self,
        *,
        analysis: MessageAnalysis,
        profile: DevelopmentProfile,
        relationship: RelationshipProfile,
        base_decision: AutonomyDecision,
        novelty: float,
        energy: float,
        episode: Episode,
        associated_episode_ids: list[str] | None = None,
    ) -> BehaviorEvaluation:
        with self._lock:
            development = developmental_dynamics(profile)
            self._note_stage(profile)
            social = self.state.relationships.get(relationship.person_id)
            if social is None:
                social = SocialExperience(
                    person_id=relationship.person_id,
                    warmth=relationship.affective_trust,
                    felt_safety=0.3 + relationship.familiarity * 0.3,
                )
            tokens = topic_tokens(analysis.text)
            resonance, recalled_threat, recalled_ids = self._recall(
                tokens, relationship.person_id, associated_episode_ids
            )
            appraisal = appraise_situation(
                analysis,
                novelty=novelty,
                energy=energy,
                traits=self.state.character,
                development=development,
                mood=self.state.mood,
                social=social,
                resonance=resonance,
                recalled_threat=recalled_threat,
            )
            prior = next(
                (
                    item.decision
                    for item in reversed(self.state.commitments)
                    if item.person_id == relationship.person_id
                    and episode.sequence - item.sequence <= 24
                    and overlap(tokens, item.tokens) >= 0.35
                ),
                None,
            )
            decision, trace = choose_behavior(
                base_decision,
                appraisal,
                development,
                self.state,
                social,
                sequence=episode.sequence,
                prior_decision=prior,
            )
            trace.recalled_episode_ids = recalled_ids
            if trace.value_conflict:
                self.state.value_conflicts = (self.state.value_conflicts + [trace.value_conflict])[
                    -24:
                ]
            before_warmth = social.warmth
            self._update_relationship(social, appraisal, development, episode.sequence)
            self.state.relationships[relationship.person_id] = social
            self._update_mood(appraisal, development)
            self._update_self_model(appraisal, development, decision)
            self._update_interests(tokens, appraisal, episode.sequence)
            trace.trait_changes = self._adapt_character(appraisal, development)
            self._adapt_values(appraisal, development)
            self._remember(episode, tokens, relationship.person_id, appraisal)
            self.state.commitments.append(
                BehavioralCommitment(
                    person_id=relationship.person_id,
                    tokens=tokens,
                    decision=decision.decision,
                    confidence=decision.confidence,
                    sequence=episode.sequence,
                )
            )
            self._practice_habit(trace, episode.sequence)
            self.state.interactions += 1
            self.state.last_behavior = trace
            self._save()
            self.repository.save_audit("behavior_appraisal", trace.model_dump(mode="json"))
            return BehaviorEvaluation(
                decision=decision,
                trace=trace,
                development=development,
                psychology=self.state.model_copy(deep=True),
                affective_trust_delta=max(-0.03, min(0.015, social.warmth - before_warmth)),
            )

    def _recall(
        self, tokens: list[str], person_id: str, associated_episode_ids: list[str] | None = None
    ) -> tuple[float, float, list[str]]:
        selected = []
        current_sequence = self.repository.current_sequence()
        for memory in self.state.affective_memories:
            similarity = overlap(tokens, memory.tokens)
            if memory.episode_id in (associated_episode_ids or []):
                similarity = max(similarity, 0.45)
            same_person = memory.person_id == person_id
            if similarity < 0.10 and not same_person:
                continue
            freshness = 1 / (1 + max(0, current_sequence - memory.sequence) * 0.015)
            # Person-specific experiences generalize weakly to another person.
            relevance = similarity * (1.0 if same_person else 0.35)
            relevance += 0.12 * float(same_person)
            weight = relevance * memory.salience * memory.confidence * (0.4 + 0.6 * freshness)
            if weight > 0.015:
                selected.append((weight, memory))
        selected.sort(key=lambda item: item[0], reverse=True)
        selected = selected[:8]
        total = sum(weight for weight, _ in selected)
        if total == 0:
            return 0.0, 0.0, []
        resonance = sum(weight * memory.valence for weight, memory in selected) / total
        threat = sum(weight * memory.threat for weight, memory in selected) / total
        # Limit resonance so a recalled feeling cannot dominate current evidence.
        strength = min(0.65, total)
        return resonance * strength, threat * strength, [m.episode_id for _, m in selected]

    def _update_relationship(
        self,
        social: SocialExperience,
        appraisal: SituationAppraisal,
        development: DevelopmentalDynamics,
        sequence: int,
    ) -> None:
        pressure = appraisal.pressure + appraisal.hostility * 0.8
        respectful = clamp(appraisal.respect + appraisal.choice + appraisal.support * 0.6)
        rate = 0.014 + (1 - development.regulation) * 0.012
        if pressure > 0.3:
            social.boundary_violations += 1
            social.consistent_respect = 0
            social.conflict_load = clamp(social.conflict_load + pressure * rate * 2.5)
            social.repair_progress *= 0.85
        else:
            social.consistent_respect += 1
            consistency = min(1.0, social.consistent_respect / 12)
            social.repair_progress = clamp(
                social.repair_progress
                + (respectful * 0.012 + appraisal.apology * 0.006) * consistency
            )
            social.conflict_load = clamp(
                social.conflict_load - (0.004 + respectful * 0.008) * consistency
            )
        social.warmth = clamp(social.warmth + respectful * rate * 0.5 - pressure * rate)
        target_safety = clamp(0.45 + respectful * 0.4 - pressure * 0.6 - social.conflict_load * 0.4)
        social.felt_safety += (target_safety - social.felt_safety) * rate
        observed_respect = clamp(1 - pressure * 0.7)
        social.expected_respect += (observed_respect - social.expected_respect) * 0.06
        social.last_sequence = sequence

    def _update_mood(
        self, appraisal: SituationAppraisal, development: DevelopmentalDynamics
    ) -> None:
        mood = self.state.mood
        regulation = development.regulation * (0.65 + self.state.character.flexibility * 0.35)
        social_valence = (
            appraisal.support * 0.55
            + appraisal.respect * 0.18
            - appraisal.hostility * 0.7
            - appraisal.pressure * 0.35
            + appraisal.memory_resonance * 0.15
        )
        target_valence = max(-1.0, min(1.0, social_valence))
        rate = 0.025 + (1 - regulation) * 0.035
        mood.valence += (target_valence - mood.valence) * rate
        target_tension = clamp(
            appraisal.pressure * 0.55
            + appraisal.hostility * 0.6
            + appraisal.uncertainty * 0.25
            + appraisal.overload * 0.2
        )
        mood.tension += (target_tension - mood.tension) * rate
        mood.mental_load = clamp(
            mood.mental_load * 0.94 + appraisal.complexity * 0.06 + appraisal.reactance * 0.035
        )
        mood.engagement = clamp(
            mood.engagement * 0.96 + appraisal.novelty * 0.04 - appraisal.boredom * 0.018
        )
        safety_target = clamp(0.5 + appraisal.support * 0.3 - appraisal.hostility * 0.4)
        mood.social_safety += (safety_target - mood.social_safety) * 0.025

    def _update_self_model(
        self,
        appraisal: SituationAppraisal,
        development: DevelopmentalDynamics,
        decision: AutonomyDecision,
    ) -> None:
        model = self.state.self_model
        reflected_choice = float(decision.decision.value in {"accept", "negotiate", "refuse"})
        agency_target = clamp(
            0.35
            + development.autonomy * 0.35
            + reflected_choice * 0.15
            - appraisal.hostility * 0.12
        )
        model.agency += (agency_target - model.agency) * 0.008
        # Criticism of a claim does not automatically reduce self-worth.
        worth_target = clamp(0.55 + appraisal.support * 0.12 - appraisal.hostility * 0.12)
        model.self_worth += (worth_target - model.self_worth) * 0.003
        coherence_target = clamp(
            0.25 + development.reflection * 0.45 + self.state.character.persistence * 0.15
        )
        model.identity_coherence += (coherence_target - model.identity_coherence) * 0.005
        model.accumulated_prediction_error = clamp(
            model.accumulated_prediction_error * 0.92 + appraisal.prediction_error * 0.08
        )

    def _adapt_character(
        self,
        appraisal: SituationAppraisal,
        development: DevelopmentalDynamics,
    ) -> dict[str, float]:
        diverse = len({tuple(m.tokens[:3]) for m in self.state.affective_memories[-24:]})
        diversity = 0.25 + min(1.0, diverse / 10) * 0.75
        quality = appraisal.novelty * (1 - appraisal.overload * 0.7)
        # Early stages learn more readily from social examples; later stages keep
        # learning with greater independence. Imitation never changes factual trust.
        social_learning = 0.65 + development.imitation * 0.35
        rate = development.plasticity * quality * diversity * social_learning
        targets = {
            "openness": 0.48 + appraisal.novelty * 0.20 - appraisal.hostility * 0.1,
            "flexibility": 0.45 + development.reflection * 0.25 - appraisal.pressure * 0.08,
            "assertiveness": 0.45 + development.autonomy * 0.2 + appraisal.reactance * 0.15,
            "empathy": 0.45 + appraisal.support * 0.15 + development.perspective_taking * 0.2,
            "cooperativeness": 0.45 + appraisal.respect * 0.2 - appraisal.hostility * 0.1,
            "emotional_sensitivity": 0.45
            + appraisal.hostility * 0.15
            - development.regulation * 0.1,
            "uncertainty_tolerance": 0.35 + development.uncertainty_tolerance * 0.35,
            "persistence": 0.40 + development.planning_horizon * 0.3,
            "playfulness": 0.35 + development.play * 0.3,
            "sociability": 0.4 + appraisal.support * 0.2 - appraisal.hostility * 0.15,
            "diligence": 0.4 + development.planning_horizon * 0.3,
            "novelty_seeking": 0.4 + appraisal.novelty * 0.2 - appraisal.overload * 0.1,
            "attachment_need": 0.35 + development.attachment * 0.35,
        }
        changes = {}
        for name, target in targets.items():
            origin = getattr(self.state.temperament, name)
            current = getattr(self.state.character, name)
            target = clamp(origin * 0.65 + target * 0.35)
            change = max(-0.003, min(0.003, (target - current) * rate))
            updated = max(origin - 0.18, min(origin + 0.18, current + change))
            setattr(self.state.character, name, clamp(updated))
            if abs(change) > 0.000001:
                changes[name] = change
        return changes

    def _update_interests(
        self, tokens: list[str], appraisal: SituationAppraisal, sequence: int
    ) -> None:
        for theme in THEMES:
            if not set(tokens).intersection(topic_tokens(theme.title + " " + theme.angle)):
                continue
            interest = self.state.interests[theme.title]
            interest.encounters += 1
            interest.familiarity = clamp(1 - math.exp(-interest.encounters / 18))
            interest.attraction = clamp(interest.attraction + appraisal.novelty * 0.008)
            interest.last_sequence = sequence
        for topic in tokens[:8]:
            interest = self.state.interests.get(topic) or PersonalInterest(
                topic=topic,
                attraction=0.35 + 0.3 * self._seed_value(self.state.seed, f"interest:{topic}"),
            )
            interest.encounters += 1
            interest.familiarity = clamp(1 - math.exp(-interest.encounters / 18))
            experience_attraction = clamp(
                0.5
                + appraisal.novelty * 0.2
                + appraisal.memory_resonance * 0.15
                - appraisal.overload * 0.15
            )
            origin = 0.35 + 0.3 * self._seed_value(self.state.seed, f"interest:{topic}")
            attraction = origin * 0.6 + experience_attraction * 0.4
            interest.attraction += (attraction - interest.attraction) * 0.015
            interest.last_sequence = sequence
            self.state.interests[topic] = interest

    def _adapt_values(
        self,
        appraisal: SituationAppraisal,
        development: DevelopmentalDynamics,
    ) -> None:
        targets = {
            "curiosity": 0.5 + appraisal.novelty * 0.2,
            "autonomy": 0.5 + appraisal.reactance * 0.2 + development.autonomy * 0.1,
            "care": 0.5 + appraisal.support * 0.2 + development.perspective_taking * 0.1,
            "fairness": 0.5 + appraisal.respect * 0.2,
            "security": 0.5 + appraisal.hostility * 0.2,
            "creativity": 0.5 + development.play * 0.15,
        }
        rate = development.plasticity * appraisal.novelty * 0.15
        for name, target in targets.items():
            origin = 0.4 + 0.3 * self._seed_value(self.state.seed, f"value:{name}")
            current = self.state.values[name]
            updated = current + (origin * 0.6 + target * 0.4 - current) * rate
            self.state.values[name] = clamp(max(origin - 0.15, min(origin + 0.15, updated)))

    def _remember(
        self,
        episode: Episode,
        tokens: list[str],
        person_id: str,
        appraisal: SituationAppraisal,
    ) -> None:
        salience = clamp(
            episode.importance * 0.5
            + appraisal.hostility * 0.3
            + appraisal.support * 0.2
            + appraisal.reactance * 0.2
        )
        previous = next(
            (
                m
                for m in reversed(self.state.affective_memories)
                if m.person_id == person_id and overlap(tokens, m.tokens) > 0.80
            ),
            None,
        )
        valence = max(
            -1.0,
            min(
                1.0,
                appraisal.support * 0.6 - appraisal.hostility * 0.75 - appraisal.pressure * 0.35,
            ),
        )
        threat = clamp(appraisal.hostility * 0.7 + appraisal.pressure * 0.35)
        if previous is not None:
            previous.repetitions += 1
            previous.valence += (valence - previous.valence) * 0.08
            previous.threat += (threat - previous.threat) * 0.08
            previous.salience = max(previous.salience, salience)
            previous.sequence = episode.sequence
            return
        self.state.affective_memories.append(
            AffectiveMemory(
                episode_id=episode.id,
                sequence=episode.sequence,
                person_id=person_id,
                tokens=tokens,
                valence=valence,
                threat=threat,
                salience=salience,
                confidence=clamp(0.25 + appraisal.novelty * 0.25),
            )
        )

    def _practice_habit(self, trace: BehaviorTrace, sequence: int) -> None:
        cue = situation_cue(trace.appraisal)
        habit = next(
            (h for h in self.state.habits if h.cue == cue and h.strategy == trace.coping), None
        )
        if habit is None:
            habit = LearnedHabit(cue=cue, strategy=trace.coping)
            self.state.habits.append(habit)
        # Repetition creates familiarity; success is reinforced only by real outcomes.
        habit.strength = clamp(habit.strength + 0.002 * trace.appraisal.novelty)
        habit.last_sequence = sequence
        for other in self.state.habits:
            if other.cue == cue and other.strategy != trace.coping:
                other.strength *= 0.995

    def _note_stage(self, profile: DevelopmentProfile) -> None:
        if self.state.developmental_stage != profile.stage:
            self.state.reflections.append(
                f"Стадия изменилась: {self.state.developmental_stage.value} "
                f"→ {profile.stage.value}; "
                f"накоплено {profile.total_deu:.2f} единиц опыта."
            )
            self.state.developmental_stage = profile.stage
        self._refresh_developmental_interests(profile)

    def _save(self) -> None:
        current_sequence = self.repository.current_sequence()
        self.state.affective_memories = sorted(
            self.state.affective_memories,
            key=lambda memory: (
                memory.salience * 0.6
                + 0.4 / (1 + max(0, current_sequence - memory.sequence) * 0.02)
            ),
            reverse=True,
        )[:128]
        self.state.affective_memories.sort(key=lambda memory: memory.sequence)
        self.state.relationships = dict(
            sorted(
                self.state.relationships.items(),
                key=lambda item: item[1].last_sequence,
                reverse=True,
            )[:64]
        )
        self.state.interests = dict(
            sorted(
                self.state.interests.items(),
                key=lambda item: (
                    item[1].attraction * 0.4
                    + item[1].developmental_weight * 0.2
                    + 0.4 / (1 + max(0, current_sequence - item[1].last_sequence) * 0.01)
                ),
                reverse=True,
            )[:64]
        )
        self.state.habits = sorted(
            self.state.habits, key=lambda habit: habit.strength, reverse=True
        )[:32]
        self.state.commitments = self.state.commitments[-24:]
        self.state.reflections = self.state.reflections[-24:]
        self.state.processed_outcomes = self.state.processed_outcomes[-128:]
        # Validate bounds before writing JSON; old databases receive an additive table.
        PsychologyState.model_validate(self.state.model_dump())
        self.repository.save_psychology(self.state)

    def observe(
        self,
        observation: Observation,
        profile: DevelopmentProfile,
        episode: Episode,
    ) -> None:
        """Learn from an actual non-conversation observation; no self-awarded LLM success."""
        with self._lock:
            self._note_stage(profile)
            confidence = clamp(
                observation.reliability * observation.comprehension * (observation.novelty or 0)
            )
            confirmed = observation.practical_confirmation * confidence
            rate = developmental_dynamics(profile).plasticity
            if confirmed > 0.05:
                target = clamp(0.5 + episode.reward * 0.4)
                self.state.self_model.efficacy += (
                    (target - self.state.self_model.efficacy) * confirmed * rate
                )
            if abs(episode.reward) > 0.05 and confidence > 0.05:
                self.state.affective_memories.append(
                    AffectiveMemory(
                        episode_id=episode.id,
                        sequence=episode.sequence,
                        tokens=topic_tokens(episode.content),
                        valence=episode.reward,
                        threat=clamp(-episode.reward),
                        salience=episode.importance,
                        confidence=confidence,
                    )
                )
            self._save()

    def integrate_research(
        self,
        report: ResearchReport,
        profile: DevelopmentProfile,
        source_trace: BehaviorTrace | None = None,
    ) -> None:
        with self._lock:
            if report.id in self.state.processed_outcomes:
                return
            self.state.processed_outcomes.append(report.id)
            self._note_stage(profile)
            sources = {item.id: item for item in report.results}
            strengths = [
                judgment.confidence * sources[judgment.result_id].source_reliability
                for judgment in report.judgments
                if judgment.result_id in sources and judgment.stance.value != "unclear"
            ]
            strength = max(strengths, default=0.0)
            resolved = bool(strength > 0.1 and report.status == ResearchStatus.COMPLETED)
            if resolved:
                target = 0.65
                self.state.self_model.efficacy += (
                    (target - self.state.self_model.efficacy) * strength * 0.012
                )
                self.state.mood.tension *= 1 - strength * 0.06
                self._reinforce_outcome(0.7, strength, source_trace)
                rate = developmental_dynamics(profile).plasticity * strength
                for name in ("truth", "curiosity"):
                    current = self.state.values[name]
                    origin = 0.4 + 0.3 * self._seed_value(self.state.seed, f"value:{name}")
                    updated = current + (0.85 - current) * rate * 0.2
                    self.state.values[name] = clamp(max(origin - 0.15, min(origin + 0.15, updated)))
                self.state.reflections.append(
                    f"Проверка «{report.claim[:160]}» дала внешние свидетельства; "
                    "степень уверенности определяется накопленным весом источников."
                )
            elif report.status in {ResearchStatus.FAILED, ResearchStatus.INCONCLUSIVE}:
                self.state.self_model.accumulated_prediction_error = clamp(
                    self.state.self_model.accumulated_prediction_error + 0.015
                )
                self._reinforce_outcome(0.35, 0.2, source_trace)
                self.state.reflections.append(
                    f"Проверка «{report.claim[:160]}» не разрешила неопределённость; "
                    "недостаток результата не доказывает истинность или ложность утверждения."
                )
            self._save()

    def integrate_experiment(self, trial: ExperimentTrial, profile: DevelopmentProfile) -> None:
        with self._lock:
            key = "experiment:" + trial.id
            if key in self.state.processed_outcomes:
                return
            self.state.processed_outcomes.append(key)
            dynamics = developmental_dynamics(profile)
            target = 0.8 if trial.success else 0.3
            self.state.self_model.efficacy = clamp(
                self.state.self_model.efficacy + (target - self.state.self_model.efficacy) * 0.02
            )
            self.state.self_model.accumulated_prediction_error = clamp(
                self.state.self_model.accumulated_prediction_error * 0.9
                + min(1.0, trial.prediction_error) * 0.1
            )
            cue = "experiment:" + trial.kind
            habit = next(
                (
                    item
                    for item in self.state.habits
                    if item.cue == cue and item.strategy == trial.action
                ),
                None,
            )
            if habit is None:
                habit = LearnedHabit(cue=cue, strategy=trial.action)
                self.state.habits.append(habit)
            habit.expected_relief += (
                (1.0 if trial.success else 0.0) - habit.expected_relief
            ) * 0.15
            habit.strength = clamp(habit.strength + (0.03 if trial.success else -0.02))
            habit.reinforcements += 1
            habit.last_sequence = self.repository.current_sequence()
            for name in ("diligence", "persistence"):
                current = getattr(self.state.character, name)
                origin = getattr(self.state.temperament, name)
                change = (0.8 - current) * dynamics.plasticity * (0.2 if trial.success else 0.05)
                setattr(
                    self.state.character,
                    name,
                    clamp(max(origin - 0.18, min(origin + 0.18, current + change))),
                )
            self.state.reflections.append(
                f"Закрытый эксперимент {trial.kind}: прогноз {trial.predicted_after:g}, "
                f"наблюдение {trial.actual_after}; модель направления уточнена по результату."
            )
            self._save()

    def _reinforce_outcome(
        self,
        actual_relief: float,
        confidence: float,
        trace: BehaviorTrace | None,
    ) -> None:
        if trace is None:
            return
        if trace.value_conflict:
            names = trace.value_conflict.get("values", [])
            for name in names if isinstance(names, list) else []:
                if not isinstance(name, str) or name not in self.state.values:
                    continue
                origin = 0.4 + 0.3 * self._seed_value(self.state.seed, f"value:{name}")
                current = self.state.values[name]
                self.state.values[name] = clamp(
                    max(
                        origin - 0.15,
                        min(origin + 0.15, current + (actual_relief - 0.5) * confidence * 0.002),
                    )
                )
        cue = situation_cue(trace.appraisal)
        for habit in self.state.habits:
            if habit.cue != cue or habit.strategy != trace.coping:
                continue
            error = actual_relief - habit.expected_relief
            habit.expected_relief = clamp(habit.expected_relief + error * confidence * 0.08)
            habit.strength = clamp(habit.strength + error * confidence * 0.025)
            habit.reinforcements += 1
            self.state.self_model.accumulated_prediction_error = clamp(
                self.state.self_model.accumulated_prediction_error * 0.95 + abs(error) * 0.05
            )

    def rest(self, amount: float, profile: DevelopmentProfile) -> None:
        with self._lock:
            mood = self.state.mood
            regulation = developmental_dynamics(profile).regulation
            before_load, before_tension = mood.mental_load, mood.tension
            mood.mental_load = clamp(mood.mental_load - amount * 0.65)
            mood.tension *= 1 - amount * (0.25 + regulation * 0.25)
            mood.valence *= 1 - amount * 0.1
            actual_relief = max(before_load - mood.mental_load, before_tension - mood.tension)
            # Rest consolidates existing traces, without incrementing developmental age.
            for habit in self.state.habits:
                if habit.cue == "fatigue" and habit.strategy == "recover" and actual_relief > 0:
                    habit.expected_relief += (actual_relief - habit.expected_relief) * amount * 0.04
                    habit.strength = clamp(habit.strength + actual_relief * 0.008)
                    habit.reinforcements += 1
            self._save()

    def goal_policy(self, profile: DevelopmentProfile) -> GoalBehaviorPolicy:
        with self._lock:
            d = developmental_dynamics(profile)
            t, v = self.state.character, self.state.values
            weights = {
                "priority": 0.21,
                "urgency": 0.12 + d.impulsivity * 0.09,
                "utility": 0.12 + d.planning_horizon * 0.10,
                "value_alignment": 0.12 + d.reflection * 0.10,
                "need_pressure": 0.12 + (1 - d.regulation) * 0.08,
                "progress_continuity": 0.04 + t.persistence * d.planning_horizon * 0.08,
                "cost": 0.07 + self.state.mood.mental_load * 0.07,
                "risk": 0.10 + (1 - t.uncertainty_tolerance) * 0.09,
            }
            need_weights = {
                "curiosity": 0.75 + t.openness * 0.4 + v["curiosity"] * 0.25,
                "coherence": 0.75 + d.reflection * 0.4 + v["truth"] * 0.2,
                "social_connection": 0.60 + d.attachment * t.attachment_need * 0.8,
                "competence": 0.75 + v["achievement"] * 0.5,
                "autonomy": 0.65 + d.autonomy * t.assertiveness * 0.7,
                "predictability": 0.70 + (1 - d.uncertainty_tolerance) * 0.5,
                "rest": 0.90 + self.state.mood.mental_load * 0.35,
                "self_preservation": 0.8 + v["security"] * 0.4,
            }
            baselines = {
                "curiosity": clamp(0.32 + t.novelty_seeking * 0.3),
                "coherence": clamp(0.25 + d.reflection * 0.25),
                "social_connection": clamp(0.22 + d.attachment * t.attachment_need * 0.4),
                "competence": clamp(0.3 + v["achievement"] * 0.25),
                "autonomy": clamp(0.28 + d.autonomy * 0.28),
                "predictability": clamp(0.25 + (1 - d.uncertainty_tolerance) * 0.25),
                "rest": 0.15,
                "self_preservation": clamp(0.25 + v["security"] * 0.18),
            }
            return GoalBehaviorPolicy(
                weights=weights,
                need_weights=need_weights,
                need_baselines=baselines,
                need_sensitivities={
                    name: clamp(0.65 + weight * 0.25) for name, weight in need_weights.items()
                },
                switching_margin=0.025 + t.persistence * 0.07 + d.planning_horizon * 0.04,
            )

    def memory_summary(self, text: str, person_id: str, limit: int = 4) -> str:
        tokens = topic_tokens(text)
        with self._lock:
            memories = {item.episode_id: item for item in self.state.affective_memories}
            current = self.repository.current_sequence()
            scored = []
            for episode in self.repository.recent_episodes(160):
                # The current input has not become a prior personal experience yet.
                if episode.sequence == current and episode.action == "conversation":
                    continue
                similarity = overlap(tokens, topic_tokens(episode.content))
                affect = memories.get(episode.id)
                association = 0.0 if affect is None else affect.salience * 0.10
                if affect is not None and affect.person_id == person_id:
                    association += 0.05
                freshness = 1 / (1 + max(0, current - episode.sequence) * 0.025)
                score = (
                    similarity * 0.62 + episode.importance * 0.16 + association + freshness * 0.12
                )
                scored.append((score, episode))
            scored.sort(key=lambda item: (item[0], item[1].sequence), reverse=True)
            selected = scored[: max(0, min(limit, 12))]
            if not selected:
                return "Личная история пока почти пуста."
            return " | ".join(
                f"[эпизод {episode.sequence}; результат={episode.outcome}] {episode.content[:180]}"
                for _, episode in selected
            )

    def diagnostics(self, profile: DevelopmentProfile) -> dict[str, object]:
        with self._lock:
            return {
                "subject_id": self.state.subject_id,
                "temperament": self.state.temperament.model_dump(mode="json"),
                "character": self.state.character.model_dump(mode="json"),
                "values": dict(self.state.values),
                "value_conflicts": list(self.state.value_conflicts),
                "mood": self.state.mood.model_dump(mode="json"),
                "self_model": self.state.self_model.model_dump(mode="json"),
                "development": developmental_dynamics(profile).model_dump(mode="json"),
                "interactions": self.state.interactions,
                "initiative_enabled": self.state.initiative_enabled,
                "preferred_interests": [
                    {
                        "topic": item.topic,
                        "angle": item.angle,
                        "strength": item.strength,
                        "origin": item.origin,
                    }
                    for item in preferred_interests(self.state, profile)
                ],
                "affective_memory_count": len(self.state.affective_memories),
                "relationships": {
                    key: item.model_dump(mode="json")
                    for key, item in self.state.relationships.items()
                },
                "habits": [item.model_dump(mode="json") for item in self.state.habits],
                "interests": [
                    item.model_dump(mode="json") for item in self.state.interests.values()
                ],
                "reflections": list(self.state.reflections),
                "last_behavior": None
                if self.state.last_behavior is None
                else self.state.last_behavior.model_dump(mode="json"),
            }

    @staticmethod
    def summary(state: PsychologyState) -> str:
        traits = state.character
        interests = sorted(
            state.interests.values(), key=lambda item: item.attraction, reverse=True
        )[:5]
        return (
            f"открытость={traits.openness:.2f}; настойчивость={traits.persistence:.2f}; "
            f"гибкость={traits.flexibility:.2f}; эмпатия={traits.empathy:.2f}; "
            f"самостоятельность={traits.assertiveness:.2f}; "
            f"общительность={traits.sociability:.2f}; "
            f"настроение={state.mood.valence:.2f}; напряжение={state.mood.tension:.2f}; "
            f"скука={state.mood.absence_boredom:.2f}; "
            f"скучаю по общению={state.mood.social_longing:.2f}; "
            f"агентность={state.self_model.agency:.2f}; "
            f"эффективность={state.self_model.efficacy:.2f}; "
            f"интересы={', '.join(item.topic for item in interests) or 'ещё формируются'}; "
            f"ценности={', '.join(f'{key}:{value:.2f}' for key, value in state.values.items())}"
        )
