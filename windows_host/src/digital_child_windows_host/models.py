from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class HostStatus(BaseModel):
    status: str
    version: str
    instance_name: str
    ollama_healthy: bool
    database_enabled: bool
    database_healthy: bool
    default_model: str
    allowed_models: list[str]
    logical_cpu_count: int | None
    total_memory_gib: float | None
    reasoning_effort: str = "none"
    max_output_tokens: int = 768
    warmup_on_start: bool = True


class AuditRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    client_id: str
    model: str
    streamed: bool
    status_code: int
    duration_ms: int
    first_token_ms: int | None = None
    request_bytes: int
    response_bytes: int
    content_sha256: str
    error_type: str | None = None
    request_content: dict[str, Any] | None = None
