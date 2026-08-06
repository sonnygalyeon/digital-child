from __future__ import annotations

import threading
from datetime import UTC, datetime
from collections.abc import Callable

from digital_child.budgets import BudgetManager
from digital_child.drives import DriveEngine
from digital_child.event_bus import CognitiveEventBus
from digital_child.goal_arbiter import GoalArbiter
from digital_child.models import (
    CognitiveEvent,
    CognitiveEventKind,
    CognitiveLoopStatus,
    DriveSignal,
    Goal,
    GoalOrigin,
    GoalStatus,
)
from digital_child.needs import NeedEngine
from digital_child.storage import SQLiteRepository


class CognitiveLoop:
    """Cheap autonomous loop. v0.5.0 creates/selects goals but executes no external actions."""

    def __init__(
        self,
        repository: SQLiteRepository,
        *,
        notifier: Callable[[str], None] | None = None,
        heartbeat_seconds: float = 5.0,
    ) -> None:
        self.repository = repository
        self.need_engine = NeedEngine(repository)
        self.drive_engine = DriveEngine()
        self.goal_arbiter = GoalArbiter()
        self.budgets = BudgetManager(repository)
        self.bus = CognitiveEventBus()
        self.notifier = notifier
        self.heartbeat_seconds = max(0.1, heartbeat_seconds)
        self.status = repository.load_cognitive_loop_status() or CognitiveLoopStatus()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._lock = threading.RLock()
        self._last_drives: list[DriveSignal] = []

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._pause.clear()
            self.status = self.status.model_copy(
                update={
                    "running": True,
                    "paused": False,
                    "started_at": self.status.started_at or datetime.now(UTC),
                    "last_action": "started",
                }
            )
            self._persist()
            if self.bus.size() == 0:
                for pending in self.repository.pending_cognitive_events(200):
                    self.bus.publish(pending)
            self._thread = threading.Thread(
                target=self._run,
                name="digital-child-cognitive-loop",
                daemon=True,
            )
            self._thread.start()
            self.publish(CognitiveEvent(kind=CognitiveEventKind.STARTUP, source="runtime"))

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self.status = self.status.model_copy(
            update={"running": False, "paused": False, "last_action": "stopped"}
        )
        self._persist()

    def pause(self) -> CognitiveLoopStatus:
        self._pause.set()
        self.status = self.status.model_copy(update={"paused": True, "last_action": "paused"})
        self._persist()
        return self.status

    def resume(self) -> CognitiveLoopStatus:
        self._pause.clear()
        self.status = self.status.model_copy(update={"paused": False, "last_action": "resumed"})
        self._persist()
        return self.status

    def publish(self, event: CognitiveEvent) -> CognitiveEvent:
        stored = self.repository.save_cognitive_event(event)
        self.bus.publish(stored)
        self.status = self.status.model_copy(update={"event_queue_size": self.bus.size()})
        self._persist()
        return stored

    def tick_once(self, event: CognitiveEvent | None = None) -> CognitiveLoopStatus:
        if event is None:
            event = self.bus.get(0.0)
        if event is None:
            event = CognitiveEvent(kind=CognitiveEventKind.IDLE, source="heartbeat")
            event = self.repository.save_cognitive_event(event)
        self.need_engine.apply(event)
        self.repository.mark_cognitive_event_processed(event.id)
        drives = self.drive_engine.evaluate(self.need_engine.list())
        self._last_drives = drives
        created = self._create_goal_from_drive(drives[0]) if drives else None
        active = self.repository.list_goals(100, active_only=True)
        arbitration = self.goal_arbiter.choose(
            active,
            self.need_engine.list(),
            self.repository.current_sequence(),
        )
        if arbitration.selected_goal is not None:
            self.repository.save_goal(arbitration.selected_goal)
        self.status = self.status.model_copy(
            update={
                "last_tick_at": datetime.now(UTC),
                "cycle_count": self.status.cycle_count + 1,
                "processed_events": self.status.processed_events + 1,
                "event_queue_size": self.bus.size(),
                "active_goal_id": (
                    None if arbitration.selected_goal is None else arbitration.selected_goal.id
                ),
                "last_action": (
                    f"created_goal:{created.id}" if created else "updated_needs_and_arbitrated"
                ),
                "created_goals": self.status.created_goals + (1 if created else 0),
            }
        )
        self._persist()
        return self.status

    def needs(self):
        return self.need_engine.list()

    def drives(self) -> list[DriveSignal]:
        self._last_drives = self.drive_engine.evaluate(self.need_engine.list())
        return self._last_drives

    def _run(self) -> None:
        idle_count = 0
        while not self._stop.is_set():
            if self._pause.is_set():
                self._stop.wait(0.25)
                continue
            event = self.bus.get(self.heartbeat_seconds)
            if event is None:
                idle_count += 1
                if idle_count % 6 != 0:
                    continue
                event = self.repository.save_cognitive_event(
                    CognitiveEvent(kind=CognitiveEventKind.IDLE, source="heartbeat")
                )
            else:
                idle_count = 0
            if not self.budgets.consume("background_cycles"):
                self.status = self.status.model_copy(
                    update={"budget_exhausted": True, "last_action": "budget_exhausted"}
                )
                self._persist()
                self._pause.set()
                continue
            self.tick_once(event)

    def _create_goal_from_drive(self, drive: DriveSignal) -> Goal | None:
        existing = self.repository.list_goals(200, active_only=True)
        if any(goal.need_kind == drive.need_kind for goal in existing):
            return None
        if not self.budgets.consume("self_generated_goals"):
            self.status = self.status.model_copy(update={"budget_exhausted": True})
            return None
        goal = Goal(
            title=drive.suggested_goal_title,
            description=drive.suggested_goal_description,
            priority=min(0.92, 0.45 + drive.intensity * 0.45),
            urgency=max(0.2, drive.intensity - 0.25),
            expected_utility=0.62,
            estimated_cost=0.22,
            risk=0.08,
            value_alignment=0.78,
            status=GoalStatus.ACTIVE,
            origin=GoalOrigin.SELF_GENERATED,
            need_kind=drive.need_kind,
            success_criteria=["Сформулирован проверяемый следующий шаг."],
        )
        self.repository.save_goal(goal)
        self.need_engine.satisfy(
            drive.need_kind,
            amount=0.05,
            sequence=self.repository.current_sequence(),
        )
        self.repository.save_audit(
            "self_generated_goal",
            {
                "goal_id": goal.id,
                "need": drive.need_kind.value,
                "drive": drive.kind.value,
                "intensity": drive.intensity,
            },
        )
        if self.notifier is not None and drive.intensity >= 0.82:
            self.notifier(f"Сформирована внутренняя цель: {goal.title}")
        return goal

    def _persist(self) -> None:
        self.repository.save_cognitive_loop_status(self.status)
