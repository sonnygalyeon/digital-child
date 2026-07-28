from pathlib import Path

from digital_child.agent import DigitalChildAgent
from digital_child.models import Observation
from digital_child.storage import SQLiteRepository


def observation(text: str) -> Observation:
    return Observation(
        content=text,
        raw_units=5,
        attention=1,
        comprehension=0.8,
        reliability=0.8,
        integration=0.7,
    )


def test_agent_calculates_novelty_and_persists_state(tmp_path: Path) -> None:
    path = tmp_path / "agent.db"
    repository = SQLiteRepository(path)
    agent = DigitalChildAgent(repository)
    first = agent.process_observation(observation("red button turns on lamp"))
    second = agent.process_observation(observation("red button turns on lamp"))
    assert first.calculated_novelty == 1.0
    assert second.calculated_novelty == 0.0
    total = agent.profile.total_deu
    repository.close()

    reopened = SQLiteRepository(path)
    restored = DigitalChildAgent(reopened)
    assert restored.profile.total_deu == total
    reopened.close()
