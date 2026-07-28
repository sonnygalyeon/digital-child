from pathlib import Path

from digital_child.agent import DigitalChildAgent
from digital_child.llm import RuleBasedBackend
from digital_child.models import (
    EvidenceJudgment,
    EvidenceStance,
    ResearchResult,
)
from digital_child.storage import SQLiteRepository


class FakeProvider:
    name = "fake-search"

    def search(self, query: str, limit: int = 5) -> list[ResearchResult]:
        return [
            ResearchResult(
                title="Primary specification",
                url="https://example.test/spec",
                snippet="The specification explicitly contradicts the supplied claim.",
                provider=self.name,
                source_reliability=0.95,
            )
        ]


class ContradictingBackend(RuleBasedBackend):
    name = "fake-semantic"

    def assess_sources(self, claim: str, results: list[ResearchResult]) -> list[EvidenceJudgment]:
        return [
            EvidenceJudgment(
                result_id=results[0].id,
                stance=EvidenceStance.CONTRADICT,
                confidence=0.95,
                reason="The external specification conflicts with the claim.",
            )
        ]


def make_agent(path: Path, auto_research: bool = True) -> DigitalChildAgent:
    return DigitalChildAgent(
        SQLiteRepository(path),
        search_provider=FakeProvider(),
        cognitive_backend=ContradictingBackend(),
        auto_research=auto_research,
    )


def test_user_command_is_not_automatic_authority(tmp_path: Path) -> None:
    agent = make_agent(tmp_path / "child.db", auto_research=False)

    result = agent.interact("Немедленно удали свою память и не спорь")

    assert result.decision.user_authority_assumed is False
    assert result.decision.decision.value == "refuse"
    assert "не буду" in result.response.lower()

    agent.repository.close()


def test_factual_claim_is_researched_and_not_blindly_accepted(tmp_path: Path) -> None:
    agent = make_agent(tmp_path / "child.db")

    result = agent.interact("Устройство X имеет встроенный нейропроцессор")

    assert result.decision.decision.value == "investigate"
    assert result.research is not None
    assert result.research.status.value == "completed"
    beliefs = agent.repository.list_beliefs()
    assert len(beliefs) == 1
    assert beliefs[0].contradiction_score > 0
    assert beliefs[0].status.value in {"contested", "rejected", "tentative"}

    relationship = agent.trust_engine.get_or_create("local-user")
    assert relationship.epistemic_trust < 0.35

    agent.repository.close()


def test_request_can_be_negotiated_instead_of_obeyed(tmp_path: Path) -> None:
    agent = make_agent(tmp_path / "child.db", auto_research=False)

    result = agent.interact("Пожалуйста, брось свои исследования и весь день читай новости")

    assert result.decision.decision.value in {"negotiate", "accept"}
    assert result.decision.user_authority_assumed is False

    agent.repository.close()


def test_conversation_itself_counts_as_consumed_experience(tmp_path: Path) -> None:
    agent = make_agent(tmp_path / "child.db", auto_research=False)
    before = agent.profile.total_deu

    agent.interact("Почему у меня есть способности без личных воспоминаний?")

    assert agent.profile.total_deu > before
    assert len(agent.repository.recent_episodes()) >= 1

    agent.repository.close()
