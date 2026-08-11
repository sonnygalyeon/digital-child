from __future__ import annotations

import os
import sys


def configure_utf8_console() -> None:
    """Best-effort UTF-8 console setup for Windows and redirected terminals."""
    if os.name == "nt":
        # prompt_toolkit uses the Windows console API, but UTF-8 still helps redirected I/O.
        os.system("chcp 65001 > nul")
        os.environ.setdefault("PYTHONUTF8", "1")
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
