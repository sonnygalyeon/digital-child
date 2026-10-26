from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from digital_child.config import load_dotenv

_configured = False


def configure_packaged_app() -> None:
    """Frozen releases never depend on the shortcut's current directory."""
    global _configured
    if _configured or not getattr(sys, "frozen", False):
        return
    override = os.environ.get("DIGITAL_CHILD_HOME")
    base = (
        Path(override).expanduser()
        if override
        else (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
            / "DigitalChild"
        )
    )
    if not base.is_absolute():
        raise ValueError("DIGITAL_CHILD_HOME должен быть абсолютным путём")
    base = base.resolve()
    base.mkdir(parents=True, exist_ok=True)
    os.environ["DIGITAL_CHILD_HOME"] = str(base)
    load_dotenv(base / ".env")
    database = Path(os.environ.get("DIGITAL_CHILD_DB", "data/digital_child.db"))
    if not database.is_absolute():
        database = base / database
    os.environ["DIGITAL_CHILD_DB"] = str(database)
    logs = base / "logs"
    logs.mkdir(exist_ok=True)
    # Separate parent/worker files avoid concurrent rotation of the same log.
    role = "desktop" if multiprocessing.current_process().name == "MainProcess" else "agent"
    handler = RotatingFileHandler(
        logs / f"{role}.log",
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _configured = True
