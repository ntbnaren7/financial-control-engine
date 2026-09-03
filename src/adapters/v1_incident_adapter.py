from dataclasses import dataclass
from typing import List, Tuple

from src.domain.core.models import ReconciliationResult, Expectation, Observation, Evidence, ReconciliationOutcome
from src.domain.incidents.models import Incident, IncidentState

@dataclass
class InvestigationContext:
    """Structured context passed to the V1 Investigator, keeping domain evidence out of Incident history."""
    reconciliation_result: ReconciliationResult
    expectation: Expectation
    observations: List[Observation]
    evidence_records: List[Evidence]


def translate_to_incident(
    reconciliation_result: ReconciliationResult,
    expectation: Expectation,
    observations: List[Observation],
    evidence_records: List[Evidence]
) -> Tuple[Incident, InvestigationContext]:
    """
    Anti-corruption boundary translating a V2 Discrepancy into the frozen V1 Incident model.
    """
    if reconciliation_result.outcome != ReconciliationOutcome.DISCREPANCY:
        raise ValueError("Cannot create an incident from a matching reconciliation result.")
        
    incident = Incident(
        lifecycle_state=IncidentState.OPEN,
        # V1 incident happens to have an expectation_id field.
        expectation_id=expectation.expectation_id,
        
        # We can also map V1-specific domain keys if A0 expects them to exist, 
        # or we leave them as None because the V2 discrepancy is generic.
        # The InvestigationContext now carries the full structural truth.
    )
    
    context = InvestigationContext(
        reconciliation_result=reconciliation_result,
        expectation=expectation,
        observations=observations,
        evidence_records=evidence_records
    )
    
    return incident, context
