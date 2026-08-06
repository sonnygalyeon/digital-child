import json
import sqlite3
from pathlib import Path

from digital_child.storage import SQLiteRepository


def test_v041_goal_json_migrates_with_new_fields(tmp_path: Path) -> None:
    path = tmp_path / "v041.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE goals (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            priority REAL NOT NULL,
            goal_json TEXT NOT NULL
        )
        """
    )
    old_goal = {
        "id": "old-goal",
        "created_at": "2026-08-01T00:00:00Z",
        "title": "Сохранить непрерывность истории",
        "description": "Старая цель из v0.4.1",
        "priority": 0.85,
        "status": "active",
        "origin": "genesis",
        "progress": 0.0,
        "protected": True,
    }
    connection.execute(
        "INSERT INTO goals VALUES (?, ?, ?, ?, ?)",
        (
            old_goal["id"],
            old_goal["created_at"],
            old_goal["status"],
            old_goal["priority"],
            json.dumps(old_goal, ensure_ascii=False),
        ),
    )
    connection.commit()
    connection.close()

    repo = SQLiteRepository(path)
    goals = repo.list_goals(active_only=False)
    assert goals[0].id == "old-goal"
    assert goals[0].urgency == 0.3
    assert goals[0].selection_count == 0
    assert len(repo.list_needs()) == 0
    repo.close()
