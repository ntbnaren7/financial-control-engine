import pytest
from src.domain.core.models import (
    CanonicalStatus,
    Expectation,
    Observation,
    Evidence,
    ReconciliationOutcome,
)
from src.engine.adapters.base_adapter import DomainAdapter
from src.engine.adapters.razorpay_payment_adapter import RazorpayPaymentAdapter
from src.engine.v2_reconciliation import reconcile


def test_razorpay_adapter_captured_payment_normalization():
    adapter = RazorpayPaymentAdapter()
    raw_payload = {
        "id": "pay_test_123",
        "order_id": "order_test_456",
        "status": "captured",
        "amount": 50000,
        "currency": "INR",
        "created_at": 1600000000,
    }

    obs, ev = adapter.normalize_payload(raw_payload)

    # Invariants
    assert isinstance(obs, Observation)
    assert isinstance(ev, Evidence)
    assert obs.provider == "razorpay"
    assert obs.provider_reference == "pay_test_123"
    assert obs.canonical_status == CanonicalStatus.SETTLED
    assert isinstance(obs.canonical_status, CanonicalStatus)
    assert obs.observed_amount == 50000
    assert obs.currency == "INR"
    assert obs.observation_type == "PAYMENT"
    assert ev.evidence_id in obs.evidence_ids
    assert ev.source == "razorpay"
    assert len(ev.payload_hash) == 64  # SHA256 hex string


def test_razorpay_adapter_pending_and_failed_statuses():
    adapter = RazorpayPaymentAdapter()

    # Pending / Authorized
    obs_pending, _ = adapter.normalize_payload({
        "id": "pay_test_pending",
        "status": "authorized",
        "amount": 10000,
    })
    assert obs_pending.canonical_status == CanonicalStatus.PENDING

    # Failed
    obs_failed, _ = adapter.normalize_payload({
        "id": "pay_test_failed",
        "status": "failed",
        "amount": 10000,
    })
    assert obs_failed.canonical_status == CanonicalStatus.FAILED

    # Unknown
    obs_unknown, _ = adapter.normalize_payload({
        "id": "pay_test_unknown",
        "status": "some_arbitrary_vendor_status",
        "amount": 10000,
    })
    assert obs_unknown.canonical_status == CanonicalStatus.UNKNOWN


def test_razorpay_adapter_webhook_wrapper_normalization():
    adapter = RazorpayPaymentAdapter()
    webhook_payload = {
        "event": "refund.processed",
        "payload": {
            "refund": {
                "entity": {
                    "id": "rfnd_test_789",
                    "payment_id": "pay_test_123",
                    "receipt": "rcpt_refund_1",
                    "status": "processed",
                    "amount": 25000,
                    "currency": "INR",
                    "created_at": 1600000050,
                }
            }
        }
    }

    obs, ev = adapter.normalize_payload(webhook_payload)

    assert obs.provider_reference == "rfnd_test_789"
    assert obs.observation_type == "REFUND"
    assert obs.canonical_status == CanonicalStatus.SETTLED
    assert obs.observed_amount == 25000
    assert obs.correlation_keys.internal_ref == "rcpt_refund_1"
    assert obs.correlation_keys.provider_ref == "pay_test_123"
    assert ev.source_type == "WEBHOOK"


def test_reconciliation_with_adapted_observation():
    adapter = RazorpayPaymentAdapter()
    raw_payload = {
        "id": "pay_matched_123",
        "status": "captured",
        "amount": 15000,
        "currency": "INR",
    }
    obs, _ = adapter.normalize_payload(raw_payload)

    exp_match = Expectation(
        domain="PAYMENT",
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=15000,
        currency="INR",
        source_system="merchant_oms",
    )

    result_match = reconcile(exp_match, [obs])
    assert result_match.outcome == ReconciliationOutcome.MATCH

    exp_mismatch = Expectation(
        domain="PAYMENT",
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=20000,  # Amount discrepancy
        currency="INR",
        source_system="merchant_oms",
    )

    result_mismatch = reconcile(exp_mismatch, [obs])
    assert result_mismatch.outcome == ReconciliationOutcome.DISCREPANCY
