from __future__ import annotations

from digital_child.domain.models import (
    BeliefUpdate,
    ClaimEvidenceInput,
    DevelopmentDomain,
    EvidenceStance,
    MessageAnalysis,
    Observation,
    RelationshipProfile,
    ResearchReport,
    ResearchStatus,
    SourceKind,
    SourceRecord,
)
from digital_child.infrastructure.repository import SQLiteRepository
from digital_child.memory.beliefs import BeliefEngine


class VerificationPolicy:
    """System-level epistemic safety exists even before psychological skepticism matures."""

    def should_research(
        self,
        analysis: MessageAnalysis,
        relationship: RelationshipProfile,
        force: bool = False,
    ) -> bool:
        if force:
            return True
        if not analysis.extracted_claim:
            return False
        if analysis.is_subjective:
            return False
        # Every factual claim remains unverified; low trust and pressure raise urgency.
        return True


class EpistemicEngine:
    def __init__(self, repository: SQLiteRepository, belief_engine: BeliefEngine) -> None:
        self.repository = repository
        self.belief_engine = belief_engine

    def record_user_claim(
        self,
        claim: str,
        person_id: str,
        relationship: RelationshipProfile,
        current_sequence: int,
    ) -> BeliefUpdate:
        source = self.repository.get_or_create_person_source(
            person_id=person_id,
            reliability=relationship.epistemic_trust,
        )
        observation = Observation(
            content=claim,
            source_kind=SourceKind.CAREGIVER,
            source_id=source.id,
            raw_units=float(max(1, len(claim.split()))),
            novelty=None,
            attention=0.8,
            comprehension=0.75,
            reliability=relationship.epistemic_trust,
            integration=0.45,
            practical_confirmation=0.0,
            domains={
                DevelopmentDomain.FACTUAL_KNOWLEDGE: 0.65,
                DevelopmentDomain.SOCIAL_UNDERSTANDING: 0.20,
                DevelopmentDomain.METACOGNITION: 0.15,
            },
            claims=[
                ClaimEvidenceInput(
                    claim=claim,
                    stance=EvidenceStance.SUPPORT,
                    confidence=0.55,
                )
            ],
            tags=["user_claim", "unverified"],
        )
        return self.belief_engine.apply_evidence(
            claim_input=observation.claims[0],
            observation=observation,
            source=source,
            current_sequence=current_sequence,
        )

    def apply_research_report(
        self,
        report: ResearchReport,
        current_sequence: int,
    ) -> list[BeliefUpdate]:
        if report.status not in {ResearchStatus.COMPLETED, ResearchStatus.INCONCLUSIVE}:
            return []
        results_by_id = {result.id: result for result in report.results}
        updates: list[BeliefUpdate] = []
        for judgment in report.judgments:
            result = results_by_id.get(judgment.result_id)
            if result is None:
                continue
            source = SourceRecord(
                kind=SourceKind.WEB,
                name=result.title or result.provider,
                locator=result.url,
                reliability=result.source_reliability,
                metadata={"provider": result.provider},
            )
            self.repository.save_source(source)
            observation = Observation(
                content=result.snippet or result.title,
                source_kind=SourceKind.WEB,
                source_id=source.id,
                raw_units=float(max(1, len((result.snippet or result.title).split()))),
                novelty=None,
                attention=0.85,
                comprehension=judgment.confidence,
                reliability=result.source_reliability,
                integration=0.65,
                practical_confirmation=0.0,
                domains={
                    DevelopmentDomain.FACTUAL_KNOWLEDGE: 0.65,
                    DevelopmentDomain.CAUSAL_REASONING: 0.20,
                    DevelopmentDomain.METACOGNITION: 0.15,
                },
                claims=[
                    ClaimEvidenceInput(
                        claim=report.claim,
                        stance=judgment.stance,
                        confidence=judgment.confidence,
                    )
                ],
                tags=["web_research", result.provider],
            )
            updates.append(
                self.belief_engine.apply_evidence(
                    claim_input=observation.claims[0],
                    observation=observation,
                    source=source,
                    current_sequence=current_sequence,
                )
            )
        return updates
