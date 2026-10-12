from __future__ import annotations

from dataclasses import dataclass

from digital_child.models import (
    AutonomyDecision,
    ConversationMessage,
    EmotionState,
    Goal,
    IdentityProfile,
    MessageAnalysis,
    RelationshipProfile,
)


@dataclass(frozen=True)
class ReplyContext:
    identity: IdentityProfile
    analysis: MessageAnalysis
    decision: AutonomyDecision
    relationship: RelationshipProfile
    goals: list[Goal]
    emotion: EmotionState
    research_summary: str | None
    personal_memory_summary: str
    beliefs_summary: str
    conversation_history: list[ConversationMessage]
    development_stage: str
    total_deu: float
    needs_summary: str = "нет данных"
    active_goal_summary: str = "нет выбранной цели"
    psychology_summary: str = "индивидуальные особенности ещё формируются"
    development_summary: str = "нет данных"
    behavior_guidance: tuple[str, ...] = ()
    behavior_style: str = "direct"
    coping_strategy: str = "respond"
    interaction_mode: str = "reply"
    initiative_reason: str = ""
    initiative_topic: str = ""
    initiative_angle: str = ""
    initiative_source_text: str = ""
    discussion_orientation: str = "explore"
    interests_summary: str = "ещё формируются"
