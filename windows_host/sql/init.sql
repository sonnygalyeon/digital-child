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
);

CREATE INDEX IF NOT EXISTS idx_llm_request_audit_created_at
ON llm_request_audit (created_at DESC);
