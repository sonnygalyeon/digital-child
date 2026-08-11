from __future__ import annotations

from datetime import UTC, datetime

from digital_child.models import Goal, GoalArbitration, GoalScore, NeedKind, NeedState


class GoalArbiter:
    """Deterministic arbitration. User suggestions compete with self-generated goals."""

    def choose(
        self,
        goals: list[Goal],
        needs: list[NeedState],
        current_sequence: int,
    ) -> GoalArbitration:
        need_levels = {item.kind: item.level for item in needs}
        scored: list[tuple[Goal, GoalScore]] = []
        for goal in goals:
            need_pressure = (
                need_levels.get(goal.need_kind, 0.35)
                if goal.need_kind is not None
                else 0.35
            )
            components = {
                "priority": 0.24 * goal.priority,
                "urgency": 0.18 * goal.urgency,
                "utility": 0.18 * goal.expected_utility,
                "value_alignment": 0.16 * goal.value_alignment,
                "need_pressure": 0.16 * need_pressure,
                "progress_continuity": 0.06 * goal.progress,
                "protected": 0.05 if goal.protected else 0.0,
                "cost": -0.08 * goal.estimated_cost,
                "risk": -0.13 * goal.risk,
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
                "Выбрана цель с максимальным суммарным соответствием потребностям, "
                "ценностям, срочности, пользе и допустимому риску."
            ),
        )
