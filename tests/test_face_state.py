from digital_child.face_state import FaceState
from digital_child.models import EmotionName, EmotionState


def test_face_state_round_trip_preserves_unicode_status() -> None:
    emotion = EmotionState(
        dominant=EmotionName.CURIOUS,
        curiosity=0.9,
        trust=0.4,
    )
    state = FaceState.from_emotion(
        emotion,
        process="thinking",
        override=EmotionName.THINKING,
        status_text="РАЗМЫШЛЯЮ",
    )
    restored = FaceState.from_payload(state.to_message()["payload"])
    assert restored.expression == "thinking"
    assert restored.status_text == "РАЗМЫШЛЯЮ"
    assert restored.curiosity == 0.9
