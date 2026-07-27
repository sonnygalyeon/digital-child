from pathlib import Path

from fastapi.testclient import TestClient

from digital_child.api import create_app


def test_health_endpoint(tmp_path: Path) -> None:
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_observation_endpoint(tmp_path: Path) -> None:
    app = create_app(tmp_path / "api-observation.db")
    payload = {
        "content": "A red button turns on a lamp",
        "source_kind": "environment",
        "raw_units": 8,
        "novelty": 0.9,
        "attention": 0.8,
        "comprehension": 0.7,
        "reliability": 1.0,
        "integration": 0.6,
        "practical_confirmation": 1.0,
        "domains": {"causal_reasoning": 1.0},
    }

    with TestClient(app) as client:
        response = client.post("/v1/observations", json=payload)

    assert response.status_code == 200
    assert response.json()["assessment"]["effective_units"] > 0
