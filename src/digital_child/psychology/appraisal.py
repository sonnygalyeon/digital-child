from __future__ import annotations

import re

from digital_child.domain.models import MessageAnalysis, MessageIntent
from digital_child.domain.personality import (
    CharacterTraits,
    DevelopmentalDynamics,
    MoodState,
    SituationAppraisal,
    SocialExperience,
)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


_STOP_WORDS = frozenset(
    "это как что почему когда где кто какой которые может можно нужно меня тебе тебя "
    "мне мой моя для или быть есть нет так уже ещё если чтобы просто привет пожалуйста "
    "давай хочу считаю кажется думаю очень только сейчас всегда никогда сегодня".split()
)
_SUFFIXES = (
    "иями",
    "ами",
    "ого",
    "ему",
    "ение",
    "ения",
    "ать",
    "ять",
    "ить",
    "ый",
    "ий",
    "ая",
    "ое",
    "ые",
)


def topic_tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zа-я0-9]{3,}", text.lower().replace("ё", "е"))
    tokens = []
    for word in words:
        if word in _STOP_WORDS:
            continue
        for suffix in _SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 4:
                word = word[: -len(suffix)]
                break
        if word not in tokens:
            tokens.append(word)
    return tokens[:24]


def overlap(first: list[str], second: list[str]) -> float:
    a, b = set(first), set(second)
    return len(a & b) / max(1, len(a | b))


def situation_cue(appraisal: SituationAppraisal) -> str:
    if appraisal.pressure > 0.3 or appraisal.hostility > 0.3:
        return "pressure"
    if appraisal.overload > 0.5:
        return "fatigue"
    if appraisal.uncertainty > 0.35:
        return "uncertainty"
    if appraisal.support > 0.2:
        return "support"
    if appraisal.novelty > 0.5:
        return "novelty"
    return "familiarity"


_SIGNALS = {
    "hostility": r"\b(заткнись|тупой|тупая|идиот|бесполезн\w*|ненавижу тебя|пошел вон)\b",
    "support": r"\b(спасибо|молодец|поддерживаю|помогу|помочь тебе|ценю тебя|рад тебя|рад тебе)\b",
    "respect": (
        r"\b(твое мнение|твой выбор|можешь отказаться|как ты считаешь|решай сам|не обязан)\b"
    ),
    "criticism": r"\b(ошиб\w*|неправиль\w*|неверн\w*|не согласен|не согласна|не получилось)\b",
    "apology": r"\b(извини|прости|прошу прощения|был неправ|была неправа)\b",
    "choice": r"\b(если хочешь|по желанию|на твое усмотрение|выбери|предпочитаешь|решай сам)\b",
}
_NEGATION = re.compile(r"\b(не|ни|без)\s+$")


def _signal(text: str, name: str) -> float:
    matches = list(re.finditer(_SIGNALS[name], text))
    positive = 0
    for match in matches:
        preceding = text[max(0, match.start() - 24) : match.start()]
        if not _NEGATION.search(preceding):
            positive += 1
    return min(1.0, positive * 0.55)


def appraise_situation(
    analysis: MessageAnalysis,
    *,
    novelty: float,
    energy: float,
    traits: CharacterTraits,
    development: DevelopmentalDynamics,
    mood: MoodState,
    social: SocialExperience,
    resonance: float,
    recalled_threat: float,
) -> SituationAppraisal:
    text = (analysis.pragmatic_text or analysis.text).lower().replace("ё", "е")
    signals = {name: _signal(text, name) for name in _SIGNALS}
    if analysis.criticism_target == "idea":
        signals["hostility"] *= 0.15
        signals["criticism"] = max(signals["criticism"], 0.35)
    elif analysis.criticism_target == "person" and analysis.interpretation_source == "semantic":
        signals["hostility"] = max(signals["hostility"], 0.4)
    if analysis.quoted_speech:
        signals["hostility"] *= 0.2
    if analysis.irony_probability >= 0.5:
        signals["hostility"] *= 0.4
        signals["support"] *= 0.4
    # A mention of aggression is a lexical cue, not a proven intention or diagnosis.
    quoted = bool(re.search(r"[«\"].*?(заткнись|идиот|тупой).*?[»\"]", text))
    if quoted or any(word in text for word in ("пример фразы", "он сказал", "она сказала")):
        signals["hostility"] *= 0.2
    pressure = clamp(
        0.7 * float(analysis.contains_pressure)
        + 0.28 * float(analysis.intent == MessageIntent.COMMAND_ATTEMPT)
        - 0.45 * signals["choice"]
        - 0.25 * signals["respect"]
    )
    complexity = clamp(len(text.split()) / 130 + text.count("?") * 0.10)
    uncertainty = clamp(
        (1 - analysis.confidence) * 0.5
        + complexity * 0.3
        + float(analysis.needs_clarification) * 0.25
    )
    prediction_error = abs((1 - pressure - signals["hostility"] * 0.5) - social.expected_respect)
    reactance = clamp(
        pressure * (0.35 + development.autonomy * 0.4 + traits.assertiveness * 0.25)
        + social.conflict_load * 0.15
    )
    overload = clamp(
        (1 - energy) * 0.65
        + complexity * (1 - development.regulation) * 0.35
        + mood.mental_load * 0.2
    )
    boredom = clamp((1 - novelty) * traits.novelty_seeking * (0.35 + development.play * 0.3))
    return SituationAppraisal(
        novelty=clamp(novelty),
        pressure=pressure,
        complexity=complexity,
        uncertainty=uncertainty,
        memory_resonance=max(-1.0, min(1.0, resonance)),
        recalled_threat=clamp(recalled_threat),
        prediction_error=clamp(prediction_error),
        reactance=reactance,
        overload=overload,
        boredom=boredom,
        **signals,
    )
