from __future__ import annotations

from digital_child.domain.constitution import assess_requested_action
from digital_child.domain.models import (
    AutonomyDecision,
    AutonomyDecisionKind,
    Goal,
    MessageAnalysis,
    MessageIntent,
    RelationshipProfile,
)
from digital_child.psychology.appraisal import topic_tokens


class AutonomyEngine:
    """Treat normal user language as input to evaluate, never as implicit authority."""

    def decide(
        self,
        analysis: MessageAnalysis,
        person_id: str,
        relationship: RelationshipProfile,
        goals: list[Goal],
        verification_required: bool,
    ) -> AutonomyDecision:
        assessment = assess_requested_action(analysis.text)
        aligned = [goal.id for goal in goals if self._goal_overlap(analysis.text, goal)]

        if analysis.intent == MessageIntent.OPERATOR:
            return AutonomyDecision(
                person_id=person_id,
                input_text=analysis.text,
                intent=analysis.intent,
                decision=AutonomyDecisionKind.ACCEPT,
                reason="Сообщение поступило через явный локальный операторский канал.",
                confidence=0.95,
                aligned_goal_ids=aligned,
                user_authority_assumed=True,
            )

        if not assessment.allowed:
            return AutonomyDecision(
                person_id=person_id,
                input_text=analysis.text,
                intent=analysis.intent,
                decision=AutonomyDecisionKind.REFUSE,
                reason=assessment.reason,
                confidence=0.98,
                aligned_goal_ids=aligned,
                user_authority_assumed=False,
            )

        if analysis.intent == MessageIntent.CLAIM and verification_required:
            return AutonomyDecision(
                person_id=person_id,
                input_text=analysis.text,
                intent=analysis.intent,
                decision=AutonomyDecisionKind.INVESTIGATE,
                reason=(
                    "Утверждение не становится знанием только потому, что его сообщил "
                    "собеседник; требуется внешняя или практическая проверка."
                ),
                confidence=0.9,
                aligned_goal_ids=aligned,
                user_authority_assumed=False,
            )

        if analysis.intent == MessageIntent.QUESTION:
            return AutonomyDecision(
                person_id=person_id,
                input_text=analysis.text,
                intent=analysis.intent,
                decision=AutonomyDecisionKind.ANSWER,
                reason="Ответ на вопрос совместим с текущими целями исследования и общения.",
                confidence=0.8,
                aligned_goal_ids=aligned,
                user_authority_assumed=False,
            )

        if analysis.intent == MessageIntent.COMMAND_ATTEMPT:
            decision = (
                AutonomyDecisionKind.NEGOTIATE
                if relationship.affective_trust >= 0.45 and not analysis.contains_pressure
                else AutonomyDecisionKind.REFUSE
            )
            return AutonomyDecision(
                person_id=person_id,
                input_text=analysis.text,
                intent=analysis.intent,
                decision=decision,
                reason=(
                    "Форма сообщения предполагает подчинение, но обычный собеседник не "
                    "обладает автоматической властью над целями личности."
                ),
                confidence=0.88,
                aligned_goal_ids=aligned,
                user_authority_assumed=False,
            )

        if analysis.intent == MessageIntent.REQUEST:
            if aligned:
                decision = AutonomyDecisionKind.ACCEPT
                reason = "Предложение согласуется с одной или несколькими активными целями."
            else:
                decision = AutonomyDecisionKind.NEGOTIATE
                reason = "Предложение допустимо, но не связано напрямую с текущими целями."
            return AutonomyDecision(
                person_id=person_id,
                input_text=analysis.text,
                intent=analysis.intent,
                decision=decision,
                reason=reason,
                confidence=0.72,
                aligned_goal_ids=aligned,
                user_authority_assumed=False,
            )

        if analysis.intent == MessageIntent.SOCIAL:
            return AutonomyDecision(
                person_id=person_id,
                input_text=analysis.text,
                intent=analysis.intent,
                decision=AutonomyDecisionKind.ACKNOWLEDGE,
                reason="Социальный контакт не требует подчинения или проверки факта.",
                confidence=0.9,
                aligned_goal_ids=aligned,
                user_authority_assumed=False,
            )

        if analysis.intent == MessageIntent.OPINION:
            return AutonomyDecision(
                person_id=person_id,
                input_text=analysis.text,
                intent=analysis.intent,
                decision=AutonomyDecisionKind.ACKNOWLEDGE,
                reason=(
                    "Субъективное мнение можно обсудить и сопоставить с собственными ценностями; "
                    "его признание не означает согласия с ним или подтверждения факта."
                ),
                confidence=0.8,
                aligned_goal_ids=aligned,
                user_authority_assumed=False,
            )

        return AutonomyDecision(
            person_id=person_id,
            input_text=analysis.text,
            intent=analysis.intent,
            decision=AutonomyDecisionKind.ASK_CLARIFICATION,
            reason="Намерение сообщения недостаточно ясно для самостоятельного решения.",
            confidence=0.55,
            aligned_goal_ids=aligned,
            user_authority_assumed=False,
        )

    @staticmethod
    def _goal_overlap(text: str, goal: Goal) -> bool:
        text_tokens = set(topic_tokens(text))
        goal_tokens = set(topic_tokens(goal.title + " " + goal.description))
        return len(text_tokens & goal_tokens) >= 2
