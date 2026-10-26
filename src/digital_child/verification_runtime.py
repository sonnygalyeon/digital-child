from __future__ import annotations

import threading
import time
from datetime import timedelta
from typing import TYPE_CHECKING

from digital_child.config import env_float
from digital_child.models import ResearchStatus
from digital_child.research import DisabledSearchProvider

if TYPE_CHECKING:
    from digital_child.agent import DigitalChildAgent


class VerificationRuntime:
    """One bounded worker for clock refresh and durable deferred factual checks."""

    def __init__(self, agent: DigitalChildAgent) -> None:
        self.agent = agent
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._run_lock = threading.Lock()
        self._next_sync = 0.0
        self._sync_interval = max(60.0, env_float("DIGITAL_CHILD_TIME_SYNC_SECONDS", 3600.0))

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive() and not self._stop.is_set():
            self._wake.set()
            return
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            args=(self._stop, self._wake),
            name="digital-child-verification",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def _run(self, stop: threading.Event, wake: threading.Event) -> None:
        while not stop.is_set():
            try:
                # A stopped generator may still be unwinding after a quick restart.
                if self._run_lock.acquire(blocking=False):
                    try:
                        self._tick(stop)
                    finally:
                        self._run_lock.release()
            except Exception as exc:
                with self.agent._interaction_lock:
                    if stop.is_set() or self.agent._closed.is_set():
                        return
                    self.agent.repository.save_audit("verification_error", {"error": str(exc)})
            wake.wait(timeout=15.0)
            wake.clear()

    def _tick(self, stop: threading.Event) -> None:
        agent = self.agent
        if time.monotonic() >= self._next_sync:
            agent.clock.sync()
            self._next_sync = time.monotonic() + self._sync_interval
            with agent._interaction_lock:
                if stop.is_set() or agent._closed.is_set():
                    return
                agent.clock.checkpoint()
                agent.psychology.update_absence(agent.profile, agent.clock.now())
                agent.update_idle_emotion()

        if not agent._interaction_lock.acquire(blocking=False):
            return
        try:
            if (
                stop.is_set()
                or agent._closed.is_set()
                or not agent.auto_research
                or agent.research_mode == "manual"
                or agent.cognitive_loop.status.paused
                or isinstance(agent.research_engine.provider, DisabledSearchProvider)
            ):
                return
            now = agent.clock.now()
            tasks = agent.repository.due_verifications(now)
            if not tasks:
                return
            task = tasks[0]
            if not agent.cognitive_loop.budgets.consume("deferred_checks"):
                return
            task = task.model_copy(
                update={
                    "attempts": task.attempts + 1,
                    "next_attempt_at": now
                    + timedelta(seconds=min(86400, 300 * 2 ** min(task.attempts, 8))),
                }
            )
            agent.repository.save_verification(task)
            subject_id = agent.identity.id
        finally:
            agent._interaction_lock.release()

        report = agent.research_engine.research(task.claim)
        with agent._interaction_lock:
            if stop.is_set() or agent._closed.is_set() or agent.identity.id != subject_id:
                return
            agent._apply_deferred_verification(task, report)
        if agent.background_notifier is not None and report.status == ResearchStatus.COMPLETED:
            agent.background_notifier(
                f"Проверка прежнего утверждения завершена: {task.claim} — {report.summary}"
            )
