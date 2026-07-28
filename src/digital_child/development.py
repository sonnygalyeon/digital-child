from __future__ import annotations

from dataclasses import dataclass

from digital_child.models import (
    DevelopmentDomain,
    DevelopmentProfile,
    DevelopmentStage,
    DevelopmentTransition,
    ExperienceAssessment,
)


@dataclass(frozen=True)
class StageRule:
    total_deu: float
    minimum_domains: dict[DevelopmentDomain, float]


STAGE_RULES: list[tuple[DevelopmentStage, StageRule]] = [
    (
        DevelopmentStage.MATURE,
        StageRule(
            total_deu=10_000,
            minimum_domains={
                DevelopmentDomain.PLANNING: 1_000,
                DevelopmentDomain.METACOGNITION: 800,
                DevelopmentDomain.SOCIAL_UNDERSTANDING: 500,
                DevelopmentDomain.SELF_MODEL: 500,
            },
        ),
    ),
    (
        DevelopmentStage.ADOLESCENT,
        StageRule(
            total_deu=2_000,
            minimum_domains={
                DevelopmentDomain.PLANNING: 200,
                DevelopmentDomain.SELF_MODEL: 100,
                DevelopmentDomain.METACOGNITION: 80,
            },
        ),
    ),
    (
        DevelopmentStage.EXPLORER,
        StageRule(
            total_deu=500,
            minimum_domains={
                DevelopmentDomain.LANGUAGE: 80,
                DevelopmentDomain.CAUSAL_REASONING: 50,
                DevelopmentDomain.SOCIAL_UNDERSTANDING: 30,
            },
        ),
    ),
    (
        DevelopmentStage.EARLY_CHILDHOOD,
        StageRule(
            total_deu=100,
            minimum_domains={
                DevelopmentDomain.LANGUAGE: 20,
                DevelopmentDomain.CAUSAL_REASONING: 10,
            },
        ),
    ),
]


class DevelopmentEngine:
    def apply(
        self,
        profile: DevelopmentProfile,
        assessment: ExperienceAssessment,
    ) -> DevelopmentTransition:
        old_stage = profile.stage
        profile.total_deu += assessment.effective_units

        for domain, gained in assessment.domain_units.items():
            profile.domain_experience.setdefault(domain, 0.0)
            profile.domain_experience[domain] += gained

        profile.stage = self._resolve_stage(profile)
        return DevelopmentTransition(
            old_stage=old_stage,
            new_stage=profile.stage,
            gained_deu=assessment.effective_units,
            domain_gains=assessment.domain_units,
        )

    def _resolve_stage(self, profile: DevelopmentProfile) -> DevelopmentStage:
        for stage, rule in STAGE_RULES:
            if profile.total_deu < rule.total_deu:
                continue
            if all(
                profile.domain_experience.get(domain, 0.0) >= minimum
                for domain, minimum in rule.minimum_domains.items()
            ):
                return stage
        return DevelopmentStage.NEWBORN
