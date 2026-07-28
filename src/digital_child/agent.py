from __future__ import annotations

from digital_child.beliefs import BeliefEngine
from digital_child.consolidation import MemoryConsolidator
from digital_child.development import DevelopmentEngine
from digital_child.experience import ExperienceEngine
from digital_child.models import (
    AgentSnapshot,
    AgentState,
    BeliefUpdate,
    ConsolidationReport,
    CycleResult,
    DevelopmentProfile,
    Episode,
    Observation,
    SourceRecord,
)
from digital_child.novelty import NoveltyEngine
from digital_child.storage import SQLiteRepository
from digital_child.text import normalize_text


def clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


class DigitalChildAgent:
    """Orchestrate one complete developmental cycle."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        self.experience_engine = ExperienceEngine()
        self.development_engine = DevelopmentEngine()
        self.novelty_engine = NoveltyEngine(repository)
        self.belief_engine = BeliefEngine(repository)
        self.memory_consolidator = MemoryConsolidator(repository)

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
        novelty = (
            observation.novelty
            if observation.novelty is not None
            else self.novelty_engine.calculate(observation.content)
        )
        prepared = observation.model_copy(update={"novelty": novelty})
        assessment = self.experience_engine.assess(prepared)
        transition = self.development_engine.apply(self.profile, assessment)
        self._update_internal_state(prepared)

        importance = clamp_probability(
            0.45 * novelty + 0.35 * abs(reward) + 0.20 * assessment.quality
        )
        episode = Episode(
            observation_id=prepared.id,
            content=prepared.content,
            normalized_content=normalize_text(prepared.content),
            action=action,
            outcome=outcome,
            reward=reward,
            importance=importance,
            effective_units=assessment.effective_units,
            access_strength=clamp_probability(0.35 + 0.65 * importance),
            metadata={
                "source_kind": prepared.source_kind.value,
                "domains": {
                    domain.value: units for domain, units in assessment.domain_units.items()
                },
                "stage": self.profile.stage.value,
                "tags": prepared.tags,
                "calculated_novelty": novelty,
            },
        )
        stored_episode = self.repository.save_episode(episode)
        source = self._resolve_source(prepared)

        belief_updates: list[BeliefUpdate] = []
        for claim in prepared.claims:
            belief_updates.append(
                self.belief_engine.apply_evidence(
                    claim_input=claim,
                    observation=prepared,
                    source=source,
                    current_sequence=stored_episode.sequence,
                )
            )

        self._persist_snapshot()
        return CycleResult(
            calculated_novelty=novelty,
            assessment=assessment,
            transition=transition,
            belief_updates=belief_updates,
            state=self.state,
            profile=self.profile,
            response=self._build_response(prepared, assessment.effective_units, belief_updates),
        )

    def consolidate_memory(self) -> ConsolidationReport:
        return self.memory_consolidator.run()

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

    def _resolve_source(self, observation: Observation) -> SourceRecord:
        if observation.source_id is not None:
            source = self.repository.get_source(observation.source_id)
            if source is None:
                raise ValueError(f"Unknown source_id: {observation.source_id}")
            return source
        return self.repository.get_or_create_default_source(
            kind=observation.source_kind,
            reliability=observation.reliability,
        )

    def _update_internal_state(self, observation: Observation) -> None:
        attention_cost = min(0.25, observation.raw_units / 1_000.0)
        self.state.energy = clamp_probability(self.state.energy - attention_cost)
        self.state.attention_capacity = clamp_probability(
            self.state.attention_capacity - attention_cost * 0.5
        )
        novelty = observation.novelty or 0.0
        self.state.curiosity = clamp_probability(
            self.state.curiosity + 0.15 * novelty - 0.10 * observation.comprehension
        )
        if observation.source_kind.value == "caregiver":
            self.state.social_need = clamp_probability(self.state.social_need - 0.05)
        else:
            self.state.social_need = clamp_probability(self.state.social_need + 0.01)

    def _persist_snapshot(self) -> None:
        self.repository.save_snapshot(AgentSnapshot(state=self.state, profile=self.profile))

    @staticmethod
    def _build_response(
        observation: Observation,
        gained_deu: float,
        updates: list[BeliefUpdate],
    ) -> str:
        if observation.comprehension < 0.35:
            return "Я заметил это, но пока плохо понимаю. Мне нужен пример или повторение."
        if updates:
            contested = sum(update.belief.status.value == "contested" for update in updates)
            if contested:
                return (
                    f"Я получил {gained_deu:.3f} DEU и обнаружил противоречие "
                    f"в {contested} убеждении(ях)."
                )
            return (
                f"Я получил {gained_deu:.3f} DEU и обновил "
                f"{len(updates)} убеждение(я)."
            )
        if (observation.novelty or 0.0) > 0.75:
            return f"Это новое для меня. Я усвоил {gained_deu:.3f} DEU опыта."
        if observation.integration > 0.70:
            return f"Я связал это с прежним опытом и получил {gained_deu:.3f} DEU."
        return f"Я сохранил наблюдение и получил {gained_deu:.3f} DEU."
