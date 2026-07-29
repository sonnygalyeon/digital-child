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
