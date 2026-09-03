from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from src.domain.core.models import Expectation, Observation, Evidence, ReconciliationResult


@dataclass(frozen=True)
class InvestigationContext:
    """
    An immutable snapshot of the financial reality at the exact moment a discrepancy was detected.
    This serves as the explicit boundary contract between the deterministic discrepancy engine (A1)
    and the untrusted AI investigator (A3).
    
    It intentionally does not interpret the evidence, but rather assembles the facts.
    """
    context_id: str
    assembled_at: datetime
    
    # The discrepancy that triggered this investigation
    active_discrepancy: ReconciliationResult
    
    # The known facts retrieved from the financial substrate
    expectation: Optional[Expectation]
    observations: List[Observation]
    evidence_records: List[Evidence]

    @classmethod
    def create(
        cls,
        active_discrepancy: ReconciliationResult,
        expectation: Optional[Expectation],
        observations: List[Observation],
        evidence_records: List[Evidence],
        assembled_at: Optional[datetime] = None
    ) -> "InvestigationContext":
        return cls(
            context_id=str(uuid.uuid4()),
            assembled_at=assembled_at or datetime.now(timezone.utc),
            active_discrepancy=active_discrepancy,
            expectation=expectation,
            observations=observations,
            evidence_records=evidence_records
        )
