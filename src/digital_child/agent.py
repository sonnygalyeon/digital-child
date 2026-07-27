from __future__ import annotations

from digital_child.development import DevelopmentEngine
from digital_child.experience import ExperienceEngine
from digital_child.models import (
    AgentSnapshot,
    AgentState,
    CycleResult,
    DevelopmentProfile,
    Episode,
    Observation,
)
from digital_child.storage import SQLiteRepository


def clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


class DigitalChildAgent:
    """Orchestrate one complete developmental cycle."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        self.experience_engine = ExperienceEngine()
        self.development_engine = DevelopmentEngine()

        snapshot = repository.load_snapshot()
        if snapshot is None:
            self.state = AgentState()
            self.profile = DevelopmentProfile()
            self._persist_snapshot()
        else:
            self.state = snapshot.state
            self.profile = snapshot.profile

    def process_observation(
        self,
        observation: Observation,
        *,
        action: str = "observe",
        outcome: str = "information_received",
        reward: float = 0.0,
    ) -> CycleResult:
        assessment = self.experience_engine.assess(observation)
        transition = self.development_engine.apply(self.profile, assessment)

        self._update_internal_state(observation)

        importance = clamp_probability(
            0.45 * observation.novelty
            + 0.35 * abs(reward)
            + 0.20 * assessment.quality
        )

        episode = Episode(
            observation_id=observation.id,
            content=observation.content,
            action=action,
            outcome=outcome,
            reward=reward,
            importance=importance,
            effective_units=assessment.effective_units,
            metadata={
                "source_kind": observation.source_kind.value,
                "domains": {
                    domain.value: units for domain, units in assessment.domain_units.items()
                },
                "stage": self.profile.stage.value,
                "tags": observation.tags,
            },
        )

        self.repository.save_episode(episode)
        self._persist_snapshot()

        return CycleResult(
            assessment=assessment,
            transition=transition,
            state=self.state,
            profile=self.profile,
            response=self._build_response(observation, assessment.effective_units),
        )

    def rest(self, amount: float = 0.25) -> AgentState:
        amount = clamp_probability(amount)
        self.state.energy = clamp_probability(self.state.energy + amount)
        self.state.attention_capacity = clamp_probability(
            self.state.attention_capacity + amount * 0.8
        )
        self.state.curiosity = clamp_probability(self.state.curiosity - amount * 0.1)
        self._persist_snapshot()
        return self.state

    def reset(self) -> None:
        self.repository.reset()
        self.state = AgentState()
        self.profile = DevelopmentProfile()
        self._persist_snapshot()

    def _update_internal_state(self, observation: Observation) -> None:
        attention_cost = min(0.25, observation.raw_units / 1_000.0)
        self.state.energy = clamp_probability(self.state.energy - attention_cost)
        self.state.attention_capacity = clamp_probability(
            self.state.attention_capacity - attention_cost * 0.5
        )
        self.state.curiosity = clamp_probability(
            self.state.curiosity
            + 0.15 * observation.novelty
            - 0.10 * observation.comprehension
        )

        if observation.source_kind.value == "caregiver":
            self.state.social_need = clamp_probability(self.state.social_need - 0.05)
        else:
            self.state.social_need = clamp_probability(self.state.social_need + 0.01)

    def _persist_snapshot(self) -> None:
        self.repository.save_snapshot(
            AgentSnapshot(state=self.state, profile=self.profile)
        )

    def _build_response(self, observation: Observation, gained_deu: float) -> str:
        if observation.comprehension < 0.35:
            return "Я заметил это, но пока плохо понимаю. Мне нужен пример или повторение."
        if observation.novelty > 0.75:
            return f"Это новое для меня. Я усвоил {gained_deu:.3f} DEU опыта."
        if observation.integration > 0.70:
            return f"Я связал это с прежним опытом и получил {gained_deu:.3f} DEU."
        return f"Я сохранил наблюдение и получил {gained_deu:.3f} DEU."
