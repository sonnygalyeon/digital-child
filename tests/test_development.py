from digital_child.development import DevelopmentEngine
from digital_child.models import (
    DevelopmentDomain,
    DevelopmentProfile,
    DevelopmentStage,
    ExperienceAssessment,
)


def make_assessment(
    total: float,
    domain_units: dict[DevelopmentDomain, float],
) -> ExperienceAssessment:
    return ExperienceAssessment(
        observation_id="test",
        quality=1.0,
        effective_units=total,
        domain_units=domain_units,
        factor_breakdown={},
    )


def test_total_experience_alone_does_not_create_adult_stage() -> None:
    profile = DevelopmentProfile()
    engine = DevelopmentEngine()

    engine.apply(
        profile,
        make_assessment(
            20_000,
            {DevelopmentDomain.FACTUAL_KNOWLEDGE: 20_000},
        ),
    )

    assert profile.stage == DevelopmentStage.NEWBORN


def test_balanced_requirements_unlock_early_childhood() -> None:
    profile = DevelopmentProfile()
    engine = DevelopmentEngine()

    engine.apply(
        profile,
        make_assessment(
            100,
            {
                DevelopmentDomain.LANGUAGE: 60,
                DevelopmentDomain.CAUSAL_REASONING: 40,
            },
        ),
    )

    assert profile.stage == DevelopmentStage.EARLY_CHILDHOOD
