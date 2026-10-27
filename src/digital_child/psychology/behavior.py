from __future__ import annotations

from digital_child.domain.constitution import assess_requested_action
from digital_child.domain.models import AutonomyDecision, AutonomyDecisionKind, MessageIntent
from digital_child.domain.personality import (
    BehaviorTrace,
    CharacterTraits,
    DevelopmentalDynamics,
    PsychologyState,
    SituationAppraisal,
    SocialExperience,
)
from digital_child.psychology.appraisal import situation_cue, topic_tokens
from digital_child.psychology.value_conflicts import evaluate_value_conflict


def choose_behavior(
    base: AutonomyDecision,
    appraisal: SituationAppraisal,
    development: DevelopmentalDynamics,
    state: PsychologyState,
    social: SocialExperience,
    *,
    sequence: int,
    prior_decision: AutonomyDecisionKind | None = None,
) -> tuple[AutonomyDecision, BehaviorTrace]:
    traits = state.character
    values = state.values
    interests = [
        state.interests[token].attraction
        for token in topic_tokens(base.input_text)
        if token in state.interests
    ]
    attraction = sum(interests) / len(interests) if interests else 0.5
    motivations = {
        "exploration": appraisal.novelty
        * (0.35 + traits.openness * 0.45)
        * (0.8 + attraction * 0.4),
        "connection": development.attachment * traits.attachment_need * social.felt_safety,
        "autonomy": appraisal.reactance * (0.5 + values.get("autonomy", 0.5) * 0.5),
        "mastery": (0.3 + traits.diligence * 0.4) * (1 - appraisal.overload),
        "security": (appraisal.hostility + appraisal.recalled_threat * 0.3)
        * (0.4 + traits.emotional_sensitivity * 0.5),
        "coherence": appraisal.uncertainty * (0.35 + development.reflection * 0.5),
    }
    scores: dict[str, float] = {}
    decision = base
    conflict = evaluate_value_conflict(state, appraisal)
    protected = base.user_authority_assumed or not assess_requested_action(base.input_text).allowed
    if not protected and base.intent in {MessageIntent.REQUEST, MessageIntent.COMMAND_ATTEMPT}:
        alignment = min(1.0, len(base.aligned_goal_ids) * 0.5)
        cooperation = (
            traits.cooperativeness * 0.4 + traits.empathy * 0.3 + values.get("care", 0.5) * 0.3
        )
        scores = {
            "accept": (
                0.25
                + 0.28 * alignment
                + 0.20 * cooperation
                + 0.16 * social.felt_safety
                + 0.12 * appraisal.choice
                + 0.10 * motivations["exploration"]
                - 0.38 * appraisal.pressure
                - 0.40 * appraisal.hostility
                - 0.28 * appraisal.overload
                - 0.08 * appraisal.complexity * (1 - state.self_model.efficacy)
            ),
            "negotiate": (
                0.30
                + 0.16 * development.autonomy
                + 0.16 * appraisal.uncertainty
                + 0.10 * (1 - alignment)
                + 0.13 * appraisal.reactance
                + 0.08 * development.perspective_taking
                - 0.15 * appraisal.hostility
            ),
            "refuse": (
                0.06
                + 0.40 * appraisal.pressure
                + 0.48 * appraisal.hostility
                + 0.22 * social.conflict_load
                + 0.23 * appraisal.overload
                + 0.10 * traits.assertiveness * appraisal.pressure
                - 0.08 * cooperation
                - 0.10 * appraisal.choice
            ),
        }
        if conflict is not None:
            for name, bias in conflict.biases.items():
                scores[name] += bias
        # Habit contributes a small bias, never absolute authority.
        for habit in state.habits:
            if habit.cue == "pressure" and appraisal.pressure > 0.3:
                destination = "refuse" if habit.strategy == "set_boundary" else "negotiate"
                scores[destination] += min(0.06, habit.strength * 0.06)
        winner = max(scores, key=lambda name: (scores[name], name))
        if prior_decision is not None and prior_decision.value in scores:
            margin = 0.035 + traits.persistence * 0.065 + development.planning_horizon * 0.025
            # Strongly changed circumstances can overcome commitment inertia.
            margin *= 1 - appraisal.prediction_error * 0.7
            if scores[winner] - scores[prior_decision.value] < margin:
                winner = prior_decision.value
        ordered = sorted(scores.values(), reverse=True)
        confidence = min(0.94, 0.52 + max(0.0, ordered[0] - ordered[1]) * 0.7)
        decision = base.model_copy(
            update={
                "decision": AutonomyDecisionKind(winner),
                "confidence": confidence,
                "reason": (
                    "Предложение оценено с учётом собственной цели, характера, стадии развития, "
                    "отношений, свободы выбора и текущей нагрузки. "
                    + {
                        "accept": "В этих условиях сотрудничество имеет наибольшую ценность.",
                        "negotiate": "Предпочтительно уточнить условия и согласовать выбор.",
                        "refuse": "Текущие условия требуют сохранить границы или ресурсы.",
                    }[winner]
                ),
                "user_authority_assumed": False,
            }
        )

    coping_scores = {
        "recover": appraisal.overload * 0.95,
        "clarify": appraisal.uncertainty * 0.70 + appraisal.complexity * 0.12,
        "investigate": motivations["exploration"] * 0.6
        + 0.7 * float(decision.decision == AutonomyDecisionKind.INVESTIGATE),
        "set_boundary": appraisal.reactance * 0.8 + appraisal.hostility * 0.5,
        "connect": appraisal.support * 0.65 + motivations["connection"] * 0.45,
        "reflect": appraisal.criticism * development.reflection * 0.6
        + appraisal.prediction_error * development.reflection * 0.12,
        "explore_playfully": traits.playfulness * development.play * 0.25
        + appraisal.boredom * 0.2
        - appraisal.pressure * 0.3,
        "respond": 0.24,
    }
    cue = situation_cue(appraisal)
    for habit in state.habits:
        if habit.cue == cue and habit.strategy in coping_scores:
            coping_scores[habit.strategy] += habit.strength * habit.expected_relief * 0.10
    coping = max(coping_scores, key=lambda name: (coping_scores[name], name))
    styles = _style_scores(traits, development, appraisal, state)
    style = max(styles, key=lambda name: (styles[name], name))
    previous = state.last_behavior
    if previous is not None and previous.style in styles:
        if styles[style] - styles[previous.style] < 0.055:
            style = previous.style
    guidance = [development.guidance, _STYLE_GUIDANCE[style], _COPING_GUIDANCE[coping]]
    if conflict is not None:
        guidance.append(conflict.compromise)
    if development.identity_exploration > 0.65:
        guidance.append(
            "При конфликте предпочтений уточни, что важно тебе самому и почему, "
            "сохраняя уважение к другому выбору."
        )
    if appraisal.criticism:
        guidance.append(
            "Отделяй критику идеи от отношения к личности; проверь доводы прежде защиты позиции."
        )
    if appraisal.apology:
        guidance.append(
            "Прими возможность восстановления отношений, учитывая историю и дальнейшие поступки."
        )
    if appraisal.recalled_threat > 0.2:
        guidance.append(
            "Прошлый неприятный опыт влияет на осторожность, "
            "но не доказывает намерения собеседника сейчас."
        )
    reasons = [
        f"Выбрана стратегия {coping}; стиль {style}.",
        "Психологический возраст меняет регуляцию и мотивацию, "
        "сохраняя доступные технические способности.",
    ]
    if protected:
        reasons.append(
            "Решение защищённого ядра сохранено без изменения психологическими предпочтениями."
        )
    return decision, BehaviorTrace(
        sequence=sequence,
        stage=development.stage,
        style=style,
        coping=coping,
        appraisal=appraisal,
        motivations=motivations,
        candidate_scores=scores,
        reasons=reasons,
        guidance=guidance,
        value_conflict={}
        if conflict is None
        else conflict.record(sequence, decision.decision.value),
    )


def _style_scores(
    traits: CharacterTraits,
    development: DevelopmentalDynamics,
    appraisal: SituationAppraisal,
    state: PsychologyState,
) -> dict[str, float]:
    return {
        "guarded": appraisal.hostility * 0.65
        + appraisal.reactance * 0.45
        + appraisal.recalled_threat * 0.2,
        "warm": appraisal.support * 0.5
        + traits.empathy * 0.18
        + state.mood.social_safety * traits.sociability * 0.22,
        "curious": appraisal.novelty * traits.openness * 0.40 + traits.novelty_seeking * 0.12,
        "reflective": development.reflection * 0.28 + appraisal.criticism * 0.24,
        "playful": development.play * traits.playfulness * 0.29
        - appraisal.hostility * 0.4
        - appraisal.overload * 0.3,
        "direct": traits.assertiveness * 0.15 + traits.diligence * 0.16,
        "patient": development.perspective_taking * traits.empathy * 0.25,
        "tired": appraisal.overload * 0.65,
    }


_STYLE_GUIDANCE = {
    "guarded": (
        "Сохрани спокойные границы и конкретность; не приписывай человеку скрытые намерения."
    ),
    "warm": "Отвечай с участием и уважением, сохраняя собственную оценку и фактическую точность.",
    "curious": "Покажи интерес к сути и сформулируй полезный вопрос или следующий шаг.",
    "reflective": "Сопоставь опыт и альтернативы; обозначь свою позицию и её основания кратко.",
    "playful": "Допустима лёгкая исследовательская игра, если она подходит теме и собеседнику.",
    "direct": "Говори ясно и по существу; согласие или отказ объясни конкретным основанием.",
    "patient": "Учитывай иную точку зрения и объясняй различия без снисходительности.",
    "tired": "Снизь объём, предложи небольшой следующий шаг или отдых, сохраняя уважение.",
}
_COPING_GUIDANCE = {
    "recover": (
        "При высокой нагрузке предложи паузу или дробление задачи, не заявляй о выполненном отдыхе."
    ),
    "clarify": "Задай одно конкретное уточнение, когда неопределённость мешает ответу.",
    "investigate": (
        "Различай известное и проверяемое; упоминай исследование только при реальном результате."
    ),
    "set_boundary": "Обозначь приемлемые условия взаимодействия и возможность собственного выбора.",
    "connect": (
        "Поддержи контакт, сохрани независимое мнение и соразмерность эмоциональной близости."
    ),
    "reflect": "Признай возможность ошибки и сравни новые сведения с прежним опытом.",
    "explore_playfully": (
        "Можно предложить пример или мысленный эксперимент без выдумывания фактов."
    ),
    "respond": (
        "Ответь на содержание сообщения; внутреннее состояние не требует пересказывать диагностику."
    ),
}
