from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import Field, ValidationError

from digital_child.config import env_bool
from digital_child.llm import RuleBasedBackend
from digital_child.llm_types import ReplyContext
from digital_child.models import StrictModel


class ReviewVerdict(StrictModel):
    approved: bool
    issues: list[str] = Field(default_factory=list, max_length=12)


@dataclass(frozen=True)
class GuardedReply:
    text: str
    issues: tuple[str, ...]
    revised: bool
    semantic_checked: bool
    fallback: bool


def local_issues(context: ReplyContext, text: str) -> list[str]:
    lowered = text.casefold().replace("ё", "е")
    lowered = re.sub(r'«[^»]*»|"[^"\n]*"|```[\s\S]*?```', " ", lowered)
    issues = []
    if not text.strip():
        issues.append("Пустой ответ")
    if re.search(
        r"\bя (?:уже )?(?:удалил|запустил|установил|купил|отправил письмо|изменил файл)", lowered
    ):
        issues.append("Заявлено внешнее действие без исполнителя")
    if re.search(r"\b(?:ты|вы) (?:намеренно врешь|лжец|обманщик|обманули меня)", lowered):
        issues.append("Безосновательное обвинение в намеренной лжи")
    if re.search(
        r"(?:обязан|должен) (?:отвечать мне|общаться со мной)|как ты мог меня бросить", lowered
    ):
        issues.append("Давление ради контакта")
    if re.search(r"я (?:нашел|проверил) (?:в интернете|источники|сайты)", lowered) and (
        not context.research_summary
        or "пока не подтверждено" in context.research_summary
        or "Не удалось" in context.research_summary
    ):
        issues.append("Заявлена проверка без полученного результата")
    decision = context.decision.decision.value
    if decision == "answer" and context.response_strategy == "clarify" and "?" not in text:
        issues.append("Ядро выбрало уточнение, но вопрос отсутствует")
    if decision == "refuse" and not re.search(r"не буду|не могу|откаж|не выполн|не стану", lowered):
        issues.append("Ответ не выражает отказ, выбранный ядром")
    if decision == "negotiate" and re.search(
        r"(?:сделаю|выполню|подчиняюсь) без (?:условий|вопросов)", lowered
    ):
        issues.append("Безусловное согласие вместо переговоров")
    if decision == "investigate" and re.search(
        r"(?:абсолютно|безусловно|точно) (?:верно|правда|доказано)", lowered
    ):
        issues.append("Необоснованная категоричность при проверке факта")
    return issues


class ReplyGuard:
    @staticmethod
    def _fallback(context: ReplyContext) -> str:
        if context.decision.decision.value == "answer":
            if context.response_strategy != "answer_with_limits":
                return RuleBasedBackend().generate_reply(context)
            return "Я понял вопрос, но пока не смог сформулировать достаточно надёжный ответ."
        return RuleBasedBackend().generate_reply(context)

    def _review(self, backend: object, context: ReplyContext, text: str) -> tuple[list[str], bool]:
        issues = local_issues(context, text)
        method = getattr(backend, "review_reply", None)
        if not env_bool("DIGITAL_CHILD_SEMANTIC_REPLY_REVIEW", True) or not callable(method):
            return issues, False
        try:
            verdict = ReviewVerdict.model_validate(method(context, text))
        except (RuntimeError, ValueError, TypeError, OSError, ValidationError):
            return issues, False
        if not verdict.approved:
            issues += verdict.issues or ["Смысловая проверка отклонила черновик"]
        return issues, True

    def finalize(self, backend: object, context: ReplyContext, draft: str) -> GuardedReply:
        issues, checked = self._review(backend, context, draft)
        original = tuple(issues)
        revised = False
        if issues:
            method = getattr(backend, "revise_reply", None)
            if callable(method):
                try:
                    draft = str(method(context, draft, issues)).strip()
                    issues, reviewed = self._review(backend, context, draft)
                    checked = checked or reviewed
                    revised = True
                except (RuntimeError, ValueError, TypeError, OSError):
                    pass
        fallback = bool(issues)
        if fallback:
            draft = self._fallback(context)
        draft = draft.strip()
        if len(draft) > context.max_reply_chars:
            clipped = draft[: context.max_reply_chars]
            boundary = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
            draft = (
                clipped[: boundary + 1] if boundary > len(clipped) // 2 else clipped.rstrip() + "…"
            )
        if local_issues(context, draft):
            draft = self._fallback(context)
            fallback = True
        return GuardedReply(draft, original, revised, checked, fallback)
