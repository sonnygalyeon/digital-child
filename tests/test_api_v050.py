from pathlib import Path

from fastapi.testclient import TestClient

from digital_child.api import create_app


def test_api_exposes_cognitive_loop(tmp_path: Path) -> None:
    app = create_app(tmp_path / "api-v050.db")
    with TestClient(app) as client:
        assert client.get("/v1/needs").status_code == 200
        assert client.get("/v1/drives").status_code == 200
        assert client.get("/v1/background").json()["running"] is True
        assert client.post("/v1/background/pause").json()["paused"] is True
        assert client.post("/v1/background/resume").json()["paused"] is False
        assert client.post("/v1/background/tick").status_code == 200
        assert client.get("/v1/background/budgets").status_code == 200
