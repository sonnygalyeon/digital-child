from digital_child.domain.models import (
    AutonomyDecision,
    AutonomyDecisionKind,
    EmotionState,
    IdentityProfile,
    MessageAnalysis,
    MessageIntent,
    RelationshipProfile,
)
from digital_child.inference.prompting import build_reply_messages
from digital_child.inference.types import ReplyContext


def test_prompt_is_compact_and_unicode(monkeypatch) -> None:
    monkeypatch.setenv("DIGITAL_CHILD_LLM_PROMPT_MAX_CHARS", "2200")
    context = ReplyContext(
        identity=IdentityProfile(display_name="Ребёнок", self_description="Я формируюсь."),
        analysis=MessageAnalysis(
            text="Привет, расскажи о себе", intent=MessageIntent.QUESTION, confidence=0.9
        ),
        decision=AutonomyDecision(
            person_id="local-user",
            intent=MessageIntent.QUESTION,
            input_text="Привет, расскажи о себе",
            decision=AutonomyDecisionKind.ANSWER,
            reason="Я решил ответить самостоятельно.",
            confidence=0.9,
        ),
        relationship=RelationshipProfile(person_id="local-user"),
        goals=[],
        emotion=EmotionState(),
        research_summary=None,
        personal_memory_summary="Память пуста.",
        beliefs_summary="Убеждений мало.",
        conversation_history=[],
        development_stage="newborn",
        total_deu=0.0,
    )
    messages = build_reply_messages(context)
    assert len(messages) == 2
    assert "Привет" in messages[1]["content"]
    assert len(messages[1]["content"]) <= 2200
