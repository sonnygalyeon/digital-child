from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from digital_child.models import EmotionName, EmotionState


@dataclass(slots=True)
class FaceState:
    expression: str = EmotionName.NEUTRAL.value
    process: str = "idle"
    valence: float = 0.0
    arousal: float = 0.25
    curiosity: float = 0.5
    confidence: float = 0.35
    confusion: float = 0.15
    trust: float = 0.35
    fatigue: float = 0.0
    speaking_level: float = 0.0
    status_text: str = "IDLE"
    frustration: float = 0.0
    anxiety: float = 0.0
    boredom: float = 0.0
    longing: float = 0.0
    regulation: float = 0.15

    @classmethod
    def from_emotion(
        cls,
        emotion: EmotionState,
        *,
        process: str = "idle",
        override: EmotionName | None = None,
        speaking_level: float = 0.0,
        status_text: str | None = None,
    ) -> FaceState:
        expression = (override or emotion.dominant).value
        return cls(
            expression=expression,
            process=process,
            valence=emotion.valence,
            arousal=emotion.arousal,
            curiosity=emotion.curiosity,
            confidence=emotion.confidence,
            confusion=emotion.confusion,
            trust=emotion.trust,
            fatigue=emotion.fatigue,
            speaking_level=max(0.0, min(1.0, speaking_level)),
            status_text=status_text or process.upper(),
            frustration=emotion.frustration,
            anxiety=emotion.anxiety,
            boredom=emotion.boredom,
            longing=emotion.longing,
            regulation=emotion.regulation,
        )

    def to_message(self) -> dict[str, Any]:
        return {"type": "state", "payload": asdict(self)}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FaceState:
        allowed = cls.__dataclass_fields__.keys()
        values = {key: payload[key] for key in allowed if key in payload}
        return cls(**values)
