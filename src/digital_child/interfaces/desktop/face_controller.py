from __future__ import annotations

import multiprocessing
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any

from digital_child.domain.models import EmotionName, EmotionState
from digital_child.interfaces.desktop.face_state import FaceState


def _desktop_face_process(connection: Connection, title: str, fps: int) -> None:
    # Imported only in the child so the core still runs without the desktop extra.
    from digital_child.interfaces.desktop.desktop_face import run_face_window

    run_face_window(connection, title=title, fps=fps)


class FaceWindowController:
    """Owns the optional PySide6 face process and sends non-blocking state updates."""

    def __init__(self, *, title: str = "Digital Child", fps: int = 60) -> None:
        self.title = title
        self.fps = max(24, min(120, fps))
        self._process: BaseProcess | None = None
        self._connection: Connection | None = None
        self._available: bool | None = None

    @staticmethod
    def dependency_available() -> bool:
        try:
            import PySide6  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def available(self) -> bool:
        if self._available is None:
            self._available = self.dependency_available()
        return self._available

    @property
    def running(self) -> bool:
        return bool(self._process and self._process.is_alive())

    def start(self) -> bool:
        if self.running:
            return True
        if not self.available:
            return False
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        process = context.Process(
            target=_desktop_face_process,
            args=(child, self.title, self.fps),
            name="digital-child-face",
            daemon=True,
        )
        process.start()
        self._connection = parent
        self._process = process
        self._send({"type": "ping"})
        return True

    def update(
        self,
        emotion: EmotionState,
        *,
        process: str = "idle",
        override: EmotionName | None = None,
        speaking_level: float = 0.0,
        status_text: str | None = None,
    ) -> None:
        if not self.running:
            return
        state = FaceState.from_emotion(
            emotion,
            process=process,
            override=override,
            speaking_level=speaking_level,
            status_text=status_text,
        )
        self._send(state.to_message())

    def pulse_speaking(self, emotion: EmotionState, token: str) -> None:
        if not token:
            return
        density = min(1.0, 0.25 + len(token.strip()) / 12.0)
        self.update(
            emotion,
            process="speaking",
            override=EmotionName.SPEAKING,
            speaking_level=density,
            status_text="ГОВОРЮ",
        )

    def close(self) -> None:
        if self._connection is not None:
            self._send({"type": "close"})
        if self._process is not None:
            self._process.join(timeout=1.5)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1.0)
        if self._connection is not None:
            try:
                self._connection.close()
            except OSError:
                pass
        self._connection = None
        self._process = None

    def _send(self, message: dict[str, Any]) -> None:
        connection = self._connection
        if connection is None:
            return
        try:
            connection.send(message)
        except (BrokenPipeError, EOFError, OSError):
            self._connection = None

    def __enter__(self) -> FaceWindowController:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
