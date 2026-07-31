from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from digital_child_windows_host.models import AuditRecord


class AuditStore(Protocol):
    @property
    def enabled(self) -> bool: ...

    def initialize(self) -> None: ...

    def healthy(self) -> bool: ...

    def save(self, record: AuditRecord) -> None: ...

    def recent(self, limit: int = 50) -> Sequence[dict[str, object]]: ...

    def close(self) -> None: ...


class NullAuditStore:
    enabled = False

    def initialize(self) -> None:
        return None

    def healthy(self) -> bool:
        return True

    def save(self, record: AuditRecord) -> None:
        return None

    def recent(self, limit: int = 50) -> Sequence[dict[str, object]]:
        return []

    def close(self) -> None:
        return None


class PostgresAuditStore:
    enabled = True

    def __init__(self, dsn: str) -> None:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "PostgreSQL logging is configured, but psycopg is not installed."
            ) from exc
        self._pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=4, open=False)

    def initialize(self) -> None:
        self._pool.open(wait=True)
        with self._pool.connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_request_audit (
                    id UUID PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL,
                    client_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    streamed BOOLEAN NOT NULL,
                    status_code INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    request_bytes INTEGER NOT NULL,
                    response_bytes INTEGER NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    error_type TEXT,
                    request_content JSONB
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_llm_request_audit_created_at
                ON llm_request_audit (created_at DESC)
                """
            )
            connection.commit()

    def healthy(self) -> bool:
        try:
            with self._pool.connection() as connection:
                return connection.execute("SELECT 1").fetchone() == (1,)
        except Exception:
            return False

    def save(self, record: AuditRecord) -> None:
        from psycopg.types.json import Jsonb

        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO llm_request_audit (
                    id, created_at, client_id, model, streamed, status_code,
                    duration_ms, request_bytes, response_bytes, content_sha256,
                    error_type, request_content
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.id,
                    record.created_at,
                    record.client_id,
                    record.model,
                    record.streamed,
                    record.status_code,
                    record.duration_ms,
                    record.request_bytes,
                    record.response_bytes,
                    record.content_sha256,
                    record.error_type,
                    Jsonb(record.request_content)
                    if record.request_content is not None
                    else None,
                ),
            )
            connection.commit()

    def recent(self, limit: int = 50) -> Sequence[dict[str, object]]:
        safe_limit = max(1, min(limit, 500))
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, client_id, model, streamed, status_code,
                       duration_ms, request_bytes, response_bytes, content_sha256,
                       error_type
                FROM llm_request_audit
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (safe_limit,),
            ).fetchall()
        return [
            {
                "id": str(row[0]),
                "created_at": row[1].isoformat(),
                "client_id": row[2],
                "model": row[3],
                "streamed": row[4],
                "status_code": row[5],
                "duration_ms": row[6],
                "request_bytes": row[7],
                "response_bytes": row[8],
                "content_sha256": row[9],
                "error_type": row[10],
            }
            for row in rows
        ]

    def close(self) -> None:
        self._pool.close()


def create_audit_store(dsn: str | None) -> AuditStore:
    return PostgresAuditStore(dsn) if dsn else NullAuditStore()
