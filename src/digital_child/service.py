from __future__ import annotations

import os
from pathlib import Path

from digital_child.agent import DigitalChildAgent
from digital_child.storage import SQLiteRepository


def create_agent(database_path: str | Path | None = None) -> DigitalChildAgent:
    path = Path(database_path or os.environ.get("DIGITAL_CHILD_DB", "data/digital_child.db"))
    return DigitalChildAgent(SQLiteRepository(path))
