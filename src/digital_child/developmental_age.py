from __future__ import annotations

from digital_child.models import DevelopmentDomain, DevelopmentProfile, DevelopmentStage


def psychological_age_equivalent(profile: DevelopmentProfile) -> float:
    """Return an interpretable age-like index driven by acquired experience, not time."""
    deu = profile.total_deu
    if deu < 100:
        return min(3.0, 3.0 * deu / 100.0)
    if deu < 500:
        return 3.0 + 5.0 * (deu - 100.0) / 400.0
    if deu < 2_000:
        return 8.0 + 7.0 * (deu - 500.0) / 1_500.0
    if deu < 10_000:
        return 15.0 + 3.0 * (deu - 2_000.0) / 8_000.0
    if deu < 40_000:
        return 18.0 + 17.0 * (deu - 10_000.0) / 30_000.0
    if deu < 100_000:
        return 35.0 + 25.0 * (deu - 40_000.0) / 60_000.0
    return min(85.0, 60.0 + 25.0 * (deu - 100_000.0) / 200_000.0)


def epistemic_vigilance_unlocked(profile: DevelopmentProfile) -> bool:
    return (
        profile.stage
        in {
            DevelopmentStage.ADOLESCENT,
            DevelopmentStage.MATURE,
            DevelopmentStage.EXPERIENCED,
            DevelopmentStage.REFLECTIVE,
        }
        and profile.domain_experience.get(DevelopmentDomain.METACOGNITION, 0.0) >= 80.0
        and profile.domain_experience.get(DevelopmentDomain.SOCIAL_UNDERSTANDING, 0.0) >= 30.0
    )
