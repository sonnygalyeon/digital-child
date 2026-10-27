"""Compatibility imports. Implementation: digital_child.interfaces.desktop.desktop_app."""

from digital_child.interfaces.desktop.desktop_app import (
    DesktopWindow,
    MessageCard,
    MessageInput,
    main,
    run_window,
)

__all__ = ["DesktopWindow", "MessageCard", "MessageInput", "main", "run_window"]

if __name__ == "__main__":
    main()
