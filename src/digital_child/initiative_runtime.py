from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from digital_child.behavioral_development import developmental_dynamics
from digital_child.initiative import (
    InitiativePlan,
    InitiativePlanner,
    InitiativeSettings,
    elapsed_seconds,
    utc,
)
from digital_child.interest_catalog import preferred_interests
from digital_child.llm import RuleBasedBackend
from digital_child.llm_types import ReplyContext
from digital_child.models import (
    AutonomyDecision,
    AutonomyDecisionKind,
    ConversationMessage,
    ConversationRole,
    DeferredVerification,
    MessageAnalysis,
    MessageIntent,
)
from digital_child.text import normalize_text

if TYPE_CHECKING:
    from digital_child.agent import DigitalChildAgent


class InitiativeRuntime:
    """Slow generation runs separately from both the cheap loop and foreground chat."""

    def __init__(self, agent: DigitalChildAgent) -> None:
        self.agent = agent
        self.settings = InitiativeSettings.from_environment()
        self.planner = InitiativePlanner()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._generation_lock = threading.Lock()
        self._activity_lock = threading.Lock()
        self._foreground = 0
        self._revision = 0

    def begin_interaction(self) -> None:
        with self._activity_lock:
            self._foreground += 1
            self._revision += 1

    def end_interaction(self) -> None:
        with self._activity_lock:
            self._foreground -= 1

    def invalidate(self) -> None:
        with self._activity_lock:
            self._revision += 1

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive() and not self._stop.is_set():
            return
        # Never clear an old event while its generator is still unwinding.
        self._stop = threading.Event()
        stop = self._stop
        self._thread = threading.Thread(
            target=self._run, args=(stop,), name="digital-child-initiative", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.invalidate()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def _cancelled(self, revision: int, stop: threading.Event) -> bool:
        with self._activity_lock:
            busy = self._foreground > 0 or self._revision != revision
        status = self.agent.cognitive_loop.status
        return (
            busy
            or stop.is_set()
            or self.agent._closed.is_set()
            or not status.running
            or status.paused
        )

    def _run(self, stop: threading.Event) -> None:
        while not stop.wait(self.settings.poll_seconds):
            try:
                self.tick(stop)
            except Exception as exc:
                with self.agent._interaction_lock:
                    if stop.is_set() or self.agent._closed.is_set():
                        return
                    self.agent.repository.save_audit("initiative_error", {"error": str(exc)})

    def tick(self, stop: threading.Event) -> None:
        if not self._generation_lock.acquire(blocking=False):
            return
        try:
            self._tick(stop)
        finally:
            self._generation_lock.release()

    def _tick(self, stop: threading.Event) -> None:
        agent = self.agent
        if not agent._interaction_lock.acquire(blocking=False):
            return
        try:
            with self._activity_lock:
                revision = self._revision
            if self._cancelled(revision, stop):
                return
            now = agent.clock.now()
            agent.maybe_regulate()
            agent.associative_memory.backfill(100)
            agent.maybe_projects()
            agent.maybe_plan()
            agent.maybe_experiment()
            inputs = agent.repository.latest_user_messages()
            agent.psychology.sync_contacts(inputs)
            agent.psychology.update_absence(agent.profile, now)
            psyche = agent.psychology.snapshot()
            agent.update_idle_emotion()
            verification = self._verification_notice(inputs)
            plan = None if verification is None else verification[0]
            if plan is None:
                plan = self.planner.choose(
                    psyche,
                    agent.profile,
                    inputs,
                    now=now,
                    settings=self.settings,
                    energy=agent.state.energy,
                    preferences={
                        source.person_id: agent.communication.get(source.person_id)
                        for source in inputs
                    },
                )
            if (
                plan is None
                or agent.cognitive_loop.budgets.get("initiative_messages").remaining == 0
            ):
                return
            history = agent.repository.recent_conversation(plan.person_id, 8)
            if plan.kind == "discussion" and history and history[-1].content.rstrip().endswith("?"):
                # A question already handed the turn to the human; give them room to answer.
                agent.psychology.skip_discussion(plan.person_id, plan.source.id)
                return
            context = self._context(plan, history)
            agent.psychology.record_initiative_attempt(plan.person_id, now)
            subject_id = agent.identity.id
        finally:
            agent._interaction_lock.release()

        response = (
            verification[2] if verification is not None else self._generate(context, revision, stop)
        )
        if not response or self._cancelled(revision, stop):
            return
        response = agent.reply_guard.finalize(
            RuleBasedBackend() if verification else agent.cognitive_backend, context, response
        ).text
        if not response or self._cancelled(revision, stop):
            return
        if not agent._interaction_lock.acquire(blocking=False):
            return
        message: ConversationMessage | None = None
        try:
            # The activity lock closes the race between validation and final delivery.
            with self._activity_lock:
                status = agent.cognitive_loop.status
                if (
                    self._foreground
                    or self._revision != revision
                    or stop.is_set()
                    or agent._closed.is_set()
                    or agent.identity.id != subject_id
                    or not status.running
                    or status.paused
                ):
                    return
                psyche = agent.psychology.snapshot()
                social = psyche.relationships.get(plan.person_id)
                if (
                    not psyche.initiative_enabled
                    or social is None
                    or not social.initiative_allowed
                    or social.last_contact_message_id != plan.source.id
                    or agent.profile.stage.value != context.development_stage
                ):
                    return
                history = agent.repository.recent_conversation(plan.person_id, 8)
                if any(
                    item.role == ConversationRole.AGENT
                    and normalize_text(item.content) == normalize_text(response)
                    for item in history
                ):
                    return
                candidate = ConversationMessage(
                    created_at=agent.clock.now(),
                    person_id=plan.person_id,
                    role=ConversationRole.AGENT,
                    content=response,
                    intent=MessageIntent.SOCIAL,
                    backend="verification" if verification else agent.cognitive_backend.name,
                    model="evidence-summary" if verification else agent.cognitive_backend.model,
                    metadata={
                        "initiative": True,
                        "trigger": plan.kind,
                        "topic": plan.topic,
                        "source_message_id": plan.source.id,
                        "stage": context.development_stage,
                        "discussion_orientation": plan.orientation,
                        "verification_task_id": None
                        if verification is None
                        else verification[1].id,
                    },
                )
                sent = agent.cognitive_loop.budgets.consume_with(
                    "initiative_messages",
                    lambda budget: agent.psychology.commit_initiative(
                        plan, candidate, budget, None if verification is None else verification[1]
                    ),
                )
                if sent:
                    message = candidate
        finally:
            agent._interaction_lock.release()
        if message is not None and agent.initiative_notifier is not None:
            agent.initiative_notifier(message)

    def _verification_notice(
        self, inputs: list[ConversationMessage]
    ) -> tuple[InitiativePlan, DeferredVerification, str] | None:
        agent = self.agent
        state = agent.psychology.snapshot()
        if not self.settings.enabled or not state.initiative_enabled or agent.state.energy < 0.12:
            return None
        now = agent.clock.now()
        sources = {item.person_id: item for item in inputs}
        for task in agent.repository.verification_notices():
            preference = agent.communication.get(task.source.person_id)
            if (
                not preference.initiative_enabled
                or preference.quiet(now)
                or not preference.allows_topic(task.claim, now)
            ):
                continue
            social = state.relationships.get(task.source.person_id)
            source = sources.get(task.source.person_id)
            if social is None or source is None or not social.initiative_allowed:
                continue
            if (
                social.unanswered_initiatives >= self.settings.max_unanswered
                or social.conflict_load > 0.75
                or social.felt_safety < 0.15
                or (social.quiet_until is not None and now < utc(social.quiet_until))
                or elapsed_seconds(now, source.created_at) < self.settings.discussion_delay
                or (
                    social.last_initiative_at is not None
                    and elapsed_seconds(now, social.last_initiative_at)
                    < (
                        self.settings.reconnect_cooldown
                        if social.unanswered_initiatives
                        else self.settings.cooldown * preference.cooldown_scale
                    )
                )
            ):
                continue
            report = task.report
            if report is None:
                continue
            result_ids = {
                item.result_id for item in report.judgments if item.stance.value == "contradict"
            }
            evidence = [item for item in report.results if item.id in result_ids]
            if not evidence:
                continue
            links = "; ".join(f"{item.title}: {item.url}" for item in evidence[:2])
            response = (
                f"Я вернулся к твоему прежнему утверждению «{task.claim[:300]}». "
                f"Нашёл свидетельства, которые ему противоречат: {links}. "
                "Эти материалы дают повод пересмотреть прежнюю оценку. "
                "Это ещё не означает намеренную ложь; "
                "можем обсудить, на чём основывалась твоя версия."
            )
            plan = InitiativePlan(
                source.person_id,
                "verification",
                source,
                task.claim[:160],
                "Обсудить независимые свидетельства без обвинения в намеренной лжи.",
                0.85,
                "Отложенная проверка обнаружила противоречие.",
                "reflect",
                (),
            )
            return plan, task, response
        return None

    def _context(self, plan: InitiativePlan, history: list[ConversationMessage]) -> ReplyContext:
        agent = self.agent
        psyche = agent.psychology.snapshot()
        preferences = agent.communication.get(plan.person_id)
        development = developmental_dynamics(agent.profile)
        interests = "; ".join(
            f"{item.topic}: {item.angle}" for item in preferred_interests(psyche, agent.profile, 5)
        )
        return ReplyContext(
            identity=agent.identity.model_copy(deep=True),
            analysis=MessageAnalysis(text="", intent=MessageIntent.SOCIAL, confidence=1.0),
            decision=AutonomyDecision(
                person_id=plan.person_id,
                input_text="",
                intent=MessageIntent.SOCIAL,
                decision=AutonomyDecisionKind.ACKNOWLEDGE,
                reason=plan.reason,
                confidence=plan.score,
            ),
            relationship=agent.trust_engine.get_or_create(plan.person_id),
            goals=agent.repository.list_goals(5, active_only=True),
            emotion=agent.emotion.model_copy(deep=True),
            research_summary=None,
            personal_memory_summary=agent._memory_summary(plan.source.content, plan.person_id),
            beliefs_summary=agent._beliefs_summary(),
            conversation_history=history,
            development_stage=agent.profile.stage.value,
            total_deu=agent.profile.total_deu,
            needs_summary=agent._needs_summary(),
            active_goal_summary=(
                agent._active_goal_summary() + " " + agent.projects.guidance(plan.person_id)
            ),
            psychology_summary=agent.psychology.summary(psyche),
            development_summary=development.guidance,
            behavior_guidance=(development.guidance,) + plan.guidance,
            interaction_mode=plan.kind,
            initiative_reason=plan.reason + " " + plan.angle,
            initiative_topic=plan.topic,
            initiative_angle=plan.angle,
            initiative_source_text=plan.source.content,
            discussion_orientation=plan.orientation,
            interests_summary=interests,
            biography_summary=agent.autobiography.summary(plan.person_id),
            communication_guidance=f"Длина ответа: {preferences.reply_length}.",
            max_reply_chars=preferences.reply_chars,
            competence_guidance=agent.competence_guidance(plan.topic),
            interlocutor_summary=agent.interlocutors.summary(plan.person_id, plan.topic),
        )

    def _generate(self, context: ReplyContext, revision: int, stop: threading.Event) -> str:
        backend = self.agent.cognitive_backend
        if self._cancelled(revision, stop):
            return ""
        try:
            if not backend.supports_streaming:
                return backend.generate_reply(context).strip()
            chunks: list[str] = []
            stream = backend.stream_reply(context)
            try:
                for token in stream:
                    if self._cancelled(revision, stop):
                        return ""
                    chunks.append(token)
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
            response = "".join(chunks).strip()
            return response or RuleBasedBackend().generate_reply(context)
        except RuntimeError:
            return RuleBasedBackend().generate_reply(context)
