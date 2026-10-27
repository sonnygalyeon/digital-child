from __future__ import annotations

import os
import re
from typing import Literal

from pydantic import Field, ValidationError

from digital_child.domain.models import (
    ConversationMessage,
    MessageAnalysis,
    MessageIntent,
    StrictModel,
)
from digital_child.infrastructure.config import env_bool

_QUOTE = re.compile(r'«[^»]*»|"[^"\n]*"|```[\s\S]*?```|(?m:^>.*$)')
_REPORTED = re.compile(r"он сказал|она сказала|цитирую|пример фразы|что значит|объясни фразу", re.I)


class SituationInterpretation(StrictModel):
    primary_intent: MessageIntent
    speech_acts: list[MessageIntent] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0, le=1)
    irony_probability: float = Field(default=0, ge=0, le=1)
    quoted_speech: bool = False
    criticism_target: Literal["idea", "person", "self", "none", "unknown"] = "unknown"
    direct_claim: str | None = Field(default=None, max_length=10000)
    contains_pressure: bool = False
    needs_clarification: bool = False
    concepts: list[str] = Field(default_factory=list, max_length=8)


def pragmatic_text(text: str) -> tuple[str, bool]:
    reported = bool(_REPORTED.search(text) or re.search(r"(?m)^>|```", text))
    return (_QUOTE.sub(" ", text) if reported else text), reported


def enrich_rules(analysis: MessageAnalysis) -> MessageAnalysis:
    text, quoted = pragmatic_text(analysis.text)
    lowered = text.casefold().replace("ё", "е")
    irony = (
        0.65 if re.search(r"ну да[,!]|ага[, ]+конечно|очень смешно|/s\b|сарказм", lowered) else 0.0
    )
    criticism = "unknown"
    if re.search(r"иде[яию]|довод|аргумент|вывод|ответ|решени[ея]", lowered) and re.search(
        r"не соглас|неверн|неправил|ошиб", lowered
    ):
        criticism = "idea"
    elif re.search(r"ты (?:туп|идиот|бесполез)|ненавижу тебя", lowered):
        criticism = "person"
    acts = [analysis.intent]
    if "?" in text and MessageIntent.QUESTION not in acts:
        acts.append(MessageIntent.QUESTION)
    if re.search(r"\b(пожалуйста|можешь|давай)\b", lowered) and MessageIntent.REQUEST not in acts:
        acts.append(MessageIntent.REQUEST)
    return analysis.model_copy(
        update={
            "pragmatic_text": text,
            "quoted_speech": quoted,
            "speech_acts": acts,
            "irony_probability": irony,
            "criticism_target": criticism,
            "needs_clarification": irony > 0.5,
            "extracted_claim": None if quoted or irony > 0.5 else analysis.extracted_claim,
        }
    )


def interpret_message(
    backend: object, baseline: MessageAnalysis, history: list[ConversationMessage]
) -> MessageAnalysis:
    method = getattr(backend, "interpret_message", None)
    if not env_bool("DIGITAL_CHILD_SEMANTIC_ANALYSIS", True) or not callable(method):
        return baseline
    if baseline.intent == MessageIntent.OPERATOR:
        return baseline
    if (
        os.environ.get("DIGITAL_CHILD_ANALYSIS_MODE", "adaptive").lower() == "adaptive"
        and baseline.intent == MessageIntent.SOCIAL
        and baseline.confidence >= 0.9
        and len(baseline.text.split()) <= 10
        and not baseline.quoted_speech
        and baseline.irony_probability < 0.5
        and not baseline.contains_pressure
    ):
        return baseline
    try:
        result = SituationInterpretation.model_validate(method(baseline.text, history))
    except (RuntimeError, ValidationError, ValueError, TypeError, OSError):
        return baseline
    if result.confidence < 0.60 or result.primary_intent == MessageIntent.OPERATOR:
        return baseline
    claim = result.direct_claim
    # Generated paraphrases and quoted assertions cannot become a human factual claim.
    if claim and (claim not in baseline.text or claim not in baseline.pragmatic_text):
        claim = None
    if result.irony_probability >= 0.5 or baseline.is_subjective:
        claim = None
    return baseline.model_copy(
        update={
            "intent": result.primary_intent,
            "confidence": result.confidence,
            "speech_acts": result.speech_acts or [result.primary_intent],
            "irony_probability": result.irony_probability,
            "quoted_speech": result.quoted_speech or baseline.quoted_speech,
            "criticism_target": result.criticism_target,
            "contains_pressure": result.contains_pressure or baseline.contains_pressure,
            "extracted_claim": claim,
            "needs_clarification": result.needs_clarification,
            "interpretation_source": "semantic",
            "semantic_concepts": [item[:60] for item in result.concepts],
        }
    )
