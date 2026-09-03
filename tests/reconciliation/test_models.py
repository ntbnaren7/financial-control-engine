from datetime import datetime, timezone
from decimal import Decimal
import pytest

from src.evidence.models import EntityType
from src.reconciliation.models import ExpectedRefund, FinancialExpectation


def test_expected_refund_valid_creation():
    now = datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc)
    exp = ExpectedRefund(
        refund_intent_id="ref_123",
        provider_payment_id="pay_abc",
        amount=Decimal("150.50"),
        currency="INR",
        created_at=now,
        sla_seconds=600,
        source_system="OMS",
        business_reason="Defective item",
        originating_trace_id="tr_999",
    )

    assert exp.intent_id == "ref_123"
    assert exp.expected_amount == Decimal("150.50")
    assert exp.entity_type == EntityType.REFUND_INTENT
    assert exp.currency == "INR"
    assert exp.reconciliation_deadline() == datetime(2026, 9, 3, 10, 10, 0, tzinfo=timezone.utc)
    assert isinstance(exp, FinancialExpectation)


def test_expected_refund_idempotency_key_deterministic():
    now = datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc)
    exp1 = ExpectedRefund(
        refund_intent_id="ref_fixed",
        provider_payment_id="pay_fixed",
        amount=Decimal("100.00"),
        currency="INR",
        created_at=now,
    )
    exp2 = ExpectedRefund(
        refund_intent_id="ref_fixed",
        provider_payment_id="pay_fixed",
        amount=Decimal("100.00"),
        currency="INR",
        created_at=now,
    )
    assert exp1.get_provider_idempotency_key() == exp2.get_provider_idempotency_key()


def test_expected_refund_invalid_amounts():
    now = datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="amount must be strictly positive"):
        ExpectedRefund(
            refund_intent_id="ref_1",
            provider_payment_id="pay_1",
            amount=Decimal("0"),
            currency="INR",
            created_at=now,
        )

    with pytest.raises(ValueError, match="amount must be strictly positive"):
        ExpectedRefund(
            refund_intent_id="ref_1",
            provider_payment_id="pay_1",
            amount=Decimal("-10.00"),
            currency="INR",
            created_at=now,
        )


def test_expected_refund_empty_identifiers():
    now = datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="refund_intent_id cannot be empty"):
        ExpectedRefund(
            refund_intent_id="",
            provider_payment_id="pay_1",
            amount=Decimal("10.00"),
            currency="INR",
            created_at=now,
        )

    with pytest.raises(ValueError, match="provider_payment_id cannot be empty"):
        ExpectedRefund(
            refund_intent_id="ref_1",
            provider_payment_id="",
            amount=Decimal("10.00"),
            currency="INR",
            created_at=now,
        )


def test_expected_refund_timezone_required():
    naive = datetime(2026, 9, 3, 10, 0, 0)
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        ExpectedRefund(
            refund_intent_id="ref_1",
            provider_payment_id="pay_1",
            amount=Decimal("10.00"),
            currency="INR",
            created_at=naive,
        )
