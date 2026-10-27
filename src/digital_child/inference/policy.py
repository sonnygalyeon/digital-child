from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from digital_child.inference.types import ReplyContext
from digital_child.infrastructure.config import env_bool, env_float, env_int

Task = Literal[
    "reply", "rewrite", "analysis", "review", "memory", "sources", "initiative", "initiative_review"
]
_FOREGROUND: ContextVar[bool] = ContextVar("digital_child_foreground", default=False)


def visible_content(text: str) -> str:
    """Discard a provider's legacy leading thinking block, never send it to chat."""
    while match := re.match(r"\s*<(think|analysis)>[\s\S]*?</\1>\s*", text, re.I):
        text = text[match.end() :]
    if re.match(r"\s*<(think|analysis)>", text, re.I):
        raise RuntimeError("Модель завершила только служебное размышление без ответа")
    return text.strip()


@dataclass(frozen=True)
class RequestPlan:
    task: Task
    model: str
    effort: str
    max_tokens: int
    prompt_chars: int
    timeout: float


class InferencePolicy:
    def __init__(self, model: str, max_tokens: int, timeout: float, effort: str) -> None:
        self.model, self.max_tokens, self.timeout = model, max(32, max_tokens), max(1.0, timeout)
        self.fixed_effort = (
            effort if effort in {"none", "low", "medium", "high", "omit"} else "none"
        )
        self.fast_model = os.environ.get("DIGITAL_CHILD_LLM_FAST_MODEL", "").strip() or model
        self.deep_model = os.environ.get("DIGITAL_CHILD_LLM_REASONING_MODEL", "").strip()
        self.profile = os.environ.get("DIGITAL_CHILD_LLM_PROFILE", "balanced").strip().lower()
        if self.profile not in {"fast", "balanced", "deep"}:
            self.profile = "balanced"
        self.reasoning_mode = (
            os.environ.get(
                "DIGITAL_CHILD_LLM_REASONING_MODE",
                "fixed" if self.fixed_effort != "none" else "auto",
            )
            .strip()
            .lower()
        )
        if self.reasoning_mode not in {"auto", "off", "fixed"}:
            self.reasoning_mode = "auto"
        self.models: set[str] | None = None
        self._lock = threading.Lock()

    def update_models(self, models: list[str]) -> None:
        with self._lock:
            self.models = set(models) if models else None

    def resolve_model(self, candidate: str) -> str:
        with self._lock:
            return (
                self.model
                if self.models is not None and candidate not in self.models
                else candidate
            )

    def plan(self, task: Task, context: ReplyContext | None = None) -> RequestPlan:
        prompt_chars = max(1600, env_int("DIGITAL_CHILD_LLM_PROMPT_MAX_CHARS", 7000))
        analysis_timeout = max(
            1.0, min(self.timeout, env_float("DIGITAL_CHILD_ANALYSIS_TIMEOUT", 10.0))
        )
        effort, model = "none", self.fast_model
        limits: dict[Task, int] = {
            "analysis": 400,
            "review": 200,
            "memory": 120,
            "sources": 600,
            "initiative": 160,
            "initiative_review": 200,
            "reply": self.max_tokens,
            "rewrite": self.max_tokens,
        }
        tokens = limits[task]
        timeout = analysis_timeout
        if task in {"analysis", "review", "memory", "sources", "initiative_review"}:
            role = "review" if task == "initiative_review" else task
            model = os.environ.get(f"DIGITAL_CHILD_LLM_{role.upper()}_MODEL", "").strip() or model
        if task == "sources":
            timeout = min(
                self.timeout, max(1.0, env_float("DIGITAL_CHILD_LLM_SOURCES_TIMEOUT", 30.0))
            )
        elif task == "initiative":
            timeout = min(
                self.timeout, max(1.0, env_float("DIGITAL_CHILD_LLM_INITIATIVE_TIMEOUT", 30.0))
            )
            prompt_chars = min(prompt_chars, 4200)
        elif task in {"reply", "rewrite"}:
            assert context is not None
            text = context.analysis.text
            social = context.analysis.intent.value == "social" and len(text.split()) <= 12
            complex_task = (
                not social
                and context.decision.decision.value != "refuse"
                and self.profile != "fast"
                and (
                    self.profile == "deep"
                    or len(text) > 700
                    or "```" in text
                    or bool(
                        re.search(
                            r"докажи|выведи формул|найди ошиб|разбер[иие].*код|"
                            r"сравни.*(?:подход|алгоритм)|пошагов.*реш|обдумай|подумай глубже",
                            text,
                            re.I,
                        )
                    )
                )
            )
            tokens = min(
                self.max_tokens,
                160
                if social or context.max_reply_chars <= 700
                else 256
                if self.profile == "fast"
                else 384,
            )
            if not social and (complex_task or context.max_reply_chars > 2400):
                tokens = self.max_tokens
            prompt_chars = min(prompt_chars, 4200 if social else 5500 if not complex_task else 7000)
            model = (self.deep_model or self.model) if complex_task else self.fast_model
            if self.reasoning_mode == "fixed":
                effort = self.fixed_effort
            elif self.reasoning_mode == "auto" and complex_task and self.deep_model:
                effort = os.environ.get("DIGITAL_CHILD_LLM_DEEP_REASONING_EFFORT", "low").lower()
                if effort not in {"low", "medium", "high"}:
                    effort = "low"
                tokens = max(32, env_int("DIGITAL_CHILD_LLM_DEEP_MAX_TOKENS", self.max_tokens))
            timeout = self.timeout
        if task == "rewrite":
            model, effort = self.fast_model, "none"
            tokens, prompt_chars = min(self.max_tokens, 384), min(prompt_chars, 5500)
        candidate = model
        model = self.resolve_model(model)
        if model != candidate:
            tokens = min(tokens, self.max_tokens)
        # Falling back to a fast model must not accidentally turn on expensive thinking.
        if (
            self.reasoning_mode == "off"
            or "instruct" in model.lower()
            or (self.deep_model and model != self.deep_model and self.reasoning_mode != "fixed")
        ):
            effort = "none"
        if not env_bool("DIGITAL_CHILD_LLM_SEND_REASONING_EFFORT", True):
            effort = "omit"
        return RequestPlan(task, model, effort, tokens, prompt_chars, timeout)

    def diagnostics(self) -> dict[str, object]:
        with self._lock:
            available = None if self.models is None else sorted(self.models)
        return {
            "profile": self.profile,
            "main_model": self.model,
            "fast_model": self.fast_model,
            "reasoning_model": self.deep_model or None,
            "reasoning_mode": self.reasoning_mode,
            "roles": {
                role: os.environ.get(f"DIGITAL_CHILD_LLM_{role.upper()}_MODEL", "").strip()
                or self.fast_model
                for role in ("analysis", "review", "memory", "sources")
            },
            "available_models": available,
        }


class InferenceRuntime:
    """One local inference slot, foreground precedence, bounded content-free metrics."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active = False
        self._waiting = 0
        self._foreground_sessions = 0
        self._history: deque[dict[str, object]] = deque(maxlen=100)
        self._reply: ContextVar[dict[str, object] | None] = ContextVar(
            "reply_inference", default=None
        )
        self._blocked_until = 0.0

    @contextmanager
    def foreground(self) -> Iterator[None]:
        token = _FOREGROUND.set(True)
        with self._condition:
            self._foreground_sessions += 1
        try:
            yield
        finally:
            _FOREGROUND.reset(token)
            with self._condition:
                self._foreground_sessions -= 1
                self._condition.notify_all()

    def connectivity_failed(self) -> None:
        with self._condition:
            self._blocked_until = time.monotonic() + max(
                0.0, env_float("DIGITAL_CHILD_LLM_FAILURE_COOLDOWN", 20.0)
            )

    def connectivity_ok(self) -> None:
        with self._condition:
            self._blocked_until = 0.0

    @contextmanager
    def _slot(self, priority: bool) -> Iterator[float]:
        started = time.monotonic()
        timeout = max(0.0, env_float("DIGITAL_CHILD_LLM_QUEUE_TIMEOUT", 10.0)) if priority else 0.0
        with self._condition:
            if time.monotonic() < self._blocked_until:
                raise RuntimeError("LLM временно пропускается после ошибки соединения")
            if priority:
                self._waiting += 1
            try:
                while self._active or (
                    not priority and (self._waiting or self._foreground_sessions)
                ):
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise RuntimeError(
                            "LLM занята; фоновая задача отложена или очередь истекла"
                        )
                    self._condition.wait(remaining)
                if time.monotonic() < self._blocked_until:
                    raise RuntimeError("LLM временно пропускается после ошибки соединения")
                self._active = True
            finally:
                if priority:
                    self._waiting -= 1
        try:
            yield round((time.monotonic() - started) * 1000, 2)
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()

    @contextmanager
    def request(self, task: Task, body: dict[str, object]) -> Iterator[dict[str, object]]:
        started = time.monotonic()
        record: dict[str, object] = {
            "task": task,
            "model": body.get("model"),
            "effort": body.get("reasoning_effort", "omitted"),
            "max_tokens": body.get("max_tokens"),
            "status": "cancelled",
            "first_content_ms": None,
        }
        priority = _FOREGROUND.get() or task in {"reply", "rewrite", "analysis", "review"}
        try:
            with self._slot(priority) as queue_ms:
                record["queue_ms"] = queue_ms
                yield record
                record["status"] = "ok"
        except Exception:
            record["status"] = "error"
            raise
        finally:
            record["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
            with self._condition:
                self._history.append(dict(record))
            if task in {"reply", "rewrite", "initiative"}:
                self._reply.set(dict(record))

    def reply_metadata(self) -> dict[str, object]:
        return dict(self._reply.get() or {})

    def diagnostics(self) -> dict[str, object]:
        with self._condition:
            rows = list(self._history)
            blocked = max(0.0, self._blocked_until - time.monotonic())
        by_task: dict[str, dict[str, float | int]] = {}
        for row in rows:
            task = str(row["task"])
            stats = by_task.setdefault(task, {"calls": 0, "errors": 0, "duration_ms": 0.0})
            stats["calls"] += 1
            stats["errors"] += int(row["status"] == "error")
            stats["duration_ms"] += float(str(row["duration_ms"]))
        for stats in by_task.values():
            stats["mean_ms"] = round(stats.pop("duration_ms") / stats["calls"], 2)
        return {
            "recent_requests": rows[-10:],
            "by_task": by_task,
            "failure_cooldown_seconds": round(blocked, 2),
        }
