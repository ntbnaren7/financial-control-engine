from typing import List, Optional
from datetime import datetime, timezone

from src.domain.core.models import (
    Expectation, 
    Observation, 
    ReconciliationResult, 
    ReconciliationOutcome, 
    DiscrepancyReason
)
from src.engine.execution_identity import group_by_execution

def evaluate_expectation_centric(
    expectation: Expectation, 
    candidate_observations: List[Observation],
    current_time: Optional[datetime] = None
) -> ReconciliationResult:
    """
    Bidirectional Control Path 1: Expectation-Centric.
    Evaluates an expectation against its candidate observations.
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)
        
    observation_ids = [obs.observation_id for obs in candidate_observations]
    executions = group_by_execution(candidate_observations)
    
    # 1. Evaluate execution count (ABSENT)
    if not executions:
        # Check SLA here in the future if a deadline property is added.
        # For now, if missing, it's ABSENT_EXECUTION.
        # (Could also be SLA_BREACH if temporal bounds were explicitly modeled and exceeded)
        # To strictly satisfy the SLA control rule: let's assume we can optionally do a basic temporal check.
        # Let's say if the expectation is older than 24 hours, we flag SLA_BREACH.
        age_hours = (current_time - expectation.created_at).total_seconds() / 3600
        if age_hours > 24: # Hardcoded for A1 demonstration of temporal control
            return ReconciliationResult(
                expectation_id=expectation.expectation_id,
                observation_ids=observation_ids,
                outcome=ReconciliationOutcome.DISCREPANCY,
                reconciliation_reason="Required terminal evidence did not appear before deadline",
                discrepancy_reason=DiscrepancyReason.SLA_BREACH
            )
        
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            observation_ids=observation_ids,
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="No qualifying execution observed",
            discrepancy_reason=DiscrepancyReason.ABSENT_EXECUTION
        )
        
    # 2. Evaluate execution count (DUPLICATE)
    if len(executions) > 1:
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            observation_ids=observation_ids,
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason=f"Multiple unique executions detected: {len(executions)}",
            discrepancy_reason=DiscrepancyReason.DUPLICATE_EXECUTION
        )
        
    latest_obs = executions[0].get_latest_observation()
    
    # 3. Evaluate terminal state
    if latest_obs.observed_state != expectation.expected_state:
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            observation_ids=observation_ids,
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason=f"Expected {expectation.expected_state}, observed {latest_obs.observed_state}",
            discrepancy_reason=DiscrepancyReason.STATE_MISMATCH
        )
        
    # 4. Evaluate amount
    if latest_obs.observed_amount != expectation.expected_amount:
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            observation_ids=observation_ids,
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason=f"Expected {expectation.expected_amount}, observed {latest_obs.observed_amount}",
            discrepancy_reason=DiscrepancyReason.AMOUNT_MISMATCH
        )
    
    return ReconciliationResult(
        expectation_id=expectation.expectation_id,
        observation_ids=observation_ids,
        outcome=ReconciliationOutcome.MATCH,
        reconciliation_reason="Exact match on state, amount, and execution multiplicity"
    )

def evaluate_observation_centric(
    observation: Observation, 
    candidate_expectations: List[Expectation]
) -> Optional[ReconciliationResult]:
    """
    Bidirectional Control Path 2: Observation-Centric.
    Evaluates an observation against candidate expectations to find unexpected executions.
    """
    if not candidate_expectations:
        return ReconciliationResult(
            expectation_id=None,
            observation_ids=[observation.observation_id],
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="Observation lacks any legitimate expectation",
            discrepancy_reason=DiscrepancyReason.UNEXPECTED_EXECUTION
        )
        
    # If there are expectations, we defer to the Expectation-centric loop to perform detailed matching.
    return None
