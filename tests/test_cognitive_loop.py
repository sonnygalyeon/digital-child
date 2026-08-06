from pathlib import Path

from digital_child.cognitive_loop import CognitiveLoop
from digital_child.models import CognitiveEvent, CognitiveEventKind, GoalOrigin, NeedKind
from digital_child.storage import SQLiteRepository


def test_loop_creates_goal_from_strong_internal_need(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "loop.db")
    loop = CognitiveLoop(repo, heartbeat_seconds=0.05)
    for _ in range(2):
        loop.publish(
            CognitiveEvent(
                kind=CognitiveEventKind.CONTRADICTION,
                source="test",
                importance=0.9,
            )
        )
        loop.tick_once()
    goals = repo.list_goals(100, active_only=True)
    assert any(
        goal.origin == GoalOrigin.SELF_GENERATED
        and goal.need_kind == NeedKind.COHERENCE
        for goal in goals
    )
    assert loop.status.active_goal_id is not None
    repo.close()


def test_loop_pause_resume_and_budget_status(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "control.db")
    loop = CognitiveLoop(repo, heartbeat_seconds=0.02)
    loop.start()
    assert loop.status.running is True
    assert loop.pause().paused is True
    assert loop.resume().paused is False
    loop.stop()
    assert loop.status.running is False
    assert loop.budgets.get("background_cycles").limit > 0
    repo.close()
