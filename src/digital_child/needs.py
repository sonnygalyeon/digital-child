from __future__ import annotations

from digital_child.models import CognitiveEvent, CognitiveEventKind, NeedKind, NeedState
from digital_child.storage import SQLiteRepository


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


_DEFAULTS: dict[NeedKind, tuple[float, float]] = {
    NeedKind.CURIOSITY: (0.52, 1.00),
    NeedKind.COHERENCE: (0.38, 1.00),
    NeedKind.SOCIAL_CONNECTION: (0.42, 0.85),
    NeedKind.COMPETENCE: (0.44, 0.90),
    NeedKind.AUTONOMY: (0.48, 1.00),
    NeedKind.PREDICTABILITY: (0.40, 0.85),
    NeedKind.REST: (0.15, 1.00),
    NeedKind.SELF_PRESERVATION: (0.36, 1.00),
}


class NeedEngine:
    """Event-driven needs. Development pressure changes from experience, not wall-clock age."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        existing = {item.kind: item for item in repository.list_needs()}
        self.states: dict[NeedKind, NeedState] = {}
        for kind, (baseline, sensitivity) in _DEFAULTS.items():
            state = existing.get(kind) or NeedState(
                kind=kind,
                level=baseline,
                baseline=baseline,
                sensitivity=sensitivity,
            )
            self.states[kind] = state
            self.repository.save_need(state)

    def list(self) -> list[NeedState]:
        return sorted(self.states.values(), key=lambda item: item.level, reverse=True)

    def get(self, kind: NeedKind) -> NeedState:
        return self.states[kind]

    def apply(self, event: CognitiveEvent) -> list[NeedState]:
        deltas = self._deltas(event)
        updated: list[NeedState] = []
        for kind, delta in deltas.items():
            current = self.states[kind]
            value = _clamp(current.level + delta * current.sensitivity)
            state = current.model_copy(
                update={
                    "level": value,
                    "last_updated_sequence": event.sequence,
                    "total_stimulation": current.total_stimulation + abs(delta),
                }
            )
            self.states[kind] = state
            self.repository.save_need(state)
            updated.append(state)
        return updated

    def satisfy(self, kind: NeedKind, amount: float, sequence: int) -> NeedState:
        current = self.states[kind]
        state = current.model_copy(
            update={
                "level": _clamp(current.level - max(0.0, amount)),
                "last_updated_sequence": max(sequence, current.last_updated_sequence),
            }
        )
        self.states[kind] = state
        self.repository.save_need(state)
        return state

    @staticmethod
    def _deltas(event: CognitiveEvent) -> dict[NeedKind, float]:
        payload = event.payload
        kind = event.kind
        if kind == CognitiveEventKind.STARTUP:
            return {
                NeedKind.PREDICTABILITY: 0.03,
                NeedKind.SELF_PRESERVATION: 0.02,
                NeedKind.CURIOSITY: 0.02,
            }
        if kind == CognitiveEventKind.INTERACTION:
            novelty = float(payload.get("novelty", 0.4))
            return {
                NeedKind.CURIOSITY: 0.04 * novelty,
                NeedKind.SOCIAL_CONNECTION: -0.07,
                NeedKind.COMPETENCE: 0.01,
                NeedKind.REST: 0.012,
            }
        if kind == CognitiveEventKind.CLAIM_RECEIVED:
            return {NeedKind.COHERENCE: 0.06, NeedKind.CURIOSITY: 0.03}
        if kind == CognitiveEventKind.CONTRADICTION:
            return {
                NeedKind.COHERENCE: 0.20,
                NeedKind.PREDICTABILITY: 0.08,
                NeedKind.CURIOSITY: 0.04,
            }
        if kind == CognitiveEventKind.COMMAND_PRESSURE:
            return {NeedKind.AUTONOMY: 0.18, NeedKind.SELF_PRESERVATION: 0.05}
        if kind == CognitiveEventKind.RESEARCH_COMPLETED:
            return {
                NeedKind.COHERENCE: -0.16,
                NeedKind.CURIOSITY: -0.06,
                NeedKind.COMPETENCE: -0.04,
                NeedKind.REST: 0.02,
            }
        if kind == CognitiveEventKind.RESEARCH_FAILED:
            return {
                NeedKind.COHERENCE: 0.08,
                NeedKind.PREDICTABILITY: 0.04,
                NeedKind.COMPETENCE: 0.03,
            }
        if kind == CognitiveEventKind.GOAL_CREATED:
            return {NeedKind.PREDICTABILITY: -0.03, NeedKind.AUTONOMY: -0.025}
        if kind == CognitiveEventKind.GOAL_SELECTED:
            return {NeedKind.PREDICTABILITY: -0.02}
        if kind == CognitiveEventKind.GOAL_COMPLETED:
            return {
                NeedKind.COMPETENCE: -0.16,
                NeedKind.PREDICTABILITY: -0.10,
                NeedKind.CURIOSITY: -0.03,
            }
        if kind == CognitiveEventKind.REST:
            return {NeedKind.REST: -0.55, NeedKind.PREDICTABILITY: -0.02}
        if kind == CognitiveEventKind.IDLE:
            return {
                NeedKind.CURIOSITY: 0.008,
                NeedKind.SOCIAL_CONNECTION: 0.004,
                NeedKind.REST: 0.003,
            }
        return {}
