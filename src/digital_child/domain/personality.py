from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from digital_child.domain.models import (
    AutonomyDecisionKind,
    DevelopmentStage,
    Probability,
    StrictModel,
)


class CharacterTraits(StrictModel):
    openness: Probability = 0.5
    diligence: Probability = 0.5
    sociability: Probability = 0.5
    cooperativeness: Probability = 0.5
    emotional_sensitivity: Probability = 0.5
    persistence: Probability = 0.5
    flexibility: Probability = 0.5
    empathy: Probability = 0.5
    assertiveness: Probability = 0.5
    playfulness: Probability = 0.5
    novelty_seeking: Probability = 0.5
    attachment_need: Probability = 0.5
    uncertainty_tolerance: Probability = 0.5


class MoodState(StrictModel):
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    tension: Probability = 0.15
    social_safety: Probability = 0.45
    engagement: Probability = 0.5
    mental_load: Probability = 0.1
    social_longing: Probability = 0.0
    absence_boredom: Probability = 0.0
    absence_valence_penalty: Probability = 0.0


class SelfModel(StrictModel):
    agency: Probability = 0.35
    efficacy: Probability = 0.3
    self_worth: Probability = 0.55
    identity_coherence: Probability = 0.3
    accumulated_prediction_error: Probability = 0.0


class SocialExperience(StrictModel):
    person_id: str
    warmth: Probability = 0.5
    felt_safety: Probability = 0.45
    expected_respect: Probability = 0.55
    conflict_load: Probability = 0.0
    boundary_violations: int = Field(default=0, ge=0)
    repair_progress: Probability = 0.0
    consistent_respect: int = Field(default=0, ge=0)
    last_sequence: int = Field(default=0, ge=0)
    last_contact_at: datetime | None = None
    last_contact_message_id: str | None = None
    longing: Probability = 0.0
    last_initiative_at: datetime | None = None
    last_initiative_attempt_at: datetime | None = None
    last_discussion_message_id: str | None = None
    unanswered_initiatives: int = Field(default=0, ge=0)
    initiative_allowed: bool = True
    quiet_until: datetime | None = None
    recent_initiative_topics: list[str] = Field(default_factory=list, max_length=8)


class AffectiveMemory(StrictModel):
    episode_id: str
    sequence: int = Field(ge=0)
    person_id: str | None = None
    tokens: list[str] = Field(default_factory=list, max_length=24)
    valence: float = Field(ge=-1.0, le=1.0)
    threat: Probability
    salience: Probability
    confidence: Probability
    repetitions: int = Field(default=1, ge=1)


class LearnedHabit(StrictModel):
    cue: str
    strategy: str
    strength: Probability = 0.1
    expected_relief: Probability = 0.5
    reinforcements: int = Field(default=0, ge=0)
    last_sequence: int = Field(default=0, ge=0)


class PersonalInterest(StrictModel):
    topic: str
    attraction: Probability = 0.5
    familiarity: Probability = 0.0
    encounters: int = Field(default=0, ge=0)
    last_sequence: int = Field(default=0, ge=0)
    origin: str = "experience"
    introduced_stage: DevelopmentStage | None = None
    developmental_weight: Probability = 0.0


class BehavioralCommitment(StrictModel):
    person_id: str
    tokens: list[str] = Field(default_factory=list, max_length=24)
    decision: AutonomyDecisionKind
    confidence: Probability
    sequence: int = Field(ge=0)


class DevelopmentalDynamics(StrictModel):
    stage: DevelopmentStage
    progress: Probability = 0.0
    regulation: Probability
    reflection: Probability
    perspective_taking: Probability
    planning_horizon: Probability
    autonomy: Probability
    attachment: Probability
    imitation: Probability
    uncertainty_tolerance: Probability
    play: Probability
    impulsivity: Probability
    identity_exploration: Probability
    plasticity: float = Field(ge=0.0, le=0.03)
    guidance: str


class SituationAppraisal(StrictModel):
    novelty: Probability
    pressure: Probability
    hostility: Probability
    support: Probability
    respect: Probability
    criticism: Probability
    apology: Probability
    choice: Probability
    complexity: Probability
    uncertainty: Probability
    memory_resonance: float = Field(default=0.0, ge=-1.0, le=1.0)
    recalled_threat: Probability = 0.0
    prediction_error: Probability = 0.0
    reactance: Probability = 0.0
    overload: Probability = 0.0
    boredom: Probability = 0.0


class BehaviorTrace(StrictModel):
    sequence: int = Field(ge=0)
    stage: DevelopmentStage
    style: str
    coping: str
    appraisal: SituationAppraisal
    candidate_scores: dict[str, float] = Field(default_factory=dict)
    motivations: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)
    recalled_episode_ids: list[str] = Field(default_factory=list, max_length=8)
    trait_changes: dict[str, float] = Field(default_factory=dict)
    value_conflict: dict[str, object] = Field(default_factory=dict)


class GoalBehaviorPolicy(StrictModel):
    weights: dict[str, float] = Field(default_factory=dict)
    need_weights: dict[str, float] = Field(default_factory=dict)
    need_sensitivities: dict[str, float] = Field(default_factory=dict)
    need_baselines: dict[str, float] = Field(default_factory=dict)
    switching_margin: float = Field(default=0.04, ge=0.0, le=0.3)


class PsychologyState(StrictModel):
    schema_version: int = 1
    subject_id: str
    seed: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    temperament: CharacterTraits
    character: CharacterTraits
    values: dict[str, Probability] = Field(default_factory=dict)
    mood: MoodState = Field(default_factory=MoodState)
    self_model: SelfModel = Field(default_factory=SelfModel)
    interactions: int = Field(default=0, ge=0)
    developmental_stage: DevelopmentStage = DevelopmentStage.NEWBORN
    relationships: dict[str, SocialExperience] = Field(default_factory=dict, max_length=64)
    affective_memories: list[AffectiveMemory] = Field(default_factory=list, max_length=128)
    habits: list[LearnedHabit] = Field(default_factory=list, max_length=32)
    interests: dict[str, PersonalInterest] = Field(default_factory=dict, max_length=64)
    commitments: list[BehavioralCommitment] = Field(default_factory=list, max_length=24)
    reflections: list[str] = Field(default_factory=list, max_length=24)
    processed_outcomes: list[str] = Field(default_factory=list, max_length=128)
    last_behavior: BehaviorTrace | None = None
    initiative_enabled: bool = True
    value_conflicts: list[dict[str, object]] = Field(default_factory=list, max_length=24)
