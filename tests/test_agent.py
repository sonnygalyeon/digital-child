from pathlib import Path

from digital_child.agent import DigitalChildAgent
from digital_child.models import DevelopmentDomain, Observation
from digital_child.storage import SQLiteRepository


def test_agent_cycle_changes_state_and_writes_memory(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "agent.db")
    agent = DigitalChildAgent(repository)

    result = agent.process_observation(
        Observation(
            content="The lamp turns on after the button is pressed",
            raw_units=20,
            novelty=0.9,
            attention=0.8,
            comprehension=0.7,
            reliability=1.0,
            integration=0.6,
            practical_confirmation=1.0,
            domains={DevelopmentDomain.CAUSAL_REASONING: 1.0},
        )
    )

    assert result.assessment.effective_units > 0
    assert agent.profile.total_deu > 0
    assert agent.state.energy < 1.0
    assert len(repository.recent_episodes()) == 1

    repository.close()


def test_agent_state_survives_restart(tmp_path: Path) -> None:
    database = tmp_path / "persistent.db"

    repository = SQLiteRepository(database)
    agent = DigitalChildAgent(repository)
    agent.rest(0.1)
    agent.process_observation(
        Observation(
            content="persistent observation",
            raw_units=5,
            novelty=1.0,
            attention=1.0,
            comprehension=1.0,
            reliability=1.0,
            integration=1.0,
            practical_confirmation=1.0,
        )
    )
    total_deu = agent.profile.total_deu
    repository.close()

    second_repository = SQLiteRepository(database)
    restored = DigitalChildAgent(second_repository)

    assert restored.profile.total_deu == total_deu
    assert len(second_repository.recent_episodes()) == 1

    second_repository.close()
