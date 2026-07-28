from __future__ import annotations

from digital_child.models import DevelopmentDomain, ExperienceAssessment, Observation


class ExperienceEngine:
    """Convert an observation into measurable developmental experience."""

    def assess(self, observation: Observation) -> ExperienceAssessment:
        if observation.novelty is None:
            raise ValueError("Observation novelty must be calculated before assessment")

        confirmation_multiplier = 0.5 + 0.5 * observation.practical_confirmation
        factors = {
            "novelty": observation.novelty,
            "attention": observation.attention,
            "comprehension": observation.comprehension,
            "reliability": observation.reliability,
            "integration": observation.integration,
            "confirmation_multiplier": confirmation_multiplier,
        }

        quality = 1.0
        for value in factors.values():
            quality *= value

        effective_units = observation.raw_units * quality
        weight_sum = sum(observation.domains.values())
        domain_units: dict[DevelopmentDomain, float] = {
            domain: effective_units * weight / weight_sum
            for domain, weight in observation.domains.items()
        }

        return ExperienceAssessment(
            observation_id=observation.id,
            quality=quality,
            effective_units=effective_units,
            domain_units=domain_units,
            factor_breakdown=factors,
        )
