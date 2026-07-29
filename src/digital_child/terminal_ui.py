from __future__ import annotations

import curses
import queue
import threading
import time
from collections.abc import Callable

from digital_child.models import EmotionName, EmotionState
from digital_child.terminal_face import TerminalFaceRenderer


class TerminalFaceApp:
    """Curses UI with independent idle animation and streaming LLM output."""

    def __init__(
        self,
        *,
        handler: Callable[[str], str],
        emotion_getter: Callable[[], EmotionState],
        stream_handler: Callable[[str, Callable[[str], None]], str] | None = None,
        opening_lines: list[str] | None = None,
        ascii_only: bool = False,
        fps: float = 12.0,
    ) -> None:
        self.handler = handler
        self.stream_handler = stream_handler
        self.emotion_getter = emotion_getter
        self.opening_lines = opening_lines or []
        self.renderer = TerminalFaceRenderer(ascii_only=ascii_only)
        self.frame_delay = 1.0 / max(2.0, min(fps, 30.0))
        self.messages: list[str] = list(self.opening_lines)
        self.input_buffer = ""
        self.partial_response = ""
        self.busy = False
        self.stopped = False
        self.event_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.speaking_until = 0.0

    def run(self) -> None:
        curses.wrapper(self._loop)

    def _loop(self, screen: curses.window) -> None:
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        screen.nodelay(True)
        screen.keypad(True)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_WHITE, -1)
            curses.init_pair(3, curses.COLOR_BLUE, -1)

        tick = 0
        while not self.stopped:
            self._collect_worker_events()
            key = screen.getch()
            self._handle_key(key)
            self._draw(screen, tick)
            tick += 1
            time.sleep(self.frame_delay)

    def _handle_key(self, key: int) -> None:
        if key == -1:
            return
        if key in {3, 4}:
            self.stopped = True
            return
        if key in {curses.KEY_BACKSPACE, 127, 8}:
            self.input_buffer = self.input_buffer[:-1]
            return
        if key in {10, 13, curses.KEY_ENTER}:
            text = self.input_buffer.strip()
            self.input_buffer = ""
            if not text:
                return
            self.messages.append(f"Вы: {text}")
            if text == "/quit":
                self.stopped = True
                return
            if self.busy:
                self.messages.append("Система: дождитесь завершения текущего размышления.")
                return
            self.busy = True
            self.partial_response = ""
            threading.Thread(target=self._worker, args=(text,), daemon=True).start()
            return
        if 0 <= key <= 0x10FFFF:
            try:
                char = chr(key)
            except ValueError:
                return
            if char.isprintable():
                self.input_buffer += char

    def _worker(self, text: str) -> None:
        try:
            if self.stream_handler is not None and not text.startswith("/"):
                result = self.stream_handler(
                    text,
                    lambda token: self.event_queue.put(("token", token)),
                )
            else:
                result = self.handler(text)
        except Exception as exc:
            result = f"Ошибка обработки: {exc}"
        self.event_queue.put(("done", result))

    def _collect_worker_events(self) -> None:
        while True:
            try:
                event, payload = self.event_queue.get_nowait()
            except queue.Empty:
                return
            if event == "token":
                self.partial_response += payload
                self.speaking_until = time.monotonic() + 0.25
                continue
            if event == "done":
                self.busy = False
                self.speaking_until = time.monotonic() + 1.0
                if self.partial_response.strip():
                    self.messages.append(f"Агент: {self.partial_response.strip()}")
                    if payload.strip():
                        self.messages.extend(payload.splitlines())
                else:
                    for line in payload.splitlines() or [payload]:
                        self.messages.append(f"Агент: {line}")
                self.partial_response = ""

    def _draw(self, screen: curses.window, tick: int) -> None:
        height, width = screen.getmaxyx()
        screen.erase()
        if height < 24 or width < 72:
            self._safe_add(screen, 0, 0, "Увеличьте окно терминала минимум до 72x24.")
            screen.refresh()
            return

        override = None
        if self.busy and not self.partial_response:
            override = EmotionName.THINKING
        elif self.partial_response or time.monotonic() < self.speaking_until:
            override = EmotionName.SPEAKING
        elif self.input_buffer:
            override = EmotionName.LISTENING

        emotion = self.emotion_getter()
        frame = self.renderer.render(emotion, tick, override=override)
        face_width = max(len(line) for line in frame.lines)
        face_x = max(0, (width - face_width) // 2)
        color = curses.color_pair(1) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
        for row, line in enumerate(frame.lines):
            self._safe_add(screen, row, face_x, line, color)

        status_y = len(frame.lines)
        if self.partial_response:
            process_label = "ГЕНЕРАЦИЯ"
        elif self.busy:
            process_label = "РАЗМЫШЛЕНИЕ / ПОИСК"
        else:
            process_label = "IDLE"
        status = (
            f"[ {frame.expression.value.upper()} ]  энергия={1-emotion.fatigue:.2f}  "
            f"любопытство={emotion.curiosity:.2f}  доверие={emotion.trust:.2f}  "
            f"{process_label}"
        )
        self._safe_add(screen, status_y, max(0, (width - len(status)) // 2), status)

        prompt_y = height - 2
        log_start = status_y + 2
        max_log_lines = max(1, prompt_y - log_start - 1)
        visible = list(self.messages)
        if self.partial_response:
            visible.append(f"Агент: {self.partial_response}▌")
        for index, message in enumerate(visible[-max_log_lines:]):
            self._safe_add(screen, log_start + index, 1, message[: width - 2])

        prompt = f"> {self.input_buffer}"
        self._safe_add(screen, prompt_y, 1, prompt[: width - 2], curses.A_BOLD)
        try:
            screen.move(prompt_y, min(width - 2, len(prompt) + 1))
        except curses.error:
            pass
        screen.refresh()

    @staticmethod
    def _safe_add(
        screen: curses.window,
        y: int,
        x: int,
        text: str,
        attr: int = 0,
    ) -> None:
        try:
            screen.addstr(y, x, text, attr)
        except curses.error:
            pass
