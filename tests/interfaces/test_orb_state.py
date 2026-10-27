import pytest

from digital_child.interfaces.desktop.face_state import FaceState
from digital_child.interfaces.desktop.orb_state import OrbDynamics


def test_fatigue_slows_and_dims_the_sphere() -> None:
    rested = OrbDynamics.from_face(FaceState(fatigue=0))
    tired = OrbDynamics.from_face(FaceState(fatigue=1))
    assert tired.speed < rested.speed
    assert tired.brightness < rested.brightness


def test_trust_and_confusion_affect_different_layers() -> None:
    calm = OrbDynamics.from_face(FaceState(trust=0.8, confusion=0))
    conflicted = OrbDynamics.from_face(FaceState(trust=0.1, confusion=0.9))
    assert conflicted.openness < calm.openness
    assert conflicted.turbulence > calm.turbulence
    assert conflicted.coherence < calm.coherence


def test_speech_preserves_emotional_hue() -> None:
    wary = FaceState(expression="wary", process="idle")
    speaking = FaceState(expression="wary", process="speaking", speaking_level=0.8)
    idle = OrbDynamics.from_face(wary)
    active = OrbDynamics.from_face(speaking)
    assert (active.red, active.green, active.blue) == (idle.red, idle.green, idle.blue)
    assert active.pulse > idle.pulse
    assert active.speech > idle.speech


def test_smoothing_is_independent_of_frame_rate() -> None:
    initial = OrbDynamics.from_face(FaceState())
    target = OrbDynamics.from_face(FaceState(confusion=1, fatigue=1, trust=0))
    coarse = initial.approach(target, 1)
    fine = initial
    for _ in range(60):
        fine = fine.approach(target, 1 / 60)
    assert fine.speed == pytest.approx(coarse.speed)
    assert fine.turbulence == pytest.approx(coarse.turbulence)
    assert target.speed < coarse.speed < initial.speed
