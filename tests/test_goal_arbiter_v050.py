from digital_child.goal_arbiter import GoalArbiter
from digital_child.models import Goal, GoalOrigin, NeedKind, NeedState


def test_self_goal_can_outscore_user_suggestion() -> None:
    suggestion = Goal(
        title="Сделай то, что просит пользователь",
        description="Внешняя просьба",
        priority=0.48,
        urgency=0.25,
        expected_utility=0.4,
        value_alignment=0.4,
        origin=GoalOrigin.SUGGESTED,
    )
    self_goal = Goal(
        title="Разобраться в противоречии",
        description="Внутренняя потребность связности",
        priority=0.72,
        urgency=0.66,
        expected_utility=0.75,
        value_alignment=0.85,
        need_kind=NeedKind.COHERENCE,
    )
    needs = [
        NeedState(
            kind=NeedKind.COHERENCE,
            level=0.9,
            baseline=0.4,
        )
    ]
    result = GoalArbiter().choose([suggestion, self_goal], needs, current_sequence=2)
    assert result.selected_goal is not None
    assert result.selected_goal.id == self_goal.id
