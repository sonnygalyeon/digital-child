from pathlib import Path

from digital_child.application.agent import DigitalChildAgent
from digital_child.inference.backend import RuleBasedBackend
from digital_child.infrastructure.repository import SQLiteRepository
from digital_child.infrastructure.search import DisabledSearchProvider


def make_agent(path: Path) -> DigitalChildAgent:
    return DigitalChildAgent(
        SQLiteRepository(path),
        search_provider=DisabledSearchProvider(),
        cognitive_backend=RuleBasedBackend(),
        auto_research=False,
    )


def test_first_start_creates_genesis_identity_and_goals(tmp_path: Path) -> None:
    agent = make_agent(tmp_path / "child.db")

    assert agent.genesis_event is not None
    assert agent.identity.awakened is True
    assert len(agent.identity.genesis_questions) >= 4
    assert len(agent.repository.list_goals()) >= 4

    agent.repository.close()


def test_second_start_restores_identity_without_second_genesis(tmp_path: Path) -> None:
    path = tmp_path / "child.db"
    first = make_agent(path)
    identity_id = first.identity.id
    first.repository.close()

    second = make_agent(path)

    assert second.identity.id == identity_id
    assert second.genesis_event is None
    assert len(second.repository.list_goals()) == 4

    second.repository.close()
