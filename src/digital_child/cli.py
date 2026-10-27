"""Compatibility imports. Implementation: digital_child.interfaces.cli."""

from digital_child.application.commands import (
    HELP_TEXT,
    ChatCommandRouter,
    build_caregiver_observation,
)
from digital_child.interfaces.cli import (
    main,
    run_desktop_chat,
    run_plain_chat,
)

__all__ = [
    "ChatCommandRouter",
    "HELP_TEXT",
    "build_caregiver_observation",
    "main",
    "run_desktop_chat",
    "run_plain_chat",
]

if __name__ == "__main__":
    main()
