from __future__ import annotations

from datetime import UTC, datetime

from digital_child.domain.models import Goal, GoalArbitration, GoalScore, NeedState
from digital_child.domain.personality import GoalBehaviorPolicy


class GoalArbiter:
    """Deterministic arbitration. User suggestions compete with self-generated goals."""

    def choose(
        self,
        goals: list[Goal],
        needs: list[NeedState],
        current_sequence: int,
        *,
        policy: GoalBehaviorPolicy | None = None,
        previous_goal_id: str | None = None,
    ) -> GoalArbitration:
        weights = {
            "priority": 0.24,
            "urgency": 0.18,
            "utility": 0.18,
            "value_alignment": 0.16,
            "need_pressure": 0.16,
            "progress_continuity": 0.06,
            "cost": 0.08,
            "risk": 0.13,
        }
        if policy is not None:
            weights.update(policy.weights)
        need_levels = {item.kind: item.level for item in needs}
        scored: list[tuple[Goal, GoalScore]] = []
        for goal in goals:
            need_pressure = (
                need_levels.get(goal.need_kind, 0.35) if goal.need_kind is not None else 0.35
            )
            components = {
                "priority": weights["priority"] * goal.priority,
                "urgency": weights["urgency"] * goal.urgency,
                "utility": weights["utility"] * goal.expected_utility,
                "value_alignment": weights["value_alignment"] * goal.value_alignment,
                "need_pressure": weights["need_pressure"]
                * need_pressure
                * (
                    policy.need_weights.get(goal.need_kind.value, 1.0)
                    if policy is not None and goal.need_kind is not None
                    else 1.0
                ),
                "progress_continuity": weights["progress_continuity"] * goal.progress,
                "protected": 0.05 if goal.protected else 0.0,
                "cost": -weights["cost"] * goal.estimated_cost,
                "risk": -weights["risk"] * goal.risk,
                "recent_selection_penalty": (
                    -0.04 if goal.last_selected_sequence == current_sequence else 0.0
                ),
            }
            score = sum(components.values())
            scored.append((goal, GoalScore(goal_id=goal.id, score=score, components=components)))
        scored.sort(key=lambda pair: pair[1].score, reverse=True)
        if not scored:
            return GoalArbitration(reason="Нет активных целей для выбора.")
        selected, _ = scored[0]
        retained = False
        if policy is not None and previous_goal_id is not None:
            previous = next((pair for pair in scored if pair[0].id == previous_goal_id), None)
            if (
                previous is not None
                and scored[0][1].score - previous[1].score < policy.switching_margin
            ):
                selected = previous[0]
                retained = selected.id != scored[0][0].id
        selected = selected.model_copy(
            update={
                "updated_at": datetime.now(UTC),
                "last_selected_sequence": current_sequence,
                "selection_count": selected.selection_count + 1,
            }
        )
        return GoalArbitration(
            selected_goal=selected,
            scores=[item[1] for item in scored],
            reason=(
                "Продолжена текущая цель: преимущество альтернативы недостаточно для переключения."
                if retained
                else "Выбрана цель с максимальным суммарным соответствием потребностям, "
                "ценностям, срочности, пользе и допустимому риску."
            ),
        )
