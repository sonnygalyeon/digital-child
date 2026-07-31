from digital_child_windows_host.models import AuditRecord
from digital_child_windows_host.storage import NullAuditStore


def test_null_store_is_safe() -> None:
    store = NullAuditStore()
    store.initialize()
    store.save(
        AuditRecord(
            client_id="test",
            model="qwen3:8b",
            streamed=True,
            status_code=200,
            duration_ms=10,
            request_bytes=100,
            response_bytes=200,
            content_sha256="0" * 64,
        )
    )
    assert store.healthy()
    assert store.recent() == []
