from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from hashlib import sha256

from pydantic import Field

from digital_child.config import env_bool
from digital_child.models import Episode, ResearchReport, StrictModel
from digital_child.storage import SQLiteRepository

# Shared concepts give offline recall more than exact word matching. Optional LLM
# labels extend this small vocabulary; labels remain retrieval hints, never facts.
_CONCEPTS = {
    "learning": r"уч[иие]|обуч|навык|осво|тренир|learn|skill",
    "uncertainty": r"сомне|не уверен|непонят|неизвест|не зна|uncertain",
    "fatigue": r"устал|утом|нагруз|отдох|перерыв|пауз|fatigue|rest",
    "causality": r"причин|следств|прогноз|эксперимент|движени|experiment|predict",
    "evidence": r"доказ|свидетел|источник|провер|подтверж|evidence|verify",
    "relationship": r"довер|общени|контакт|друж|разговор|trust|friend",
    "autonomy": r"самостоят|выбор|границ|давлен|приказ|autonomy|choice",
    "error": r"ошиб|неверн|неправ|исправ|error|mistake",
}


def concepts(text: str) -> list[str]:
    lowered = text.casefold().replace("ё", "е")
    return [key for key, pattern in _CONCEPTS.items() if re.search(pattern, lowered)]


def features(text: str, labels: list[str]) -> set[str]:
    words = re.findall(r"[а-яa-z]{4,}", text.casefold().replace("ё", "е"))
    return {"word:" + word[:6] for word in words} | {
        "concept:" + label.casefold().strip() for label in labels if label.strip()
    }


class SemanticLabels(StrictModel):
    concepts: list[str] = Field(default_factory=list, max_length=12)


class MemoryAssociation(StrictModel):
    episode_id: str
    person_id: str | None = None
    concepts: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    belief_ids: list[str] = Field(default_factory=list)
    decision: str = ""
    consequences: list[str] = Field(default_factory=list, max_length=12)


class MemoryMatch(StrictModel):
    episode: Episode
    score: float
    shared_concepts: list[str]
    belief_ids: list[str]
    decision: str = ""
    consequences: list[str] = Field(default_factory=list)


class AssociativeMemory:
    def __init__(
        self,
        repository: SQLiteRepository,
        subject_id: str,
        backend: object,
        allow_analysis: Callable[[], bool],
    ) -> None:
        self.repository, self.subject_id = repository, subject_id
        self.backend, self.allow_analysis = backend, allow_analysis
        self._label_cache: dict[str, list[str]] = {}

    def _labels(self, text: str, semantic: bool) -> list[str]:
        key = sha256(text.encode()).hexdigest()
        if key in self._label_cache:
            return self._label_cache[key]
        labels = concepts(text)
        method = getattr(self.backend, "memory_concepts", None)
        if semantic and env_bool("DIGITAL_CHILD_SEMANTIC_MEMORY", True) and callable(method):
            if self.allow_analysis():
                try:
                    result = SemanticLabels.model_validate(method(text))
                    labels += [label[:60] for label in result.concepts]
                except (RuntimeError, ValueError, TypeError, OSError):
                    pass
        result_labels = list(dict.fromkeys(labels))[:20]
        if semantic:
            self._label_cache[key] = result_labels
            if len(self._label_cache) > 128:
                self._label_cache.pop(next(iter(self._label_cache)))
        return result_labels

    def seed_labels(self, text: str, labels: list[str]) -> None:
        if not env_bool("DIGITAL_CHILD_SEMANTIC_MEMORY", True):
            labels = []
        key = sha256(text.encode()).hexdigest()
        self._label_cache[key] = list(dict.fromkeys(concepts(text) + labels))[:20]
        if len(self._label_cache) > 128:
            self._label_cache.pop(next(iter(self._label_cache)))

    def record(
        self,
        episode: Episode,
        person_id: str | None = None,
        belief_ids: list[str] | None = None,
        *,
        semantic: bool = True,
        decision: str = "",
        consequences: list[str] | None = None,
    ) -> None:
        labels = self._labels(episode.content, semantic)
        entry = MemoryAssociation(
            episode_id=episode.id,
            person_id=person_id,
            concepts=labels,
            features=sorted(features(episode.content, labels)),
            belief_ids=belief_ids or [],
            decision=decision,
            consequences=(consequences or [])[-12:],
        )
        self.repository.save_feature(
            "association", episode.id, self.subject_id, entry.model_dump(mode="json")
        )

    def search(
        self, text: str, person_id: str, limit: int = 4, *, semantic: bool = True
    ) -> list[MemoryMatch]:
        if not text.strip():
            return []
        entries = [
            MemoryAssociation.model_validate(item)
            for item in self.repository.list_features("association", self.subject_id, 500)
        ]
        entries = [item for item in entries if item.person_id in (None, person_id)]
        labels = self._labels(text, semantic=semantic)
        query = features(text, labels)
        counts = Counter(feature for item in entries for feature in set(item.features))

        def weight(feature: str) -> float:
            return (2.5 if feature.startswith("concept:") else 1.0) * (
                1 + math.log((1 + len(entries)) / (1 + counts[feature]))
            )

        def norm(values: set[str]) -> float:
            return math.sqrt(sum(weight(value) ** 2 for value in values)) or 1.0

        matches = []
        for item in entries:
            shared = query & set(item.features)
            if not shared:
                continue
            episode = self.repository.get_episode(item.episode_id)
            if episode is None:
                continue
            score = sum(weight(value) ** 2 for value in shared) / (
                norm(query) * norm(set(item.features))
            )
            score *= (0.7 + 0.3 * episode.importance) * (0.6 if episode.archived else 1.0)
            if score >= 0.06:
                matches.append(
                    MemoryMatch(
                        episode=episode,
                        score=score,
                        shared_concepts=sorted(set(labels) & set(item.concepts)),
                        belief_ids=item.belief_ids,
                        decision=item.decision,
                        consequences=item.consequences,
                    )
                )
        return sorted(matches, key=lambda item: (item.score, item.episode.sequence), reverse=True)[
            : max(1, min(limit, 20))
        ]

    @staticmethod
    def summary(matches: list[MemoryMatch]) -> str:
        return (
            " | ".join(
                f"Эпизод {item.episode.sequence} [{item.episode.id}]: "
                f"{item.episode.content[:230]}; наблюдаемый исход={item.episode.outcome}; "
                f"связанные убеждения={','.join(item.belief_ids)}"
                f"; решение={item.decision}; последствия={'; '.join(item.consequences)[-350:]}"
                for item in matches
            )
            or "Связанные эпизоды не найдены."
        )

    def link_report(self, episode_id: str | None, report: ResearchReport) -> None:
        if episode_id is None:
            return
        row = self.repository.load_feature("association", episode_id, self.subject_id)
        if row is None:
            return
        entry = MemoryAssociation.model_validate(row)
        result = f"Проверка [{report.id}]: {report.summary[:280]}"
        entry.consequences = list(dict.fromkeys(entry.consequences + [result]))[-12:]
        self.repository.save_feature(
            "association", episode_id, self.subject_id, entry.model_dump(mode="json")
        )
