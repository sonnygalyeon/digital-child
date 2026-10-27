from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from prompt_toolkit import HTML, PromptSession, print_formatted_text
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

from digital_child.domain.models import EmotionName, EmotionState
from digital_child.interfaces.desktop.face_controller import FaceWindowController

_COMMANDS = [
    "/help",
    "/state",
    "/diagnostics",
    "/llm",
    "/history",
    "/identity",
    "/personality",
    "/interests",
    "/initiative",
    "/initiative on",
    "/initiative off",
    "/development",
    "/behavior",
    "/habits",
    "/reflections",
    "/goals",
    "/needs",
    "/drives",
    "/background",
    "/budgets",
    "/events",
    "/pause",
    "/resume",
    "/tick",
    "/trust",
    "/beliefs",
    "/research",
    "/reports",
    "/decisions",
    "/memory",
    "/summaries",
    "/consolidate",
    "/rest",
    "/operator reset",
    "/quit",
]

_STYLE = Style.from_dict(
    {
        "prompt": "bold #58d6dd",
        "agent": "bold #7ce7b8",
        "system": "#7fa7b3",
        "warning": "bold #ffb45f",
        "error": "bold #ff7a7a",
        "title": "bold #8ae9ef",
        "status": "#9cb6c0",
        "tag": "#8eabff",
    }
)


class TerminalChatApp:
    """Unicode-safe Prompt Toolkit chat with an optional separate animated face window."""

    def __init__(
        self,
        *,
        handler: Callable[[str], str],
        stream_handler: Callable[[str, Callable[[str], None]], str] | None,
        emotion_getter: Callable[[], EmotionState],
        opening_lines: list[str],
        face: FaceWindowController | None = None,
        history_path: Path = Path("data/terminal_history.txt"),
    ) -> None:
        self.handler = handler
        self.stream_handler = stream_handler
        self.emotion_getter = emotion_getter
        self.opening_lines = opening_lines
        self.face = face
        history_path.parent.mkdir(parents=True, exist_ok=True)
        self.session: PromptSession[str] = PromptSession(
            history=FileHistory(str(history_path)),
            completer=WordCompleter(_COMMANDS, ignore_case=True, sentence=True),
            complete_while_typing=False,
            enable_history_search=True,
        )
        self._first_token = True
        self._spinner_stop = threading.Event()

    def run(self) -> None:
        self._print_header()
        for line in self.opening_lines:
            print_formatted_text(HTML(f"<system>{self._escape(line)}</system>"), style=_STYLE)
        self._set_face("idle")

        with patch_stdout(raw=True):
            while True:
                self._set_face("listening", override=EmotionName.LISTENING, status="СЛУШАЮ")
                try:
                    text = self.session.prompt(
                        HTML("<prompt>Вы › </prompt>"),
                        style=_STYLE,
                        bottom_toolbar=self._bottom_toolbar,
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not text:
                    continue
                if text == "/quit":
                    break
                self._set_face("thinking", override=EmotionName.THINKING, status="РАЗМЫШЛЯЮ")
                self._first_token = True
                spinner = threading.Thread(target=self._spinner, daemon=True)
                self._spinner_stop.clear()
                spinner.start()
                started = time.perf_counter()
                try:
                    if self.stream_handler is not None and not text.startswith("/"):
                        metadata = self.stream_handler(text, self._on_token)
                        if self._first_token:
                            self._spinner_stop.set()
                            sys.stdout.write("\r\033[2K\033[1;38;5;79mАгент ›\033[0m ")
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        if metadata.strip():
                            self._print_metadata(metadata)
                    else:
                        result = self.handler(text)
                        self._print_agent(result)
                except Exception as exc:
                    self._print_error(f"Ошибка обработки: {exc}")
                finally:
                    self._spinner_stop.set()
                    spinner.join(timeout=0.4)
                    elapsed = time.perf_counter() - started
                    print_formatted_text(
                        HTML(f"<status>⏱ {elapsed:.2f} с</status>"),
                        style=_STYLE,
                    )
                    self._set_face("idle", status="IDLE")
        if self.face is not None:
            self.face.close()

    def notify(self, message: str) -> None:
        print_formatted_text(
            HTML(f"<warning>↳ {self._escape(message)}</warning>"),
            style=_STYLE,
        )

    def notify_initiative(self, message: str) -> None:
        self._print_agent(message)
        self._print_metadata("[самостоятельная реплика]")

    def _on_token(self, token: str) -> None:
        if self._first_token:
            self._spinner_stop.set()
            sys.stdout.write("\r\033[2K\033[1;38;5;79mАгент ›\033[0m ")
            self._first_token = False
        sys.stdout.write(token)
        sys.stdout.flush()
        if self.face is not None:
            self.face.pulse_speaking(self.emotion_getter(), token)

    def _spinner(self) -> None:
        frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        index = 0
        while not self._spinner_stop.wait(0.12):
            sys.stdout.write(f"\r\033[2K  {frames[index % len(frames)]} обработка…")
            sys.stdout.flush()
            index += 1
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

    def _set_face(
        self,
        process: str,
        *,
        override: EmotionName | None = None,
        status: str | None = None,
    ) -> None:
        if self.face is None:
            return
        self.face.update(
            self.emotion_getter(),
            process=process,
            override=override,
            status_text=status,
        )

    def _print_header(self) -> None:
        backend = "LLM + память + потребности + автономный цикл"
        width = 64
        print_formatted_text(
            HTML(
                "<title>╭" + "─" * width + "╮</title>\n"
                "<title>│</title>  DIGITAL CHILD  <status>v0.5.0</status>"
                + " "
                * 27
                + "<title>│</title>\n"
                "<title>│</title>  <status>"
                + backend
                + "</status>"
                + " " * max(1, width - len(backend) - 2)
                + "<title>│</title>\n"
                "<title>╰" + "─" * width + "╯</title>"
            ),
            style=_STYLE,
        )

    def _bottom_toolbar(self) -> HTML:
        emotion = self.emotion_getter()
        face_status = "окно лица: ON" if self.face and self.face.running else "окно лица: OFF"
        return HTML(
            f" <status>{face_status} │ эмоция: {emotion.dominant.value} │ "
            f"энергия: {1.0 - emotion.fatigue:.2f} │ /help</status> "
        )

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _print_user_echo(self, text: str) -> None:
        print_formatted_text(
            HTML(f"<prompt>Вы ›</prompt> {self._escape(text)}"),
            style=_STYLE,
        )

    def _print_agent(self, text: str) -> None:
        print_formatted_text(
            HTML(f"<agent>Агент ›</agent> {self._escape(text)}"),
            style=_STYLE,
        )

    def _print_metadata(self, text: str) -> None:
        for line in text.splitlines():
            print_formatted_text(
                HTML(f"<tag>{self._escape(line)}</tag>"),
                style=_STYLE,
            )

    def _print_error(self, text: str) -> None:
        print_formatted_text(
            HTML(f"<error>{self._escape(text)}</error>"),
            style=_STYLE,
        )
