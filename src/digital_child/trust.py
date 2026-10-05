from __future__ import annotations

from datetime import UTC, datetime

from digital_child.models import RelationshipProfile, TrustEvent
from digital_child.storage import SQLiteRepository


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class TrustEngine:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def get_or_create(self, person_id: str) -> RelationshipProfile:
        relationship = self.repository.load_relationship(person_id)
        if relationship is None:
            relationship = RelationshipProfile(person_id=person_id)
            self.repository.save_relationship(relationship)
        return relationship

    def register_interaction(self, relationship: RelationshipProfile) -> RelationshipProfile:
        updated = relationship.model_copy(
            update={
                "updated_at": datetime.now(UTC),
                "interactions": relationship.interactions + 1,
                "familiarity": clamp(relationship.familiarity + 0.015),
            }
        )
        self.repository.save_relationship(updated)
        return updated

    def apply_verification_outcome(
        self,
        relationship: RelationshipProfile,
        *,
        supported: bool,
        contradicted: bool,
        repeated_after_correction: bool = False,
    ) -> RelationshipProfile:
        epistemic_delta = 0.0
        deception_delta = 0.0
        supported_claims = relationship.supported_claims
        refuted_claims = relationship.refuted_claims

        if supported:
            epistemic_delta += 0.025
            supported_claims += 1
        if contradicted:
            epistemic_delta -= 0.06
            deception_delta += 0.015
            refuted_claims += 1
        if repeated_after_correction:
            epistemic_delta -= 0.08
            deception_delta += 0.08

        updated = relationship.model_copy(
            update={
                "updated_at": datetime.now(UTC),
                "epistemic_trust": clamp(relationship.epistemic_trust + epistemic_delta),
                "deception_risk": clamp(relationship.deception_risk + deception_delta),
                "supported_claims": supported_claims,
                "refuted_claims": refuted_claims,
            }
        )
        self.repository.save_relationship(updated)
        self.repository.save_trust_event(
            TrustEvent(
                person_id=relationship.person_id,
                reason="verification_outcome",
                epistemic_delta=epistemic_delta,
                affective_delta=0.0,
                deception_delta=deception_delta,
            )
        )
        return updated

    def apply_social_experience(self, person_id: str, delta: float) -> RelationshipProfile:
        # Emotional familiarity is independent of whether factual claims are true.
        relationship = self.get_or_create(person_id)
        delta = max(-0.03, min(0.015, delta))
        updated = relationship.model_copy(
            update={
                "updated_at": datetime.now(UTC),
                "affective_trust": clamp(relationship.affective_trust + delta),
            }
        )
        self.repository.save_relationship(updated)
        if abs(delta) > 0.00001:
            self.repository.save_trust_event(
                TrustEvent(
                    person_id=person_id,
                    reason="observed_social_interaction",
                    affective_delta=delta,
                    epistemic_delta=0.0,
                    deception_delta=0.0,
                )
            )
        return updated
