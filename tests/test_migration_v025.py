import sqlite3
from pathlib import Path

from digital_child.storage import SQLiteRepository


def test_v02_database_is_extended_without_deleting_old_tables(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE agent_snapshot (
            singleton_id INTEGER PRIMARY KEY,
            state_json TEXT NOT NULL,
            profile_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE episodes (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            content TEXT NOT NULL,
            action TEXT NOT NULL,
            outcome TEXT NOT NULL,
            reward REAL NOT NULL,
            importance REAL NOT NULL,
            effective_units REAL NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()

    repository = SQLiteRepository(path)
    tables = {
        row[0]
        for row in repository.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    snapshot_columns = {
        row[1]
        for row in repository.connection.execute(
            "PRAGMA table_info(agent_snapshot)"
        ).fetchall()
    }

    assert "identity" in tables
    assert "goals" in tables
    assert "relationships" in tables
    assert "decisions" in tables
    assert "research_reports" in tables
    assert "emotion_json" in snapshot_columns

    repository.close()


def test_v025_database_gains_conversation_history_table(tmp_path: Path) -> None:
    path = tmp_path / "v025.db"
    repository = SQLiteRepository(path)
    tables = {
        row[0]
        for row in repository.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "conversation_messages" in tables
    repository.close()
