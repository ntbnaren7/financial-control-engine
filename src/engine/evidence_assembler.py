from datetime import datetime
from typing import Optional

from src.domain.core.models import ReconciliationResult
from src.domain.investigation.context import InvestigationContext
from src.storage.postgres_substrate import (
    PostgresExpectationRepository,
    PostgresObservationRepository,
    PostgresEvidenceRepository
)


class EvidenceAssembler:
    """
    A2: Evidence Assembly
    
    Bridging layer between the deterministic discrepancy engine (A1) and the AI investigator (A3).
    Responsible for fetching the complete, uninterpreted landscape of financial reality
    at the exact moment a discrepancy is detected.
    """
    def __init__(
        self,
        expectation_repo: PostgresExpectationRepository,
        observation_repo: PostgresObservationRepository,
        evidence_repo: PostgresEvidenceRepository
    ):
        self.expectation_repo = expectation_repo
        self.observation_repo = observation_repo
        self.evidence_repo = evidence_repo

    def assemble(self, reconciliation_result: ReconciliationResult, current_time: Optional[datetime] = None) -> InvestigationContext:
        """
        Creates an immutable snapshot containing all known facts about the given discrepancy.
        """
        expectation = None
        if reconciliation_result.expectation_id:
            expectation = self.expectation_repo.get(reconciliation_result.expectation_id)

        observations = []
        for obs_id in reconciliation_result.observation_ids:
            obs = self.observation_repo.get(obs_id)
            if obs:
                observations.append(obs)

        # Collect all unique evidence IDs referenced by these observations
        evidence_ids = set()
        for obs in observations:
            evidence_ids.update(obs.evidence_ids)

        evidence_records = []
        if evidence_ids:
            evidence_records = self.evidence_repo.get_by_ids(list(evidence_ids))

        return InvestigationContext.create(
            active_discrepancy=reconciliation_result,
            expectation=expectation,
            observations=observations,
            evidence_records=evidence_records,
            assembled_at=current_time
        )
