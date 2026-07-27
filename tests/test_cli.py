from digital_child.cli import build_caregiver_observation, main


def test_cli_exports_main() -> None:
    assert callable(main)


def test_caregiver_observation_uses_attention() -> None:
    observation = build_caregiver_observation("hello world", attention=0.42)

    assert observation.attention == 0.42
    assert observation.raw_units == 2
