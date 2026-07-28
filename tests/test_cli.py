from digital_child.cli import build_caregiver_observation, main
from digital_child.models import EvidenceStance


def test_cli_main_is_importable() -> None:
    assert callable(main)


def test_teaching_observation_contains_claim() -> None:
    observation = build_caregiver_observation("A causes B", 1.0, EvidenceStance.SUPPORT)
    assert len(observation.claims) == 1
