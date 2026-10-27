from __future__ import annotations

import argparse
import multiprocessing
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

from digital_child.application.commands import ChatCommandRouter
from digital_child.application.commands import (
    build_caregiver_observation as build_caregiver_observation,
)
from digital_child.application.service import create_agent
from digital_child.interfaces.desktop.face_controller import FaceWindowController
from digital_child.interfaces.terminal.console import configure_utf8_console
from digital_child.interfaces.terminal.terminal_chat import TerminalChatApp

if TYPE_CHECKING:
    from digital_child.application.agent import DigitalChildAgent


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

        from digital_child.infrastructure.config import env_bool, load_dotenv
        from digital_child.interfaces.desktop.desktop_app import run_window

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
        uvicorn.run(
            "digital_child.interfaces.http.api:app", host=args.host, port=args.port, reload=False
        )
        return
    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
