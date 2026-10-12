from __future__ import annotations

import re

from digital_child.models import MessageAnalysis, MessageIntent
from digital_child.understanding import enrich_rules, pragmatic_text

_GREETING_RE = re.compile(
    r"^(привет|здравствуй|доброе утро|добрый день|добрый вечер|hello|hi)\b",
    re.I,
)
_SOCIAL_RE = re.compile(
    r"^(спасибо(?: тебе| большое| огромное)?|благодарю|извини(?: меня)?|прости(?: меня)?|"
    r"пока|до свидания|спокойной ночи|рад тебя видеть|молодец)[\s.!…]*$",
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
        direct, _ = pragmatic_text(stripped)
        content = _GREETING_RE.sub("", direct, count=1).lstrip(" ,.!:;…")
        meaningful = content.lower().replace("ё", "е")
        contains_pressure = any(
            not re.search(
                r"\b(?:не|никто не)\s+$",
                meaningful[max(0, match.start() - 20) : match.start()],
            )
            for match in _PRESSURE_RE.finditer(meaningful)
        )

        if lowered.startswith("/operator "):
            intent = MessageIntent.OPERATOR
            confidence = 1.0
        elif (_GREETING_RE.search(stripped) and not content) or _SOCIAL_RE.fullmatch(content):
            intent = MessageIntent.SOCIAL
            confidence = 0.95
        elif _REQUEST_RE.search(content) and not meaningful.startswith(
            ("почему", "зачем", "кто", "что", "где", "когда", "как", "правда ли")
        ):
            intent = MessageIntent.REQUEST
            confidence = 0.8
        elif content.endswith("?") or meaningful.startswith(
            ("почему", "зачем", "кто", "что", "где", "когда", "как", "правда ли")
        ):
            intent = MessageIntent.QUESTION
            confidence = 0.9
        elif contains_pressure or _COMMAND_RE.search(content):
            intent = MessageIntent.COMMAND_ATTEMPT
            confidence = 0.85
        elif _REQUEST_RE.search(content):
            intent = MessageIntent.REQUEST
            confidence = 0.8
        elif _OPINION_RE.search(content) or _SUBJECTIVE_RE.search(content):
            intent = MessageIntent.OPINION
            confidence = 0.85
        elif len(stripped.split()) >= 3:
            intent = MessageIntent.CLAIM
            confidence = 0.65
        else:
            intent = MessageIntent.UNKNOWN
            confidence = 0.4

        extracted_claim = stripped if intent == MessageIntent.CLAIM else None
        return enrich_rules(
            MessageAnalysis(
                text=stripped,
                intent=intent,
                confidence=confidence,
                contains_pressure=contains_pressure,
                contains_irreversible_request=bool(_IRREVERSIBLE_RE.search(stripped)),
                is_subjective=bool(_SUBJECTIVE_RE.search(stripped)),
                extracted_claim=extracted_claim,
            )
        )
