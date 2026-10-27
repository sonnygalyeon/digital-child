from digital_child.domain.models import (
    DevelopmentDomain,
    DevelopmentProfile,
    DevelopmentStage,
    ExperienceAssessment,
)
from digital_child.psychology.development import DevelopmentEngine


def assessment(total: float, domains: dict[DevelopmentDomain, float]) -> ExperienceAssessment:
    return ExperienceAssessment(
        observation_id="test",
        quality=1.0,
        effective_units=total,
        domain_units=domains,
        factor_breakdown={},
    )


def test_unbalanced_knowledge_does_not_create_maturity() -> None:
    profile = DevelopmentProfile()
    DevelopmentEngine().apply(
        profile,
        assessment(20_000, {DevelopmentDomain.FACTUAL_KNOWLEDGE: 20_000}),
    )
    assert profile.stage == DevelopmentStage.NEWBORN


def test_balanced_requirements_unlock_early_childhood() -> None:
    profile = DevelopmentProfile()
    DevelopmentEngine().apply(
        profile,
        assessment(
            100,
            {
                DevelopmentDomain.LANGUAGE: 60,
                DevelopmentDomain.CAUSAL_REASONING: 40,
            },
        ),
    )
    assert profile.stage == DevelopmentStage.EARLY_CHILDHOOD
