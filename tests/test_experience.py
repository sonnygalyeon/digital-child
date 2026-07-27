from digital_child.experience import ExperienceEngine
from digital_child.models import DevelopmentDomain, Observation


def test_experience_is_distributed_between_domains() -> None:
    observation = Observation(
        content="A causes B",
        raw_units=100,
        novelty=1.0,
        attention=1.0,
        comprehension=1.0,
        reliability=1.0,
        integration=1.0,
        practical_confirmation=1.0,
        domains={
            DevelopmentDomain.CAUSAL_REASONING: 3,
            DevelopmentDomain.FACTUAL_KNOWLEDGE: 1,
        },
    )

    result = ExperienceEngine().assess(observation)

    assert result.effective_units == 100
    assert result.domain_units[DevelopmentDomain.CAUSAL_REASONING] == 75
    assert result.domain_units[DevelopmentDomain.FACTUAL_KNOWLEDGE] == 25


def test_missing_confirmation_does_not_zero_experience() -> None:
    observation = Observation(
        content="Unconfirmed explanation",
        raw_units=10,
        novelty=1.0,
        attention=1.0,
        comprehension=1.0,
        reliability=1.0,
        integration=1.0,
        practical_confirmation=0.0,
    )

    result = ExperienceEngine().assess(observation)

    assert result.effective_units == 5
