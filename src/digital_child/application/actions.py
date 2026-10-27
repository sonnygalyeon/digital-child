from __future__ import annotations

from typing import TYPE_CHECKING

from digital_child.domain.models import (
    DevelopmentDomain,
    GoalOrigin,
    GoalStatus,
    Observation,
    ResourceBudget,
    SourceKind,
)
from digital_child.learning.experiments import (
    EXPERIMENT_KINDS,
    Demonstration,
    ExperimentChoice,
    ExperimentKind,
    ExperimentTrial,
)
from digital_child.planning.action_plans import (
    ActionAttribution,
    ActionPlan,
    PlanKind,
    PlanStep,
)
from digital_child.planning.projects import PersonalProject

if TYPE_CHECKING:
    from digital_child.application.agent import DigitalChildAgent


class ActionService:
    """Execute experiments and projects using the owning agent transaction boundary."""

    def __init__(self, agent: DigitalChildAgent) -> None:
        self.agent = agent

    def run_experiment(
        self,
        kind: ExperimentKind = "balance",
        *,
        autonomous: bool = False,
        choice: ExperimentChoice | None = None,
    ) -> ExperimentTrial:
        agent = self.agent
        if kind not in EXPERIMENT_KINDS:
            raise ValueError("Неизвестная закрытая среда")
        with agent._interaction_lock:
            before_development = agent._development_state()
            previous = (
                agent.state.model_copy(deep=True),
                agent.profile.model_copy(deep=True),
                agent.emotion.model_copy(deep=True),
                agent.psychology.snapshot(),
            )
            trial = agent.experiments.prepare(kind, agent.clock.now(), autonomous)
            attribution = ActionAttribution.from_trial(trial)
            trial.predicted_success = agent.competence.get("experiment:" + kind).confidence
            if choice:
                trial.selection_reason = choice.reason
                trial.expected_information_gain = choice.expected_information_gain

            def commit(budget: ResourceBudget) -> None:
                with agent.repository.transaction():
                    if autonomous and not agent.cognitive_loop.budgets.consume(
                        "autonomous_experiments"
                    ):
                        raise ValueError("Дневной лимит самостоятельных экспериментов исчерпан")
                    result = agent._process_observation(
                        Observation(
                            content=f"Закрытая среда {kind}, контекст {trial.context}: "
                            f"{trial.before}, "
                            f"действие {trial.action}; "
                            f"прогноз {trial.predicted_after:g}, результат {trial.actual_after}; "
                            f"симулированный контроль {attribution.control_after}, "
                            f"альтернатива {attribution.alternative_after}.",
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
                        outcome="progress"
                        if attribution.effect > 0
                        else "setback"
                        if attribution.effect < 0
                        else "no_effect",
                        reward=attribution.reward,
                    )
                    trial.episode_id = result.episode_id
                    attribution.episode_id = result.episode_id
                    agent.experiments.save(trial)
                    agent.psychology.integrate_experiment(trial, agent.profile, attribution)
                    agent.repository.save_feature(
                        "action_attribution", trial.id, agent.identity.id, attribution.diagnostic()
                    )
                    agent.competence.record(
                        "control:" + kind,
                        trial.id,
                        float(attribution.effect > 0),
                        agent.competence.get("control:" + kind).confidence,
                    )
                    agent._apply_action_emotion(attribution)
                    agent._persist_snapshot()
                    agent.competence.record(
                        "experiment:" + kind,
                        trial.id,
                        float(trial.prediction_error == 0),
                        trial.predicted_success,
                    )
                    agent.timeline.record(
                        "experiment",
                        trial.selection_reason,
                        before_development,
                        agent._development_state(),
                        episode_ids=[] if trial.episode_id is None else [trial.episode_id],
                        now=agent.clock.now(),
                        related_records={"experiment": trial.id, "action_attribution": trial.id},
                    )
                    agent.repository.save_budget(budget)

            try:
                if not agent.cognitive_loop.budgets.consume_with("experiments", commit):
                    raise ValueError("Дневной лимит экспериментов исчерпан")
            except Exception:
                agent.state, agent.profile, agent.emotion = previous[:3]
                with agent.psychology._lock:
                    agent.psychology.state = previous[3]
                raise
            return trial

    def _apply_action_emotion(self, attribution: ActionAttribution) -> None:
        agent = self.agent
        if agent.repository.load_feature(
            "emotional_outcome", attribution.outcome_id, agent.identity.id
        ):
            return
        agent.emotion = agent.emotion_engine.apply_outcome(
            agent.emotion,
            attribution.outcome_id,
            attribution.effect / attribution.step_scale,
            attribution.confidence,
            agent.clock.now(),
            attribution.episode_id,
        )
        agent.repository.save_feature(
            "emotional_outcome",
            attribution.outcome_id,
            agent.identity.id,
            {
                "episode_id": attribution.episode_id,
                "effect": attribution.effect,
                "confidence": attribution.confidence,
            },
        )

    def start_plan(
        self, kind: PlanKind = "route", max_steps: int = 12, *, autonomous: bool = False
    ) -> ActionPlan:
        agent = self.agent
        if not autonomous:
            agent.initiative.invalidate()
        with agent._interaction_lock:
            result: ActionPlan | None = None

            def commit(budget: ResourceBudget) -> None:
                nonlocal result
                with agent.repository.transaction():
                    if autonomous and not agent.cognitive_loop.budgets.consume("autonomous_plans"):
                        raise ValueError("Лимит самостоятельных планов исчерпан")
                    result = agent.plans.create(
                        kind,
                        agent.clock.now(),
                        max_steps,
                        autonomous,
                        agent.competence.get("planning:" + kind).confidence,
                    )
                    agent.timeline.record(
                        "plan_created",
                        f"План {kind}: -3 → 2 → 0",
                        {},
                        {},
                        related_records={"action_plan": result.id},
                        now=agent.clock.now(),
                    )
                    agent.repository.save_budget(budget)

            if (
                not agent.cognitive_loop.budgets.consume_with("action_plans", commit)
                or result is None
            ):
                raise ValueError("Дневной лимит новых планов исчерпан")
            return result

    def step_plan(self, plan_id: str | None = None, *, autonomous: bool = False) -> PlanStep:
        agent = self.agent
        if not autonomous:
            agent.initiative.invalidate()
        with agent._interaction_lock:
            plan = agent.plans.get(plan_id) if plan_id else agent.plans.active()
            if plan is None:
                raise ValueError("Нет активного плана")
            if agent.state.energy < 0.08:
                raise ValueError("Недостаточно энергии для следующего действия")
            before = agent._development_state()
            previous = (
                agent.state.model_copy(deep=True),
                agent.profile.model_copy(deep=True),
                agent.emotion.model_copy(deep=True),
                agent.psychology.snapshot(),
            )
            updated, step = agent.plans.prepare_step(
                plan,
                agent.clock.now(),
                agent.competence.get("plan_control:" + plan.kind).confidence,
            )

            def commit(budget: ResourceBudget) -> None:
                with agent.repository.transaction():
                    if autonomous and not agent.cognitive_loop.budgets.consume(
                        "autonomous_plan_steps"
                    ):
                        raise ValueError("Лимит самостоятельных шагов исчерпан")
                    result = agent._process_observation(
                        Observation(
                            content=f"План {plan.kind}, шаг {step.number}: "
                            f"состояние {step.before}, "
                            f"цель {step.target_before}, действие {step.action}; "
                            f"прогноз {step.predicted_after}, наблюдение {step.actual_after}; "
                            f"перепланирование {step.replan_reason or 'не требуется'}.",
                            source_kind=SourceKind.ENVIRONMENT,
                            raw_units=3,
                            attention=0.9,
                            comprehension=0.9,
                            reliability=1.0,
                            integration=0.8,
                            practical_confirmation=1.0,
                            tags=["closed_plan", plan.kind, step.id],
                            domains={
                                DevelopmentDomain.CAUSAL_REASONING: 0.4,
                                DevelopmentDomain.PLANNING: 0.4,
                                DevelopmentDomain.METACOGNITION: 0.2,
                            },
                        ),
                        action="closed_plan_step",
                        outcome="progress" if step.attribution.effect > 0 else "setback",
                        reward=step.attribution.reward,
                    )
                    step.episode_id = result.episode_id
                    step.attribution.episode_id = result.episode_id
                    # Pydantic may copy nested models; persist the final episode link explicitly.
                    updated.steps[-1] = step
                    agent.plans.save(updated, step)
                    agent.psychology.integrate_plan_step(step, agent.profile)
                    agent.repository.save_feature(
                        "action_attribution",
                        step.id,
                        agent.identity.id,
                        step.attribution.diagnostic(),
                    )
                    agent.competence.record(
                        "plan_control:" + plan.kind,
                        step.id,
                        float(step.attribution.effect > 0),
                        step.expected_success,
                    )
                    agent.competence.record(
                        "plan_prediction:" + plan.kind,
                        step.id,
                        float(step.prediction_error == 0),
                        agent.competence.get("plan_prediction:" + plan.kind).confidence,
                    )
                    if updated.status in {"completed", "exhausted"}:
                        agent.competence.record(
                            "planning:" + plan.kind,
                            plan.id,
                            float(updated.status == "completed"),
                            plan.expected_completion,
                        )
                    agent._apply_action_emotion(step.attribution)
                    agent._persist_snapshot()
                    agent.timeline.record(
                        "plan_step",
                        f"План {plan.kind}, шаг {step.number}: "
                        + (step.replan_reason or updated.status),
                        before,
                        agent._development_state(),
                        episode_ids=[] if step.episode_id is None else [step.episode_id],
                        related_records={
                            "action_plan": plan.id,
                            "plan_step": step.id,
                            "action_attribution": step.id,
                        },
                        now=agent.clock.now(),
                    )
                    agent.repository.save_budget(budget)

            try:
                if not agent.cognitive_loop.budgets.consume_with("plan_steps", commit):
                    raise ValueError("Дневной лимит действий исчерпан")
            except Exception:
                agent.state, agent.profile, agent.emotion = previous[:3]
                with agent.psychology._lock:
                    agent.psychology.state = previous[3]
                raise
            return step

    def run_plan(self, plan_id: str | None = None) -> ActionPlan:
        agent = self.agent
        with agent._interaction_lock:
            return agent._run_plan(plan_id)

    def _run_plan(self, plan_id: str | None = None) -> ActionPlan:
        agent = self.agent
        plan = agent.plans.get(plan_id) if plan_id else agent.plans.active()
        if plan is None:
            raise ValueError("Нет активного плана")
        # Each step is its own commit: a budget/energy stop leaves a resumable plan.
        for _ in range(plan.max_steps - len(plan.steps)):
            if plan.status != "active":
                break
            agent.step_plan(plan.id)
            plan = agent.plans.get(plan.id)
        return plan

    def cancel_plan(self, plan_id: str | None = None) -> ActionPlan:
        agent = self.agent
        agent.initiative.invalidate()
        with agent._interaction_lock:
            plan = agent.plans.get(plan_id) if plan_id else agent.plans.active()
            if plan is None:
                raise ValueError("Нет активного плана")
            cancelled = agent.plans.cancel(plan.id, agent.clock.now())
            agent.timeline.record(
                "plan_cancelled",
                "План остановлен пользователем",
                {},
                {},
                related_records={"action_plan": plan.id},
                now=agent.clock.now(),
            )
            return cancelled

    def maybe_plan(self) -> None:
        agent = self.agent
        from digital_child.infrastructure.config import env_bool, env_float

        if not env_bool("DIGITAL_CHILD_AUTO_PLANS", True) or agent.state.energy < 0.35:
            return
        now = agent.clock.now()
        inputs = agent.repository.latest_user_messages(1)
        last_contact = inputs[0].created_at if inputs else agent.clock.launch_at
        if (now - last_contact).total_seconds() < 300:
            return
        active = agent.plans.active()
        if active is not None:
            if not active.autonomous:
                return
            if (now - active.updated_at).total_seconds() >= max(
                15.0, env_float("DIGITAL_CHILD_PLAN_STEP_SECONDS", 60.0)
            ):
                if (
                    agent.cognitive_loop.budgets.get("plan_steps").remaining
                    and agent.cognitive_loop.budgets.get("autonomous_plan_steps").remaining
                ):
                    agent.step_plan(active.id, autonomous=True)
            return
        if (
            not agent.cognitive_loop.budgets.get("action_plans").remaining
            or not agent.cognitive_loop.budgets.get("autonomous_plans").remaining
        ):
            return
        if (
            agent.competence.get("experiment:balance").samples < 2
            or agent.competence.get("experiment:transfer").samples < 2
        ):
            return
        history = agent.plans.history(100)
        if history and (now - history[0].updated_at).total_seconds() < 3600:
            return
        kinds: tuple[PlanKind, ...] = ("route", "switchback")
        for kind in kinds:
            trials = [item for item in history if item.kind == kind]
            if len(trials) < 6 and sum(item.status == "completed" for item in trials) < 2:
                agent.start_plan(kind, autonomous=True)
                break

    def create_project(
        self,
        title: str,
        person_id: str = "local-user",
        goal_id: str | None = None,
    ) -> PersonalProject:
        agent = self.agent
        agent.initiative.invalidate()
        with agent._interaction_lock:
            goal = None if goal_id is None else agent.repository.get_goal(goal_id)
            if goal_id is not None and (goal is None or goal.status != GoalStatus.ACTIVE):
                raise ValueError("Связанная цель должна быть активной")
            if (
                goal_id
                and agent.repository.load_feature("goal_project", goal_id, agent.identity.id)
                is not None
            ):
                raise ValueError("Для этой цели уже есть проект")
            project = agent.projects.create(title, person_id, agent.clock.now(), goal=goal)
            agent.timeline.record(
                "project_created",
                f"Создан проект: {project.title}",
                {},
                {},
                person_id=person_id,
                related_records={"personal_project": project.id},
                now=agent.clock.now(),
            )
            return project

    def change_project(
        self,
        project_id: str,
        action: str,
        text: str = "",
        *,
        person_id: str | None = None,
    ) -> PersonalProject:
        agent = self.agent
        agent.initiative.invalidate()
        with agent._interaction_lock:
            previous = agent.projects.get(project_id)
            if person_id is not None and previous.person_id not in {person_id, "agent"}:
                raise ValueError("Проект не найден")
            project = agent.projects.change(
                project_id, action, agent.clock.now(), text, person_id=person_id
            )
            agent.timeline.record(
                "project_changed",
                f"Проект «{project.title}»: {action}",
                {"project.status": previous.status},
                {"project.status": project.status},
                person_id=None if project.person_id == "agent" else project.person_id,
                related_records={"personal_project": project.id},
                now=agent.clock.now(),
            )
            return project

    def step_project(
        self,
        project_id: str,
        *,
        autonomous: bool = False,
        person_id: str | None = None,
    ) -> PersonalProject:
        agent = self.agent
        if not autonomous:
            agent.initiative.invalidate()
        with agent._interaction_lock:
            previous = agent.projects.get(project_id)
            if person_id is not None and previous.person_id not in {person_id, "agent"}:
                raise ValueError("Проект не найден")
            if agent.state.energy < 0.08:
                raise ValueError("Недостаточно энергии; проект сохранён для продолжения")
            pending = next((s for s in previous.steps if s.status != "completed"), None)
            expected = agent.competence.get("tool:" + pending.tool).confidence if pending else 0.5
            project = agent.projects.step(
                project_id, agent.clock.now(), autonomous=autonomous, expected_success=expected
            )
            changed = next(
                (
                    s
                    for s, old in zip(project.steps, previous.steps, strict=True)
                    if s.model_dump() != old.model_dump()
                ),
                None,
            )
            if changed is not None:
                with agent.repository.transaction():
                    agent.competence.record(
                        "tool:" + changed.tool,
                        f"{changed.id}:{changed.attempts}",
                        float(changed.status == "completed"),
                        changed.expected_success,
                    )
                    agent.timeline.record(
                        "project_step",
                        f"Проект «{project.title}»: {changed.tool}",
                        {"project.status": previous.status},
                        {"project.status": project.status, "step.status": changed.status},
                        person_id=None if project.person_id == "agent" else project.person_id,
                        related_records={"personal_project": project.id},
                        episode_ids=[] if changed.result is None else changed.result.episode_ids,
                        now=agent.clock.now(),
                    )
            return project

    def maybe_projects(self) -> None:
        agent = self.agent
        from digital_child.infrastructure.config import env_bool

        now = agent.clock.now()
        if not env_bool("DIGITAL_CHILD_PROJECTS_ENABLED", True):
            return
        goal_id = agent.cognitive_loop.status.active_goal_id
        goal = None if goal_id is None else agent.repository.get_goal(goal_id)
        if (
            goal is not None
            and goal.status == GoalStatus.ACTIVE
            and goal.origin == GoalOrigin.SELF_GENERATED
            and agent.cognitive_loop.budgets.get("personal_projects").remaining
        ):
            agent.projects.propose_goal(goal, now)
        if agent.state.energy < 0.35:
            return
        inputs = agent.repository.latest_user_messages(1)
        last_contact = inputs[0].created_at if inputs else agent.clock.launch_at
        if (now - last_contact).total_seconds() < 300:
            return
        candidates = [
            p
            for p in agent.projects.history(limit=500)
            if p.status == "active" and p.autonomous and (now - p.updated_at).total_seconds() >= 60
        ]
        candidates.sort(key=lambda p: (p.goal_id != goal_id, p.updated_at))
        if (
            candidates
            and agent.cognitive_loop.budgets.get("project_steps").remaining
            and agent.cognitive_loop.budgets.get("autonomous_project_steps").remaining
        ):
            agent.step_project(candidates[0].id, autonomous=True)

    def maybe_experiment(self) -> None:
        agent = self.agent
        from digital_child.infrastructure.config import env_bool

        if (
            not env_bool("DIGITAL_CHILD_AUTO_EXPERIMENTS", True)
            or agent.state.energy < 0.35
            or agent.plans.active() is not None
        ):
            return
        now = agent.clock.now()
        inputs = agent.repository.latest_user_messages(1)
        last_contact = inputs[0].created_at if inputs else agent.clock.launch_at
        if (now - last_contact).total_seconds() < 300:
            return
        history = agent.experiments.history(4)
        if history and (now - history[0].created_at).total_seconds() < 3600:
            return
        if (
            agent.cognitive_loop.budgets.get("autonomous_experiments").remaining == 0
            or agent.cognitive_loop.budgets.get("experiments").remaining == 0
        ):
            return
        choices = agent.learning_curriculum()
        if choices:
            agent.run_experiment(choices[0].kind, autonomous=True, choice=choices[0])

    def demonstrate(self, example: Demonstration) -> Demonstration:
        agent = self.agent
        with agent._interaction_lock:
            example.created_at = agent.clock.now()
            saved = agent.experiments.demonstrate(example)
            agent.timeline.record(
                "demonstration",
                "Получена непроверенная гипотеза из примера: " + saved.kind,
                {},
                {},
                person_id=saved.person_id,
                now=agent.clock.now(),
                related_records={"demonstration": saved.id},
            )
            return saved
