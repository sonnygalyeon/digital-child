from __future__ import annotations

import math
from dataclasses import dataclass

from digital_child.face_state import FaceState


@dataclass(frozen=True, slots=True)
class OrbDynamics:
    """Visual targets only: the renderer never writes to the agent's psychology."""

    red: float = 100.0
    green: float = 235.0
    blue: float = 160.0
    speed: float = 0.24
    turbulence: float = 0.025
    openness: float = 0.45
    brightness: float = 0.8
    pulse: float = 0.025
    coherence: float = 0.65
    curiosity: float = 0.5
    speech: float = 0.0

    @classmethod
    def from_face(cls, state: FaceState) -> OrbDynamics:
        palette = {
            "happy": (161, 245, 114),
            "curious": (75, 239, 202),
            "skeptical": (229, 189, 104),
            "wary": (237, 144, 104),
            "confused": (175, 150, 246),
            "sad": (98, 148, 209),
            "frustrated": (239, 155, 88),
            "anxious": (188, 167, 218),
            "proud": (203, 220, 127),
            "affectionate": (133, 232, 183),
            "bored": (126, 166, 148),
            "missing_contact": (102, 185, 211),
        }
        color = palette.get(state.expression, (100, 235, 160))
        fatigue = max(0.0, min(1.0, state.fatigue))
        thinking = float(state.process == "thinking")
        listening = float(state.process == "listening")
        speech = state.speaking_level if state.process == "speaking" else 0.0
        return cls(
            red=float(color[0]),
            green=float(color[1]),
            blue=float(color[2]),
            speed=(0.12 + state.arousal * 0.55 + thinking * 0.25)
            * (1 - fatigue * 0.7)
            * (1 - state.boredom * 0.25),
            turbulence=(
                0.008
                + state.confusion * 0.065
                + state.arousal * 0.018
                + state.frustration * 0.025
                + state.anxiety * 0.02
            )
            * (1 - state.regulation * 0.30),
            openness=0.2 + state.trust * 0.6 + state.longing * 0.12,
            brightness=0.9 - fatigue * 0.5 + state.valence * 0.08,
            pulse=0.018
            + state.arousal * 0.018
            + listening * 0.018
            + speech * 0.065
            + state.longing * 0.012,
            coherence=0.3 + state.confidence * 0.6 - state.confusion * 0.2,
            curiosity=state.curiosity,
            speech=speech,
        )

    def approach(self, target: OrbDynamics, seconds: float) -> OrbDynamics:
        # Exponential smoothing behaves the same at different frame rates.
        amount = 1.0 - math.exp(-max(0.0, seconds) / 0.7)
        return OrbDynamics(
            **{
                name: getattr(self, name) + (getattr(target, name) - getattr(self, name)) * amount
                for name in self.__dataclass_fields__
            }
        )
