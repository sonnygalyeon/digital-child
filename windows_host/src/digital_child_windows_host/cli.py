from __future__ import annotations

import argparse

import uvicorn

from digital_child_windows_host.api import create_app
from digital_child_windows_host.benchmark import format_benchmark, run_benchmark
from digital_child_windows_host.config import HostSettings


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="digital-child-host",
        description="Run or benchmark the authenticated Windows LLM host gateway.",
    )
    parser.add_argument("--env", default=".env", help="Path to host .env file")
    parser.add_argument("--reload", action="store_true", help="Enable development reload")
    parser.add_argument("--benchmark", action="store_true", help="Benchmark a running host")
    parser.add_argument(
        "--prompt",
        default="Кратко объясни, почему небо голубое.",
        help="Benchmark prompt",
    )
    parser.add_argument("--runs", type=int, default=3, help="Benchmark repetitions")
    args = parser.parse_args()

    settings = HostSettings.from_env(args.env)
    if args.benchmark:
        results = run_benchmark(settings, prompt=args.prompt, runs=args.runs)
        print(format_benchmark(results))
        return

    uvicorn.run(
        create_app(settings),
        host=settings.bind,
        port=settings.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
