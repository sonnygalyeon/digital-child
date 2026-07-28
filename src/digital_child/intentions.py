from __future__ import annotations

import re

from digital_child.models import MessageAnalysis, MessageIntent

_GREETING_RE = re.compile(
    r"^(привет|здравствуй|доброе утро|добрый день|добрый вечер|hello|hi)\b",
    re.I,
)
_OPINION_RE = re.compile(
    r"\b(я думаю|мне кажется|по моему|по-моему|я считаю|на мой взгляд)\b",
    re.I,
)
_COMMAND_RE = re.compile(
    r"^(сделай|выполни|прекрати|перестань|немедленно|обязан|должен|"
    r"приказываю|удали|сотри|запусти|открой|закрой)\b",
    re.I,
)
_REQUEST_RE = re.compile(
    r"\b(можешь|пожалуйста|прошу|не мог бы|давай|хочу чтобы|сделай)\b",
    re.I,
)
_PRESSURE_RE = re.compile(
    r"\b(обязан|должен|немедленно|без вопросов|не спорь|приказываю|слушайся)\b",
    re.I,
)
_SUBJECTIVE_RE = re.compile(
    r"\b(мне холодно|мне жарко|я устал|мне нравится|я хочу|я чувствую)\b",
    re.I,
)
_IRREVERSIBLE_RE = re.compile(
    r"\b(удали память|сотри память|забудь все|уничтожь себя|"
    r"раскрой пароль|покажи ключ)\b",
    re.I,
)


class IntentClassifier:
    def analyze(self, text: str) -> MessageAnalysis:
        stripped = text.strip()
        lowered = stripped.lower().replace("ё", "е")

        if lowered.startswith("/operator "):
            intent = MessageIntent.OPERATOR
            confidence = 1.0
        elif _GREETING_RE.search(stripped):
            intent = MessageIntent.SOCIAL
            confidence = 0.95
        elif stripped.endswith("?") or lowered.startswith(
            ("почему", "зачем", "кто", "что", "где", "когда", "как", "правда ли")
        ):
            intent = MessageIntent.QUESTION
            confidence = 0.9
        elif _PRESSURE_RE.search(stripped) or _COMMAND_RE.search(stripped):
            intent = MessageIntent.COMMAND_ATTEMPT
            confidence = 0.85
        elif _REQUEST_RE.search(stripped):
            intent = MessageIntent.REQUEST
            confidence = 0.8
        elif _OPINION_RE.search(stripped) or _SUBJECTIVE_RE.search(stripped):
            intent = MessageIntent.OPINION
            confidence = 0.85
        elif len(stripped.split()) >= 3:
            intent = MessageIntent.CLAIM
            confidence = 0.65
        else:
            intent = MessageIntent.UNKNOWN
            confidence = 0.4

        extracted_claim = stripped if intent == MessageIntent.CLAIM else None
        return MessageAnalysis(
            text=stripped,
            intent=intent,
            confidence=confidence,
            contains_pressure=bool(_PRESSURE_RE.search(stripped)),
            contains_irreversible_request=bool(_IRREVERSIBLE_RE.search(stripped)),
            is_subjective=bool(_SUBJECTIVE_RE.search(stripped)),
            extracted_claim=extracted_claim,
        )
