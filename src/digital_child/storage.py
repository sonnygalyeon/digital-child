from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from digital_child.models import (
    AgentSnapshot,
    AgentState,
    AuditEvent,
    AutonomyDecision,
    Belief,
    ConversationMessage,
    ConversationRole,
    CognitiveEvent,
    CognitiveEventKind,
    CognitiveLoopStatus,
    DevelopmentProfile,
    EmotionState,
    Episode,
    EvidenceRecord,
    GenesisEvent,
    Goal,
    IdentityProfile,
    MemorySummary,
    NeedKind,
    NeedState,
    ResourceBudget,
    RelationshipProfile,
    ResearchReport,
    SourceKind,
    SourceRecord,
    TrustEvent,
)


class SQLiteRepository:
    """Persistent storage for episodes, beliefs, evidence, sources and state."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    normalized_content TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    reward REAL NOT NULL,
                    importance REAL NOT NULL,
                    effective_units REAL NOT NULL,
                    access_strength REAL NOT NULL DEFAULT 1.0,
                    last_decay_sequence INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            self._ensure_episode_columns()
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_snapshot (
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                    state_json TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    emotion_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            self._ensure_snapshot_columns()
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    locator TEXT,
                    reliability REAL NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS beliefs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    normalized_claim TEXT NOT NULL UNIQUE,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    support_score REAL NOT NULL,
                    contradiction_score REAL NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    access_strength REAL NOT NULL,
                    access_count INTEGER NOT NULL,
                    last_accessed_sequence INTEGER NOT NULL,
                    tags_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    belief_id TEXT NOT NULL REFERENCES beliefs(id) ON DELETE CASCADE,
                    observation_id TEXT NOT NULL,
                    source_id TEXT NOT NULL REFERENCES sources(id),
                    stance TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    weight REAL NOT NULL,
                    excerpt TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_summaries (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    normalized_key TEXT NOT NULL UNIQUE,
                    representative_text TEXT NOT NULL,
                    episode_count INTEGER NOT NULL,
                    total_deu REAL NOT NULL,
                    mean_importance REAL NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS identity (
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                    identity_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS genesis_events (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    event_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority REAL NOT NULL,
                    goal_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS relationships (
                    person_id TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    relationship_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trust_events (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    event_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    decision_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_reports (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    intent TEXT,
                    decision_id TEXT,
                    backend TEXT,
                    model TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_person_created
                ON conversation_messages(person_id, created_at)
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS needs (
                    kind TEXT PRIMARY KEY,
                    level REAL NOT NULL,
                    baseline REAL NOT NULL,
                    sensitivity REAL NOT NULL,
                    last_updated_sequence INTEGER NOT NULL,
                    total_stimulation REAL NOT NULL,
                    need_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cognitive_events (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    processed INTEGER NOT NULL DEFAULT 0,
                    event_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cognitive_events_processed_sequence
                ON cognitive_events(processed, sequence)
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cognitive_loop_state (
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                    status_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS resource_budgets (
                    name TEXT NOT NULL,
                    window_key TEXT NOT NULL,
                    budget_json TEXT NOT NULL,
                    PRIMARY KEY(name, window_key)
                )
                """
            )


    def _ensure_snapshot_columns(self) -> None:
        columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(agent_snapshot)")
        }
        if "emotion_json" not in columns:
            self.connection.execute(
                "ALTER TABLE agent_snapshot ADD COLUMN emotion_json TEXT NOT NULL DEFAULT '{}'"
            )

    def _ensure_episode_columns(self) -> None:
        columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(episodes)")
        }
        definitions = {
            "sequence": "INTEGER NOT NULL DEFAULT 0",
            "normalized_content": "TEXT NOT NULL DEFAULT ''",
            "access_strength": "REAL NOT NULL DEFAULT 1.0",
            "last_decay_sequence": "INTEGER NOT NULL DEFAULT 0",
            "archived": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in definitions.items():
            if name not in columns:
                self.connection.execute(
                    f"ALTER TABLE episodes ADD COLUMN {name} {definition}"
                )

    def current_sequence(self) -> int:
        with self._lock:
            value = self.connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM episodes"
            ).fetchone()[0]
        return int(value)

    def save_episode(self, episode: Episode) -> Episode:
        sequence = self.current_sequence() + 1
        stored = episode.model_copy(update={"sequence": sequence})
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO episodes (
                    id, sequence, created_at, observation_id, content,
                    normalized_content, action, outcome, reward, importance,
                    effective_units, access_strength, last_decay_sequence,
                    archived, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.id,
                    stored.sequence,
                    stored.created_at.isoformat(),
                    stored.observation_id,
                    stored.content,
                    stored.normalized_content,
                    stored.action,
                    stored.outcome,
                    stored.reward,
                    stored.importance,
                    stored.effective_units,
                    stored.access_strength,
                    stored.sequence,
                    int(stored.archived),
                    json.dumps(stored.metadata, ensure_ascii=False),
                ),
            )
        return stored

    def recent_episodes(self, limit: int = 20, include_archived: bool = False) -> list[Episode]:
        if limit <= 0:
            return []
        condition = "" if include_archived else "WHERE archived = 0"
        with self._lock:
            rows = self.connection.execute(
                f"""
                SELECT * FROM episodes
                {condition}
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._episode_from_row(row) for row in rows]

    @staticmethod
    def _episode_from_row(row: sqlite3.Row) -> Episode:
        return Episode.model_validate(
            {
                "id": row["id"],
                "sequence": row["sequence"],
                "created_at": row["created_at"],
                "observation_id": row["observation_id"],
                "content": row["content"],
                "normalized_content": row["normalized_content"] or row["content"],
                "action": row["action"],
                "outcome": row["outcome"],
                "reward": row["reward"],
                "importance": row["importance"],
                "effective_units": row["effective_units"],
                "access_strength": row["access_strength"],
                "archived": bool(row["archived"]),
                "metadata": json.loads(row["metadata_json"]),
            }
        )

    def save_source(self, source: SourceRecord) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO sources (
                    id, created_at, kind, name, locator, reliability, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind = excluded.kind,
                    name = excluded.name,
                    locator = excluded.locator,
                    reliability = excluded.reliability,
                    metadata_json = excluded.metadata_json
                """,
                (
                    source.id,
                    source.created_at.isoformat(),
                    source.kind.value,
                    source.name,
                    source.locator,
                    source.reliability,
                    json.dumps(source.metadata, ensure_ascii=False),
                ),
            )

    def get_source(self, source_id: str) -> SourceRecord | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        return None if row is None else self._source_from_row(row)

    def list_sources(self, limit: int = 100) -> list[SourceRecord]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM sources ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._source_from_row(row) for row in rows]

    @staticmethod
    def _source_from_row(row: sqlite3.Row) -> SourceRecord:
        return SourceRecord.model_validate(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "kind": row["kind"],
                "name": row["name"],
                "locator": row["locator"],
                "reliability": row["reliability"],
                "metadata": json.loads(row["metadata_json"]),
            }
        )

    def get_or_create_default_source(
        self,
        kind: SourceKind,
        reliability: float,
    ) -> SourceRecord:
        source_id = f"default:{kind.value}"
        existing = self.get_source(source_id)
        if existing is not None:
            if abs(existing.reliability - reliability) > 1e-12:
                existing.reliability = reliability
                self.save_source(existing)
            return existing
        source = SourceRecord(
            id=source_id,
            kind=kind,
            name=f"Default {kind.value} source",
            locator=source_id,
            reliability=reliability,
        )
        self.save_source(source)
        return source

    def save_belief(self, belief: Belief) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO beliefs (
                    id, created_at, updated_at, claim, normalized_claim,
                    confidence, status, support_score, contradiction_score,
                    evidence_count, access_strength, access_count,
                    last_accessed_sequence, tags_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    claim = excluded.claim,
                    confidence = excluded.confidence,
                    status = excluded.status,
                    support_score = excluded.support_score,
                    contradiction_score = excluded.contradiction_score,
                    evidence_count = excluded.evidence_count,
                    access_strength = excluded.access_strength,
                    access_count = excluded.access_count,
                    last_accessed_sequence = excluded.last_accessed_sequence,
                    tags_json = excluded.tags_json
                """,
                (
                    belief.id,
                    belief.created_at.isoformat(),
                    belief.updated_at.isoformat(),
                    belief.claim,
                    belief.normalized_claim,
                    belief.confidence,
                    belief.status.value,
                    belief.support_score,
                    belief.contradiction_score,
                    belief.evidence_count,
                    belief.access_strength,
                    belief.access_count,
                    belief.last_accessed_sequence,
                    json.dumps(belief.tags, ensure_ascii=False),
                ),
            )

    def get_belief_by_normalized_claim(self, normalized_claim: str) -> Belief | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM beliefs WHERE normalized_claim = ?", (normalized_claim,)
            ).fetchone()
        return None if row is None else self._belief_from_row(row)

    def list_beliefs(self, limit: int = 100) -> list[Belief]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT * FROM beliefs
                ORDER BY access_strength DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._belief_from_row(row) for row in rows]

    @staticmethod
    def _belief_from_row(row: sqlite3.Row) -> Belief:
        return Belief.model_validate(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "claim": row["claim"],
                "normalized_claim": row["normalized_claim"],
                "confidence": row["confidence"],
                "status": row["status"],
                "support_score": row["support_score"],
                "contradiction_score": row["contradiction_score"],
                "evidence_count": row["evidence_count"],
                "access_strength": row["access_strength"],
                "access_count": row["access_count"],
                "last_accessed_sequence": row["last_accessed_sequence"],
                "tags": json.loads(row["tags_json"]),
            }
        )

    def save_evidence(self, evidence: EvidenceRecord) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO evidence (
                    id, created_at, belief_id, observation_id, source_id,
                    stance, confidence, weight, excerpt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.id,
                    evidence.created_at.isoformat(),
                    evidence.belief_id,
                    evidence.observation_id,
                    evidence.source_id,
                    evidence.stance.value,
                    evidence.confidence,
                    evidence.weight,
                    evidence.excerpt,
                ),
            )

    def evidence_for_belief(self, belief_id: str, limit: int = 100) -> list[EvidenceRecord]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT * FROM evidence
                WHERE belief_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (belief_id, limit),
            ).fetchall()
        return [EvidenceRecord.model_validate(dict(row)) for row in rows]

    def apply_interference_decay(
        self,
        current_sequence: int,
        decay_per_episode: float,
        archive_threshold: float,
    ) -> tuple[int, int]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT id, sequence, access_strength, importance, last_decay_sequence
                FROM episodes
                WHERE archived = 0
                """
            ).fetchall()

        decayed = 0
        archived = 0
        with self._lock, self.connection:
            for row in rows:
                last_sequence = max(int(row["sequence"]), int(row["last_decay_sequence"]))
                interference = max(0, current_sequence - last_sequence)
                if interference == 0:
                    continue
                protection = 0.35 + 0.65 * float(row["importance"])
                loss = interference * decay_per_episode * (1.0 - 0.6 * protection)
                strength = max(0.0, float(row["access_strength"]) - loss)
                is_archived = strength < archive_threshold
                self.connection.execute(
                    """
                    UPDATE episodes
                    SET access_strength = ?, last_decay_sequence = ?, archived = ?
                    WHERE id = ?
                    """,
                    (strength, current_sequence, int(is_archived), row["id"]),
                )
                decayed += 1
                archived += int(is_archived)
        return decayed, archived

    def consolidate_repeated_episodes(self, minimum_repetitions: int = 3) -> tuple[int, int]:
        with self._lock:
            groups = self.connection.execute(
                """
                SELECT normalized_content, COUNT(*) AS count,
                       SUM(effective_units) AS total_deu,
                       AVG(importance) AS mean_importance,
                       MAX(sequence) AS newest_sequence
                FROM episodes
                WHERE normalized_content <> ''
                GROUP BY normalized_content
                HAVING COUNT(*) >= ?
                """,
                (minimum_repetitions,),
            ).fetchall()

        created = 0
        updated = 0
        with self._lock, self.connection:
            for group in groups:
                representative = self.connection.execute(
                    """
                    SELECT content FROM episodes
                    WHERE normalized_content = ?
                    ORDER BY sequence DESC LIMIT 1
                    """,
                    (group["normalized_content"],),
                ).fetchone()["content"]
                existing = self.connection.execute(
                    "SELECT id FROM memory_summaries WHERE normalized_key = ?",
                    (group["normalized_content"],),
                ).fetchone()
                summary = MemorySummary(
                    id=existing["id"] if existing else MemorySummary(
                        normalized_key=group["normalized_content"],
                        representative_text=representative,
                        episode_count=group["count"],
                        total_deu=group["total_deu"],
                        mean_importance=group["mean_importance"],
                    ).id,
                    normalized_key=group["normalized_content"],
                    representative_text=representative,
                    episode_count=group["count"],
                    total_deu=group["total_deu"],
                    mean_importance=group["mean_importance"],
                )
                self.connection.execute(
                    """
                    INSERT INTO memory_summaries (
                        id, created_at, updated_at, normalized_key,
                        representative_text, episode_count, total_deu, mean_importance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(normalized_key) DO UPDATE SET
                        updated_at = excluded.updated_at,
                        representative_text = excluded.representative_text,
                        episode_count = excluded.episode_count,
                        total_deu = excluded.total_deu,
                        mean_importance = excluded.mean_importance
                    """,
                    (
                        summary.id,
                        summary.created_at.isoformat(),
                        summary.updated_at.isoformat(),
                        summary.normalized_key,
                        summary.representative_text,
                        summary.episode_count,
                        summary.total_deu,
                        summary.mean_importance,
                    ),
                )
                if existing:
                    updated += 1
                else:
                    created += 1
                self.connection.execute(
                    """
                    UPDATE episodes SET archived = 1
                    WHERE normalized_content = ? AND sequence <> ?
                    """,
                    (group["normalized_content"], group["newest_sequence"]),
                )
        return created, updated

    def list_memory_summaries(self, limit: int = 100) -> list[MemorySummary]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT * FROM memory_summaries
                ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [MemorySummary.model_validate(dict(row)) for row in rows]


    def get_or_create_person_source(
        self,
        person_id: str,
        reliability: float,
    ) -> SourceRecord:
        source_id = f"person:{person_id}"
        existing = self.get_source(source_id)
        if existing is not None:
            updated = existing.model_copy(update={"reliability": reliability})
            self.save_source(updated)
            return updated
        source = SourceRecord(
            id=source_id,
            kind=SourceKind.CAREGIVER,
            name=f"Собеседник {person_id}",
            reliability=reliability,
            metadata={"person_id": person_id},
        )
        self.save_source(source)
        return source

    def save_identity(self, identity: IdentityProfile) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO identity (singleton_id, identity_json)
                VALUES (1, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    identity_json = excluded.identity_json
                """,
                (identity.model_dump_json(),),
            )

    def load_identity(self) -> IdentityProfile | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT identity_json FROM identity WHERE singleton_id = 1"
            ).fetchone()
        return None if row is None else IdentityProfile.model_validate_json(row["identity_json"])

    def save_genesis_event(self, event: GenesisEvent) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO genesis_events (id, created_at, event_json)
                VALUES (?, ?, ?)
                """,
                (event.id, event.created_at.isoformat(), event.model_dump_json()),
            )

    def latest_genesis_event(self) -> GenesisEvent | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT event_json FROM genesis_events ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return None if row is None else GenesisEvent.model_validate_json(row["event_json"])

    def save_goal(self, goal: Goal) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO goals (id, created_at, status, priority, goal_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    priority = excluded.priority,
                    goal_json = excluded.goal_json
                """,
                (
                    goal.id,
                    goal.created_at.isoformat(),
                    goal.status.value,
                    goal.priority,
                    goal.model_dump_json(),
                ),
            )

    def list_goals(self, limit: int = 100, active_only: bool = True) -> list[Goal]:
        condition = "WHERE status = 'active'" if active_only else ""
        with self._lock:
            rows = self.connection.execute(
                (
                    f"SELECT goal_json FROM goals {condition} "
                    "ORDER BY priority DESC, created_at ASC LIMIT ?"
                ),
                (limit,),
            ).fetchall()
        return [Goal.model_validate_json(row["goal_json"]) for row in rows]

    def save_relationship(self, relationship: RelationshipProfile) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO relationships (person_id, updated_at, relationship_json)
                VALUES (?, ?, ?)
                ON CONFLICT(person_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    relationship_json = excluded.relationship_json
                """,
                (
                    relationship.person_id,
                    relationship.updated_at.isoformat(),
                    relationship.model_dump_json(),
                ),
            )

    def load_relationship(self, person_id: str) -> RelationshipProfile | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT relationship_json FROM relationships WHERE person_id = ?",
                (person_id,),
            ).fetchone()
        return None if row is None else RelationshipProfile.model_validate_json(
            row["relationship_json"]
        )

    def save_trust_event(self, event: TrustEvent) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO trust_events (id, created_at, person_id, event_json)
                VALUES (?, ?, ?, ?)
                """,
                (event.id, event.created_at.isoformat(), event.person_id, event.model_dump_json()),
            )

    def save_decision(self, decision: AutonomyDecision) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO decisions (id, created_at, person_id, decision_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    decision.id,
                    decision.created_at.isoformat(),
                    decision.person_id,
                    decision.model_dump_json(),
                ),
            )

    def list_decisions(self, limit: int = 50) -> list[AutonomyDecision]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT decision_json FROM decisions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [AutonomyDecision.model_validate_json(row["decision_json"]) for row in rows]

    def save_research_report(self, report: ResearchReport) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO research_reports (id, created_at, status, report_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    report.id,
                    report.created_at.isoformat(),
                    report.status.value,
                    report.model_dump_json(),
                ),
            )

    def list_research_reports(self, limit: int = 50) -> list[ResearchReport]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT report_json FROM research_reports ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [ResearchReport.model_validate_json(row["report_json"]) for row in rows]

    def save_audit(self, event_type: str, payload: dict[str, object]) -> AuditEvent:
        event = AuditEvent(event_type=event_type, payload=payload)
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO audit_events (id, created_at, event_type, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.created_at.isoformat(),
                    event.event_type,
                    json.dumps(event.payload, ensure_ascii=False),
                ),
            )
        return event

    def list_audit(self, limit: int = 100) -> list[AuditEvent]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            AuditEvent(
                id=row["id"],
                created_at=row["created_at"],
                event_type=row["event_type"],
                payload=json.loads(row["payload_json"]),
            )
            for row in rows
        ]

    def save_conversation_message(self, message: ConversationMessage) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO conversation_messages (
                    id, created_at, person_id, role, content, intent,
                    decision_id, backend, model, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.created_at.isoformat(),
                    message.person_id,
                    message.role.value,
                    message.content,
                    None if message.intent is None else message.intent.value,
                    message.decision_id,
                    message.backend,
                    message.model,
                    json.dumps(message.metadata, ensure_ascii=False),
                ),
            )

    def recent_conversation(
        self,
        person_id: str,
        limit: int = 20,
    ) -> list[ConversationMessage]:
        if limit <= 0:
            return []
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT * FROM conversation_messages
                WHERE person_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (person_id, limit),
            ).fetchall()
        messages = [
            ConversationMessage(
                id=row["id"],
                created_at=row["created_at"],
                person_id=row["person_id"],
                role=ConversationRole(row["role"]),
                content=row["content"],
                intent=None if row["intent"] is None else row["intent"],
                decision_id=row["decision_id"],
                backend=row["backend"],
                model=row["model"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]
        return list(reversed(messages))

    def save_need(self, need: NeedState) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO needs (
                    kind, level, baseline, sensitivity, last_updated_sequence,
                    total_stimulation, need_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kind) DO UPDATE SET
                    level = excluded.level,
                    baseline = excluded.baseline,
                    sensitivity = excluded.sensitivity,
                    last_updated_sequence = excluded.last_updated_sequence,
                    total_stimulation = excluded.total_stimulation,
                    need_json = excluded.need_json
                """,
                (
                    need.kind.value,
                    need.level,
                    need.baseline,
                    need.sensitivity,
                    need.last_updated_sequence,
                    need.total_stimulation,
                    need.model_dump_json(),
                ),
            )

    def list_needs(self) -> list[NeedState]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT need_json FROM needs ORDER BY level DESC"
            ).fetchall()
        return [NeedState.model_validate_json(row["need_json"]) for row in rows]

    def save_cognitive_event(self, event: CognitiveEvent) -> CognitiveEvent:
        with self._lock:
            sequence = int(
                self.connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM cognitive_events"
                ).fetchone()[0]
            )
        stored = event.model_copy(update={"sequence": sequence})
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO cognitive_events (
                    id, created_at, kind, sequence, processed, event_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.id,
                    stored.created_at.isoformat(),
                    stored.kind.value,
                    stored.sequence,
                    int(stored.processed),
                    stored.model_dump_json(),
                ),
            )
        return stored

    def mark_cognitive_event_processed(self, event_id: str) -> None:
        with self._lock, self.connection:
            row = self.connection.execute(
                "SELECT event_json FROM cognitive_events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                return
            event = CognitiveEvent.model_validate_json(row["event_json"]).model_copy(
                update={"processed": True}
            )
            self.connection.execute(
                "UPDATE cognitive_events SET processed = 1, event_json = ? WHERE id = ?",
                (event.model_dump_json(), event_id),
            )

    def pending_cognitive_events(self, limit: int = 100) -> list[CognitiveEvent]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT event_json FROM cognitive_events
                WHERE processed = 0
                ORDER BY sequence ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [CognitiveEvent.model_validate_json(row["event_json"]) for row in rows]

    def recent_cognitive_events(self, limit: int = 100) -> list[CognitiveEvent]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT event_json FROM cognitive_events ORDER BY sequence DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [CognitiveEvent.model_validate_json(row["event_json"]) for row in rows]

    def save_cognitive_loop_status(self, status: CognitiveLoopStatus) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO cognitive_loop_state (singleton_id, status_json)
                VALUES (1, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET status_json = excluded.status_json
                """,
                (status.model_dump_json(),),
            )

    def load_cognitive_loop_status(self) -> CognitiveLoopStatus | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT status_json FROM cognitive_loop_state WHERE singleton_id = 1"
            ).fetchone()
        return None if row is None else CognitiveLoopStatus.model_validate_json(
            row["status_json"]
        )

    def save_budget(self, budget: ResourceBudget) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO resource_budgets (name, window_key, budget_json)
                VALUES (?, ?, ?)
                ON CONFLICT(name, window_key) DO UPDATE SET
                    budget_json = excluded.budget_json
                """,
                (budget.name, budget.window_key, budget.model_dump_json()),
            )

    def load_budget(self, name: str, window_key: str) -> ResourceBudget | None:
        with self._lock:
            row = self.connection.execute(
                """
                SELECT budget_json FROM resource_budgets
                WHERE name = ? AND window_key = ?
                """,
                (name, window_key),
            ).fetchone()
        return None if row is None else ResourceBudget.model_validate_json(row["budget_json"])

    def save_snapshot(self, snapshot: AgentSnapshot) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO agent_snapshot (
                    singleton_id, state_json, profile_json, emotion_json
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    profile_json = excluded.profile_json,
                    emotion_json = excluded.emotion_json
                """,
                (
                    snapshot.state.model_dump_json(),
                    snapshot.profile.model_dump_json(),
                    snapshot.emotion.model_dump_json(),
                ),
            )

    def load_snapshot(self) -> AgentSnapshot | None:
        with self._lock:
            row = self.connection.execute(
                """
                SELECT state_json, profile_json, emotion_json FROM agent_snapshot
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None:
            return None
        raw_emotion = row["emotion_json"] if "emotion_json" in row.keys() else "{}"
        try:
            emotion = EmotionState.model_validate_json(raw_emotion or "{}")
        except ValueError:
            emotion = EmotionState()
        return AgentSnapshot(
            state=AgentState.model_validate_json(row["state_json"]),
            profile=DevelopmentProfile.model_validate_json(row["profile_json"]),
            emotion=emotion,
        )

    def reset(self) -> None:
        with self._lock, self.connection:
            for table in (
                "resource_budgets",
                "cognitive_loop_state",
                "cognitive_events",
                "needs",
                "conversation_messages",
                "trust_events",
                "decisions",
                "research_reports",
                "audit_events",
                "relationships",
                "goals",
                "genesis_events",
                "identity",
                "evidence",
                "beliefs",
                "sources",
                "memory_summaries",
                "episodes",
                "agent_snapshot",
            ):
                self.connection.execute(f"DELETE FROM {table}")

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> SQLiteRepository:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
