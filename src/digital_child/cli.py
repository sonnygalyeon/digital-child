from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import uvicorn

from digital_child.developmental_age import psychological_age_equivalent
from digital_child.models import (
    ClaimEvidenceInput,
    DevelopmentDomain,
    EvidenceStance,
    Observation,
    SourceKind,
)
from digital_child.console import configure_utf8_console
from digital_child.face_controller import FaceWindowController
from digital_child.service import create_agent
from digital_child.terminal_chat import TerminalChatApp




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
  /llm                          состояние подключения полноценной LLM
  /history [N]                  сохранённая история диалога
  /identity                     самомодель и вопросы первого пробуждения
  /goals [N]                    собственные активные цели
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
    def __init__(self, agent) -> None:
        self.agent = agent
        self.person_id = "local-user"

    def handle(self, text: str) -> str:
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
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
        if text == "/llm":
            return self.agent.llm_health().model_dump_json(indent=2)
        if text.startswith("/history"):
            limit = _parse_limit(text, 20)
            if limit is None:
                return "Количество должно быть целым числом."
            messages = self.agent.repository.recent_conversation(self.person_id, limit)
            if not messages:
                return "История диалога пока пуста."
            return "\n".join(
                f"- [{item.role.value}] {item.content}" for item in messages
            )
        if text == "/identity":
            return self.agent.identity.model_dump_json(indent=2)
        if text.startswith("/goals"):
            limit = _parse_limit(text)
            if limit is None:
                return "Количество должно быть целым числом."
            goals = self.agent.repository.list_goals(limit, active_only=False)
            if not goals:
                return "Целей пока нет."
            return "\n".join(
                f"- [{goal.status.value}] p={goal.priority:.2f} progress={goal.progress:.2f} | "
                f"{goal.title}: {goal.description}"
                for goal in goals
            )
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
                f"- [{report.status.value}] {report.claim} | {report.summary}"
                for report in reports
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
            payload = text.removeprefix("/teach ").strip()
            return self._format_interaction(
                self.agent.interact(payload, person_id=self.person_id)
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
            result = self.agent.process_observation(observation)
            return result.response
        if text.startswith("/"):
            return "Неизвестная команда. Используй /help."

        return self._format_interaction(
            self.agent.interact(text, person_id=self.person_id)
        )

    def handle_stream(self, text: str, on_token) -> str:
        if text.startswith("/"):
            return self.handle(text)
        result = self.agent.interact(
            text,
            person_id=self.person_id,
            on_token=on_token,
        )
        return self._format_interaction_metadata(result)

    @staticmethod
    def _format_interaction_metadata(result) -> str:
        lines = [
            f"[решение={result.decision.decision.value}; "
            f"намерение={result.analysis.intent.value}; "
            f"эмоция={result.emotion.dominant.value}]"
        ]
        if result.research is not None:
            lines.append(
                f"[проверка={result.research.status.value}] {result.research.summary}"
            )
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
    def _format_interaction(result) -> str:
        metadata = ChatCommandRouter._format_interaction_metadata(result)
        return f"{result.response}\n{metadata}"



def _opening_lines(agent) -> list[str]:
    if agent.genesis_event is None:
        return ["Личность восстановлена из долговременной памяти. /help — команды."]
    return [
        "=== ПЕРВОЕ ПРОБУЖДЕНИЕ ===",
        *agent.genesis_event.monologue,
        "Вопросы, которые я сохраняю:",
        *[f"• {question}" for question in agent.genesis_event.questions],
        "Введите /help для списка команд.",
    ]


def run_plain_chat(database_path: Path, auto_research: bool) -> None:
    agent = create_agent(database_path, auto_research=auto_research)
    router = ChatCommandRouter(agent)
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
        agent.repository.close()


def run_desktop_chat(
    database_path: Path,
    *,
    auto_research: bool,
    face_window: bool,
) -> None:
    agent = create_agent(database_path, auto_research=auto_research)
    router = ChatCommandRouter(agent)
    face = FaceWindowController(title=f"{agent.identity.display_name} — Digital Child") if face_window else None
    if face is not None and not face.start():
        print(
            "[лицо] PySide6 не установлен. Выполни: "
            "uv sync --extra dev --extra desktop"
        )
        face = None
    app = TerminalChatApp(
        handler=router.handle,
        stream_handler=router.handle_stream,
        emotion_getter=lambda: agent.emotion,
        opening_lines=_opening_lines(agent),
        face=face,
    )
    agent.set_background_notifier(app.notify)
    try:
        app.run()
    finally:
        if face is not None:
            face.close()
        agent.repository.close()


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(
        prog="digital-child",
        description=(
            "Digital Child v0.4.0: faster LLM profile, Unicode terminal input "
            "and a separate animated human-like face window."
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

    face_parser = subparsers.add_parser("face", help="Проверить отдельное окно лица")
    face_parser.add_argument("--seconds", type=float, default=0.0)

    llm_parser = subparsers.add_parser("llm", help="Проверить подключение LLM")
    llm_parser.add_argument("--db", type=Path, default=Path("data/digital_child.db"))

    serve_parser = subparsers.add_parser("serve", help="Запустить HTTP API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8000, type=int)

    args = parser.parse_args()
    if args.command == "chat":
        auto_research = not args.no_auto_research
        if args.plain or not (sys.stdin.isatty() and sys.stdout.isatty()):
            run_plain_chat(args.db, auto_research=auto_research)
        else:
            run_desktop_chat(
                args.db,
                auto_research=auto_research,
                face_window=not args.no_face_window,
            )
        return
    if args.command == "face":
        import time

        controller = FaceWindowController()
        if not controller.start():
            parser.error(
                "PySide6 не установлен. Выполни: uv sync --extra dev --extra desktop"
            )
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
            agent.repository.close()
        return
    if args.command == "serve":
        uvicorn.run("digital_child.api:app", host=args.host, port=args.port, reload=False)
        return
    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
