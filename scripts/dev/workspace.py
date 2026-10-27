"""Inspect workspace size or remove only known, regenerable cache directories."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHES = (".cache", ".mypy_cache", ".ruff_cache", ".pytest_cache")
CODE_ROOTS = ("src", "tests", "scripts", "packaging", "windows_host/src", "windows_host/tests")


def size(path: Path) -> int:
    if path.is_symlink():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def cache_paths() -> list[Path]:
    paths = [ROOT / name for name in CACHES]
    for name in CODE_ROOTS:
        base = ROOT / name
        if base.is_dir():
            paths.extend(base.rglob("__pycache__"))
    paths.extend([ROOT / ".DS_Store"])
    return [p for p in paths if p.exists() and not p.is_symlink() and not p.is_junction()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "clean"), nargs="?", default="inspect")
    args = parser.parse_args()
    if args.action == "inspect":
        for name in ("src", "docs", "tests", "data", ".venv", ".venv-build", ".git", ".cache"):
            path = ROOT / name
            if path.exists():
                print(f"{name:16s} {size(path) / 1024**2:9.2f} MiB")
        print(f"Regenerable caches: {sum(size(p) for p in cache_paths()) / 1024**2:.2f} MiB")
        return
    removed = 0
    for path in cache_paths():
        # Reject symlinked ancestors before any deletion.
        if not path.resolve().is_relative_to(ROOT) or any(
            parent.is_symlink() or parent.is_junction()
            for parent in path.parents if parent != ROOT
        ):
            raise ValueError(f"Cache points outside the workspace: {path}")
        removed += size(path)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    print(f"Removed {removed / 1024**2:.2f} MiB of regenerable caches.")


if __name__ == "__main__":
    main()
