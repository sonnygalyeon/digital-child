from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx


class OllamaGateway:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def healthy(self) -> bool:
        try:
            response = await self.client.get(f"{self.base_url}/models")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def models(self) -> tuple[int, Any]:
        response = await self.client.get(f"{self.base_url}/models")
        return response.status_code, response.json()

    async def chat(self, payload: dict[str, Any]) -> tuple[int, bytes, str]:
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        return (
            response.status_code,
            response.content,
            response.headers.get("content-type", "application/json"),
        )

    async def stream_chat(self, payload: dict[str, Any]) -> AsyncIterator[bytes]:
        async with self.client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk
