from __future__ import annotations

import math
import re
from collections.abc import Callable
from hashlib import sha256

from pydantic import Field

from digital_child.domain.models import Episode, ResearchReport, StrictModel
from digital_child.infrastructure.config import env_bool
from digital_child.infrastructure.repository import SQLiteRepository

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
        labels = self._labels(text, semantic=semantic)
        query = features(text, labels)
        total, counts = self.repository.association_term_counts(
            self.subject_id, person_id, sorted(query)
        )
        weights = {
            term: (2.5 if term.startswith("concept:") else 1.0)
            * (1 + math.log((1 + total) / (1 + count)))
            for term, count in counts.items()
            if count > 0
        }
        # Bound the candidate set, not the age of memories. Rare indexed terms can
        # retrieve an arbitrarily old episode, including an archived one.
        weights = dict(sorted(weights.items(), key=lambda item: item[1], reverse=True)[:128])
        denominator = sum(weights.values()) or 1.0
        matches = []
        for payload, episode in self.repository.association_candidates(
            self.subject_id, person_id, weights
        ):
            item = MemoryAssociation.model_validate(payload)
            shared = set(weights) & set(item.features)
            coverage = sum(weights[term] for term in shared) / denominator
            length = min(1.0, math.sqrt((len(query) + 4) / (len(item.features) + 4)))
            score = coverage * (0.5 + 0.5 * length)
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

    def backfill(self, batch_size: int = 100) -> dict[str, int]:
        with self.repository.transaction():
            saved = (
                self.repository.load_feature("association_scan", "cursor", self.subject_id) or {}
            )
            sequence = int(str(saved.get("sequence", 0)))
            skipped = int(str(saved.get("unattributed_conversations", 0)))
            indexed = 0
            for episode in self.repository.episodes_after(sequence, batch_size):
                if self.repository.load_feature("association", episode.id, self.subject_id) is None:
                    owner = episode.metadata.get("person_id")
                    if episode.action != "conversation" or isinstance(owner, str):
                        self.record(
                            episode, owner if isinstance(owner, str) else None, semantic=False
                        )
                        indexed += 1
                    else:
                        # Never expose an unattributed private conversation as global memory.
                        skipped += 1
                sequence = episode.sequence
            self.repository.save_feature(
                "association_scan",
                "cursor",
                self.subject_id,
                {"sequence": sequence, "unattributed_conversations": skipped},
            )
        return {
            **self.repository.association_index_status(self.subject_id, sequence),
            "indexed_now": indexed,
            "unattributed_conversations": skipped,
        }

    def index_status(self) -> dict[str, int]:
        saved = self.repository.load_feature("association_scan", "cursor", self.subject_id) or {}
        return {
            **self.repository.association_index_status(
                self.subject_id, int(str(saved.get("sequence", 0)))
            ),
            "unattributed_conversations": int(str(saved.get("unattributed_conversations", 0))),
        }

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
