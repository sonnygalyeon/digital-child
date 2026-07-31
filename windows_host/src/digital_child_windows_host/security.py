from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from digital_child_windows_host.config import HostSettings


def _extract_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.headers.get("x-api-key", "").strip()


def require_api_key(request: Request, settings: HostSettings) -> None:
    provided = _extract_token(request)
    if not provided or not hmac.compare_digest(provided, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
