from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass

import httpx

from digital_child_windows_host.config import HostSettings


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    first_token_seconds: float
    total_seconds: float
    output_characters: int


def run_benchmark(
    settings: HostSettings,
    *,
    prompt: str,
    runs: int = 3,
) -> list[BenchmarkResult]:
    endpoint = f"http://127.0.0.1:{settings.port}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
        "X-Client-ID": "windows-local-benchmark",
    }
    payload = {
        "model": settings.default_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": min(256, settings.max_output_tokens),
        "reasoning_effort": settings.reasoning_effort,
        "temperature": 0.2,
    }
    results: list[BenchmarkResult] = []
    with httpx.Client(timeout=settings.request_timeout) as client:
        for _ in range(max(1, runs)):
            started = time.perf_counter()
            first_token: float | None = None
            output: list[str] = []
            with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        data = json.loads(raw)
                        content = data["choices"][0].get("delta", {}).get("content")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if content:
                        if first_token is None:
                            first_token = time.perf_counter()
                        output.append(str(content))
            finished = time.perf_counter()
            results.append(
                BenchmarkResult(
                    first_token_seconds=(first_token or finished) - started,
                    total_seconds=finished - started,
                    output_characters=len("".join(output)),
                )
            )
    return results


def format_benchmark(results: list[BenchmarkResult]) -> str:
    if not results:
        return "No benchmark results."
    first = [item.first_token_seconds for item in results]
    total = [item.total_seconds for item in results]
    chars = [item.output_characters for item in results]
    lines = [
        "Digital Child Windows Host benchmark",
        f"runs: {len(results)}",
        f"first token: mean={statistics.mean(first):.2f}s min={min(first):.2f}s max={max(first):.2f}s",
        f"total:       mean={statistics.mean(total):.2f}s min={min(total):.2f}s max={max(total):.2f}s",
        f"characters:  mean={statistics.mean(chars):.0f}",
    ]
    return "\n".join(lines)
