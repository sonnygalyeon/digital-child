from pathlib import Path

from digital_child.models import AgentSnapshot, AgentState, DevelopmentProfile, Episode
from digital_child.storage import SQLiteRepository
from digital_child.text import normalize_text


def test_snapshot_and_episode_round_trip(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "storage.db")
    repository.save_snapshot(AgentSnapshot(state=AgentState(energy=0.4), profile=DevelopmentProfile()))
    loaded = repository.load_snapshot()
    assert loaded is not None
    assert loaded.state.energy == 0.4

    episode = repository.save_episode(
        Episode(
            observation_id="obs",
            content="hello",
            normalized_content=normalize_text("hello"),
            action="observe",
            outcome="ok",
            reward=0,
            importance=0.5,
            effective_units=1,
        )
    )
    assert episode.sequence == 1
    assert repository.recent_episodes()[0].content == "hello"
    repository.close()
