import pytest
from datetime import datetime, timezone
import uuid

from src.domain.core.models import (
    Expectation,
    Observation,
    Evidence,
    BusinessStatus,
    ReconciliationResult,
    ReconciliationOutcome,
    CanonicalStatus,
)
from src.storage.substrate_repo import MemoryObservationRepository, MemoryExpectationRepository
from src.engine.v2_reconciliation import reconcile


def test_observation_identity_in_memory_repo():
    repo = MemoryObservationRepository()
    
    obs1 = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=500,
        currency="INR",
        evidence_ids=["ev_1"],
        provider_event_id="evt_001"
    )
    
    obs2 = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        canonical_status=CanonicalStatus.SETTLED,
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
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=500,
        currency="INR",
        source_system="merchant_ledger"
    )
    
    obs_matching = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        canonical_status=CanonicalStatus.SETTLED,
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
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=500,
        currency="INR",
        source_system="merchant_ledger"
    )
    
    obs_mismatch = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        canonical_status=CanonicalStatus.FAILED,
        observed_amount=500,
        currency="INR",
        evidence_ids=[]
    )
    
    result = reconcile(exp, [obs_mismatch])
    assert result.outcome == ReconciliationOutcome.DISCREPANCY

