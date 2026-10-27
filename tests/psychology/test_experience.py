import pytest

from digital_child.domain.models import DevelopmentDomain, Observation
from digital_child.psychology.experience import ExperienceEngine


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


def test_experience_requires_calculated_novelty() -> None:
    observation = Observation(
        content="unknown",
        raw_units=1,
        novelty=None,
        attention=1,
        comprehension=1,
        reliability=1,
        integration=1,
    )
    with pytest.raises(ValueError):
        ExperienceEngine().assess(observation)
