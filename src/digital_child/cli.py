from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

from digital_child.action_plans import PlanKind
from digital_child.console import configure_utf8_console
from digital_child.developmental_age import psychological_age_equivalent
from digital_child.experiments import EXPERIMENT_KINDS, Demonstration
from digital_child.face_controller import FaceWindowController
from digital_child.models import (
    ClaimEvidenceInput,
    DevelopmentDomain,
    EvidenceStance,
    InteractionResult,
    Observation,
    SourceKind,
)
from digital_child.service import create_agent
from digital_child.terminal_chat import TerminalChatApp

if TYPE_CHECKING:
    from digital_child.agent import DigitalChildAgent


def build_caregiver_observation(
    text: str,
    attention: float,
    stance: EvidenceStance | None = None,
) -> Observation:
    claims = [] if stance is None else [ClaimEvidenceInput(claim=text, stance=stance)]
    return Observation(
        content=text,
        source_kind=SourceKind.CAREGIVER,
        raw_units=float(max(1, len(text.split()))),
        novelty=None,
        attention=attention,
        comprehension=0.65,
        reliability=0.35,
        integration=0.55,
        practical_confirmation=0.0,
        domains={
            DevelopmentDomain.LANGUAGE: 0.25,
            DevelopmentDomain.FACTUAL_KNOWLEDGE: 0.45,
            DevelopmentDomain.SOCIAL_UNDERSTANDING: 0.15,
            DevelopmentDomain.METACOGNITION: 0.15,
        },
        claims=claims,
        tags=["caregiver_testimony"],
    )


HELP_TEXT = """Команды:
  /help                         показать справку
  /state                        развитие, состояние и психологический возраст
  /diagnostics                  сводная диагностика всех подсистем
  /llm                          состояние подключения полноценной LLM
  /inference                    модели, размышление и время вызовов по задачам
  /history [N]                  сохранённая история диалога
  /identity                     самомодель и вопросы первого пробуждения
  /personality                  темперамент, характер, настроение и самомодель
  /development                  возрастная регуляция и индивидуальная зрелость
  /behavior                     оценка последней ситуации и выбор стратегии
  /habits                       сформированные привычки и ожидания результата
  /reflections                  значимые изменения и результаты исследований
  /goals [N]                    активные и предложенные цели
  /needs                        текущие внутренние потребности
  /drives                       активные внутренние импульсы
  /background                   состояние когнитивного цикла
  /budgets                      операционные бюджеты автономии
  /interests                    текущие интересы с учётом стадии и опыта
  /initiative [on|off]           самостоятельные реплики и их состояние
  /time                         источник UTC и время предыдущего запуска
  /verifications                отложенные проверки фактов и их результаты
  /experiment [balance|transfer] закрытый эксперимент; без аргумента — история
  /experiment noise|conditional|reversal  среды с шумом, контекстом и сменой правил
  /plan                         активный многошаговый план и история
  /plan start route|switchback [N]  создать план с пределом N действий (по умолчанию 12)
  /plan step [ID]                выполнить следующее действие
  /plan run [ID]                 выполнить оставшиеся шаги в пределах бюджетов
  /plan cancel [ID]              остановить план
  /plan show ID                  полный план с результатами и объяснениями шагов
  /action-outcomes               причинные эффекты наблюдаемых действий
  /memory-index [N]              состояние индекса; N — просканировать следующую порцию
  /recall ТЕКСТ                  поиск связанного опыта по смыслу
  /competence                    наблюдаемые навыки и уверенность в них
  /curriculum                    пробелы и предлагаемые эксперименты
  /teach JSON                    показать пример шага закрытой среды
  /demonstrations                гипотезы из демонстраций и результаты проверок
  /person-model                  сведения о текущем собеседнике
  /person-model correct ТЕКСТ    поправить сведения о себе
  /person-model clear ТЕКСТ      очистить сведения, сохранив новую поправку
  /regulation                    применённые стратегии саморегуляции
  /regulation feedback ID helpful|unhelpful  оценить стратегию
  /timeline [ID]                 история развития или исходные данные события
  /conflicts                    последние конфликты личных ценностей
  /biography                    главы автобиографии со ссылками на эпизоды
  /biography sources ID         исходные эпизоды главы
  /biography correct ID ТЕКСТ   сохранить поправку к главе
  /preferences                  настройки общения с текущим собеседником
  /preferences JSON             изменить настройки общения
  /feedback ТЕМА                не предлагать тему следующие 7 суток
  /events [N]                   последние внутренние события
  /pause                        приостановить внутренний цикл
  /resume                       возобновить внутренний цикл
  /tick                         выполнить один безопасный цикл вручную
  /trust                        отношение к локальному собеседнику
  /beliefs [N]                  убеждения с уверенностью и противоречиями
  /research <утверждение>       принудительно проверить утверждение в интернете
  /reports [N]                  последние отчёты интернет-проверки
  /decisions [N]                журнал автономных решений
  /memory [N]                   активные эпизодические воспоминания
  /summaries [N]                консолидированные воспоминания
  /consolidate                  запустить забывание и консолидацию
  /rest [0..1]                  восстановить энергию и внимание
  /operator reset               операторский сброс памяти с подтверждением
  /quit                         завершить программу

Обычный текст не является командой для личности. Он классифицируется как вопрос,
утверждение, мнение, просьба или попытка давления.
"""


def _parse_limit(text: str, default: int = 10) -> int | None:
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return default
    try:
        return max(1, min(int(parts[1]), 100))
    except ValueError:
        return None


class ChatCommandRouter:
    def __init__(self, agent: DigitalChildAgent) -> None:
        self.agent = agent
        self.person_id = "local-user"

    def handle(self, text: str) -> str:
        if text == "/memory-index":
            return json.dumps(
                self.agent.associative_memory.index_status(), ensure_ascii=False, indent=2
            )
        if text.startswith("/memory-index "):
            try:
                batch = int(text.split(maxsplit=1)[1])
                if not 1 <= batch <= 2000:
                    raise ValueError("Размер порции: от 1 до 2000")
                with self.agent._interaction_lock:
                    status = self.agent.associative_memory.backfill(batch)
                return json.dumps(status, ensure_ascii=False, indent=2)
            except ValueError as exc:
                return str(exc)
        if text == "/action-outcomes":
            return json.dumps(
                self.agent.repository.list_features(
                    "action_attribution", self.agent.identity.id, 20
                ),
                ensure_ascii=False,
                indent=2,
            )
        if text == "/plan":
            active_plan = self.agent.plans.active()
            return json.dumps(
                {
                    "active": None if active_plan is None else active_plan.model_dump(mode="json"),
                    "recent": [
                        item.model_dump(mode="json") for item in self.agent.plans.history(5)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        if text.startswith("/plan "):
            parts = text.split()
            try:
                if (
                    len(parts) in {3, 4}
                    and parts[1] == "start"
                    and parts[2] in {"route", "switchback"}
                ):
                    kind: PlanKind = "route" if parts[2] == "route" else "switchback"
                    return self.agent.start_plan(
                        kind, int(parts[3]) if len(parts) == 4 else 12
                    ).model_dump_json(indent=2)
                if len(parts) in {2, 3} and parts[1] in {"step", "run", "cancel"}:
                    plan_id = parts[2] if len(parts) == 3 else None
                    if parts[1] == "step":
                        return self.agent.step_plan(plan_id).model_dump_json(indent=2)
                    if parts[1] == "run":
                        return self.agent.run_plan(plan_id).model_dump_json(indent=2)
                    return self.agent.cancel_plan(plan_id).model_dump_json(indent=2)
                if len(parts) == 3 and parts[1] == "show":
                    return self.agent.plans.get(parts[2]).model_dump_json(indent=2)
                return "Используйте /plan start route|switchback [N], step, run, cancel или show ID"
            except ValueError as exc:
                return str(exc)
        if text == "/inference":
            return json.dumps(self.agent.inference_diagnostics(), ensure_ascii=False, indent=2)
        if text.startswith("/recall "):
            with self.agent._interaction_lock:
                return self.agent.associative_memory.summary(
                    self.agent.associative_memory.search(text.split(maxsplit=1)[1], self.person_id)
                )
        if text == "/competence":
            return json.dumps(self.agent.competence.diagnostics(), ensure_ascii=False, indent=2)
        if text == "/curriculum":
            return json.dumps(
                [item.model_dump(mode="json") for item in self.agent.learning_curriculum()],
                ensure_ascii=False,
                indent=2,
            )
        if text.startswith("/teach "):
            try:
                payload = json.loads(text.split(maxsplit=1)[1])
                example = Demonstration.model_validate(payload)
                example.person_id = self.person_id
                return self.agent.demonstrate(example).model_dump_json(indent=2)
            except ValueError as exc:
                return f"Пример не сохранён: {exc}"
        if text == "/demonstrations":
            return json.dumps(
                [item.model_dump(mode="json") for item in self.agent.experiments.demonstrations()],
                ensure_ascii=False,
                indent=2,
            )
        if text == "/person-model":
            return self.agent.interlocutors.get(self.person_id).model_dump_json(indent=2)
        if text.startswith(("/person-model correct ", "/person-model clear ")):
            try:
                model = self.agent.correct_interlocutor(
                    self.person_id,
                    text.split(maxsplit=2)[2],
                    clear_notes=text.startswith("/person-model clear "),
                )
                return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2)
            except ValueError as exc:
                return str(exc)
        if text == "/regulation":
            return json.dumps(
                [
                    item.model_dump(mode="json")
                    for item in self.agent.regulation.history(self.person_id)
                ],
                ensure_ascii=False,
                indent=2,
            )
        if text.startswith("/regulation feedback "):
            parts = text.split()
            if len(parts) != 4 or parts[3] not in {"helpful", "unhelpful"}:
                return "Используйте /regulation feedback ID helpful|unhelpful"
            try:
                regulation_result = self.agent.regulation_feedback(parts[2], parts[3] == "helpful")
                return json.dumps(
                    regulation_result.model_dump(mode="json"), ensure_ascii=False, indent=2
                )
            except ValueError as exc:
                return str(exc)
        if text == "/timeline":
            return (
                "\n".join(
                    f"{item.id} {item.created_at.isoformat()} {item.title}"
                    for item in self.agent.timeline.history(self.person_id)
                )
                or "Событий пока нет."
            )
        if text.startswith("/timeline "):
            try:
                timeline_event, episodes = self.agent.timeline.detail(text.split(maxsplit=1)[1])
                return json.dumps(
                    {
                        "event": timeline_event.model_dump(mode="json"),
                        "episodes": [item.model_dump(mode="json") for item in episodes],
                        "related": self.agent.timeline.related(timeline_event),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            except ValueError as exc:
                return str(exc)
        if text == "/preferences":
            return self.agent.communication.get(self.person_id).model_dump_json(indent=2)
        if text.startswith("/preferences "):
            try:
                patch = json.loads(text.split(maxsplit=1)[1])
                if not isinstance(patch, dict):
                    raise ValueError("Ожидается JSON-объект")
                return self.agent.update_communication(self.person_id, patch).model_dump_json(
                    indent=2
                )
            except ValueError as exc:
                return f"Не удалось изменить настройки: {exc}"
        if text.startswith("/feedback "):
            with self.agent._interaction_lock:
                self.agent.initiative.invalidate()
                self.agent.communication.snooze_topic(
                    self.person_id, text.split(maxsplit=1)[1], self.agent.clock.now()
                )
            return "Не буду самостоятельно предлагать эту тему следующие 7 суток."
        if text == "/experiment":
            return json.dumps(
                [item.model_dump(mode="json") for item in self.agent.experiments.history()],
                ensure_ascii=False,
                indent=2,
            )
        if text.startswith("/experiment "):
            try:
                name = text.split(maxsplit=1)[1]
                if name not in EXPERIMENT_KINDS:
                    return "Доступны: " + ", ".join(EXPERIMENT_KINDS)
                return self.agent.run_experiment(name).model_dump_json(indent=2)
            except ValueError as exc:
                return str(exc)
        if text == "/conflicts":
            return json.dumps(
                self.agent.psychology.snapshot().value_conflicts, ensure_ascii=False, indent=2
            )
        if text == "/biography":
            chapters = self.agent.autobiography.chapters()
            return (
                "\n\n".join(
                    f"{item.title}\n{item.summary}\n"
                    + (
                        f"Поправка собеседника: {item.revisions[-1]['text']}\n"
                        if item.revisions
                        else ""
                    )
                    + f"Источники: /biography sources {item.id}"
                    for item in chapters
                )
                or "Главы личной истории ещё не сформировались."
            )
        if text.startswith("/biography sources "):
            try:
                return json.dumps(
                    [
                        item.model_dump(mode="json")
                        for item in self.agent.autobiography.sources(text.split(maxsplit=2)[2])
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            except ValueError as exc:
                return str(exc)
        if text.startswith("/biography correct "):
            parts = text.split(maxsplit=3)
            if len(parts) != 4:
                return "Используйте /biography correct ID ТЕКСТ"
            try:
                with self.agent._interaction_lock:
                    return self.agent.autobiography.revise(parts[2], parts[3]).model_dump_json(
                        indent=2
                    )
            except ValueError as exc:
                return str(exc)
        if text == "/help":
            return HELP_TEXT
        if text == "/state":
            payload = {
                "psychological_age_equivalent": round(
                    psychological_age_equivalent(self.agent.profile), 3
                ),
                "profile": self.agent.profile.model_dump(mode="json"),
                "state": self.agent.state.model_dump(mode="json"),
                "emotion": self.agent.emotion.model_dump(mode="json"),
                "backend": self.agent.cognitive_backend.name,
                "research_provider": self.agent.research_engine.provider.name,
                "cognitive_loop": self.agent.cognitive_loop.status.model_dump(mode="json"),
                "active_goal": self.agent._active_goal_summary(),
                "psychology": self.agent.psychology.diagnostics(self.agent.profile),
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
        if text == "/diagnostics":
            return json.dumps(self.agent.diagnostics(), ensure_ascii=False, indent=2)
        if text == "/llm":
            return self.agent.llm_health().model_dump_json(indent=2)
        if text.startswith("/history"):
            limit = _parse_limit(text, 20)
            if limit is None:
                return "Количество должно быть целым числом."
            messages = self.agent.repository.recent_conversation(self.person_id, limit)
            if not messages:
                return "История диалога пока пуста."
            return "\n".join(f"- [{item.role.value}] {item.content}" for item in messages)
        if text == "/identity":
            return self.agent.identity.model_dump_json(indent=2)
        if text == "/interests":
            data = self.agent.psychology.diagnostics(self.agent.profile)
            return json.dumps(data["preferred_interests"], ensure_ascii=False, indent=2)
        if text in {"/initiative", "/initiative on", "/initiative off"}:
            if text != "/initiative":
                self.agent.set_initiative_enabled(text.endswith(" on"))
            return json.dumps(self.agent.initiative_status(), ensure_ascii=False, indent=2)
        if text == "/time":
            return json.dumps(self.agent.clock.diagnostics(), ensure_ascii=False, indent=2)
        if text == "/verifications":
            return json.dumps(
                [
                    item.model_dump(mode="json")
                    for item in self.agent.repository.list_verifications()
                ],
                ensure_ascii=False,
                indent=2,
            )
        if text in {"/personality", "/development", "/behavior", "/habits", "/reflections"}:
            data = self.agent.psychology.diagnostics(self.agent.profile)
            selection = {
                "/development": "development",
                "/behavior": "last_behavior",
                "/habits": "habits",
                "/reflections": "reflections",
            }
            psychology_result = (
                data.get(selection[text])
                if text in selection
                else {
                    key: data[key]
                    for key in (
                        "temperament",
                        "character",
                        "values",
                        "mood",
                        "self_model",
                        "interests",
                    )
                }
            )
            return json.dumps(psychology_result, ensure_ascii=False, indent=2)
        if text.startswith("/goals"):
            limit = _parse_limit(text)
            if limit is None:
                return "Количество должно быть целым числом."
            goals = self.agent.repository.list_goals(limit, active_only=False)
            if not goals:
                return "Целей пока нет."
            return "\n".join(
                f"- [{goal.status.value}/{goal.origin.value}] p={goal.priority:.2f} "
                f"urgency={goal.urgency:.2f} progress={goal.progress:.2f} "
                f"selected={goal.selection_count} need="
                f"{None if goal.need_kind is None else goal.need_kind.value} | "
                f"{goal.title}: {goal.description}"
                for goal in goals
            )
        if text == "/needs":
            needs = self.agent.cognitive_loop.needs()
            return "\n".join(
                f"- {item.kind.value}: {item.level:.3f} "
                f"(baseline={item.baseline:.2f}, stimulation={item.total_stimulation:.3f})"
                for item in needs
            )
        if text == "/drives":
            drives = self.agent.cognitive_loop.drives()
            if not drives:
                return "Сильных внутренних импульсов сейчас нет."
            return "\n".join(
                f"- [{item.kind.value}] intensity={item.intensity:.3f} "
                f"need={item.need_kind.value} | {item.title}: {item.rationale}"
                for item in drives
            )
        if text == "/background":
            return self.agent.cognitive_loop.status.model_dump_json(indent=2)
        if text == "/budgets":
            return "\n".join(
                f"- {item.name}: used={item.used}/{item.limit}, remaining={item.remaining}, "
                f"window={item.window_key}"
                for item in self.agent.cognitive_loop.budgets.list()
            )
        if text.startswith("/events"):
            limit = _parse_limit(text, 20)
            if limit is None:
                return "Количество должно быть целым числом."
            events = self.agent.repository.recent_cognitive_events(limit)
            if not events:
                return "Внутренних событий пока нет."
            return "\n".join(
                f"- #{event.sequence} [{event.kind.value}] processed={event.processed} "
                f"source={event.source} importance={event.importance:.2f}"
                for event in events
            )
        if text == "/pause":
            return self.agent.pause_cognitive_loop().model_dump_json(indent=2)
        if text == "/resume":
            return self.agent.resume_cognitive_loop().model_dump_json(indent=2)
        if text == "/tick":
            return self.agent.cognitive_tick().model_dump_json(indent=2)
        if text == "/trust":
            relationship = self.agent.trust_engine.get_or_create(self.person_id)
            return relationship.model_dump_json(indent=2)
        if text.startswith("/beliefs"):
            limit = _parse_limit(text)
            if limit is None:
                return "Количество должно быть целым числом."
            beliefs = self.agent.repository.list_beliefs(limit)
            if not beliefs:
                return "Убеждений пока нет."
            return "\n".join(
                f"- [{belief.status.value}] p={belief.confidence:.3f} "
                f"за={belief.support_score:.3f} против={belief.contradiction_score:.3f} | "
                f"{belief.claim}"
                for belief in beliefs
            )
        if text.startswith("/research "):
            claim = text.removeprefix("/research ").strip()
            if not claim:
                return "После /research требуется утверждение."
            result = self.agent.research_claim(claim, person_id=self.person_id)
            return self._format_interaction(result)
        if text.startswith("/reports"):
            limit = _parse_limit(text)
            if limit is None:
                return "Количество должно быть целым числом."
            reports = self.agent.repository.list_research_reports(limit)
            if not reports:
                return "Отчётов проверки пока нет."
            return "\n".join(
                f"- [{report.status.value}] {report.claim} | {report.summary}" for report in reports
            )
        if text.startswith("/decisions"):
            limit = _parse_limit(text)
            if limit is None:
                return "Количество должно быть целым числом."
            decisions = self.agent.repository.list_decisions(limit)
            if not decisions:
                return "Автономных решений пока нет."
            return "\n".join(
                f"- [{item.decision.value}] intent={item.intent.value} "
                f"authority={item.user_authority_assumed} | {item.reason}"
                for item in decisions
            )
        if text.startswith("/memory"):
            limit = _parse_limit(text)
            if limit is None:
                return "Количество должно быть целым числом."
            episodes = self.agent.repository.recent_episodes(limit)
            if not episodes:
                return "Активная память пока пуста."
            return "\n".join(
                f"- #{episode.sequence} strength={episode.access_strength:.3f} "
                f"DEU={episode.effective_units:.3f} | {episode.content}"
                for episode in episodes
            )
        if text.startswith("/summaries"):
            limit = _parse_limit(text)
            if limit is None:
                return "Количество должно быть целым числом."
            summaries = self.agent.repository.list_memory_summaries(limit)
            if not summaries:
                return "Консолидированных воспоминаний пока нет."
            return "\n".join(
                f"- повторов={summary.episode_count} DEU={summary.total_deu:.3f} | "
                f"{summary.representative_text}"
                for summary in summaries
            )
        if text == "/consolidate":
            return self.agent.consolidate_memory().model_dump_json(indent=2)
        if text.startswith("/rest"):
            parts = text.split(maxsplit=1)
            amount = 0.25
            if len(parts) == 2:
                try:
                    amount = float(parts[1])
                except ValueError:
                    return "Значение отдыха должно быть числом от 0 до 1."
            if not 0.0 <= amount <= 1.0:
                return "Значение отдыха должно быть от 0 до 1."
            return self.agent.rest(amount).model_dump_json(indent=2)
        if text == "/operator reset":
            return (
                "Для необратимого сброса запусти `/operator reset YES`. "
                "Обычное сообщение не может удалить личность."
            )
        if text == "/operator reset YES":
            event = self.agent.reset()
            lines = ["Операторский сброс выполнен. Создано новое событие пробуждения."]
            if event is not None:
                lines.extend(event.monologue)
            return "\n".join(lines)
        if text.startswith("/teach "):
            # Compatibility command: this is still only testimony from the user.
            teaching_text = text.removeprefix("/teach ").strip()
            return self._format_interaction(
                self.agent.interact(teaching_text, person_id=self.person_id)
            )
        if text.startswith("/contradict "):
            claim = text.removeprefix("/contradict ").strip()
            observation = Observation(
                content=f"Собеседник сообщает свидетельство против: {claim}",
                source_kind=SourceKind.CAREGIVER,
                raw_units=float(max(1, len(claim.split()))),
                novelty=None,
                attention=self.agent.state.attention_capacity,
                comprehension=0.7,
                reliability=0.35,
                integration=0.55,
                practical_confirmation=0.0,
                domains={
                    DevelopmentDomain.FACTUAL_KNOWLEDGE: 0.7,
                    DevelopmentDomain.METACOGNITION: 0.3,
                },
                claims=[
                    ClaimEvidenceInput(
                        claim=claim,
                        stance=EvidenceStance.CONTRADICT,
                        confidence=0.55,
                    )
                ],
            )
            observation_result = self.agent.process_observation(observation)
            return observation_result.response
        if text.startswith("/"):
            return "Неизвестная команда. Используй /help."

        return self._format_interaction(self.agent.interact(text, person_id=self.person_id))

    def handle_stream(self, text: str, on_token: Callable[[str], None]) -> str:
        if text.startswith("/"):
            return self.handle(text)
        result = self.agent.interact(
            text,
            person_id=self.person_id,
            on_token=on_token,
        )
        return self._format_interaction_metadata(result)

    @staticmethod
    def _format_interaction_metadata(result: InteractionResult) -> str:
        lines = [
            f"[решение={result.decision.decision.value}; "
            f"намерение={result.analysis.intent.value}; "
            f"эмоция={result.emotion.dominant.value}]"
        ]
        if result.research is not None:
            lines.append(f"[проверка={result.research.status.value}] {result.research.summary}")
        if result.deception is not None and result.deception.unlocked:
            lines.append(
                "[оценка обмана] "
                f"конфликт={result.deception.factual_conflict:.2f}; "
                f"ошибка={result.deception.speaker_may_be_mistaken:.2f}; "
                f"намеренный обман={result.deception.intentional_deception_risk:.2f}; "
                f"уверенность={result.deception.confidence_in_assessment:.2f}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_interaction(result: InteractionResult) -> str:
        metadata = ChatCommandRouter._format_interaction_metadata(result)
        return f"{result.response}\n{metadata}"


def _opening_lines(agent: DigitalChildAgent) -> list[str]:
    if agent.genesis_event is None:
        lines = ["Личность восстановлена из долговременной памяти. /help — команды."]
    else:
        lines = [
            "=== ПЕРВОЕ ПРОБУЖДЕНИЕ ===",
            *agent.genesis_event.monologue,
            "Вопросы, которые я сохраняю:",
            *[f"• {question}" for question in agent.genesis_event.questions],
            "Введите /help для списка команд.",
        ]

    health = agent.llm_health()
    if not health.enabled:
        lines.append(
            "⚠ Полноценная LLM не настроена: используется rule-based fallback. "
            "Проверь .env командой /llm."
        )
    elif not health.healthy:
        lines.append(
            f"⚠ LLM настроена, но endpoint недоступен: {health.detail} "
            "Проверь Windows-host и команду /llm."
        )
    return lines


def run_plain_chat(database_path: Path, auto_research: bool, cognitive_loop: bool = True) -> None:
    agent = create_agent(database_path, auto_research=auto_research)
    router = ChatCommandRouter(agent)
    agent.set_initiative_notifier(
        lambda message: (
            print(f"\nАгент> {message.content}\n[самостоятельная реплика]")
            if message.person_id == router.person_id
            else None
        )
    )
    if cognitive_loop:
        agent.start_cognitive_loop()
    try:
        for line in _opening_lines(agent):
            print(line)
        while True:
            try:
                text = input("\nВы> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text == "/quit":
                break
            print(f"Агент> {router.handle(text)}")
    finally:
        agent.close()


def run_desktop_chat(
    database_path: Path,
    *,
    auto_research: bool,
    face_window: bool,
    cognitive_loop: bool = True,
) -> None:
    agent = create_agent(database_path, auto_research=auto_research)
    router = ChatCommandRouter(agent)
    face = (
        FaceWindowController(title=f"{agent.identity.display_name} — Digital Child")
        if face_window
        else None
    )
    if face is not None and not face.start():
        print("[лицо] PySide6 не установлен. Выполни: uv sync --extra dev --extra desktop")
        face = None
    app = TerminalChatApp(
        handler=router.handle,
        stream_handler=router.handle_stream,
        emotion_getter=lambda: agent.emotion,
        opening_lines=_opening_lines(agent),
        face=face,
    )
    agent.set_background_notifier(app.notify)
    agent.set_initiative_notifier(
        lambda message: (
            app.notify_initiative(message.content)
            if message.person_id == router.person_id
            else None
        )
    )
    if cognitive_loop:
        agent.start_cognitive_loop()
    try:
        app.run()
    finally:
        if face is not None:
            face.close()
        agent.close()


def main() -> None:
    multiprocessing.freeze_support()
    configure_utf8_console()
    parser = argparse.ArgumentParser(
        prog="digital-child",
        description=(
            "Digital Child v0.5.0: event-driven needs, self-generated goals, "
            "goal arbitration and a bounded autonomous cognitive loop."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="Запустить общение")
    chat_parser.add_argument("--db", type=Path, default=Path("data/digital_child.db"))
    chat_parser.add_argument(
        "--plain",
        action="store_true",
        help="Обычный input()/print() без Prompt Toolkit",
    )
    chat_parser.add_argument(
        "--no-face-window",
        action="store_true",
        help="Не запускать отдельное графическое окно лица",
    )
    chat_parser.add_argument(
        "--no-auto-research",
        action="store_true",
        help="Не запускать поиск автоматически для фактических утверждений",
    )
    chat_parser.add_argument(
        "--no-cognitive-loop",
        action="store_true",
        help="Не запускать автономный фоновый когнитивный цикл",
    )

    desktop_parser = subparsers.add_parser("desktop", help="Оконный чат со слоистой сферой")
    desktop_parser.add_argument("--db", type=Path, default=None)
    desktop_parser.add_argument("--no-auto-research", action="store_true")
    desktop_parser.add_argument("--no-cognitive-loop", action="store_true")

    face_parser = subparsers.add_parser("face", help="Проверить отдельное окно сферы")
    face_parser.add_argument("--seconds", type=float, default=0.0)

    llm_parser = subparsers.add_parser("llm", help="Проверить подключение LLM")
    llm_parser.add_argument("--db", type=Path, default=Path("data/digital_child.db"))

    serve_parser = subparsers.add_parser("serve", help="Запустить HTTP API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8000, type=int)

    args = parser.parse_args()
    if args.command == "desktop":
        if not FaceWindowController.dependency_available():
            parser.error("Для оконного интерфейса выполните: uv sync --extra desktop")
        import os

        from digital_child.config import env_bool, load_dotenv
        from digital_child.desktop_app import run_window

        load_dotenv()
        run_window(
            args.db or Path(os.environ.get("DIGITAL_CHILD_DB", "data/digital_child.db")),
            auto_research=(
                not args.no_auto_research and env_bool("DIGITAL_CHILD_AUTO_RESEARCH", True)
            ),
            cognitive_loop=not args.no_cognitive_loop,
        )
        return
    if args.command == "chat":
        auto_research = not args.no_auto_research
        if args.plain or not (sys.stdin.isatty() and sys.stdout.isatty()):
            run_plain_chat(
                args.db,
                auto_research=auto_research,
                cognitive_loop=not args.no_cognitive_loop,
            )
        else:
            run_desktop_chat(
                args.db,
                auto_research=auto_research,
                face_window=not args.no_face_window,
                cognitive_loop=not args.no_cognitive_loop,
            )
        return
    if args.command == "face":
        import time

        controller = FaceWindowController()
        if not controller.start():
            parser.error("PySide6 не установлен. Выполни: uv sync --extra dev --extra desktop")
        try:
            if args.seconds > 0:
                time.sleep(args.seconds)
            else:
                while controller.running:
                    time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            controller.close()
        return
    if args.command == "llm":
        agent = create_agent(args.db)
        try:
            print(agent.llm_health().model_dump_json(indent=2))
        finally:
            agent.close()
        return
    if args.command == "serve":
        uvicorn.run("digital_child.api:app", host=args.host, port=args.port, reload=False)
        return
    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
