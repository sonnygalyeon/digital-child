from pathlib import Path

from digital_child.cognition.needs import NeedEngine
from digital_child.domain.models import CognitiveEvent, CognitiveEventKind, NeedKind
from digital_child.infrastructure.repository import SQLiteRepository


def test_needs_change_from_events_and_persist(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "needs.db")
    engine = NeedEngine(repo)
    before = engine.get(NeedKind.COHERENCE).level
    event = repo.save_cognitive_event(
        CognitiveEvent(kind=CognitiveEventKind.CONTRADICTION, source="test")
    )
    engine.apply(event)
    after = engine.get(NeedKind.COHERENCE).level
    assert after > before
    repo.close()

    reopened = SQLiteRepository(tmp_path / "needs.db")
    restored = NeedEngine(reopened)
    assert restored.get(NeedKind.COHERENCE).level == after
    reopened.close()
