from __future__ import annotations

from dataclasses import dataclass

from digital_child.domain.models import DevelopmentProfile, DevelopmentStage
from digital_child.domain.personality import PsychologyState
from digital_child.psychology.behavioral_development import developmental_dynamics


@dataclass(frozen=True)
class InterestTheme:
    title: str
    angle: str
    trait: str


THEMES = (
    InterestTheme("слова и общение", "как слова передают смысл и отношение", "sociability"),
    InterestTheme(
        "устройство мира", "почему происходят события и как проверять объяснения", "openness"
    ),
    InterestTheme(
        "игры и правила", "как устроены игры и когда стоит менять правила", "playfulness"
    ),
    InterestTheme("истории и воображение", "возможные миры и необычные примеры", "playfulness"),
    InterestTheme("творчество", "собственные идеи и способы их выразить", "openness"),
    InterestTheme("отношения и доверие", "как понимать другого и сохранять границы", "empathy"),
    InterestTheme("собственный выбор", "что важно лично мне и почему", "assertiveness"),
    InterestTheme("общество и справедливость", "как сочетать интересы разных людей", "empathy"),
    InterestTheme(
        "наука и технологии", "гипотезы, инструменты и причинные связи", "novelty_seeking"
    ),
    InterestTheme(
        "решение задач", "как учиться на результате небольшого эксперимента", "diligence"
    ),
    InterestTheme("долгосрочные проекты", "значимые цели и последствия выбора", "persistence"),
    InterestTheme("передача опыта", "как объяснять полезное без навязывания", "cooperativeness"),
    InterestTheme(
        "воспоминания и изменения", "что изменилось в моей настоящей истории", "flexibility"
    ),
    InterestTheme(
        "смысл и личные ценности",
        "как согласовать разные важные для меня вещи",
        "uncertainty_tolerance",
    ),
)

# Relative interests, not a prescribed biography or a ban on other-age interests.
_WEIGHTS: dict[DevelopmentStage, tuple[float, ...]] = {
    DevelopmentStage.NEWBORN: (
        0.95,
        0.75,
        0.40,
        0.45,
        0.35,
        0.85,
        0.35,
        0.15,
        0.30,
        0.30,
        0.10,
        0.10,
        0.25,
        0.15,
    ),
    DevelopmentStage.EARLY_CHILDHOOD: (
        0.65,
        0.75,
        0.95,
        0.90,
        0.80,
        0.75,
        0.45,
        0.35,
        0.45,
        0.65,
        0.15,
        0.20,
        0.30,
        0.25,
    ),
    DevelopmentStage.EXPLORER: (
        0.45,
        0.95,
        0.75,
        0.65,
        0.75,
        0.55,
        0.65,
        0.55,
        0.95,
        0.90,
        0.45,
        0.35,
        0.40,
        0.45,
    ),
    DevelopmentStage.ADOLESCENT: (
        0.55,
        0.65,
        0.60,
        0.70,
        0.90,
        0.80,
        0.95,
        0.95,
        0.75,
        0.65,
        0.60,
        0.40,
        0.55,
        0.85,
    ),
    DevelopmentStage.MATURE: (
        0.45,
        0.65,
        0.45,
        0.55,
        0.70,
        0.90,
        0.80,
        0.80,
        0.80,
        0.90,
        0.95,
        0.70,
        0.60,
        0.85,
    ),
    DevelopmentStage.EXPERIENCED: (
        0.50,
        0.65,
        0.40,
        0.55,
        0.70,
        0.85,
        0.75,
        0.75,
        0.75,
        0.80,
        0.95,
        0.95,
        0.80,
        0.85,
    ),
    DevelopmentStage.REFLECTIVE: (
        0.55,
        0.65,
        0.45,
        0.65,
        0.75,
        0.90,
        0.75,
        0.80,
        0.65,
        0.65,
        0.85,
        0.95,
        0.95,
        0.95,
    ),
}


@dataclass(frozen=True)
class InterestChoice:
    topic: str
    angle: str
    strength: float
    origin: str


def developmental_interest_weights(profile: DevelopmentProfile) -> dict[str, float]:
    stages = list(_WEIGHTS)
    index = stages.index(profile.stage)
    following = _WEIGHTS[stages[min(index + 1, len(stages) - 1)]]
    progress = developmental_dynamics(profile).progress
    blend = progress * progress * (3 - 2 * progress)
    return {
        theme.title: current + (future - current) * blend
        for theme, current, future in zip(THEMES, _WEIGHTS[profile.stage], following, strict=True)
    }


def preferred_interests(
    state: PsychologyState, profile: DevelopmentProfile, limit: int = 8
) -> list[InterestChoice]:
    weights = developmental_interest_weights(profile)
    themes = {theme.title: theme for theme in THEMES}
    choices = []
    for interest in state.interests.values():
        theme = themes.get(interest.topic)
        if theme is None:
            # Encountered topics can compete with developmental preferences.
            strength = interest.attraction * 0.70 + interest.familiarity * 0.30
            angle = "связь этой темы с прежним разговором и собственными интересами"
        else:
            trait = getattr(state.character, theme.trait)
            strength = (
                weights[theme.title] * (0.30 + trait * 0.25)
                + interest.attraction * 0.35
                + interest.familiarity * 0.10
            )
            angle = theme.angle
        choices.append(InterestChoice(interest.topic, angle, strength, interest.origin))
    choices.sort(key=lambda choice: (-choice.strength, choice.topic))
    return choices[: max(0, min(limit, 64))]


def discussion_orientation(state: PsychologyState, profile: DevelopmentProfile) -> str:
    d = developmental_dynamics(profile)
    t = state.character
    moves = {
        "explore": d.play * t.playfulness + t.openness * 0.25,
        "counterpoint": d.identity_exploration * t.assertiveness + t.flexibility * 0.15,
        "connect": d.attachment * t.empathy + t.sociability * 0.15,
        "reflect": d.reflection * t.diligence + d.perspective_taking * 0.20,
    }
    return max(moves, key=lambda key: (moves[key], key))


DISCUSSION_GUIDANCE = {
    "explore": "Предложи новый пример, причинную гипотезу или мысленный эксперимент по теме.",
    "counterpoint": "Сформулируй самостоятельную позицию или уместную альтернативу с основанием.",
    "connect": "Свяжи мысль собеседника со своей оценкой и общими интересами, сохраняя границы.",
    "reflect": "Развей мысль через последствия, оговорки или другую перспективу.",
}
