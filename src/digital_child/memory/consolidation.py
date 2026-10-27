from __future__ import annotations

from digital_child.domain.models import ConsolidationReport
from digital_child.infrastructure.repository import SQLiteRepository


class MemoryConsolidator:
    """Apply interference-based forgetting and merge exact repeated episodes."""

    def __init__(
        self,
        repository: SQLiteRepository,
        decay_per_intervening_episode: float = 0.015,
        archive_threshold: float = 0.08,
        repetition_threshold: int = 3,
    ) -> None:
        self.repository = repository
        self.decay_per_intervening_episode = decay_per_intervening_episode
        self.archive_threshold = archive_threshold
        self.repetition_threshold = repetition_threshold

    def run(self) -> ConsolidationReport:
        current_sequence = self.repository.current_sequence()
        decayed, archived = self.repository.apply_interference_decay(
            current_sequence=current_sequence,
            decay_per_episode=self.decay_per_intervening_episode,
            archive_threshold=self.archive_threshold,
        )
        created, updated = self.repository.consolidate_repeated_episodes(
            minimum_repetitions=self.repetition_threshold
        )
        return ConsolidationReport(
            current_sequence=current_sequence,
            decayed_episodes=decayed,
            archived_episodes=archived,
            created_summaries=created,
            updated_summaries=updated,
        )
