from typing import List
from src.domain.core.models import Expectation, Observation, ReconciliationResult, ReconciliationOutcome

def reconcile(expectation: Expectation, candidate_observations: List[Observation]) -> ReconciliationResult:
    """
    V2-A0 Deterministic Reconciliation Contract.
    
    Given an expectation and candidate observations, produce an immutable ReconciliationResult.
    This serves as the deterministic evaluation boundary. The generalized discrepancy taxonomy
    (ABSENT_EXECUTION, AMOUNT_MISMATCH, etc.) is deferred to V2-A1.
    """
    observation_ids = [obs.observation_id for obs in candidate_observations]
    
    # A0 Placeholder logic: naive match on expected_state and expected_amount.
    outcome = ReconciliationOutcome.DISCREPANCY
    reason = "No matching observation found for expectation"
    
    for obs in candidate_observations:
        if obs.observed_state == expectation.expected_state and obs.observed_amount == expectation.expected_amount:
            outcome = ReconciliationOutcome.MATCH
            reason = "Observation exactly matches expectation state and amount"
            break
            
    return ReconciliationResult(
        expectation_id=expectation.expectation_id,
        observation_ids=observation_ids,
        outcome=outcome,
        reconciliation_reason=reason
    )
