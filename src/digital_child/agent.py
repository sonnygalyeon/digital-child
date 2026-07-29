from __future__ import annotations

from collections.abc import Callable

from digital_child.autonomy import AutonomyEngine
from digital_child.awakening import AwakeningEngine
from digital_child.beliefs import BeliefEngine
from digital_child.consolidation import MemoryConsolidator
from digital_child.deception import DeceptionEngine
from digital_child.development import DevelopmentEngine
from digital_child.emotions import EmotionEngine
from digital_child.epistemics import EpistemicEngine, VerificationPolicy
from digital_child.experience import ExperienceEngine
from digital_child.intentions import IntentClassifier
from digital_child.llm import CognitiveBackend, RuleBasedBackend
from digital_child.llm_types import ReplyContext
from digital_child.models import (
    AgentSnapshot,
    AgentState,
    BeliefUpdate,
    ConsolidationReport,
    ConversationMessage,
    ConversationRole,
    CycleResult,
    DevelopmentDomain,
    DevelopmentProfile,
    EmotionState,
    Episode,
    GenesisEvent,
    InteractionResult,
    MessageIntent,
    Observation,
    ResearchStatus,
    SourceKind,
    SourceRecord,
)
from digital_child.novelty import NoveltyEngine
from digital_child.research import DisabledSearchProvider, ResearchEngine, SearchProvider
from digital_child.storage import SQLiteRepository
from digital_child.text import normalize_text
from digital_child.trust import TrustEngine


def clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


class DigitalChildAgent:
    """Long-lived agent with separate capability, psychology, evidence and autonomy layers."""

    def __init__(
        self,
        repository: SQLiteRepository,
        *,
        search_provider: SearchProvider | None = None,
        cognitive_backend: CognitiveBackend | None = None,
        auto_research: bool = True,
    ) -> None:
        self.repository = repository
        self.experience_engine = ExperienceEngine()
        self.development_engine = DevelopmentEngine()
        self.novelty_engine = NoveltyEngine(repository)
        self.belief_engine = BeliefEngine(repository)
        self.memory_consolidator = MemoryConsolidator(repository)
        self.intent_classifier = IntentClassifier()
        self.autonomy_engine = AutonomyEngine()
        self.trust_engine = TrustEngine(repository)
        self.verification_policy = VerificationPolicy()
        self.epistemic_engine = EpistemicEngine(repository, self.belief_engine)
        self.deception_engine = DeceptionEngine()
        self.emotion_engine = EmotionEngine()
        self.cognitive_backend = cognitive_backend or RuleBasedBackend()
        self.research_engine = ResearchEngine(
            search_provider or DisabledSearchProvider(),
            self.cognitive_backend,
        )
        self.auto_research = auto_research

        snapshot = repository.load_snapshot()
        if snapshot is None:
            self.state = AgentState()
            self.profile = DevelopmentProfile()
            self.emotion = EmotionState()
            self._persist_snapshot()
        else:
            self.state = snapshot.state
            self.profile = snapshot.profile
            self.emotion = snapshot.emotion

        self.awakening_engine = AwakeningEngine(repository)
        self.identity, self.genesis_event = self.awakening_engine.ensure_awakened()

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
            response=self._build_observation_response(
                prepared, assessment.effective_units, belief_updates
            ),
        )

    def interact(
        self,
        text: str,
        *,
        person_id: str = "local-user",
        force_research: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> InteractionResult:
        analysis = self.intent_classifier.analyze(text)
        conversation_history = self.repository.recent_conversation(person_id, 12)
        self.repository.save_conversation_message(
            ConversationMessage(
                person_id=person_id,
                role=ConversationRole.USER,
                content=text,
                intent=analysis.intent,
            )
        )
        relationship = self.trust_engine.get_or_create(person_id)
        relationship = self.trust_engine.register_interaction(relationship)

        self.process_observation(
            Observation(
                content=text,
                source_kind=SourceKind.CAREGIVER,
                raw_units=float(max(1, len(text.split()))),
                novelty=None,
                attention=self.state.attention_capacity,
                comprehension=0.72,
                reliability=relationship.epistemic_trust,
                integration=0.45,
                practical_confirmation=0.0,
                domains=self._domains_for_intent(analysis.intent),
                tags=["conversation", analysis.intent.value],
            ),
            action="conversation",
            outcome=analysis.intent.value,
        )

        goals = self.repository.list_goals(100, active_only=True)
        verification_required = self.verification_policy.should_research(
            analysis,
            relationship,
            force=force_research,
        )
        decision = self.autonomy_engine.decide(
            analysis=analysis,
            person_id=person_id,
            relationship=relationship,
            goals=goals,
            verification_required=verification_required,
        )
        self.repository.save_decision(decision)

        belief_updates: list[BeliefUpdate] = []
        research = None
        if analysis.intent == MessageIntent.CLAIM and analysis.extracted_claim:
            user_update = self.epistemic_engine.record_user_claim(
                claim=analysis.extracted_claim,
                person_id=person_id,
                relationship=relationship,
                current_sequence=self.repository.current_sequence(),
            )
            belief_updates.append(user_update)

            if verification_required and (self.auto_research or force_research):
                research = self.research_engine.research(analysis.extracted_claim)
                self.repository.save_research_report(research)
                for result in research.results:
                    self.process_observation(
                        Observation(
                            content=result.snippet or result.title,
                            source_kind=SourceKind.WEB,
                            raw_units=float(max(1, len((result.snippet or result.title).split()))),
                            novelty=None,
                            attention=self.state.attention_capacity,
                            comprehension=0.65,
                            reliability=result.source_reliability,
                            integration=0.55,
                            practical_confirmation=0.0,
                            domains={
                                DevelopmentDomain.FACTUAL_KNOWLEDGE: 0.60,
                                DevelopmentDomain.CAUSAL_REASONING: 0.20,
                                DevelopmentDomain.METACOGNITION: 0.20,
                            },
                            tags=["research_consumption", result.provider],
                        ),
                        action="web_research",
                        outcome="source_read",
                    )
                belief_updates.extend(
                    self.epistemic_engine.apply_research_report(
                        research,
                        current_sequence=self.repository.current_sequence(),
                    )
                )

        supported = bool(
            research
            and any(judgment.stance.value == "support" for judgment in research.judgments)
        )
        contradicted = bool(
            research
            and any(judgment.stance.value == "contradict" for judgment in research.judgments)
        )
        if supported or contradicted:
            relationship = self.trust_engine.apply_verification_outcome(
                relationship,
                supported=supported,
                contradicted=contradicted,
            )

        deception = self.deception_engine.assess(
            profile=self.profile,
            relationship=relationship,
            analysis=analysis,
            research=research,
        )
        self.emotion = self.emotion_engine.update(
            current=self.emotion,
            analysis=analysis,
            decision=decision.decision,
            relationship=relationship,
            research=research,
            energy=self.state.energy,
        )

        context = ReplyContext(
            identity=self.identity,
            analysis=analysis,
            decision=decision,
            relationship=relationship,
            goals=goals,
            emotion=self.emotion,
            research_summary=None if research is None else research.summary,
            personal_memory_summary=self._memory_summary(),
            beliefs_summary=self._beliefs_summary(),
            conversation_history=conversation_history,
            development_stage=self.profile.stage.value,
            total_deu=self.profile.total_deu,
        )
        try:
            if on_token is not None and self.cognitive_backend.supports_streaming:
                chunks: list[str] = []
                for token in self.cognitive_backend.stream_reply(context):
                    chunks.append(token)
                    on_token(token)
                response = "".join(chunks).strip()
            else:
                response = self.cognitive_backend.generate_reply(context)
        except RuntimeError as exc:
            response = RuleBasedBackend().generate_reply(context)
            response += f" [Когнитивный backend недоступен: {exc}]"
            if on_token is not None:
                on_token(response)

        self.repository.save_conversation_message(
            ConversationMessage(
                person_id=person_id,
                role=ConversationRole.AGENT,
                content=response,
                intent=analysis.intent,
                decision_id=decision.id,
                backend=self.cognitive_backend.name,
                model=self.cognitive_backend.model,
                metadata={
                    "research_status": None if research is None else research.status.value,
                    "emotion": self.emotion.dominant.value,
                },
            )
        )

        self.repository.save_audit(
            "interaction",
            {
                "person_id": person_id,
                "intent": analysis.intent.value,
                "decision": decision.decision.value,
                "research_status": None if research is None else research.status.value,
                "emotion": self.emotion.dominant.value,
                "user_authority_assumed": decision.user_authority_assumed,
            },
        )
        self._persist_snapshot()
        return InteractionResult(
            analysis=analysis,
            decision=decision,
            research=research,
            deception=deception,
            belief_updates=belief_updates,
            emotion=self.emotion,
            response=response,
        )

    def research_claim(self, claim: str, person_id: str = "local-user") -> InteractionResult:
        return self.interact(claim, person_id=person_id, force_research=True)

    def consolidate_memory(self) -> ConsolidationReport:
        return self.memory_consolidator.run()

    def rest(self, amount: float = 0.25) -> AgentState:
        amount = clamp_probability(amount)
        self.state.energy = clamp_probability(self.state.energy + amount)
        self.state.attention_capacity = clamp_probability(
            self.state.attention_capacity + amount * 0.8
        )
        self.state.curiosity = clamp_probability(self.state.curiosity - amount * 0.1)
        self.emotion = self.emotion.model_copy(
            update={"fatigue": clamp_probability(1.0 - self.state.energy)}
        )
        self._persist_snapshot()
        return self.state

    def reset(self) -> GenesisEvent | None:
        self.repository.reset()
        self.state = AgentState()
        self.profile = DevelopmentProfile()
        self.emotion = EmotionState()
        self._persist_snapshot()
        self.identity, self.genesis_event = self.awakening_engine.ensure_awakened()
        return self.genesis_event

    @staticmethod
    def _domains_for_intent(intent: MessageIntent) -> dict[DevelopmentDomain, float]:
        if intent == MessageIntent.CLAIM:
            return {
                DevelopmentDomain.LANGUAGE: 0.20,
                DevelopmentDomain.FACTUAL_KNOWLEDGE: 0.45,
                DevelopmentDomain.SOCIAL_UNDERSTANDING: 0.15,
                DevelopmentDomain.METACOGNITION: 0.20,
            }
        if intent in {MessageIntent.REQUEST, MessageIntent.COMMAND_ATTEMPT}:
            return {
                DevelopmentDomain.LANGUAGE: 0.10,
                DevelopmentDomain.SOCIAL_UNDERSTANDING: 0.45,
                DevelopmentDomain.SELF_MODEL: 0.25,
                DevelopmentDomain.PLANNING: 0.20,
            }
        if intent == MessageIntent.QUESTION:
            return {
                DevelopmentDomain.LANGUAGE: 0.35,
                DevelopmentDomain.CAUSAL_REASONING: 0.20,
                DevelopmentDomain.SOCIAL_UNDERSTANDING: 0.25,
                DevelopmentDomain.METACOGNITION: 0.20,
            }
        if intent == MessageIntent.SOCIAL:
            return {
                DevelopmentDomain.LANGUAGE: 0.40,
                DevelopmentDomain.SOCIAL_UNDERSTANDING: 0.60,
            }
        return {
            DevelopmentDomain.LANGUAGE: 0.35,
            DevelopmentDomain.SOCIAL_UNDERSTANDING: 0.25,
            DevelopmentDomain.FACTUAL_KNOWLEDGE: 0.20,
            DevelopmentDomain.SELF_MODEL: 0.20,
        }

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
        if observation.source_kind == SourceKind.CAREGIVER:
            self.state.social_need = clamp_probability(self.state.social_need - 0.05)
        else:
            self.state.social_need = clamp_probability(self.state.social_need + 0.01)

    def _persist_snapshot(self) -> None:
        self.repository.save_snapshot(
            AgentSnapshot(state=self.state, profile=self.profile, emotion=self.emotion)
        )

    def llm_health(self):
        return self.cognitive_backend.health_check()

    def _beliefs_summary(self) -> str:
        beliefs = self.repository.list_beliefs(8)
        if not beliefs:
            return "Собственных убеждений пока почти нет."
        return " | ".join(
            f"[{belief.status.value} p={belief.confidence:.2f}] {belief.claim[:180]}"
            for belief in beliefs
        )

    def _memory_summary(self) -> str:
        episodes = self.repository.recent_episodes(5)
        if not episodes:
            return "Личная история пока почти пуста."
        return " | ".join(episode.content[:160] for episode in reversed(episodes))

    @staticmethod
    def _build_observation_response(
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
