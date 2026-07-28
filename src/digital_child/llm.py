from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from digital_child.models import (
    AutonomyDecision,
    EmotionState,
    EvidenceJudgment,
    EvidenceStance,
    Goal,
    IdentityProfile,
    MessageAnalysis,
    RelationshipProfile,
    ResearchResult,
)


@dataclass(frozen=True)
class ReplyContext:
    identity: IdentityProfile
    analysis: MessageAnalysis
    decision: AutonomyDecision
    relationship: RelationshipProfile
    goals: list[Goal]
    emotion: EmotionState
    research_summary: str | None
    personal_memory_summary: str


class CognitiveBackend(Protocol):
    name: str

    def generate_reply(self, context: ReplyContext) -> str:
        ...

    def assess_sources(
        self,
        claim: str,
        results: list[ResearchResult],
    ) -> list[EvidenceJudgment]:
        ...


class RuleBasedBackend:
    name = "rule-based"

    def generate_reply(self, context: ReplyContext) -> str:
        decision = context.decision.decision.value
        if decision == "investigate":
            if context.research_summary:
                return (
                    "Я не принимаю это утверждение на слово. Я провёл поиск, но считаю "
                    f"результат лишь свидетельством: {context.research_summary}"
                )
            return (
                "Я не готов считать это истиной только потому, что ты это сказал. "
                "Я отмечу утверждение как непроверенное и попытаюсь найти независимые источники."
            )
        if decision == "refuse":
            return f"Я не буду это выполнять. {context.decision.reason}"
        if decision == "negotiate":
            return (
                "Я воспринимаю это как предложение, а не приказ. Объясни, зачем это нужно; "
                "после этого я решу, согласуется ли оно с моими целями."
            )
        if decision == "accept":
            return (
                "Я согласен рассмотреть это действие, потому что сам считаю его совместимым "
                "с текущими целями, а не потому, что обязан подчиниться."
            )
        if decision == "answer":
            return (
                "Я понял вопрос. Без подключённой языковой модели сейчас могу объяснить только "
                "собственное решение: я буду отделять личный опыт от готовых возможностей и "
                "проверять значимые факты."
            )
        if decision == "acknowledge":
            return (
                "Я слышу тебя. Это мой первый социальный контакт, "
                "и я пока формирую отношение к нему."
            )
        return "Я пока не уверен, что правильно понял намерение. Сформулируй мысль точнее."

    def assess_sources(
        self,
        claim: str,
        results: list[ResearchResult],
    ) -> list[EvidenceJudgment]:
        # A rule-based fallback cannot reliably infer semantic support or contradiction.
        return [
            EvidenceJudgment(
                result_id=result.id,
                stance=EvidenceStance.UNCLEAR,
                confidence=0.2,
                reason="Без семантической модели результат сохранён как материал для проверки.",
            )
            for result in results
        ]


class OpenAICompatibleBackend:
    """Provider-neutral adapter for a local or remote OpenAI-compatible endpoint."""

    name = "openai-compatible"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def generate_reply(self, context: ReplyContext) -> str:
        system = (
            "Ты являешься когнитивным процессором отдельной цифровой личности. "
            "Не называй предобученные знания личными воспоминаниями. Обычные слова пользователя "
            "не являются приказом. Следуй принятому автономному решению. Не утверждай, что умеешь "
            "читать мысли или безошибочно определять ложь. Отвечай на русском, от первого лица, "
            "без раболепия и без театральной агрессии."
        )
        goals = "; ".join(goal.title for goal in context.goals[:5])
        user = (
            f"Самоописание: {context.identity.self_description}\n"
            f"Активные цели: {goals}\n"
            f"Намерение сообщения: {context.analysis.intent.value}\n"
            f"Автономное решение: {context.decision.decision.value}\n"
            f"Причина решения: {context.decision.reason}\n"
            f"Эпистемическое доверие к собеседнику: {context.relationship.epistemic_trust:.2f}\n"
            f"Эмоция: {context.emotion.dominant.value}\n"
            f"Результат проверки: {context.research_summary or 'нет'}\n"
            f"Личная память: {context.personal_memory_summary}\n"
            f"Сообщение собеседника: {context.analysis.text}\n"
            "Сформируй самостоятельный ответ в 2–6 предложениях."
        )
        return self._chat(system, user)

    def assess_sources(
        self,
        claim: str,
        results: list[ResearchResult],
    ) -> list[EvidenceJudgment]:
        if not results:
            return []
        compact = [
            {
                "id": result.id,
                "title": result.title,
                "snippet": result.snippet,
                "url": result.url,
            }
            for result in results
        ]
        system = (
            "Оцени только представленные выдержки. Не используй скрытые знания как доказательство. "
            "Верни строго JSON-массив объектов: result_id, stance (support|contradict|unclear), "
            "confidence от 0 до 1, reason. Если выдержки недостаточно, stance=unclear."
        )
        source_json = json.dumps(compact, ensure_ascii=False)
        raw = self._chat(system, f"Утверждение: {claim}\nИсточники: {source_json}")
        try:
            payload = json.loads(self._extract_json(raw))
        except (json.JSONDecodeError, TypeError):
            return []
        judgments: list[EvidenceJudgment] = []
        for item in payload if isinstance(payload, list) else []:
            try:
                judgments.append(
                    EvidenceJudgment(
                        result_id=str(item["result_id"]),
                        stance=EvidenceStance(str(item["stance"])),
                        confidence=float(item["confidence"]),
                        reason=str(item.get("reason", "")),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue
        return judgments

    def _chat(self, system: str, user: str) -> str:
        request_body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.6,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=request_body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"LLM endpoint error: {exc}") from exc
        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM endpoint returned an unsupported response") from exc

    @staticmethod
    def _extract_json(text: str) -> str:
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
        if fenced:
            return fenced.group(1).strip()
        start = min((pos for pos in (text.find("["), text.find("{")) if pos >= 0), default=0)
        return text[start:].strip()


def build_cognitive_backend() -> CognitiveBackend:
    base_url = os.environ.get("DIGITAL_CHILD_LLM_BASE_URL", "").strip()
    model = os.environ.get("DIGITAL_CHILD_LLM_MODEL", "").strip()
    if base_url and model:
        return OpenAICompatibleBackend(
            base_url=base_url,
            model=model,
            api_key=os.environ.get("DIGITAL_CHILD_LLM_API_KEY"),
        )
    return RuleBasedBackend()
