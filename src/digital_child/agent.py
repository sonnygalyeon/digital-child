from __future__ import annotations

import re
import threading
from collections.abc import Callable

from digital_child.associative_memory import AssociativeMemory, concepts
from digital_child.autobiography import Autobiography
from digital_child.autonomy import AutonomyEngine
from digital_child.awakening import AwakeningEngine
from digital_child.beliefs import BeliefEngine
from digital_child.cognitive_loop import CognitiveLoop
from digital_child.communication import CommunicationPreferences, CommunicationSettings
from digital_child.competence import CompetenceModel
from digital_child.consolidation import MemoryConsolidator
from digital_child.deception import DeceptionEngine
from digital_child.development import DevelopmentEngine
from digital_child.development_timeline import DevelopmentTimeline
from digital_child.emotions import EmotionEngine
from digital_child.epistemics import EpistemicEngine, VerificationPolicy
from digital_child.experience import ExperienceEngine
from digital_child.experiments import (
    EXPERIMENT_KINDS,
    Demonstration,
    ExperimentChoice,
    ExperimentEnvironment,
    ExperimentKind,
    ExperimentTrial,
)
from digital_child.initiative_runtime import InitiativeRuntime
from digital_child.intentions import IntentClassifier
from digital_child.interest_catalog import (
    DISCUSSION_GUIDANCE,
    discussion_orientation,
    preferred_interests,
)
from digital_child.interlocutor import InterlocutorMemory, InterlocutorModel
from digital_child.llm import CognitiveBackend, RuleBasedBackend
from digital_child.llm_types import ReplyContext
from digital_child.models import (
    AgentSnapshot,
    AgentState,
    BeliefUpdate,
    CognitiveEvent,
    CognitiveEventKind,
    CognitiveLoopStatus,
    ConsolidationReport,
    ConversationMessage,
    ConversationRole,
    CycleResult,
    DeferredVerification,
    DevelopmentDomain,
    DevelopmentProfile,
    EmotionState,
    Episode,
    GenesisEvent,
    Goal,
    GoalOrigin,
    GoalStatus,
    InteractionResult,
    LLMHealth,
    MessageIntent,
    Observation,
    ResearchReport,
    ResearchStatus,
    ResourceBudget,
    SourceKind,
    SourceRecord,
)
from digital_child.novelty import NoveltyEngine
from digital_child.psychology import PsychologyEngine
from digital_child.psychology_models import BehaviorTrace
from digital_child.regulation import GUIDANCE, RegulationAttempt, RegulationLearner
from digital_child.reply_guard import ReplyGuard
from digital_child.research import DisabledSearchProvider, ResearchEngine, SearchProvider
from digital_child.storage import SQLiteRepository
from digital_child.text import normalize_text
from digital_child.timekeeping import AgentClock
from digital_child.trust import TrustEngine
from digital_child.understanding import interpret_message
from digital_child.verification_runtime import VerificationRuntime


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
        research_mode: str = "blocking",
    ) -> None:
        self.repository = repository
        self._interaction_lock = threading.RLock()
        self._closed = threading.Event()
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
        self.research_mode = (
            research_mode if research_mode in {"blocking", "background", "manual"} else "background"
        )
        self.background_notifier: Callable[[str], None] | None = None
        self.initiative_notifier: Callable[[ConversationMessage], None] | None = None
        self.clock = AgentClock(repository)

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
        self.autobiography = Autobiography(repository, self.identity.id)
        self.communication = CommunicationSettings(repository, self.identity.id)
        self.experiments = ExperimentEnvironment(repository, self.identity.id)
        self.reply_guard = ReplyGuard()
        self.psychology = PsychologyEngine(repository, self.identity, self.profile)
        self.psychology.update_absence(self.profile, self.clock.now())
        self.emotion = self.emotion_engine.social_idle(self.emotion, self.psychology.snapshot())
        self._persist_snapshot()
        from digital_child.config import env_float

        self.cognitive_loop = CognitiveLoop(
            repository,
            notifier=self._notify_background,
            heartbeat_seconds=env_float("DIGITAL_CHILD_COGNITIVE_HEARTBEAT_SECONDS", 5.0),
            behavior_policy_getter=lambda: self.psychology.goal_policy(self.profile),
            clock_now=self.clock.now,
        )
        self.initiative = InitiativeRuntime(self)
        self.verification = VerificationRuntime(self)
        self._init_learning()
        self._restore_unverified_claims()

    def _init_learning(self) -> None:
        self.competence = CompetenceModel(self.repository, self.identity.id)
        self.interlocutors = InterlocutorMemory(self.repository, self.identity.id)
        self.regulation = RegulationLearner(self.repository, self.identity.id)
        self.timeline = DevelopmentTimeline(self.repository, self.identity.id)
        self.associative_memory = AssociativeMemory(
            self.repository,
            self.identity.id,
            self.cognitive_backend,
            lambda: self.cognitive_loop.budgets.consume("memory_analysis"),
        )
        # Backfill only attributable observations; legacy conversations lack a
        # reliable per-person link and stay in the existing dialogue memory.
        for episode in self.repository.recent_episodes(100, include_archived=True):
            if (
                episode.action != "conversation"
                and self.repository.load_feature("association", episode.id, self.identity.id)
                is None
            ):
                self.associative_memory.record(episode, semantic=False)
        for trial in reversed(self.experiments.history(100)):
            self.competence.record(
                "experiment:" + trial.kind,
                trial.id,
                float(trial.prediction_error == 0),
                trial.predicted_success,
            )

    def _development_state(self, person_id: str | None = None) -> dict[str, float | str]:
        psyche = self.psychology.snapshot()
        result: dict[str, float | str] = {
            "stage": self.profile.stage.value,
            "deu": round(self.profile.total_deu, 4),
            "energy": round(self.state.energy, 4),
        }
        for prefix, values in (
            ("character", psyche.character.model_dump()),
            ("value", psyche.values),
            ("mood", psyche.mood.model_dump()),
            ("self", psyche.self_model.model_dump()),
        ):
            for key, value in values.items():
                if isinstance(value, (int, float)):
                    result[f"{prefix}.{key}"] = round(float(value), 4)
        for habit in psyche.habits:
            result[f"habit.{habit.cue}.{habit.strategy}"] = round(habit.strength, 4)
        for estimate in self.competence.diagnostics():
            confidence = estimate["confidence"]
            if isinstance(confidence, (float, int)):
                result["skill." + str(estimate["skill"])] = round(float(confidence), 4)
        for belief in self.repository.list_beliefs(500):
            result["belief." + belief.id + ".confidence"] = round(belief.confidence, 4)
            result["belief." + belief.id + ".status"] = belief.status.value
        if person_id:
            relationship = self.repository.load_relationship(person_id)
            if relationship:
                result["trust.epistemic"] = round(relationship.epistemic_trust, 4)
                result["trust.affective"] = round(relationship.affective_trust, 4)
        return result

    def competence_guidance(self, text: str) -> str:
        topics = concepts(text)
        skills = (
            ["experiment:balance", "experiment:transfer"]
            if "causality" in topics
            else ["finding_evidence"]
            if "evidence" in topics
            else ["topic:" + topic for topic in topics[:2]] or ["general_dialogue"]
        )
        return self.competence.guidance(skills)

    def learning_curriculum(self) -> list[ExperimentChoice]:
        return self.experiments.curriculum(self.competence)

    def _response_strategy(self, text: str, needs_clarification: bool) -> str:
        if needs_clarification:
            return "clarify"
        if re.search(r"эксперимент|модел[ьи] направления|закрыт[а-я]* сред", text, re.I):
            estimate = self.competence.get("experiment:balance")
            if estimate.samples < 4 or estimate.confidence < 0.65:
                return "propose_experiment"
        return "answer_with_limits"

    def _restore_unverified_claims(self) -> None:
        reports = {
            report.claim: report
            for report in self.repository.list_research_reports(500)
            if report.status == ResearchStatus.COMPLETED
        }
        with self.repository.transaction():
            for message in self.repository.untracked_claim_messages():
                analysis = self.intent_classifier.analyze(message.content)
                if analysis.is_subjective or not analysis.extracted_claim:
                    continue
                report = reports.get(message.content)
                self.repository.save_verification(
                    DeferredVerification(
                        source=message,
                        claim=message.content,
                        next_attempt_at=self.clock.now(),
                        report=report,
                        completed=report is not None,
                        notified=report is not None,
                    )
                )

    def process_observation(
        self,
        observation: Observation,
        *,
        action: str = "observe",
        outcome: str = "information_received",
        reward: float = 0.0,
    ) -> CycleResult:
        with self._interaction_lock:
            before = self._development_state() if action != "conversation" else {}
            result = self._process_observation(
                observation, action=action, outcome=outcome, reward=reward
            )
            if action != "conversation":
                self.timeline.record(
                    "observation",
                    "Получен опыт: " + outcome,
                    before,
                    self._development_state(),
                    episode_ids=[] if result.episode_id is None else [result.episode_id],
                    now=self.clock.now(),
                )
            return result

    def _process_observation(
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

        if action != "conversation":
            self.psychology.observe(prepared, self.profile, stored_episode)
            self.autobiography.record(stored_episode, self.profile)
            self.associative_memory.record(stored_episode, semantic=False)
        self._persist_snapshot()
        return CycleResult(
            episode_id=stored_episode.id,
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
        self.initiative.begin_interaction()
        try:
            with self._interaction_lock:
                return self._interact(
                    text, person_id=person_id, force_research=force_research, on_token=on_token
                )
        finally:
            self.initiative.end_interaction()

    def _interact(
        self,
        text: str,
        *,
        person_id: str = "local-user",
        force_research: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> InteractionResult:
        before_development = self._development_state(person_id)
        associated = self.associative_memory.search(text, person_id)
        analysis = self.intent_classifier.analyze(text)
        from digital_child.config import env_int

        conversation_history = self.repository.recent_conversation(
            person_id, env_int("DIGITAL_CHILD_LLM_HISTORY_MESSAGES", 6)
        )
        analysis = interpret_message(self.cognitive_backend, analysis, conversation_history)
        feedback = re.search(
            r"слишком часто (?:возвращаешься к|пишешь про|говоришь о)\s+(.+)", text, re.I
        )
        if feedback:
            self.communication.snooze_topic(person_id, feedback[1].rstrip(".!? "), self.clock.now())
            analysis = analysis.model_copy(
                update={
                    "intent": MessageIntent.SOCIAL,
                    "speech_acts": [MessageIntent.SOCIAL],
                    "extracted_claim": None,
                    "is_subjective": True,
                }
            )
        incoming = ConversationMessage(
            created_at=self.clock.now(),
            person_id=person_id,
            role=ConversationRole.USER,
            content=text,
            intent=analysis.intent,
        )
        self.repository.save_conversation_message(incoming)
        self.psychology.sync_contacts(
            [incoming],
            {
                person_id: self.communication.get(person_id).initiative_enabled,
            },
        )
        contact = self.psychology.snapshot().relationships.get(person_id)
        if contact is not None and (
            contact.initiative_allowed != self.communication.get(person_id).initiative_enabled
        ):
            self.communication.update(person_id, {"initiative_enabled": contact.initiative_allowed})
        self.psychology.update_absence(self.profile, incoming.created_at)
        relationship = self.trust_engine.get_or_create(person_id)
        relationship = self.trust_engine.register_interaction(relationship)

        observation_result = self.process_observation(
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
        episode = self.repository.get_episode(observation_result.episode_id or "")
        if episode is None:
            raise RuntimeError("Conversation experience was not persisted")
        affective_before = relationship.affective_trust
        behavior = self.psychology.evaluate(
            analysis=analysis,
            profile=self.profile,
            relationship=relationship,
            base_decision=decision,
            novelty=observation_result.calculated_novelty,
            energy=self.state.energy,
            episode=episode,
            associated_episode_ids=[item.episode.id for item in associated],
        )
        decision = behavior.decision
        self.regulation.observe_next(
            person_id,
            behavior.trace.appraisal.overload,
            analysis.intent != MessageIntent.SOCIAL and behavior.trace.appraisal.overload < 0.6,
            episode.id,
            self.clock.now(),
            text,
        )
        regulation = self.regulation.choose(
            person_id,
            behavior.trace.appraisal.overload,
            self.state.energy,
            episode.id,
            self.clock.now(),
            analysis.needs_clarification,
            text,
        )
        self.interlocutors.observe(person_id, analysis, episode.id)
        relationship = self.trust_engine.apply_social_experience(
            person_id,
            behavior.affective_trust_delta,
        )
        self.repository.save_decision(decision)
        self.emit_cognitive_event(
            CognitiveEventKind.INTERACTION,
            source=f"person:{person_id}",
            importance=0.55,
            payload={
                "intent": analysis.intent.value,
                "decision": decision.decision.value,
                "novelty": observation_result.calculated_novelty,
                "contains_pressure": analysis.contains_pressure,
                "psychological_load": behavior.trace.appraisal.overload,
                "boredom": behavior.trace.appraisal.boredom,
            },
        )
        if analysis.extracted_claim:
            self.emit_cognitive_event(
                CognitiveEventKind.CLAIM_RECEIVED,
                source=f"person:{person_id}",
                importance=0.60,
                payload={"claim": analysis.extracted_claim or text},
            )
        if analysis.contains_pressure or analysis.intent == MessageIntent.COMMAND_ATTEMPT:
            self.emit_cognitive_event(
                CognitiveEventKind.COMMAND_PRESSURE,
                source=f"person:{person_id}",
                importance=0.72,
                payload={"text": text, "decision": decision.decision.value},
            )
        if analysis.intent == MessageIntent.REQUEST:
            self._record_suggested_goal(text, decision.decision.value)

        belief_updates: list[BeliefUpdate] = []
        research = None
        research_pending = False
        verification_task = None
        if analysis.extracted_claim and not analysis.is_subjective:
            user_update = self.epistemic_engine.record_user_claim(
                claim=analysis.extracted_claim,
                person_id=person_id,
                relationship=relationship,
                current_sequence=self.repository.current_sequence(),
            )
            belief_updates.append(user_update)
            verification_task = DeferredVerification(
                source=incoming,
                claim=analysis.extracted_claim,
                next_attempt_at=self.clock.now(),
                behavior_trace_json=behavior.trace.model_dump_json(),
                source_episode_id=episode.id,
            )
            self.repository.save_verification(verification_task)

            if verification_required and (self.auto_research or force_research):
                if self.research_mode == "background" and not force_research:
                    research_pending = True
                elif self.research_mode != "manual" or force_research:
                    research = self._perform_research(analysis.extracted_claim)
                    belief_updates.extend(
                        self.epistemic_engine.apply_research_report(
                            research,
                            current_sequence=self.repository.current_sequence(),
                        )
                    )

        if any(update.belief.status.value == "contested" for update in belief_updates):
            self.emit_cognitive_event(
                CognitiveEventKind.CONTRADICTION,
                source="belief_engine",
                importance=0.82,
                payload={
                    "belief_ids": [
                        update.belief.id
                        for update in belief_updates
                        if update.belief.status.value == "contested"
                    ]
                },
            )

        supported = bool(
            research and any(judgment.stance.value == "support" for judgment in research.judgments)
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
        if research is not None:
            self.psychology.integrate_research(research, self.profile, behavior.trace)
            self._learn_research(research)
            if verification_task is not None:
                from datetime import timedelta

                self.repository.save_verification(
                    verification_task.model_copy(
                        update={
                            "attempts": 1,
                            "report": research,
                            "completed": research.status == ResearchStatus.COMPLETED,
                            "notified": research.status == ResearchStatus.COMPLETED,
                            "next_attempt_at": self.clock.now() + timedelta(minutes=5),
                        }
                    )
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
            appraisal=behavior.trace.appraisal,
            development=behavior.development,
            psychology=self.psychology.snapshot(),
        )

        psyche = self.psychology.snapshot()
        orientation = discussion_orientation(psyche, self.profile)
        preferences = self.communication.get(person_id)
        context = ReplyContext(
            identity=self.identity,
            analysis=analysis,
            decision=decision,
            relationship=relationship,
            goals=goals,
            emotion=self.emotion,
            research_summary=(
                "Проверка поставлена в фоновую очередь; утверждение пока не подтверждено."
                if research_pending
                else (None if research is None else research.summary)
            ),
            personal_memory_summary=(
                self.associative_memory.summary(associated)
                + " | "
                + self._memory_summary(text, person_id, associative=False)
            ),
            beliefs_summary=self._beliefs_summary(),
            needs_summary=self._needs_summary(),
            active_goal_summary=self._active_goal_summary(),
            conversation_history=conversation_history,
            development_stage=self.profile.stage.value,
            total_deu=self.profile.total_deu,
            psychology_summary=self.psychology.summary(self.psychology.snapshot()),
            development_summary=(
                f"регуляция={behavior.development.regulation:.2f}; "
                f"рефлексия={behavior.development.reflection:.2f}; "
                f"учёт другой точки зрения={behavior.development.perspective_taking:.2f}; "
                f"горизонт планирования={behavior.development.planning_horizon:.2f}"
            ),
            behavior_guidance=tuple(behavior.trace.guidance) + (DISCUSSION_GUIDANCE[orientation],),
            discussion_orientation=orientation,
            interests_summary="; ".join(
                item.topic for item in preferred_interests(psyche, self.profile, 6)
            ),
            behavior_style=behavior.trace.style,
            coping_strategy=behavior.trace.coping,
            biography_summary=self.autobiography.summary(person_id),
            communication_guidance=f"Предпочтительная длина ответа: {preferences.reply_length}.",
            max_reply_chars=preferences.reply_chars,
            competence_guidance=self.competence_guidance(text),
            interlocutor_summary=self.interlocutors.summary(person_id, text),
            regulation_guidance="" if regulation is None else GUIDANCE[regulation.strategy],
            response_strategy=self._response_strategy(text, analysis.needs_clarification),
        )
        review_backend = self.cognitive_backend
        try:
            draft = self.cognitive_backend.generate_reply(context).strip()
        except RuntimeError:
            draft = RuleBasedBackend().generate_reply(context)
            review_backend = RuleBasedBackend()
        guarded = self.reply_guard.finalize(review_backend, context, draft)
        response = guarded.text
        if regulation is not None:
            self.regulation.finish(regulation, response)
        if analysis.intent == MessageIntent.QUESTION and not guarded.fallback:
            self.interlocutors.record_explanation(person_id, response)
        self.associative_memory.record(
            episode,
            person_id,
            [update.belief.id for update in belief_updates],
            decision=decision.decision.value,
            consequences=[
                f"Изменение эмоционального доверия: "
                f"{relationship.affective_trust - affective_before:+.3f}"
            ],
        )
        if research is not None and research.status == ResearchStatus.COMPLETED:
            self.associative_memory.link_report(episode.id, research)
        self.repository.save_audit(
            "reply_review",
            {
                "person_id": person_id,
                "issues": list(guarded.issues),
                "revised": guarded.revised,
                "semantic_checked": guarded.semantic_checked,
                "fallback": guarded.fallback,
            },
        )
        # Only reviewed text reaches the UI, including the streaming callback.
        if on_token is not None:
            on_token(response)
        self.autobiography.record(
            episode,
            self.profile,
            person_id,
            decision.decision.value,
            relationship.affective_trust - affective_before,
        )
        if research is not None and research.status == ResearchStatus.COMPLETED:
            self.autobiography.record_research(research, episode.id)
        self.timeline.record(
            "interaction",
            f"Диалог: {decision.decision.value}; "
            + ("саморегуляция " + regulation.strategy if regulation else "оценка ситуации"),
            before_development,
            self._development_state(person_id),
            person_id=person_id,
            episode_ids=[episode.id],
            report=research,
            now=self.clock.now(),
            related_records={} if regulation is None else {"regulation": regulation.id},
        )

        self.repository.save_conversation_message(
            ConversationMessage(
                created_at=self.clock.now(),
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
                    "behavior_style": behavior.trace.style,
                    "coping_strategy": behavior.trace.coping,
                    "reply_review": {
                        "revised": guarded.revised,
                        "semantic_checked": guarded.semantic_checked,
                        "fallback": guarded.fallback,
                    },
                    "understanding": analysis.model_dump(mode="json"),
                    "response_strategy": context.response_strategy,
                    "regulation_attempt_id": None if regulation is None else regulation.id,
                    "memory_episode_ids": [item.episode.id for item in associated],
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
        if research_pending:
            self.verification.start()
        return InteractionResult(
            analysis=analysis,
            decision=decision,
            research=research,
            deception=deception,
            belief_updates=belief_updates,
            emotion=self.emotion,
            response=response,
        )

    def set_background_notifier(self, notifier: Callable[[str], None] | None) -> None:
        self.background_notifier = notifier

    def set_initiative_notifier(
        self, notifier: Callable[[ConversationMessage], None] | None
    ) -> None:
        self.initiative_notifier = notifier

    def set_initiative_enabled(self, enabled: bool) -> None:
        self.initiative.invalidate()
        with self._interaction_lock:
            self.psychology.set_initiative_enabled(enabled)

    def update_communication(
        self, person_id: str, patch: dict[str, object]
    ) -> CommunicationPreferences:
        self.initiative.invalidate()
        with self._interaction_lock:
            preferences = self.communication.update(person_id, patch)
            if "initiative_enabled" in patch:
                self.psychology.set_contact_initiative(person_id, preferences.initiative_enabled)
            return preferences

    def run_experiment(
        self,
        kind: ExperimentKind = "balance",
        *,
        autonomous: bool = False,
        choice: ExperimentChoice | None = None,
    ) -> ExperimentTrial:
        if kind not in EXPERIMENT_KINDS:
            raise ValueError("Неизвестная закрытая среда")
        with self._interaction_lock:
            before_development = self._development_state()
            previous = (
                self.state.model_copy(deep=True),
                self.profile.model_copy(deep=True),
                self.emotion.model_copy(deep=True),
                self.psychology.snapshot(),
            )
            trial = self.experiments.prepare(kind, self.clock.now(), autonomous)
            trial.predicted_success = self.competence.get("experiment:" + kind).confidence
            if choice:
                trial.selection_reason = choice.reason
                trial.expected_information_gain = choice.expected_information_gain

            def commit(budget: ResourceBudget) -> None:
                with self.repository.transaction():
                    if autonomous and not self.cognitive_loop.budgets.consume(
                        "autonomous_experiments"
                    ):
                        raise ValueError("Дневной лимит самостоятельных экспериментов исчерпан")
                    result = self._process_observation(
                        Observation(
                            content=f"Закрытая среда {kind}, контекст {trial.context}: "
                            f"{trial.before}, "
                            f"действие {trial.action}; "
                            f"прогноз {trial.predicted_after:g}, результат {trial.actual_after}.",
                            source_kind=SourceKind.ENVIRONMENT,
                            raw_units=4,
                            attention=0.9,
                            comprehension=0.9,
                            reliability=1.0,
                            integration=0.8,
                            practical_confirmation=1.0,
                            tags=["closed_experiment", kind],
                            domains={
                                DevelopmentDomain.CAUSAL_REASONING: 0.5,
                                DevelopmentDomain.METACOGNITION: 0.3,
                                DevelopmentDomain.TOOL_USE: 0.2,
                            },
                        ),
                        action="closed_experiment",
                        outcome="success" if trial.success else "prediction_error",
                        reward=trial.reward,
                    )
                    trial.episode_id = result.episode_id
                    self.experiments.save(trial)
                    self.psychology.integrate_experiment(trial, self.profile)
                    self.competence.record(
                        "experiment:" + kind,
                        trial.id,
                        float(trial.prediction_error == 0),
                        trial.predicted_success,
                    )
                    self.timeline.record(
                        "experiment",
                        trial.selection_reason,
                        before_development,
                        self._development_state(),
                        episode_ids=[] if trial.episode_id is None else [trial.episode_id],
                        now=self.clock.now(),
                        related_records={"experiment": trial.id},
                    )
                    self.repository.save_budget(budget)

            try:
                if not self.cognitive_loop.budgets.consume_with("experiments", commit):
                    raise ValueError("Дневной лимит экспериментов исчерпан")
            except Exception:
                self.state, self.profile, self.emotion = previous[:3]
                with self.psychology._lock:
                    self.psychology.state = previous[3]
                raise
            return trial

    def maybe_experiment(self) -> None:
        from digital_child.config import env_bool

        if not env_bool("DIGITAL_CHILD_AUTO_EXPERIMENTS", True) or self.state.energy < 0.35:
            return
        now = self.clock.now()
        inputs = self.repository.latest_user_messages(1)
        last_contact = inputs[0].created_at if inputs else self.clock.launch_at
        if (now - last_contact).total_seconds() < 300:
            return
        history = self.experiments.history(4)
        if history and (now - history[0].created_at).total_seconds() < 3600:
            return
        if (
            self.cognitive_loop.budgets.get("autonomous_experiments").remaining == 0
            or self.cognitive_loop.budgets.get("experiments").remaining == 0
        ):
            return
        choices = self.learning_curriculum()
        if choices:
            self.run_experiment(choices[0].kind, autonomous=True, choice=choices[0])

    def demonstrate(self, example: Demonstration) -> Demonstration:
        with self._interaction_lock:
            example.created_at = self.clock.now()
            saved = self.experiments.demonstrate(example)
            self.timeline.record(
                "demonstration",
                "Получена непроверенная гипотеза из примера: " + saved.kind,
                {},
                {},
                person_id=saved.person_id,
                now=self.clock.now(),
                related_records={"demonstration": saved.id},
            )
            return saved

    def correct_interlocutor(
        self, person_id: str, text: str, *, clear_notes: bool = False
    ) -> InterlocutorModel:
        self.initiative.invalidate()
        with self._interaction_lock:
            model = self.interlocutors.correct(person_id, text, clear_notes=clear_notes)
            self.timeline.record(
                "person_model",
                "Собеседник исправил сведения о себе: " + text[:160],
                {},
                {},
                person_id=person_id,
                now=self.clock.now(),
                related_records={"interlocutor": person_id},
            )
            return model

    def regulation_feedback(self, attempt_id: str, helpful: bool) -> RegulationAttempt:
        with self._interaction_lock:
            result = self.regulation.feedback(attempt_id, helpful)
            self.timeline.record(
                "regulation_feedback",
                "Оценка стратегии "
                + result.strategy
                + (": помогла" if helpful else ": не помогла"),
                {},
                {},
                person_id=result.person_id,
                episode_ids=[result.episode_id],
                now=self.clock.now(),
                related_records={"regulation": result.id},
            )
            return result

    def maybe_regulate(self) -> None:
        if self.state.energy >= 0.35:
            return
        from digital_child.config import env_bool

        if not env_bool("DIGITAL_CHILD_AUTO_REGULATION", True):
            return
        saved = self.repository.load_feature("regulation_clock", "rest", self.identity.id)
        if saved and (self.clock.now().timestamp() - float(str(saved["at"]))) < 3600:
            return
        if self.cognitive_loop.budgets.consume("regulated_rest"):
            self._rest(0.08)
            self.repository.save_feature(
                "regulation_clock", "rest", self.identity.id, {"at": self.clock.now().timestamp()}
            )

    def _learn_research(self, report: ResearchReport) -> None:
        # Measures ability to obtain usable evidence, not truth of the original claim.
        if report.status != ResearchStatus.COMPLETED:
            return
        informative = bool(
            report.results
            and any(item.stance.value in {"support", "contradict"} for item in report.judgments)
        )
        self.competence.record(
            "finding_evidence",
            report.id,
            float(informative),
            self.competence.get("finding_evidence").confidence,
        )

    def initiative_status(self) -> dict[str, object]:
        with self._interaction_lock:
            psyche = self.psychology.snapshot()
            status = self.cognitive_loop.status
            return {
                "enabled": self.initiative.settings.enabled and psyche.initiative_enabled,
                "running": status.running and not status.paused,
                "longing": psyche.mood.social_longing,
                "boredom": psyche.mood.absence_boredom,
                "budget": self.cognitive_loop.budgets.get("initiative_messages").model_dump(
                    mode="json"
                ),
                "contacts": {
                    key: {
                        "last_contact_at": None
                        if item.last_contact_at is None
                        else item.last_contact_at.isoformat(),
                        "longing": item.longing,
                        "unanswered": item.unanswered_initiatives,
                        "allowed": item.initiative_allowed,
                    }
                    for key, item in psyche.relationships.items()
                },
            }

    def _perform_research(self, claim: str) -> ResearchReport:
        research = self.research_engine.research(claim)
        self.repository.save_research_report(research)
        return research

    def _apply_deferred_verification(
        self, task: DeferredVerification, report: ResearchReport
    ) -> None:
        completed = report.status == ResearchStatus.COMPLETED
        previous_psychology = self.psychology.snapshot()
        before_development = self._development_state(task.source.person_id)
        try:
            # Evidence, trust and queue completion are committed together.
            with self.repository.transaction():
                self.repository.save_research_report(report)
                if completed:
                    self.epistemic_engine.apply_research_report(
                        report, current_sequence=self.repository.current_sequence()
                    )
                    supported = any(j.stance.value == "support" for j in report.judgments)
                    contradicted = any(j.stance.value == "contradict" for j in report.judgments)
                    relationship = self.trust_engine.get_or_create(task.source.person_id)
                    self.trust_engine.apply_verification_outcome(
                        relationship, supported=supported, contradicted=contradicted
                    )
                    trace = (
                        None
                        if task.behavior_trace_json is None
                        else BehaviorTrace.model_validate_json(task.behavior_trace_json)
                    )
                    self.psychology.integrate_research(report, self.profile, trace)
                    self._learn_research(report)
                    self.autobiography.record_research(report, task.source_episode_id)
                    self.associative_memory.link_report(task.source_episode_id, report)
                    self.timeline.record(
                        "research",
                        "Пересмотр убеждений и доверия по внешним свидетельствам",
                        before_development,
                        self._development_state(task.source.person_id),
                        person_id=task.source.person_id,
                        report=report,
                        episode_ids=[]
                        if task.source_episode_id is None
                        else [task.source_episode_id],
                        now=self.clock.now(),
                    )
                self.repository.save_verification(
                    task.model_copy(
                        update={
                            "report": report,
                            "completed": completed,
                            "notified": completed
                            and not any(j.stance.value == "contradict" for j in report.judgments),
                        }
                    )
                )
                self.repository.save_audit(
                    "deferred_verification",
                    {
                        "task_id": task.id,
                        "person_id": task.source.person_id,
                        "claim": task.claim,
                        "status": report.status.value,
                    },
                )
        except Exception:
            with self.psychology._lock:
                self.psychology.state = previous_psychology
            raise
        self.emit_cognitive_event(
            CognitiveEventKind.RESEARCH_COMPLETED
            if completed
            else CognitiveEventKind.RESEARCH_FAILED,
            source="verification_worker",
            importance=0.72,
            payload={"claim": task.claim, "status": report.status.value},
        )

    def research_claim(self, claim: str, person_id: str = "local-user") -> InteractionResult:
        return self.interact(claim, person_id=person_id, force_research=True)

    def consolidate_memory(self) -> ConsolidationReport:
        return self.memory_consolidator.run()

    def rest(self, amount: float = 0.25) -> AgentState:
        with self._interaction_lock:
            return self._rest(amount)

    def _rest(self, amount: float = 0.25) -> AgentState:
        before_development = self._development_state()
        amount = clamp_probability(amount)
        self.state.energy = clamp_probability(self.state.energy + amount)
        self.state.attention_capacity = clamp_probability(
            self.state.attention_capacity + amount * 0.8
        )
        self.state.curiosity = clamp_probability(self.state.curiosity - amount * 0.1)
        self.emotion = self.emotion.model_copy(
            update={"fatigue": clamp_probability(1.0 - self.state.energy)}
        )
        self.psychology.rest(amount, self.profile)
        self.emotion = self.emotion_engine.idle_decay(self.emotion, amount=amount * 0.3)
        self._persist_snapshot()
        self.timeline.record(
            "recovery",
            "Восстановление ресурсов без начисления опыта",
            before_development,
            self._development_state(),
            now=self.clock.now(),
        )
        self.emit_cognitive_event(
            CognitiveEventKind.REST,
            source="self",
            importance=0.45,
            payload={"amount": amount},
        )
        return self.state

    def reset(self) -> GenesisEvent | None:
        with self._interaction_lock:
            return self._reset()

    def _reset(self) -> GenesisEvent | None:
        was_running = self.cognitive_loop.status.running
        self.initiative.stop()
        self.verification.stop()
        self.cognitive_loop.stop()
        self.repository.reset()
        self.state = AgentState()
        self.profile = DevelopmentProfile()
        self.emotion = EmotionState()
        self._persist_snapshot()
        self.identity, self.genesis_event = self.awakening_engine.ensure_awakened()
        self.autobiography = Autobiography(self.repository, self.identity.id)
        self.communication = CommunicationSettings(self.repository, self.identity.id)
        self.experiments = ExperimentEnvironment(self.repository, self.identity.id)
        self.psychology = PsychologyEngine(self.repository, self.identity, self.profile)
        from digital_child.config import env_float

        self.cognitive_loop = CognitiveLoop(
            self.repository,
            notifier=self._notify_background,
            heartbeat_seconds=env_float("DIGITAL_CHILD_COGNITIVE_HEARTBEAT_SECONDS", 5.0),
            behavior_policy_getter=lambda: self.psychology.goal_policy(self.profile),
            clock_now=self.clock.now,
        )
        self._init_learning()
        if was_running:
            self.cognitive_loop.start()
            self.initiative.start()
            self.verification.start()
        return self.genesis_event

    def _notify_background(self, message: str) -> None:
        if self.background_notifier is not None:
            self.background_notifier(message)

    def emit_cognitive_event(
        self,
        kind: CognitiveEventKind,
        *,
        source: str,
        importance: float = 0.5,
        payload: dict[str, object] | None = None,
    ) -> CognitiveEvent:
        return self.cognitive_loop.publish(
            CognitiveEvent(
                kind=kind,
                source=source,
                importance=clamp_probability(importance),
                payload=payload or {},
            )
        )

    def start_cognitive_loop(self) -> CognitiveLoopStatus:
        self.cognitive_loop.start()
        self.initiative.start()
        self.verification.start()
        return self.cognitive_loop.status

    def stop_cognitive_loop(self) -> CognitiveLoopStatus:
        self.initiative.stop()
        self.verification.stop()
        self.cognitive_loop.stop()
        return self.cognitive_loop.status

    def pause_cognitive_loop(self) -> CognitiveLoopStatus:
        self.initiative.invalidate()
        return self.cognitive_loop.pause()

    def resume_cognitive_loop(self) -> CognitiveLoopStatus:
        self.cognitive_loop.start()
        self.initiative.start()
        self.verification.start()
        return self.cognitive_loop.resume()

    def cognitive_tick(self) -> CognitiveLoopStatus:
        return self.cognitive_loop.tick_once()

    def close(self) -> None:
        self._closed.set()
        self.initiative.stop()
        self.verification.stop()
        with self._interaction_lock:
            self.cognitive_loop.stop()
            self.repository.close()

    def _record_suggested_goal(self, text: str, decision: str) -> Goal | None:
        if decision == "refuse":
            return None
        normalized = normalize_text(text)
        for goal in self.repository.list_goals(100, active_only=True):
            if normalize_text(goal.description) == normalized:
                return None
        goal = Goal(
            title=(text[:96] + "…") if len(text) > 96 else text,
            description=text,
            priority=0.46 if decision == "negotiate" else 0.56,
            urgency=0.30,
            expected_utility=0.48,
            estimated_cost=0.35,
            risk=0.12,
            value_alignment=0.50,
            status=GoalStatus.ACTIVE,
            origin=GoalOrigin.SUGGESTED,
            success_criteria=["Личность самостоятельно решила, принимать ли предложение."],
        )
        self.repository.save_goal(goal)
        self.emit_cognitive_event(
            CognitiveEventKind.GOAL_CREATED,
            source="user_suggestion",
            importance=0.50,
            payload={"goal_id": goal.id, "origin": goal.origin.value},
        )
        return goal

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

    def diagnostics(self) -> dict[str, object]:
        health = self.llm_health()
        return {
            "version": "0.5.0",
            "database": str(self.repository.database_path),
            "llm": health.model_dump(mode="json"),
            "cognitive_loop": self.cognitive_loop.status.model_dump(mode="json"),
            "needs": [item.model_dump(mode="json") for item in self.cognitive_loop.needs()],
            "budgets": [
                item.model_dump(mode="json") for item in self.cognitive_loop.budgets.list()
            ],
            "active_goal": self._active_goal_summary(),
            "active_goal_count": len(self.repository.list_goals(500, active_only=True)),
            "pending_cognitive_events": len(self.repository.pending_cognitive_events(500)),
            "conversation_messages": len(self.repository.recent_conversation("local-user", 500)),
            "psychology": self.psychology.diagnostics(self.profile),
            "time": self.clock.diagnostics(),
            "pending_verifications": self.repository.pending_verification_count(),
            "experiments": [item.model_dump(mode="json") for item in self.experiments.history(5)],
            "biography_chapters": len(self.autobiography.chapters(500)),
            "competence": self.competence.diagnostics(),
            "curriculum": [item.model_dump(mode="json") for item in self.learning_curriculum()],
            "regulation": [
                item.model_dump(mode="json") for item in self.regulation.history(limit=5)
            ],
            "timeline": [item.model_dump(mode="json") for item in self.timeline.history(limit=5)],
        }

    def llm_health(self) -> LLMHealth:
        return self.cognitive_backend.health_check()

    def _needs_summary(self) -> str:
        needs = self.cognitive_loop.needs()
        return " | ".join(f"{item.kind.value}={item.level:.2f}" for item in needs)

    def _active_goal_summary(self) -> str:
        status = self.cognitive_loop.status
        if status.active_goal_id is None:
            return "нет выбранной внутренним циклом цели"
        for goal in self.repository.list_goals(100, active_only=True):
            if goal.id == status.active_goal_id:
                return f"{goal.title}; priority={goal.priority:.2f}; origin={goal.origin.value}"
        return "выбранная цель больше не активна"

    def _beliefs_summary(self) -> str:
        from digital_child.config import env_int

        beliefs = self.repository.list_beliefs(env_int("DIGITAL_CHILD_LLM_BELIEF_ITEMS", 4))
        if not beliefs:
            return "Собственных убеждений пока почти нет."
        return " | ".join(
            f"[{belief.status.value} p={belief.confidence:.2f}] {belief.claim[:180]}"
            for belief in beliefs
        )

    def _memory_summary(
        self, text: str = "", person_id: str = "local-user", *, associative: bool = True
    ) -> str:
        from digital_child.config import env_int

        old = self.psychology.memory_summary(
            text,
            person_id,
            env_int("DIGITAL_CHILD_LLM_MEMORY_ITEMS", 4),
        )
        if not associative:
            return old
        return (
            self.associative_memory.summary(self.associative_memory.search(text, person_id))
            + " | "
            + old
        )

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
            return f"Я получил {gained_deu:.3f} DEU и обновил {len(updates)} убеждение(я)."
        if (observation.novelty or 0.0) > 0.75:
            return f"Это новое для меня. Я усвоил {gained_deu:.3f} DEU опыта."
        if observation.integration > 0.70:
            return f"Я связал это с прежним опытом и получил {gained_deu:.3f} DEU."
        return f"Я сохранил наблюдение и получил {gained_deu:.3f} DEU."
