from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class HostSettings:
    bind: str
    port: int
    api_key: str
    ollama_base_url: str
    default_model: str
    allowed_models: frozenset[str]
    request_timeout: float
    max_request_bytes: int
    postgres_dsn: str | None
    store_content: bool
    log_requests: bool
    instance_name: str
    ollama_native_url: str = "http://127.0.0.1:11434"
    max_output_tokens: int = 768
    reasoning_effort: str = "none"
    warmup_on_start: bool = True

    @classmethod
    def from_env(cls, dotenv_path: str | Path = ".env") -> HostSettings:
        load_dotenv(dotenv_path)
        key = os.environ.get("WINDOWS_HOST_API_KEY", "").strip()
        if len(key) < 24:
            raise RuntimeError(
                "WINDOWS_HOST_API_KEY must contain at least 24 characters. "
                "Run scripts/windows/setup_windows_host.ps1 to generate it."
            )

        default_model = os.environ.get(
            "WINDOWS_HOST_DEFAULT_MODEL", "digital-child-fast"
        ).strip()
        allowed_raw = os.environ.get("WINDOWS_HOST_ALLOWED_MODELS", default_model)
        allowed_models = frozenset(
            item.strip() for item in allowed_raw.split(",") if item.strip()
        )
        if default_model not in allowed_models:
            allowed_models = frozenset((*allowed_models, default_model))

        dsn = os.environ.get("WINDOWS_HOST_POSTGRES_DSN", "").strip() or None
        reasoning = os.environ.get("WINDOWS_HOST_REASONING_EFFORT", "none").strip().lower()
        if reasoning not in {"none", "low", "medium", "high"}:
            reasoning = "none"
        return cls(
            bind=os.environ.get("WINDOWS_HOST_BIND", "0.0.0.0").strip(),
            port=int(os.environ.get("WINDOWS_HOST_PORT", "8787")),
            api_key=key,
            ollama_base_url=os.environ.get(
                "WINDOWS_HOST_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"
            ).rstrip("/"),
            ollama_native_url=os.environ.get(
                "WINDOWS_HOST_OLLAMA_NATIVE_URL", "http://127.0.0.1:11434"
            ).rstrip("/"),
            default_model=default_model,
            allowed_models=allowed_models,
            request_timeout=float(os.environ.get("WINDOWS_HOST_REQUEST_TIMEOUT", "180")),
            max_request_bytes=int(
                os.environ.get("WINDOWS_HOST_MAX_REQUEST_BYTES", "2097152")
            ),
            max_output_tokens=max(
                64, int(os.environ.get("WINDOWS_HOST_MAX_OUTPUT_TOKENS", "768"))
            ),
            reasoning_effort=reasoning,
            warmup_on_start=env_bool("WINDOWS_HOST_WARMUP_ON_START", True),
            postgres_dsn=dsn,
            store_content=env_bool("WINDOWS_HOST_STORE_CONTENT", False),
            log_requests=env_bool("WINDOWS_HOST_LOG_REQUESTS", True),
            instance_name=os.environ.get(
                "WINDOWS_HOST_INSTANCE_NAME", "windows-llm-host"
            ).strip(),
        )
