from digital_child_windows_host.api import _prepare_payload
from digital_child_windows_host.config import HostSettings


def settings() -> HostSettings:
    return HostSettings(
        bind="127.0.0.1",
        port=8787,
        api_key="abcdefghijklmnopqrstuvwxyz123456",
        ollama_base_url="http://127.0.0.1:11434/v1",
        default_model="digital-child-fast",
        allowed_models=frozenset({"digital-child-fast"}),
        request_timeout=30,
        max_request_bytes=1024,
        postgres_dsn=None,
        store_content=False,
        log_requests=False,
        instance_name="test",
        max_output_tokens=512,
        reasoning_effort="none",
    )


def test_payload_is_cpu_limited() -> None:
    payload = _prepare_payload(
        {
            "model": "digital-child-fast",
            "stream": True,
            "max_tokens": 5000,
            "messages": [{"role": "user", "content": "Привет"}],
        },
        settings(),
    )
    assert payload["max_tokens"] == 512
    assert payload["reasoning_effort"] == "none"
    assert payload["stream_options"] == {"include_usage": True}
