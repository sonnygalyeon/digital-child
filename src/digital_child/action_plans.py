from __future__ import annotations

import hashlib
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import Field

from digital_child.models import StrictModel
from digital_child.storage import SQLiteRepository

if TYPE_CHECKING:
    from digital_child.experiments import ExperimentTrial

PlanKind = Literal["route", "switchback"]
Action = Literal["left", "right"]


class ActionAttribution(StrictModel):
    outcome_id: str
    kind: str
    before: int
    after: int
    target: int = 0
    control_after: int
    alternative_after: int
    step_scale: int = Field(default=1, ge=1)
    confidence: float = Field(default=1.0, ge=0, le=1)
    episode_id: str | None = None
    explanation: str = (
        "Детерминированная закрытая среда: сравнение с бездействием "
        "и противоположным действием при тех же условиях; вывод ограничен этой симуляцией."
    )

    @property
    def effect(self) -> float:
        return float(abs(self.control_after - self.target) - abs(self.after - self.target))

    @property
    def alternative_advantage(self) -> float:
        return float(abs(self.alternative_after - self.target) - abs(self.after - self.target))

    @property
    def reward(self) -> float:
        return max(-0.7, min(0.7, self.effect / self.step_scale * 0.7)) * self.confidence

    def diagnostic(self) -> dict[str, object]:
        return {
            **self.model_dump(mode="json"),
            "effect": self.effect,
            "alternative_advantage": self.alternative_advantage,
            "reward": self.reward,
        }

    @classmethod
    def from_trial(cls, trial: ExperimentTrial) -> ActionAttribution:
        control = trial.before + trial.noise
        return cls(
            outcome_id=trial.id,
            kind="experiment:" + trial.kind,
            before=trial.before,
            after=trial.actual_after,
            control_after=control,
            alternative_after=2 * control - trial.actual_after,
            step_scale=2 if trial.kind == "transfer" else 1,
            episode_id=trial.episode_id,
        )


class PlanStep(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    plan_id: str
    number: int = Field(ge=1, le=20)
    created_at: datetime
    before: int
    action: Action
    target_before: int
    predicted_after: int
    actual_after: int
    prediction_error: float = Field(ge=0)
    model_sign_before: int
    learned_sign_after: int
    expected_success: float = Field(ge=0, le=1)
    replan_reason: str = ""
    recovered_after_failure: bool = False
    corrected_prediction: bool = False
    attribution: ActionAttribution
    episode_id: str | None = None


class ActionPlan(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: PlanKind
    created_at: datetime
    updated_at: datetime
    status: Literal["active", "completed", "exhausted", "cancelled"] = "active"
    position: int = -3
    waypoints: list[int] = Field(default_factory=lambda: [2, 0], max_length=5)
    waypoint_index: int = 0
    model_sign: int = 1
    queued_actions: list[Action] = Field(default_factory=list, max_length=20)
    max_steps: int = Field(default=12, ge=2, le=20)
    steps: list[PlanStep] = Field(default_factory=list, max_length=20)
    expected_completion: float = Field(default=0.5, ge=0, le=1)
    autonomous: bool = False
    stop_reason: str = ""


class PlanEnvironment:
    """Persistent short plans in a closed numerical world. No external executors."""

    def __init__(self, repository: SQLiteRepository, subject_id: str) -> None:
        self.repository, self.subject_id = repository, subject_id

    def get(self, plan_id: str) -> ActionPlan:
        saved = self.repository.load_feature("action_plan", plan_id, self.subject_id)
        if saved is None:
            raise ValueError("План не найден")
        return ActionPlan.model_validate(saved)

    def active(self) -> ActionPlan | None:
        saved = self.repository.load_feature("plan_runtime", "active", self.subject_id) or {}
        key = saved.get("id")
        return self.get(key) if isinstance(key, str) else None

    def history(self, limit: int = 20) -> list[ActionPlan]:
        return [
            ActionPlan.model_validate(item)
            for item in self.repository.list_features("action_plan", self.subject_id, limit)
        ]

    @staticmethod
    def _actions(position: int, target: int, model_sign: int, remaining: int) -> list[Action]:
        if position == target:
            return []
        direction = 1 if target > position else -1
        action: Action = "right" if direction * model_sign > 0 else "left"
        return [action] * min(abs(target - position), remaining)

    def create(
        self,
        kind: PlanKind,
        now: datetime,
        max_steps: int = 12,
        autonomous: bool = False,
        expected_completion: float = 0.5,
    ) -> ActionPlan:
        if self.active() is not None:
            raise ValueError("Сначала завершите или отмените текущий план")
        if kind not in {"route", "switchback"}:
            raise ValueError("Доступны route и switchback")
        saved = self.repository.load_feature("plan_model", kind, self.subject_id) or {}
        sign = int(str(saved.get("sign", 1)))
        if sign not in {-1, 1}:
            sign = 1
        plan = ActionPlan(
            kind=kind,
            created_at=now,
            updated_at=now,
            max_steps=max_steps,
            model_sign=sign,
            autonomous=autonomous,
            expected_completion=expected_completion,
        )
        plan.queued_actions = self._actions(plan.position, plan.waypoints[0], sign, max_steps)
        self.save(plan)
        return plan

    def _transition(self, plan: ActionPlan, action: Action) -> int:
        seed = hashlib.blake2b(self.subject_id.encode(), digest_size=1).digest()[0]
        actual_sign = 1 if seed % 2 else -1
        if plan.kind == "switchback" and len(plan.steps) >= 2:
            actual_sign *= -1
        return plan.position + (1 if action == "right" else -1) * actual_sign

    def prepare_step(
        self, plan: ActionPlan, now: datetime, expected_success: float
    ) -> tuple[ActionPlan, PlanStep]:
        if plan.status != "active":
            raise ValueError("План уже завершён или остановлен")
        if len(plan.steps) >= plan.max_steps:
            raise ValueError("Лимит действий плана исчерпан")
        target = plan.waypoints[plan.waypoint_index]
        actions = plan.queued_actions or self._actions(
            plan.position, target, plan.model_sign, plan.max_steps - len(plan.steps)
        )
        if not actions:
            raise ValueError("План не содержит следующего действия")
        action = actions[0]
        action_sign = 1 if action == "right" else -1
        predicted = plan.position + action_sign * plan.model_sign
        # The private transition is evaluated only after the plan's choice/prediction.
        actual = self._transition(plan, action)
        alternative: Action = "left" if action == "right" else "right"
        step_id = str(uuid4())
        attribution = ActionAttribution(
            outcome_id=step_id,
            kind="plan:" + plan.kind,
            before=plan.position,
            after=actual,
            target=target,
            control_after=plan.position,
            alternative_after=self._transition(plan, alternative),
        )
        learned = (actual - plan.position) * action_sign
        updated = plan.model_copy(deep=True)
        updated.position, updated.model_sign, updated.updated_at = actual, learned, now
        reason = "prediction_mismatch" if actual != predicted else ""
        if actual == target:
            if updated.waypoint_index == len(updated.waypoints) - 1:
                updated.status, updated.stop_reason = (
                    "completed",
                    "Все контрольные точки достигнуты",
                )
            else:
                updated.waypoint_index += 1
                reason = reason or "waypoint_reached"
        if updated.status == "active" and len(plan.steps) + 1 >= plan.max_steps:
            updated.status, updated.stop_reason = "exhausted", "Достигнут предел действий"
        step = PlanStep(
            id=step_id,
            plan_id=plan.id,
            number=len(plan.steps) + 1,
            created_at=now,
            before=plan.position,
            action=action,
            target_before=target,
            predicted_after=predicted,
            actual_after=actual,
            prediction_error=abs(predicted - actual) / 2,
            model_sign_before=plan.model_sign,
            learned_sign_after=learned,
            expected_success=expected_success,
            replan_reason=reason,
            recovered_after_failure=bool(
                plan.steps and plan.steps[-1].attribution.effect < 0 and attribution.effect > 0
            ),
            corrected_prediction=bool(
                plan.steps and plan.steps[-1].prediction_error > 0 and actual == predicted
            ),
            attribution=attribution,
        )
        updated.steps.append(step)
        updated.queued_actions = actions[1:]
        if updated.status != "active":
            updated.queued_actions = []
        elif reason or not updated.queued_actions:
            updated.queued_actions = self._actions(
                actual,
                updated.waypoints[updated.waypoint_index],
                learned,
                plan.max_steps - len(updated.steps),
            )
        return updated, step

    def save(self, plan: ActionPlan, step: PlanStep | None = None) -> None:
        with self.repository.transaction():
            self.repository.save_feature(
                "action_plan", plan.id, self.subject_id, plan.model_dump(mode="json")
            )
            self.repository.save_feature(
                "plan_runtime",
                "active",
                self.subject_id,
                {"id": plan.id if plan.status == "active" else None},
            )
            if step is not None:
                self.repository.save_feature(
                    "plan_step", step.id, self.subject_id, step.model_dump(mode="json")
                )
                self.repository.save_feature(
                    "plan_model",
                    plan.kind,
                    self.subject_id,
                    {"sign": step.learned_sign_after, "source_step_id": step.id},
                )

    def cancel(self, plan_id: str, now: datetime) -> ActionPlan:
        plan = self.get(plan_id)
        if plan.status != "active":
            raise ValueError("План уже остановлен")
        plan.status, plan.stop_reason, plan.updated_at = "cancelled", "Отменён пользователем", now
        plan.queued_actions = []
        self.save(plan)
        return plan
