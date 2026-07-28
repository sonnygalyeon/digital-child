from __future__ import annotations

from datetime import UTC, datetime

from digital_child.models import (
    Belief,
    BeliefStatus,
    BeliefUpdate,
    ClaimEvidenceInput,
    EvidenceRecord,
    EvidenceStance,
    Observation,
    SourceRecord,
)
from digital_child.storage import SQLiteRepository
from digital_child.text import normalize_text


class BeliefEngine:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def apply_evidence(
        self,
        claim_input: ClaimEvidenceInput,
        observation: Observation,
        source: SourceRecord,
        current_sequence: int,
    ) -> BeliefUpdate:
        normalized = normalize_text(claim_input.claim)
        if not normalized:
            raise ValueError("Claim contains no searchable tokens")

        belief = self.repository.get_belief_by_normalized_claim(normalized)
        created = belief is None
        if belief is None:
            belief = Belief(
                claim=claim_input.claim.strip(),
                normalized_claim=normalized,
                tags=list(observation.tags),
                last_accessed_sequence=current_sequence,
            )

        weight = (
            source.reliability
            * claim_input.confidence
            * observation.attention
            * observation.comprehension
        )

        if claim_input.stance == EvidenceStance.SUPPORT:
            belief.support_score += weight
        elif claim_input.stance == EvidenceStance.CONTRADICT:
            belief.contradiction_score += weight
        else:
            weight = 0.0

        belief.evidence_count += 1
        belief.access_count += 1
        belief.last_accessed_sequence = current_sequence
        belief.access_strength = min(1.0, belief.access_strength + 0.05)
        belief.updated_at = datetime.now(UTC)
        belief.confidence = self._confidence(belief)
        belief.status = self._status(belief)

        self.repository.save_belief(belief)
        evidence = EvidenceRecord(
            belief_id=belief.id,
            observation_id=observation.id,
            source_id=source.id,
            stance=claim_input.stance,
            confidence=claim_input.confidence,
            weight=weight,
            excerpt=claim_input.claim,
        )
        self.repository.save_evidence(evidence)
        return BeliefUpdate(belief=belief, evidence=evidence, created=created)

    @staticmethod
    def _confidence(belief: Belief) -> float:
        numerator = 0.5 + belief.support_score
        denominator = 1.0 + belief.support_score + belief.contradiction_score
        return max(0.0, min(1.0, numerator / denominator))

    @staticmethod
    def _status(belief: Belief) -> BeliefStatus:
        support = belief.support_score
        contradiction = belief.contradiction_score

        if support >= 0.35 and contradiction >= 0.35:
            return BeliefStatus.CONTESTED
        if belief.confidence >= 0.70 and support > contradiction:
            return BeliefStatus.SUPPORTED
        if belief.confidence <= 0.30 and contradiction > support:
            return BeliefStatus.REJECTED
        return BeliefStatus.TENTATIVE
