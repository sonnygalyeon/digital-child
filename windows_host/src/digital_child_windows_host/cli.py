from __future__ import annotations

import argparse

import uvicorn

from digital_child_windows_host.api import create_app
from digital_child_windows_host.config import HostSettings


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="digital-child-host",
        description="Run the authenticated Windows LLM host gateway.",
    )
    parser.add_argument("--env", default=".env", help="Path to host .env file")
    parser.add_argument("--reload", action="store_true", help="Enable development reload")
    args = parser.parse_args()

    settings = HostSettings.from_env(args.env)
    uvicorn.run(
        create_app(settings),
        host=settings.bind,
        port=settings.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
