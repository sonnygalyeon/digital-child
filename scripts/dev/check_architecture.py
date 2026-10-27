"""Check local import targets and layer boundaries without importing application code."""

from __future__ import annotations

import ast
import sys
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"
PACKAGE = SOURCE / "digital_child"
FACADES = {"agent", "api", "cli", "desktop_app", "emotions", "llm", "models", "service", "storage"}
BUSINESS = {"cognition", "psychology", "memory", "learning", "planning", "inference"}
UI_LIBRARIES = {"PySide6", "fastapi", "uvicorn", "prompt_toolkit"}


def module_name(path: Path) -> str:
    parts = path.relative_to(SOURCE).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


class Imports(ast.NodeVisitor):
    def __init__(self, module: str, is_package: bool) -> None:
        self.package = module if is_package else module.rpartition(".")[0]
        self.typed = False
        self.found: list[tuple[str, bool, int]] = []

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        type_only = isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"
        type_only |= isinstance(node.test, ast.Attribute) and node.test.attr == "TYPE_CHECKING"
        previous = self.typed
        self.typed |= type_only
        for child in node.body:
            self.visit(child)
        self.typed = previous
        for child in node.orelse:
            self.visit(child)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        self.found.extend((item.name, self.typed, node.lineno) for item in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        name = node.module or ""
        if node.level:
            name = resolve_name("." * node.level + name, self.package)
        self.found.append((name, self.typed, node.lineno))


def main() -> int:
    paths = sorted(PACKAGE.rglob("*.py"))
    modules = {module_name(path): path for path in paths}
    graph: dict[str, set[str]] = {name: set() for name in modules}
    errors: list[str] = []
    for module, path in modules.items():
        parts = module.split(".")
        layer = parts[1] if len(parts) > 1 else ""
        facade = len(parts) == 2 and layer in FACADES
        visitor = Imports(module, path.name == "__init__.py")
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for target, typed, line in visitor.found:
            problem = ""
            if target.startswith("digital_child."):
                other = target.split(".")[1]
                if target not in modules:
                    problem = f"missing module {target}"
                elif not typed:
                    graph[module].add(target)
                if not facade and len(parts) > 2 and other in FACADES:
                    problem = f"internal code must use canonical modules, not facade {target}"
                if layer == "domain" and other != "domain":
                    problem = f"domain cannot depend on {target}"
                if (layer in BUSINESS or layer == "infrastructure") and other in {
                    "application",
                    "interfaces",
                }:
                    problem = f"{layer} cannot depend on {target}"
                if layer == "application" and other == "interfaces":
                    problem = f"application cannot depend on an interface: {target}"
            elif layer == "domain" and target.split(".")[0] not in (
                sys.stdlib_module_names | {"pydantic", "digital_child", "__future__"}
            ):
                problem = f"external dependency outside domain contract: {target}"
            elif layer in BUSINESS | {"domain", "application", "infrastructure"}:
                if target.split(".")[0] in UI_LIBRARIES:
                    problem = f"UI dependency outside interfaces: {target}"
            if problem:
                errors.append(f"{path.relative_to(ROOT)}:{line}: {problem}")

    active: list[str] = []
    visited: set[str] = set()

    def walk(module: str) -> None:
        if module in active:
            errors.append("import cycle: " + " -> ".join(active[active.index(module) :] + [module]))
            return
        if module in visited:
            return
        visited.add(module)
        active.append(module)
        for target in sorted(graph[module]):
            walk(target)
        active.pop()

    for module in sorted(graph):
        walk(module)
    if errors:
        print("\n".join(errors))
        return 1
    print(
        f"Architecture: {len(paths)} modules; local imports and layer boundaries valid; "
        "no import cycles."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
