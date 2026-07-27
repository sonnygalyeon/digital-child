from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from digital_child.models import AgentSnapshot, AgentState, DevelopmentProfile, Episode


class SQLiteRepository:
    """Persistent storage for episodic memory and the current agent snapshot."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
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
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_snapshot (
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                    state_json TEXT NOT NULL,
                    profile_json TEXT NOT NULL
                )
                """
            )

    def save_episode(self, episode: Episode) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO episodes (
                    id,
                    created_at,
                    observation_id,
                    content,
                    action,
                    outcome,
                    reward,
                    importance,
                    effective_units,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode.id,
                    episode.created_at.isoformat(),
                    episode.observation_id,
                    episode.content,
                    episode.action,
                    episode.outcome,
                    episode.reward,
                    episode.importance,
                    episode.effective_units,
                    json.dumps(episode.metadata, ensure_ascii=False),
                ),
            )

    def recent_episodes(self, limit: int = 20) -> list[Episode]:
        if limit <= 0:
            return []

        with self._lock:
            rows = self.connection.execute(
                """
                SELECT *
                FROM episodes
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            Episode.model_validate(
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "observation_id": row["observation_id"],
                    "content": row["content"],
                    "action": row["action"],
                    "outcome": row["outcome"],
                    "reward": row["reward"],
                    "importance": row["importance"],
                    "effective_units": row["effective_units"],
                    "metadata": json.loads(row["metadata_json"]),
                }
            )
            for row in rows
        ]

    def save_snapshot(self, snapshot: AgentSnapshot) -> None:
        state_json = snapshot.state.model_dump_json()
        profile_json = snapshot.profile.model_dump_json()

        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO agent_snapshot (singleton_id, state_json, profile_json)
                VALUES (1, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    profile_json = excluded.profile_json
                """,
                (state_json, profile_json),
            )

    def load_snapshot(self) -> AgentSnapshot | None:
        with self._lock:
            row = self.connection.execute(
                """
                SELECT state_json, profile_json
                FROM agent_snapshot
                WHERE singleton_id = 1
                """
            ).fetchone()

        if row is None:
            return None

        return AgentSnapshot(
            state=AgentState.model_validate_json(row["state_json"]),
            profile=DevelopmentProfile.model_validate_json(row["profile_json"]),
        )

    def reset(self) -> None:
        with self._lock, self.connection:
            self.connection.execute("DELETE FROM episodes")
            self.connection.execute("DELETE FROM agent_snapshot")

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> SQLiteRepository:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
