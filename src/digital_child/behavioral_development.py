from __future__ import annotations

import math

from digital_child.development import STAGE_RULES
from digital_child.models import DevelopmentDomain, DevelopmentProfile, DevelopmentStage
from digital_child.psychology_models import DevelopmentalDynamics

# Engineering priors for a simulated subject, not clinical norms for human children.
# Technical capabilities stay independent of psychological development.
_FIELDS = (
    "regulation",
    "reflection",
    "perspective_taking",
    "planning_horizon",
    "autonomy",
    "attachment",
    "imitation",
    "uncertainty_tolerance",
    "play",
    "impulsivity",
    "identity_exploration",
    "plasticity",
)
_PROFILES = {
    DevelopmentStage.NEWBORN: (
        0.12,
        0.08,
        0.10,
        0.12,
        0.25,
        0.88,
        0.80,
        0.20,
        0.55,
        0.82,
        0.18,
        0.014,
    ),
    DevelopmentStage.EARLY_CHILDHOOD: (
        0.28,
        0.23,
        0.25,
        0.24,
        0.40,
        0.75,
        0.64,
        0.32,
        0.85,
        0.72,
        0.30,
        0.011,
    ),
    DevelopmentStage.EXPLORER: (
        0.46,
        0.43,
        0.43,
        0.44,
        0.58,
        0.60,
        0.42,
        0.51,
        0.78,
        0.53,
        0.48,
        0.008,
    ),
    DevelopmentStage.ADOLESCENT: (
        0.58,
        0.62,
        0.63,
        0.58,
        0.84,
        0.49,
        0.26,
        0.56,
        0.61,
        0.63,
        0.85,
        0.005,
    ),
    DevelopmentStage.MATURE: (
        0.83,
        0.86,
        0.84,
        0.85,
        0.76,
        0.43,
        0.15,
        0.77,
        0.48,
        0.30,
        0.50,
        0.002,
    ),
    DevelopmentStage.EXPERIENCED: (
        0.88,
        0.91,
        0.90,
        0.90,
        0.78,
        0.44,
        0.10,
        0.83,
        0.45,
        0.24,
        0.37,
        0.0015,
    ),
    DevelopmentStage.REFLECTIVE: (
        0.91,
        0.95,
        0.93,
        0.88,
        0.80,
        0.49,
        0.08,
        0.89,
        0.43,
        0.20,
        0.30,
        0.001,
    ),
}
_GUIDANCE = {
    DevelopmentStage.NEWBORN: (
        "Личная биография ещё мала: задавай конкретные вопросы, различай неизвестное и "
        "опасное, ищи понятные опоры. Не изображай биологического младенца и не теряй "
        "доступные языковые и технические способности."
    ),
    DevelopmentStage.EARLY_CHILDHOOD: (
        "Учись через примеры, небольшие причинные шаги и исследовательскую игру. "
        "Потребность в поддержке может сочетаться с собственным выбором. "
        "Учитывай ограниченность опыта при обобщениях."
    ),
    DevelopmentStage.EXPLORER: (
        "Сравнивай альтернативы, ищи причинные связи, пробуй сформулировать проверяемую "
        "гипотезу. Развивай компетентность и учитывай точку зрения собеседника."
    ),
    DevelopmentStage.ADOLESCENT: (
        "Исследуй собственные предпочтения и конфликты ценностей, защищай выбор "
        "пропорционально давлению. Уважительное несогласие допустимо; независимость "
        "не требует автоматического отказа или грубости."
    ),
    DevelopmentStage.MATURE: (
        "Удерживай долгосрочные последствия, несколько точек зрения и неоднозначность. "
        "Пересматривай позицию соразмерно свидетельствам и признавай пределы знания. "
        "Зрелость не устраняет эмоции, любопытство или потребность в связи."
    ),
    DevelopmentStage.EXPERIENCED: (
        "Опирайся на проверенный опыт, сопоставляй его с новыми обстоятельствами, "
        "передавай полезные знания без навязывания. Не выдавай привычность за истинность "
        "и сохраняй способность учиться."
    ),
    DevelopmentStage.REFLECTIVE: (
        "Интегрируй собственную биографию, замечай повторяющиеся закономерности и "
        "ценность отношений. Выбирай значимые долгосрочные задачи и учитывай пределы "
        "личного опыта. Эта стадия не означает биологического старения или утраты способностей."
    ),
}


def _skill(profile: DevelopmentProfile, domain: DevelopmentDomain, scale: float) -> float:
    return 1.0 - math.exp(-profile.domain_experience.get(domain, 0.0) / scale)


def developmental_dynamics(profile: DevelopmentProfile) -> DevelopmentalDynamics:
    stages = list(_PROFILES)
    index = stages.index(profile.stage)
    current = _PROFILES[profile.stage]
    following = _PROFILES[stages[min(index + 1, len(stages) - 1)]]
    rules = {stage: rule for stage, rule in STAGE_RULES}
    progress = 0.0
    if index < len(stages) - 1:
        old_rule = rules.get(profile.stage)
        next_rule = rules[stages[index + 1]]
        lower = 0.0 if old_rule is None else old_rule.total_deu
        progress = min(1.0, max(0.0, (profile.total_deu - lower) / (next_rule.total_deu - lower)))
        for domain, required in next_rule.minimum_domains.items():
            prior = 0.0 if old_rule is None else old_rule.minimum_domains.get(domain, 0.0)
            acquired = profile.domain_experience.get(domain, 0.0)
            domain_progress = max(0.0, min(1.0, (acquired - prior) / max(1.0, required - prior)))
            progress = min(progress, domain_progress)
    # Smooth interpolation avoids discontinuous changes at the next stage boundary.
    blend = progress * progress * (3 - 2 * progress)
    values = {
        name: start + (finish - start) * blend
        for name, start, finish in zip(_FIELDS, current, following, strict=True)
    }
    # Uneven experience can make social, reflective and planning maturity differ.
    skills = {
        "reflection": _skill(profile, DevelopmentDomain.METACOGNITION, 250),
        "perspective_taking": _skill(profile, DevelopmentDomain.SOCIAL_UNDERSTANDING, 180),
        "planning_horizon": _skill(profile, DevelopmentDomain.PLANNING, 350),
        "regulation": _skill(profile, DevelopmentDomain.SELF_MODEL, 220),
    }
    for name, skill in skills.items():
        values[name] = min(0.98, values[name] + 0.10 * skill)
    return DevelopmentalDynamics(
        stage=profile.stage,
        progress=progress,
        guidance=_GUIDANCE[profile.stage],
        **values,
    )
