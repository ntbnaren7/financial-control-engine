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
    
    # 4. State Mismatch across all observed providers
    # Group by provider to get the latest observation per provider.
    # Normalise observed_at to UTC-aware before comparing — SQLite returns naive datetimes
    # for DateTime(timezone=True) columns, so raw comparison is unsafe.
    def _to_utc_safe(dt):
        if dt.tzinfo is None:
            from datetime import timezone as _tz
            return dt.replace(tzinfo=_tz.utc)
        return dt

    provider_latest = {}
    for obs in executions[0].observations:
        provider = obs.provider.lower()
        if provider not in provider_latest or _to_utc_safe(obs.observed_at) > _to_utc_safe(provider_latest[provider].observed_at):
            provider_latest[provider] = obs

    for provider, obs in provider_latest.items():
        if obs.canonical_status != expectation.expected_canonical_status:
            return ReconciliationResult(
                expectation_id=expectation.expectation_id,
                observation_ids=observation_ids,
                outcome=ReconciliationOutcome.DISCREPANCY,
                reconciliation_reason=f"Provider {provider} expected {expectation.expected_canonical_status.value}, observed {obs.canonical_status.value}",
                discrepancy_reason=DiscrepancyReason.STATE_MISMATCH
            )
            
    latest_obs = executions[0].get_latest_observation()
    # 4. Evaluate amount and currency
    if latest_obs.currency != expectation.currency:
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            observation_ids=observation_ids,
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason=f"Expected currency {expectation.currency}, observed {latest_obs.currency}",
            discrepancy_reason=DiscrepancyReason.AMOUNT_MISMATCH
        )
        
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
