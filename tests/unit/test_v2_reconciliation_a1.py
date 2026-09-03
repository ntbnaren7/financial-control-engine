import pytest
from datetime import datetime, timezone, timedelta
from src.domain.core.models import Expectation, Observation, CorrelationKeys, ReconciliationOutcome, DiscrepancyReason
from src.engine.reconciliation_controls import evaluate_expectation_centric, evaluate_observation_centric

def test_absent_execution():
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant",
        correlation_keys=CorrelationKeys(internal_ref="refund_123")
    )
    result = evaluate_expectation_centric(exp, [])
    assert result.outcome == ReconciliationOutcome.DISCREPANCY
    assert result.discrepancy_reason == DiscrepancyReason.ABSENT_EXECUTION

def test_sla_breach():
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant",
        created_at=datetime.now(timezone.utc) - timedelta(hours=25),
        correlation_keys=CorrelationKeys(internal_ref="refund_123")
    )
    result = evaluate_expectation_centric(exp, [])
    assert result.outcome == ReconciliationOutcome.DISCREPANCY
    assert result.discrepancy_reason == DiscrepancyReason.SLA_BREACH

def test_duplicate_execution():
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant"
    )
    obs1 = Observation(
        provider="razorpay",
        provider_reference="pay_123", 
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[]
    )
    obs2 = Observation(
        provider="razorpay",
        provider_reference="pay_456", 
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[]
    )
    result = evaluate_expectation_centric(exp, [obs1, obs2])
    assert result.outcome == ReconciliationOutcome.DISCREPANCY
    assert result.discrepancy_reason == DiscrepancyReason.DUPLICATE_EXECUTION

def test_observation_multiplicity_is_not_duplicate_execution():
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant"
    )
    obs_processing = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSING",
        observed_amount=500,
        currency="INR",
        evidence_ids=[],
        observed_at=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    obs_processed = Observation(
        provider="razorpay",
        provider_reference="pay_123", 
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[],
        observed_at=datetime.now(timezone.utc)
    )
    result = evaluate_expectation_centric(exp, [obs_processing, obs_processed])
    assert result.outcome == ReconciliationOutcome.MATCH

def test_state_mismatch():
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant"
    )
    obs = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="FAILED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[]
    )
    result = evaluate_expectation_centric(exp, [obs])
    assert result.outcome == ReconciliationOutcome.DISCREPANCY
    assert result.discrepancy_reason == DiscrepancyReason.STATE_MISMATCH

def test_amount_mismatch():
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant"
    )
    obs = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=450,
        currency="INR",
        evidence_ids=[]
    )
    result = evaluate_expectation_centric(exp, [obs])
    assert result.outcome == ReconciliationOutcome.DISCREPANCY
    assert result.discrepancy_reason == DiscrepancyReason.AMOUNT_MISMATCH

def test_unexpected_execution():
    obs = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[]
    )
    result = evaluate_observation_centric(obs, [])
    assert result.outcome == ReconciliationOutcome.DISCREPANCY
    assert result.discrepancy_reason == DiscrepancyReason.UNEXPECTED_EXECUTION
