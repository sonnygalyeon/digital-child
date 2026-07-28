from pathlib import Path

from digital_child.agent import DigitalChildAgent
from digital_child.models import (
    BeliefStatus,
    ClaimEvidenceInput,
    EvidenceStance,
    Observation,
    SourceKind,
)
from digital_child.storage import SQLiteRepository


def make_observation(stance: EvidenceStance) -> Observation:
    claim = "Красная кнопка включает лампу"
    return Observation(
        content=claim,
        source_kind=SourceKind.CAREGIVER,
        raw_units=5,
        attention=1,
        comprehension=1,
        reliability=1,
        integration=1,
        practical_confirmation=1,
        claims=[ClaimEvidenceInput(claim=claim, stance=stance)],
    )


def test_support_then_contradiction_creates_contested_belief(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "beliefs.db")
    agent = DigitalChildAgent(repository)
    agent.process_observation(make_observation(EvidenceStance.SUPPORT))
    result = agent.process_observation(make_observation(EvidenceStance.CONTRADICT))

    belief = result.belief_updates[0].belief
    assert belief.status == BeliefStatus.CONTESTED
    assert belief.support_score > 0
    assert belief.contradiction_score > 0
    assert len(repository.evidence_for_belief(belief.id)) == 2
    repository.close()


def test_reliable_source_has_more_weight(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "weight.db")
    agent = DigitalChildAgent(repository)
    result = agent.process_observation(make_observation(EvidenceStance.SUPPORT))
    assert result.belief_updates[0].evidence.weight == 1.0
    repository.close()
