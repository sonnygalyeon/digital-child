from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock

from digital_child.config import env_int
from digital_child.models import ResourceBudget
from digital_child.storage import SQLiteRepository


class BudgetManager:
    DEFAULTS = {
        "self_generated_goals": ("DIGITAL_CHILD_MAX_SELF_GOALS_PER_DAY", 8),
        "background_cycles": ("DIGITAL_CHILD_MAX_BACKGROUND_CYCLES_PER_DAY", 10_000),
        "initiative_messages": ("DIGITAL_CHILD_MAX_INITIATIVE_MESSAGES_PER_DAY", 5),
        "deferred_checks": ("DIGITAL_CHILD_MAX_DEFERRED_CHECKS_PER_DAY", 8),
        "experiments": ("DIGITAL_CHILD_MAX_EXPERIMENTS_PER_DAY", 8),
        "autonomous_experiments": ("DIGITAL_CHILD_MAX_AUTO_EXPERIMENTS_PER_DAY", 2),
        "memory_analysis": ("DIGITAL_CHILD_MAX_MEMORY_ANALYSES_PER_DAY", 20),
        "regulated_rest": ("DIGITAL_CHILD_MAX_REGULATED_RESTS_PER_DAY", 4),
        "action_plans": ("DIGITAL_CHILD_MAX_PLANS_PER_DAY", 4),
        "plan_steps": ("DIGITAL_CHILD_MAX_PLAN_STEPS_PER_DAY", 32),
        "autonomous_plans": ("DIGITAL_CHILD_MAX_AUTO_PLANS_PER_DAY", 1),
        "autonomous_plan_steps": ("DIGITAL_CHILD_MAX_AUTO_PLAN_STEPS_PER_DAY", 8),
        "personal_projects": ("DIGITAL_CHILD_MAX_PROJECTS_PER_DAY", 4),
        "project_steps": ("DIGITAL_CHILD_MAX_PROJECT_STEPS_PER_DAY", 24),
        "autonomous_project_steps": ("DIGITAL_CHILD_MAX_AUTO_PROJECT_STEPS_PER_DAY", 3),
    }

    def __init__(
        self, repository: SQLiteRepository, now: Callable[[], datetime] | None = None
    ) -> None:
        self.repository = repository
        self._lock = RLock()
        self._now = now

    @staticmethod
    def window_key() -> str:
        return datetime.now(UTC).date().isoformat()

    def get(self, name: str) -> ResourceBudget:
        with self._lock:
            return self._get(name)

    def _get(self, name: str) -> ResourceBudget:
        env_name, default = self.DEFAULTS[name]
        limit = max(
            0
            if name
            in {
                "initiative_messages",
                "deferred_checks",
                "experiments",
                "autonomous_experiments",
                "memory_analysis",
                "regulated_rest",
                "action_plans",
                "plan_steps",
                "autonomous_plans",
                "autonomous_plan_steps",
                "personal_projects",
                "project_steps",
                "autonomous_project_steps",
            }
            else 1,
            env_int(env_name, default),
        )
        key = self.window_key() if self._now is None else self._now().date().isoformat()
        stored = self.repository.load_budget(name, key)
        if stored is None:
            stored = ResourceBudget(name=name, window_key=key, limit=limit)
            self.repository.save_budget(stored)
        elif stored.limit != limit:
            stored = stored.model_copy(update={"limit": limit})
            self.repository.save_budget(stored)
        return stored

    def consume(self, name: str, amount: int = 1) -> bool:
        with self._lock:
            budget = self.get(name)
            if amount < 1 or budget.used + amount > budget.limit:
                return False
            budget = budget.model_copy(update={"used": budget.used + amount})
            self.repository.save_budget(budget)
            return True

    def list(self) -> list[ResourceBudget]:
        return [self.get(name) for name in self.DEFAULTS]

    def consume_with(self, name: str, writer: Callable[[ResourceBudget], None]) -> bool:
        """Writer atomically persists both the increment and the operation it pays for."""
        with self._lock:
            budget = self.get(name)
            if budget.remaining == 0:
                return False
            writer(budget.model_copy(update={"used": budget.used + 1}))
            return True
