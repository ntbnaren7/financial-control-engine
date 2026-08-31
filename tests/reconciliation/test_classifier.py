import pytest
from datetime import datetime, timezone
from reconciliation.models import (
    ProviderPayment,
    MerchantOrderState,
    DiscrepancyClassification
)
from reconciliation.classifier import reconcile_payment_and_order

def create_payment(**kwargs) -> ProviderPayment:
    defaults = {
        "payment_id": "pay_123",
        "order_id": "razor_order_123",
        "amount": 50000,
        "currency": "INR",
        "status": "captured",
        "captured": True,
        "observed_at": datetime.now(timezone.utc)
    }
    defaults.update(kwargs)
    return ProviderPayment(**defaults)

def create_order(**kwargs) -> MerchantOrderState:
    defaults = {
        "merchant_order_id": "merch_ord_123",
        "razorpay_order_id": "razor_order_123",
        "expected_amount": 50000,
        "currency": "INR",
        "status": "UNPAID"
    }
    defaults.update(kwargs)
    return MerchantOrderState(**defaults)

def test_captured_payment_stale_order():
    payment = create_payment(status="captured", captured=True, amount=50000, currency="INR")
    order = create_order(status="UNPAID", expected_amount=50000, currency="INR")
    result = reconcile_payment_and_order(payment, order)
    assert result.classification == DiscrepancyClassification.CAPTURED_PAYMENT_STALE_ORDER

def test_consistent():
    payment = create_payment(status="captured", captured=True, amount=50000, currency="INR")
    order = create_order(status="PAID", expected_amount=50000, currency="INR")
    result = reconcile_payment_and_order(payment, order)
    assert result.classification == DiscrepancyClassification.CONSISTENT

def test_captured_payment_amount_mismatch():
    payment = create_payment(status="captured", captured=True, amount=40000, currency="INR")
    order = create_order(status="UNPAID", expected_amount=50000, currency="INR")
    result = reconcile_payment_and_order(payment, order)
    assert result.classification == DiscrepancyClassification.CAPTURED_PAYMENT_AMOUNT_MISMATCH

def test_captured_payment_currency_mismatch():
    payment = create_payment(status="captured", captured=True, amount=50000, currency="USD")
    order = create_order(status="UNPAID", expected_amount=50000, currency="INR")
    result = reconcile_payment_and_order(payment, order)
    assert result.classification == DiscrepancyClassification.CAPTURED_PAYMENT_CURRENCY_MISMATCH

def test_payment_order_identity_unknown_none():
    payment = create_payment()
    result = reconcile_payment_and_order(payment, None)
    assert result.classification == DiscrepancyClassification.PAYMENT_ORDER_IDENTITY_UNKNOWN

def test_payment_order_identity_unknown_mismatch():
    payment = create_payment(order_id="razor_order_123")
    order = create_order(razorpay_order_id="razor_order_456")
    result = reconcile_payment_and_order(payment, order)
    assert result.classification == DiscrepancyClassification.PAYMENT_ORDER_IDENTITY_UNKNOWN

def test_payment_not_captured_failed():
    payment = create_payment(status="failed", captured=False)
    order = create_order(status="UNPAID")
    result = reconcile_payment_and_order(payment, order)
    assert result.classification == DiscrepancyClassification.PAYMENT_NOT_CAPTURED

def test_payment_not_captured_authorized():
    payment = create_payment(status="authorized", captured=False)
    order = create_order(status="UNPAID")
    result = reconcile_payment_and_order(payment, order)
    assert result.classification == DiscrepancyClassification.PAYMENT_NOT_CAPTURED

def test_fail_safely_unknown_status():
    payment = create_payment(status="captured", captured=True)
    order = create_order(status="REFUNDED")
    with pytest.raises(ValueError, match="Invalid merchant order status"):
        reconcile_payment_and_order(payment, order)
