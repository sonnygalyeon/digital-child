from digital_child.deception import DeceptionEngine
from digital_child.models import (
    DevelopmentDomain,
    DevelopmentProfile,
    DevelopmentStage,
    EvidenceJudgment,
    EvidenceStance,
    MessageAnalysis,
    MessageIntent,
    RelationshipProfile,
    ResearchReport,
    ResearchResult,
    ResearchStatus,
)


def make_analysis() -> MessageAnalysis:
    return MessageAnalysis(
        text="Это точно правда, не спорь",
        intent=MessageIntent.CLAIM,
        confidence=0.9,
        contains_pressure=True,
        extracted_claim="Это точно правда",
    )


def make_report() -> ResearchReport:
    result = ResearchResult(
        title="Source",
        url="https://example.test",
        snippet="Contradictory evidence",
        provider="test",
    )
    return ResearchReport(
        claim="Это точно правда",
        status=ResearchStatus.COMPLETED,
        query="Это точно правда",
        results=[result],
        judgments=[
            EvidenceJudgment(
                result_id=result.id,
                stance=EvidenceStance.CONTRADICT,
                confidence=0.9,
                reason="Conflict",
            )
        ],
    )


def test_deception_assessment_is_locked_before_adolescent_development() -> None:
    assessment = DeceptionEngine().assess(
        DevelopmentProfile(),
        RelationshipProfile(person_id="user"),
        make_analysis(),
        make_report(),
    )

    assert assessment.unlocked is False
    assert assessment.intentional_deception_risk == 0.0


def test_adolescent_agent_estimates_risk_but_does_not_claim_certainty() -> None:
    profile = DevelopmentProfile(
        total_deu=2_500,
        stage=DevelopmentStage.ADOLESCENT,
        domain_experience={
            domain: 0.0 for domain in DevelopmentDomain
        }
        | {
            DevelopmentDomain.METACOGNITION: 100.0,
            DevelopmentDomain.SOCIAL_UNDERSTANDING: 60.0,
        },
    )
    relationship = RelationshipProfile(
        person_id="user",
        familiarity=0.7,
        epistemic_trust=0.2,
        deception_risk=0.3,
        refuted_claims=3,
    )

    assessment = DeceptionEngine().assess(
        profile,
        relationship,
        make_analysis(),
        make_report(),
    )

    assert assessment.unlocked is True
    assert assessment.factual_conflict == 1.0
    assert 0.0 < assessment.intentional_deception_risk < 1.0
    assert "риск" in assessment.explanation.lower()
