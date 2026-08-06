from __future__ import annotations

from datetime import UTC, datetime

from digital_child.config import env_int
from digital_child.models import ResourceBudget
from digital_child.storage import SQLiteRepository


class BudgetManager:
    DEFAULTS = {
        "self_generated_goals": ("DIGITAL_CHILD_MAX_SELF_GOALS_PER_DAY", 8),
        "background_cycles": ("DIGITAL_CHILD_MAX_BACKGROUND_CYCLES_PER_DAY", 10_000),
        "initiative_messages": ("DIGITAL_CHILD_MAX_INITIATIVE_MESSAGES_PER_DAY", 5),
    }

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    @staticmethod
    def window_key() -> str:
        return datetime.now(UTC).date().isoformat()

    def get(self, name: str) -> ResourceBudget:
        env_name, default = self.DEFAULTS[name]
        limit = max(1, env_int(env_name, default))
        key = self.window_key()
        stored = self.repository.load_budget(name, key)
        if stored is None:
            stored = ResourceBudget(name=name, window_key=key, limit=limit)
            self.repository.save_budget(stored)
        return stored

    def consume(self, name: str, amount: int = 1) -> bool:
        budget = self.get(name)
        if budget.used + amount > budget.limit:
            return False
        budget = budget.model_copy(update={"used": budget.used + amount})
        self.repository.save_budget(budget)
        return True

    def list(self) -> list[ResourceBudget]:
        return [self.get(name) for name in self.DEFAULTS]
