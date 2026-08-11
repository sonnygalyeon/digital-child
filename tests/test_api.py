from pathlib import Path

from fastapi.testclient import TestClient

from digital_child.api import create_app


def test_api_supports_beliefs_and_consolidation(tmp_path: Path) -> None:
    app = create_app(tmp_path / "api.db")
    with TestClient(app) as client:
        assert client.get("/health").json()["version"] == "0.5.0"
        payload = {
            "content": "Красная кнопка включает лампу",
            "source_kind": "caregiver",
            "raw_units": 5,
            "attention": 1,
            "comprehension": 1,
            "reliability": 1,
            "integration": 1,
            "practical_confirmation": 1,
            "domains": {"factual_knowledge": 1},
            "claims": [
                {
                    "claim": "Красная кнопка включает лампу",
                    "stance": "support",
                    "confidence": 1,
                }
            ],
        }
        response = client.post("/v1/observations", json=payload)
        assert response.status_code == 200
        assert len(client.get("/v1/beliefs").json()) == 1
        assert client.post("/v1/memory/consolidate").status_code == 200


def test_api_reset_requires_operator_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DIGITAL_CHILD_OPERATOR_TOKEN", "secret")
    app = create_app(tmp_path / "protected.db")
    with TestClient(app) as client:
        assert client.delete("/v1/state").status_code == 403
        assert (
            client.delete(
                "/v1/state",
                headers={"X-Operator-Token": "secret"},
            ).status_code
            == 204
        )
