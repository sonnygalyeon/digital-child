from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from digital_child_windows_host.config import HostSettings
from digital_child_windows_host.security import require_api_key


def settings() -> HostSettings:
    return HostSettings(
        bind="127.0.0.1",
        port=8787,
        api_key="abcdefghijklmnopqrstuvwxyz123456",
        ollama_base_url="http://127.0.0.1:11434/v1",
        default_model="qwen3:8b",
        allowed_models=frozenset({"qwen3:8b"}),
        request_timeout=30,
        max_request_bytes=1024,
        postgres_dsn=None,
        store_content=False,
        log_requests=False,
        instance_name="test",
    )


def test_bearer_auth() -> None:
    app = FastAPI()

    @app.get("/")
    def root(request: Request):
        require_api_key(request, settings())
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/").status_code == 401
    assert (
        client.get(
            "/", headers={"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456"}
        ).status_code
        == 200
    )
