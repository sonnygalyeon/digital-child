from __future__ import annotations

import os
import threading
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from digital_child.config import env_bool, env_float
from digital_child.storage import SQLiteRepository


class AgentClock:
    """UTC from HTTPS Date when available, monotonic elapsed time between syncs."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        self._lock = threading.RLock()
        saved = repository.load_runtime_state("clock")
        self.enabled = env_bool("DIGITAL_CHILD_TIME_SYNC", True)
        self.endpoint = os.environ.get("DIGITAL_CHILD_TIME_URL", "https://www.wikipedia.org/")
        self.timeout = max(0.2, min(10.0, env_float("DIGITAL_CHILD_TIME_TIMEOUT", 3.0)))
        self._offset = float(str(saved.get("offset_seconds", 0.0)))
        self._anchor = datetime.now(UTC) + timedelta(seconds=self._offset)
        self._monotonic = time.monotonic()
        self.last_sync_at = saved.get("last_sync_at")
        self.previous_launch_at = saved.get("last_launch_at")
        self.launch_at = self._anchor
        self.source = "cached_offset" if self.last_sync_at else "system"
        self.error: str | None = None
        self._persist()

    def now(self) -> datetime:
        with self._lock:
            return self._anchor + timedelta(seconds=max(0, time.monotonic() - self._monotonic))

    def sync(self) -> None:
        if not self.enabled:
            return
        try:
            if not self.endpoint.startswith("https://"):
                raise ValueError("Time endpoint must use HTTPS")
            started = time.monotonic()
            request = urllib.request.Request(
                self.endpoint, method="HEAD", headers={"Cache-Control": "no-cache"}
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if not response.geturl().startswith("https://"):
                    raise ValueError("Time endpoint redirected away from HTTPS")
                date = response.headers.get("Date")
                if date is None or int(response.headers.get("Age", "0")) > 60:
                    raise ValueError("Missing or stale server date")
                remote = parsedate_to_datetime(date).astimezone(UTC)
            elapsed = time.monotonic() - started
            remote += timedelta(seconds=elapsed / 2)
            with self._lock:
                self.launch_at += remote - self.now()
                self._anchor = remote
                self._monotonic = time.monotonic()
                self._offset = (remote - datetime.now(UTC)).total_seconds()
                self.last_sync_at = remote.isoformat()
                self.source = "https_date"
                self.error = None
        except (OSError, ValueError, OverflowError) as exc:
            with self._lock:
                self.error = str(exc)

    def _persist(self) -> None:
        self.repository.save_runtime_state(
            "clock",
            {
                "offset_seconds": self._offset,
                "last_sync_at": self.last_sync_at,
                "last_launch_at": self.launch_at.isoformat(),
            },
        )

    def checkpoint(self) -> None:
        with self._lock:
            self._persist()

    def diagnostics(self) -> dict[str, object]:
        with self._lock:
            return {
                "now": self.now().isoformat(),
                "source": self.source,
                "sync_enabled": self.enabled,
                "last_sync_at": self.last_sync_at,
                "last_launch_at": self.launch_at.isoformat(),
                "previous_launch_at": self.previous_launch_at,
                "error": self.error,
            }
