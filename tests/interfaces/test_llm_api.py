from pathlib import Path

from fastapi.testclient import TestClient

from digital_child.interfaces.http.api import create_app


def test_llm_and_conversation_endpoints_exist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DIGITAL_CHILD_LLM_PROVIDER", "disabled")
    app = create_app(tmp_path / "api.db")
    with TestClient(app) as client:
        status = client.get("/v1/llm")
        assert status.status_code == 200
        assert status.json()["backend"] == "rule-based"

        response = client.post(
            "/v1/interactions",
            json={"text": "Привет", "person_id": "tester"},
        )
        assert response.status_code == 200

        history = client.get("/v1/conversation/tester")
        assert history.status_code == 200
        assert len(history.json()) == 2
