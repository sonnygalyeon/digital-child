from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from pydantic import Field

from digital_child.domain.models import StrictModel
from digital_child.memory.associative_memory import AssociativeMemory


class ToolResult(StrictModel):
    summary: str
    episode_ids: list[str] = Field(default_factory=list)
    content: str = ""
    sha256: str = ""
    file_name: str = ""
    verified: bool = False
    # An observed operation does not establish counterfactual causality.
    causal_confidence: float = 0.0


class ProjectTools:
    """Three local tools; filenames are internal IDs, never user-supplied paths."""

    def __init__(self, root: Path, memory: AssociativeMemory) -> None:
        self.root, self.memory = root.absolute(), memory

    @staticmethod
    def digest(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _path(self, project_id: str, step_id: str) -> Path:
        for value in (project_id, step_id):
            if re.fullmatch(r"[0-9a-f-]{36}", value) is None:
                raise ValueError("Некорректный идентификатор файла проекта")
        # Reject existing links/reparse points at every component, including root.
        for component in (*reversed(self.root.parents), self.root):
            if component.is_symlink() or component.is_junction():
                raise ValueError("Рабочий каталог не должен содержать ссылки")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{project_id}-{step_id}.md"
        if path.is_symlink() or path.is_junction():
            raise ValueError("Файл проекта не должен быть ссылкой")
        return path

    def search(self, query: str, person_id: str) -> ToolResult:
        matches = self.memory.search(query[:2000], person_id, 8, semantic=False)
        content = "\n\n".join(
            f"Источник {item.episode.id}:\n{item.episode.content[:1500]}" for item in matches
        )
        if not matches:
            content = "В доступной индексированной памяти подходящих эпизодов не найдено."
        return ToolResult(
            summary=f"Найдено эпизодов: {len(matches)}",
            content=content,
            episode_ids=[item.episode.id for item in matches],
            verified=True,
        )

    def write(self, project_id: str, step_id: str, content: str) -> ToolResult:
        if len(content.encode("utf-8")) > 64_000:
            raise ValueError("Заметка превышает 64 КБ")
        path = self._path(project_id, step_id)
        expected = self.digest(content)
        # A crash can leave a partial file. Never overwrite it silently.
        try:
            with path.open("x", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if self._read(path) != content:
                raise ValueError(
                    "Файл уже существует с другим содержимым; шаг остановлен"
                ) from None
        return ToolResult(
            summary="Заметка записана",
            sha256=expected,
            file_name=path.name,
        )

    @staticmethod
    def _read(path: Path) -> str:
        with path.open("rb") as stream:
            payload = stream.read(64_001)
        if len(payload) > 64_000:
            raise ValueError("Файл превышает 64 КБ")
        return payload.decode("utf-8")

    def read(self, project_id: str, step_id: str, expected: str) -> ToolResult:
        path = self._path(project_id, step_id)
        content = self._read(path)
        digest = self.digest(content)
        if digest != expected:
            raise ValueError("Содержимое файла изменилось: контрольная сумма не совпала")
        return ToolResult(
            summary="Заметка прочитана; контрольная сумма совпала",
            content=content,
            sha256=digest,
            file_name=path.name,
            verified=True,
        )
