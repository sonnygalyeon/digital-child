from __future__ import annotations

import queue

from digital_child.domain.models import CognitiveEvent


class CognitiveEventBus:
    def __init__(self) -> None:
        self._queue: queue.Queue[CognitiveEvent] = queue.Queue()

    def publish(self, event: CognitiveEvent) -> None:
        self._queue.put(event)

    def get(self, timeout: float) -> CognitiveEvent | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def size(self) -> int:
        return self._queue.qsize()
