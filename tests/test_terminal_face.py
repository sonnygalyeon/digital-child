from digital_child.models import EmotionName, EmotionState
from digital_child.terminal_face import TerminalFaceRenderer


def test_face_is_clear_and_has_multiple_lines() -> None:
    frame = TerminalFaceRenderer().render(EmotionState(), tick=10)

    assert len(frame.lines) >= 14
    assert any("◉" in line for line in frame.lines)
    assert max(len(line) for line in frame.lines) >= 30


def test_idle_animation_changes_blink_and_position() -> None:
    renderer = TerminalFaceRenderer()
    normal = renderer.render(EmotionState(), tick=10)
    blink = renderer.render(EmotionState(), tick=73)
    floated = renderer.render(EmotionState(), tick=31)

    assert normal.blink is False
    assert blink.blink is True
    assert normal.lines != blink.lines
    assert normal.lines != floated.lines


def test_expression_override_changes_face() -> None:
    renderer = TerminalFaceRenderer()
    neutral = renderer.render(EmotionState(), tick=10)
    speaking = renderer.render(
        EmotionState(),
        tick=10,
        override=EmotionName.SPEAKING,
    )

    assert speaking.expression == EmotionName.SPEAKING
    assert neutral.lines != speaking.lines
