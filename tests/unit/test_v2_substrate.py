import pytest
from datetime import datetime, timezone
import uuid

from src.domain.core.models import Expectation, Observation, Evidence, BusinessStatus, ReconciliationResult, ReconciliationOutcome
from src.storage.substrate_repo import MemoryObservationRepository, MemoryExpectationRepository
from src.engine.v2_reconciliation import reconcile
from src.adapters.v1_incident_adapter import translate_to_incident

def test_observation_identity_in_memory_repo():
    repo = MemoryObservationRepository()
    
    obs1 = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSING",
        observed_amount=500,
        currency="INR",
        evidence_ids=["ev_1"],
        provider_event_id="evt_001"
    )
    
    obs2 = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=500,
        currency="INR",
        evidence_ids=["ev_2"],
        provider_event_id="evt_002"
    )
    
    repo.save(obs1)
    repo.save(obs2)
    
    results = repo.find_by_business_identity("razorpay", "pay_123", "refund")
    assert len(results) == 2

def test_reconciliation_contract_naive_match():
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant_ledger"
    )
    
    obs_matching = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[]
    )
    
    result = reconcile(exp, [obs_matching])
    assert result.outcome == ReconciliationOutcome.MATCH
    assert result.expectation_id == exp.expectation_id

def test_reconciliation_contract_discrepancy():
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant_ledger"
    )
    
    obs_mismatch = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="FAILED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[]
    )
    
    result = reconcile(exp, [obs_mismatch])
    assert result.outcome == ReconciliationOutcome.DISCREPANCY

def test_v2_to_v1_adapter():
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant_ledger"
    )
    result = ReconciliationResult(
        expectation_id=exp.expectation_id,
        observation_ids=["obs_1"],
        outcome=ReconciliationOutcome.DISCREPANCY,
        reconciliation_reason="Mismatch"
    )
    
    incident, context = translate_to_incident(result, exp, [], [])
    
    assert incident.expectation_id == exp.expectation_id
    assert incident.lifecycle_state.value == "OPEN"
    assert context.reconciliation_result.outcome == ReconciliationOutcome.DISCREPANCY
    assert context.expectation == exp
