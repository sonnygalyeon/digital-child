from pathlib import Path

from digital_child_windows_host.config import HostSettings


def test_settings_load_from_dotenv(tmp_path: Path, monkeypatch) -> None:
    for name in list(__import__("os").environ):
        if name.startswith("WINDOWS_HOST_"):
            monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "WINDOWS_HOST_API_KEY=abcdefghijklmnopqrstuvwxyz123456",
                "WINDOWS_HOST_DEFAULT_MODEL=qwen3:8b",
                "WINDOWS_HOST_ALLOWED_MODELS=qwen3:8b,qwen3:4b",
            ]
        ),
        encoding="utf-8",
    )
    settings = HostSettings.from_env(env)
    assert settings.default_model == "qwen3:8b"
    assert "qwen3:4b" in settings.allowed_models
