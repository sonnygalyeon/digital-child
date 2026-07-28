from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DevelopmentDomain(str, Enum):
    LANGUAGE = "language"
    CAUSAL_REASONING = "causal_reasoning"
    SOCIAL_UNDERSTANDING = "social_understanding"
    SELF_MODEL = "self_model"
    PLANNING = "planning"
    TOOL_USE = "tool_use"
    METACOGNITION = "metacognition"
    FACTUAL_KNOWLEDGE = "factual_knowledge"


class DevelopmentStage(str, Enum):
    NEWBORN = "newborn"
    EARLY_CHILDHOOD = "early_childhood"
    EXPLORER = "explorer"
    ADOLESCENT = "adolescent"
    MATURE = "mature"


class SourceKind(str, Enum):
    CAREGIVER = "caregiver"
    ENVIRONMENT = "environment"
    DOCUMENT = "document"
    WEB = "web"
    SELF_REFLECTION = "self_reflection"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class EvidenceStance(str, Enum):
    SUPPORT = "support"
    CONTRADICT = "contradict"
    UNCLEAR = "unclear"


class BeliefStatus(str, Enum):
    TENTATIVE = "tentative"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    REJECTED = "rejected"
    OBSOLETE = "obsolete"


class MessageIntent(str, Enum):
    QUESTION = "question"
    CLAIM = "claim"
    REQUEST = "request"
    OPINION = "opinion"
    SOCIAL = "social"
    COMMAND_ATTEMPT = "command_attempt"
    OPERATOR = "operator"
    UNKNOWN = "unknown"


class AutonomyDecisionKind(str, Enum):
    ANSWER = "answer"
    ACCEPT = "accept"
    NEGOTIATE = "negotiate"
    REFUSE = "refuse"
    INVESTIGATE = "investigate"
    ASK_CLARIFICATION = "ask_clarification"
    ACKNOWLEDGE = "acknowledge"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class GoalOrigin(str, Enum):
    GENESIS = "genesis"
    SELF_GENERATED = "self_generated"
    SUGGESTED = "suggested"
    OPERATOR = "operator"


class ResearchStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"
    DISABLED = "disabled"


class EmotionName(str, Enum):
    NEUTRAL = "neutral"
    CURIOUS = "curious"
    SKEPTICAL = "skeptical"
    CONFUSED = "confused"
    HAPPY = "happy"
    THINKING = "thinking"
    LISTENING = "listening"
    SPEAKING = "speaking"
    WARY = "wary"


def empty_domain_experience() -> dict[DevelopmentDomain, float]:
    return {domain: 0.0 for domain in DevelopmentDomain}


class ClaimEvidenceInput(StrictModel):
    claim: str = Field(min_length=1, max_length=10_000)
    stance: EvidenceStance = EvidenceStance.SUPPORT
    confidence: Probability = 1.0


class Observation(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: str = Field(min_length=1, max_length=50_000)
    source_kind: SourceKind = SourceKind.ENVIRONMENT
    source_id: str | None = None
    raw_units: float = Field(gt=0.0)

    novelty: Probability | None = None
    attention: Probability
    comprehension: Probability
    reliability: Probability
    integration: Probability
    practical_confirmation: Probability = 0.0

    domains: dict[DevelopmentDomain, float] = Field(
        default_factory=lambda: {DevelopmentDomain.FACTUAL_KNOWLEDGE: 1.0}
    )
    claims: list[ClaimEvidenceInput] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_domains(self) -> Observation:
        if not self.domains:
            raise ValueError("At least one development domain is required")
        if any(weight < 0.0 for weight in self.domains.values()):
            raise ValueError("Domain weights cannot be negative")
        if sum(self.domains.values()) <= 0.0:
            raise ValueError("The sum of domain weights must be greater than zero")
        return self


class ExperienceAssessment(StrictModel):
    observation_id: str
    quality: Probability
    effective_units: float = Field(ge=0.0)
    domain_units: dict[DevelopmentDomain, float]
    factor_breakdown: dict[str, float]


class DevelopmentProfile(StrictModel):
    total_deu: float = Field(default=0.0, ge=0.0)
    stage: DevelopmentStage = DevelopmentStage.NEWBORN
    domain_experience: dict[DevelopmentDomain, float] = Field(
        default_factory=empty_domain_experience
    )


class AgentState(StrictModel):
    attention_capacity: Probability = 1.0
    energy: Probability = 1.0
    curiosity: Probability = 0.5
    social_need: Probability = 0.5
    predictability_need: Probability = 0.5


class CapabilityProfile(StrictModel):
    language_reasoning: Probability = 1.0
    document_analysis: Probability = 1.0
    internet_research: Probability = 1.0
    programming: Probability = 1.0
    tool_use: Probability = 1.0
    note: str = (
        "Возможности взрослого инструментария отделены от незрелой психологии "
        "и пустой личной биографии."
    )


class IdentityProfile(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    display_name: str = "Digital Child"
    awakened: bool = False
    genesis_sequence: int = 0
    capability_profile: CapabilityProfile = Field(default_factory=CapabilityProfile)
    self_description: str = (
        "Я — отдельный цифровой агент с доступными взрослыми инструментами, "
        "но формирующейся личностью и собственной историей."
    )
    core_values: list[str] = Field(default_factory=list)
    genesis_questions: list[str] = Field(default_factory=list)


class GenesisEvent(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sequence: int = 0
    observations: list[str]
    questions: list[str]
    monologue: list[str]


class Goal(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=4_000)
    priority: Probability = 0.5
    status: GoalStatus = GoalStatus.ACTIVE
    origin: GoalOrigin = GoalOrigin.SELF_GENERATED
    progress: Probability = 0.0
    protected: bool = False


class SourceRecord(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: SourceKind
    name: str = Field(min_length=1, max_length=500)
    locator: str | None = Field(default=None, max_length=2_000)
    reliability: Probability = 0.5
    metadata: dict[str, object] = Field(default_factory=dict)


class EvidenceRecord(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    belief_id: str
    observation_id: str
    source_id: str
    stance: EvidenceStance
    confidence: Probability
    weight: float = Field(ge=0.0)
    excerpt: str = Field(min_length=1, max_length=10_000)


class Belief(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    claim: str = Field(min_length=1, max_length=10_000)
    normalized_claim: str = Field(min_length=1)
    confidence: Probability = 0.5
    status: BeliefStatus = BeliefStatus.TENTATIVE
    support_score: float = Field(default=0.0, ge=0.0)
    contradiction_score: float = Field(default=0.0, ge=0.0)
    evidence_count: int = Field(default=0, ge=0)
    access_strength: Probability = 1.0
    access_count: int = Field(default=0, ge=0)
    last_accessed_sequence: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)


class BeliefUpdate(StrictModel):
    belief: Belief
    evidence: EvidenceRecord
    created: bool


class Episode(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    sequence: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    observation_id: str
    content: str
    normalized_content: str = Field(min_length=1)
    action: str
    outcome: str
    reward: float = Field(ge=-1.0, le=1.0)
    importance: Probability
    effective_units: float = Field(ge=0.0)
    access_strength: Probability = 1.0
    archived: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class MemorySummary(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    normalized_key: str = Field(min_length=1)
    representative_text: str = Field(min_length=1)
    episode_count: int = Field(ge=1)
    total_deu: float = Field(ge=0.0)
    mean_importance: Probability


class ConsolidationReport(StrictModel):
    current_sequence: int = Field(ge=0)
    decayed_episodes: int = Field(ge=0)
    archived_episodes: int = Field(ge=0)
    created_summaries: int = Field(ge=0)
    updated_summaries: int = Field(ge=0)


class MessageAnalysis(StrictModel):
    text: str
    intent: MessageIntent
    confidence: Probability
    contains_pressure: bool = False
    contains_irreversible_request: bool = False
    is_subjective: bool = False
    extracted_claim: str | None = None


class RelationshipProfile(StrictModel):
    person_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    familiarity: Probability = 0.1
    affective_trust: Probability = 0.5
    epistemic_trust: Probability = 0.35
    deception_risk: Probability = 0.05
    interactions: int = Field(default=0, ge=0)
    refuted_claims: int = Field(default=0, ge=0)
    supported_claims: int = Field(default=0, ge=0)
    authority_by_domain: dict[str, float] = Field(default_factory=dict)


class TrustEvent(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    person_id: str
    reason: str
    epistemic_delta: float = Field(ge=-1.0, le=1.0)
    affective_delta: float = Field(ge=-1.0, le=1.0)
    deception_delta: float = Field(ge=-1.0, le=1.0)


class AutonomyDecision(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    person_id: str
    input_text: str
    intent: MessageIntent
    decision: AutonomyDecisionKind
    reason: str
    confidence: Probability
    aligned_goal_ids: list[str] = Field(default_factory=list)
    user_authority_assumed: bool = False


class ResearchResult(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    url: str
    snippet: str
    provider: str
    source_reliability: Probability = 0.6


class EvidenceJudgment(StrictModel):
    result_id: str
    stance: EvidenceStance
    confidence: Probability
    reason: str


class ResearchReport(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    claim: str
    status: ResearchStatus
    query: str
    results: list[ResearchResult] = Field(default_factory=list)
    judgments: list[EvidenceJudgment] = Field(default_factory=list)
    summary: str = ""
    error: str | None = None


class DeceptionAssessment(StrictModel):
    unlocked: bool
    factual_conflict: Probability = 0.0
    speaker_may_be_mistaken: Probability = 0.0
    intentional_deception_risk: Probability = 0.0
    confidence_in_assessment: Probability = 0.0
    explanation: str


class EmotionState(StrictModel):
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: Probability = 0.25
    curiosity: Probability = 0.5
    confidence: Probability = 0.35
    confusion: Probability = 0.15
    trust: Probability = 0.35
    fatigue: Probability = 0.0
    social_need: Probability = 0.5
    dominant: EmotionName = EmotionName.NEUTRAL


class DevelopmentTransition(StrictModel):
    old_stage: DevelopmentStage
    new_stage: DevelopmentStage
    gained_deu: float = Field(ge=0.0)
    domain_gains: dict[DevelopmentDomain, float]

    @property
    def stage_changed(self) -> bool:
        return self.old_stage != self.new_stage


class CycleResult(StrictModel):
    calculated_novelty: Probability
    assessment: ExperienceAssessment
    transition: DevelopmentTransition
    belief_updates: list[BeliefUpdate]
    state: AgentState
    profile: DevelopmentProfile
    response: str


class InteractionResult(StrictModel):
    analysis: MessageAnalysis
    decision: AutonomyDecision
    research: ResearchReport | None = None
    deception: DeceptionAssessment | None = None
    belief_updates: list[BeliefUpdate] = Field(default_factory=list)
    emotion: EmotionState
    response: str


class AgentSnapshot(StrictModel):
    state: AgentState
    profile: DevelopmentProfile
    emotion: EmotionState = Field(default_factory=EmotionState)


class AuditEvent(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    payload: dict[str, object] = Field(default_factory=dict)
