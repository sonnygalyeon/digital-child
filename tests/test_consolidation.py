from pathlib import Path

from digital_child.consolidation import MemoryConsolidator
from digital_child.models import Episode
from digital_child.storage import SQLiteRepository
from digital_child.text import normalize_text


def add_episode(repository: SQLiteRepository, text: str, importance: float = 0.1) -> None:
    repository.save_episode(
        Episode(
            observation_id=text,
            content=text,
            normalized_content=normalize_text(text),
            action="observe",
            outcome="ok",
            reward=0,
            importance=importance,
            effective_units=1,
            access_strength=0.3,
        )
    )


def test_repeated_episodes_are_consolidated(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "consolidate.db")
    for _ in range(3):
        add_episode(repository, "same memory")
    report = MemoryConsolidator(repository).run()
    assert report.created_summaries == 1
    assert repository.list_memory_summaries()[0].episode_count == 3
    assert len(repository.recent_episodes()) == 1
    repository.close()


def test_interference_can_archive_weak_old_memory(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "forget.db")
    add_episode(repository, "old weak", importance=0.0)
    for index in range(50):
        add_episode(repository, f"new {index}", importance=1.0)
    report = MemoryConsolidator(
        repository,
        decay_per_intervening_episode=0.05,
        archive_threshold=0.1,
        repetition_threshold=100,
    ).run()
    assert report.archived_episodes >= 1
    active_contents = {episode.content for episode in repository.recent_episodes(100)}
    assert "old weak" not in active_contents
    repository.close()
