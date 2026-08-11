from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from digital_child_windows_host import __version__
from digital_child_windows_host.config import HostSettings
from digital_child_windows_host.models import AuditRecord, HostStatus
from digital_child_windows_host.ollama import OllamaGateway
from digital_child_windows_host.security import require_api_key
from digital_child_windows_host.storage import AuditStore, create_audit_store
from digital_child_windows_host.system_info import logical_cpu_count, total_memory_gib


def _content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _client_id(request: Request, settings: HostSettings) -> str:
    explicit = request.headers.get("x-client-id", "").strip()
    if explicit:
        return explicit[:128]
    host = request.client.host if request.client else "unknown"
    return f"{settings.instance_name}:{host}"


def _safe_payload_for_storage(
    payload: dict[str, Any], store_content: bool
) -> dict[str, Any] | None:
    return payload if store_content else None


def _prepare_payload(payload: dict[str, Any], settings: HostSettings) -> dict[str, Any]:
    prepared = dict(payload)
    model = str(prepared.get("model") or settings.default_model)
    if model not in settings.allowed_models:
        raise HTTPException(
            status_code=403,
            detail=f"Model '{model}' is not allowed on this host.",
        )
    prepared["model"] = model

    requested_tokens = prepared.get("max_tokens", settings.max_output_tokens)
    try:
        requested_tokens = int(requested_tokens)
    except (TypeError, ValueError):
        requested_tokens = settings.max_output_tokens
    prepared["max_tokens"] = max(16, min(requested_tokens, settings.max_output_tokens))

    # Ollama's OpenAI compatibility supports reasoning_effort. CPU mode defaults to none.
    prepared.setdefault("reasoning_effort", settings.reasoning_effort)
    if prepared.get("stream"):
        prepared.setdefault("stream_options", {"include_usage": True})
    return prepared


async def _safe_save(store: AuditStore, record: AuditRecord) -> None:
    try:
        await asyncio.to_thread(store.save, record)
    except Exception:
        # Audit storage must never make model inference unavailable.
        return


def create_app(settings: HostSettings | None = None) -> FastAPI:
    resolved = settings or HostSettings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        gateway = OllamaGateway(
            resolved.ollama_base_url,
            resolved.ollama_native_url,
            resolved.request_timeout,
        )
        store = create_audit_store(resolved.postgres_dsn)
        await asyncio.to_thread(store.initialize)
        application.state.settings = resolved
        application.state.gateway = gateway
        application.state.store = store
        warmup_task: asyncio.Task[bool] | None = None
        if resolved.warmup_on_start:
            warmup_task = asyncio.create_task(gateway.warmup(resolved.default_model))
        application.state.warmup_task = warmup_task
        try:
            yield
        finally:
            if warmup_task and not warmup_task.done():
                warmup_task.cancel()
            await gateway.close()
            await asyncio.to_thread(store.close)

    app = FastAPI(
        title="Digital Child Windows LLM Host",
        version=__version__,
        description=(
            "Authenticated OpenAI-compatible LAN gateway with CPU-oriented limits, "
            "model warmup and optional PostgreSQL performance audit."
        ),
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HostStatus)
    async def health(request: Request) -> HostStatus:
        gateway: OllamaGateway = request.app.state.gateway
        store: AuditStore = request.app.state.store
        ollama_healthy, database_healthy = await asyncio.gather(
            gateway.healthy(), asyncio.to_thread(store.healthy)
        )
        return HostStatus(
            status="ok" if ollama_healthy and database_healthy else "degraded",
            version=__version__,
            instance_name=resolved.instance_name,
            ollama_healthy=ollama_healthy,
            database_enabled=store.enabled,
            database_healthy=database_healthy,
            default_model=resolved.default_model,
            allowed_models=sorted(resolved.allowed_models),
            logical_cpu_count=logical_cpu_count(),
            total_memory_gib=total_memory_gib(),
            reasoning_effort=resolved.reasoning_effort,
            max_output_tokens=resolved.max_output_tokens,
            warmup_on_start=resolved.warmup_on_start,
        )

    @app.get("/v1/models")
    async def models(request: Request):
        require_api_key(request, resolved)
        gateway: OllamaGateway = request.app.state.gateway
        try:
            code, payload = await gateway.models()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=f"Ollama unavailable: {exc}") from exc

        if code != 200:
            return JSONResponse(status_code=code, content=payload)
        data = [
            item
            for item in payload.get("data", [])
            if str(item.get("id", "")) in resolved.allowed_models
        ]
        return {"object": "list", "data": data}

    @app.post("/v1/host/warmup")
    async def warmup(request: Request):
        require_api_key(request, resolved)
        gateway: OllamaGateway = request.app.state.gateway
        ok = await gateway.warmup(resolved.default_model)
        return {"ok": ok, "model": resolved.default_model}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        require_api_key(request, resolved)
        body = await request.body()
        if len(body) > resolved.max_request_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Request body exceeds configured limit.",
            )
        try:
            raw_payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
        if not isinstance(raw_payload, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object.")

        payload = _prepare_payload(raw_payload, resolved)
        model = str(payload["model"])
        streamed = bool(payload.get("stream", False))
        started = time.perf_counter()
        request_hash = _content_hash(body)
        client_id = _client_id(request, resolved)
        gateway: OllamaGateway = request.app.state.gateway
        store: AuditStore = request.app.state.store

        if streamed:

            async def iterator():
                response_bytes = 0
                status_code = 200
                error_type: str | None = None
                first_token_ms: int | None = None
                try:
                    async for chunk in gateway.stream_chat(payload):
                        if first_token_ms is None:
                            first_token_ms = int((time.perf_counter() - started) * 1000)
                        response_bytes += len(chunk)
                        yield chunk
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    error_type = type(exc).__name__
                    message = json.dumps(
                        {"error": {"message": str(exc), "type": "upstream_error"}}
                    ).encode("utf-8")
                    response_bytes += len(message)
                    yield b"data: " + message + b"\n\n"
                except httpx.HTTPError as exc:
                    status_code = 502
                    error_type = type(exc).__name__
                    message = json.dumps(
                        {"error": {"message": str(exc), "type": "gateway_error"}}
                    ).encode("utf-8")
                    response_bytes += len(message)
                    yield b"data: " + message + b"\n\n"
                finally:
                    if resolved.log_requests:
                        await _safe_save(
                            store,
                            AuditRecord(
                                client_id=client_id,
                                model=model,
                                streamed=True,
                                status_code=status_code,
                                duration_ms=int((time.perf_counter() - started) * 1000),
                                first_token_ms=first_token_ms,
                                request_bytes=len(body),
                                response_bytes=response_bytes,
                                content_sha256=request_hash,
                                error_type=error_type,
                                request_content=_safe_payload_for_storage(
                                    payload, resolved.store_content
                                ),
                            ),
                        )

            return StreamingResponse(
                iterator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "X-Digital-Child-Host": __version__,
                    "X-Digital-Child-Model": model,
                },
            )

        response_bytes = 0
        status_code = 502
        error_type: str | None = None
        try:
            status_code, content, content_type = await gateway.chat(payload)
            response_bytes = len(content)
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = {"error": {"message": content.decode("utf-8", errors="replace")}}
            return JSONResponse(
                status_code=status_code,
                content=parsed,
                media_type=content_type,
                headers={
                    "X-Digital-Child-Host": __version__,
                    "X-Digital-Child-Model": model,
                },
            )
        except httpx.HTTPError as exc:
            error_type = type(exc).__name__
            raise HTTPException(status_code=502, detail=f"Ollama unavailable: {exc}") from exc
        finally:
            if resolved.log_requests:
                await _safe_save(
                    store,
                    AuditRecord(
                        client_id=client_id,
                        model=model,
                        streamed=False,
                        status_code=status_code,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        first_token_ms=None,
                        request_bytes=len(body),
                        response_bytes=response_bytes,
                        content_sha256=request_hash,
                        error_type=error_type,
                        request_content=_safe_payload_for_storage(
                            payload, resolved.store_content
                        ),
                    ),
                )

    @app.get("/v1/host/audit/recent")
    async def recent_audit(request: Request, limit: int = 50):
        require_api_key(request, resolved)
        store: AuditStore = request.app.state.store
        if not store.enabled:
            return {"enabled": False, "items": []}
        items = await asyncio.to_thread(store.recent, limit)
        return {"enabled": True, "items": list(items)}

    return app
