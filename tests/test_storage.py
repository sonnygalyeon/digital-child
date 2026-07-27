from pathlib import Path

from digital_child.models import AgentSnapshot, AgentState, DevelopmentProfile, Episode
from digital_child.storage import SQLiteRepository


def test_episode_round_trip(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "memory.db")
    episode = Episode(
        observation_id="obs-1",
        content="red button",
        action="press",
        outcome="light_on",
        reward=0.5,
        importance=0.8,
        effective_units=2.5,
        metadata={"verified": True},
    )

    repository.save_episode(episode)
    loaded = repository.recent_episodes(1)

    assert len(loaded) == 1
    assert loaded[0].id == episode.id
    assert loaded[0].metadata == {"verified": True}

    repository.close()


def test_snapshot_round_trip(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "snapshot.db")
    snapshot = AgentSnapshot(
        state=AgentState(energy=0.4),
        profile=DevelopmentProfile(total_deu=12.5),
    )

    repository.save_snapshot(snapshot)
    loaded = repository.load_snapshot()

    assert loaded is not None
    assert loaded.state.energy == 0.4
    assert loaded.profile.total_deu == 12.5

    repository.close()
