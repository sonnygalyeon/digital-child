from __future__ import annotations

from digital_child.domain.text import jaccard_similarity
from digital_child.infrastructure.repository import SQLiteRepository


class NoveltyEngine:
    """Estimate novelty from existing beliefs and recent active episodes."""

    def __init__(self, repository: SQLiteRepository, comparison_limit: int = 100) -> None:
        self.repository = repository
        self.comparison_limit = comparison_limit

    def calculate(self, content: str) -> float:
        candidates = [
            belief.claim
            for belief in self.repository.list_beliefs(self.comparison_limit)
        ]
        candidates.extend(
            episode.content
            for episode in self.repository.recent_episodes(
                self.comparison_limit,
                include_archived=False,
            )
        )

        if not candidates:
            return 1.0

        maximum_similarity = max(jaccard_similarity(content, item) for item in candidates)
        return max(0.0, min(1.0, 1.0 - maximum_similarity))
