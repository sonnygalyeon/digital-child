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
    SELF_REFLECTION = "self_reflection"


def empty_domain_experience() -> dict[DevelopmentDomain, float]:
    return {domain: 0.0 for domain in DevelopmentDomain}


class Observation(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: str = Field(min_length=1, max_length=50_000)
    source_kind: SourceKind = SourceKind.ENVIRONMENT
    raw_units: float = Field(gt=0.0)

    novelty: Probability
    attention: Probability
    comprehension: Probability
    reliability: Probability
    integration: Probability
    practical_confirmation: Probability = 0.0

    domains: dict[DevelopmentDomain, float] = Field(
        default_factory=lambda: {DevelopmentDomain.FACTUAL_KNOWLEDGE: 1.0}
    )
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


class Episode(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    observation_id: str
    content: str
    action: str
    outcome: str
    reward: float = Field(ge=-1.0, le=1.0)
    importance: Probability
    effective_units: float = Field(ge=0.0)
    metadata: dict[str, object] = Field(default_factory=dict)


class DevelopmentTransition(StrictModel):
    old_stage: DevelopmentStage
    new_stage: DevelopmentStage
    gained_deu: float = Field(ge=0.0)
    domain_gains: dict[DevelopmentDomain, float]

    @property
    def stage_changed(self) -> bool:
        return self.old_stage != self.new_stage


class CycleResult(StrictModel):
    assessment: ExperienceAssessment
    transition: DevelopmentTransition
    state: AgentState
    profile: DevelopmentProfile
    response: str


class AgentSnapshot(StrictModel):
    state: AgentState
    profile: DevelopmentProfile
