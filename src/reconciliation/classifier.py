from .models import (
    ProviderPayment,
    MerchantOrderState,
    ReconciliationResult,
    DiscrepancyClassification
)

def reconcile_payment_and_order(
    payment: ProviderPayment,
    order: MerchantOrderState | None
) -> ReconciliationResult:
    """
    Pure deterministic function to compare a ProviderPayment and MerchantOrderState.
    Returns a deterministic ReconciliationResult classification.
    """
    # 1. Identity Check
    if not order or payment.order_id != order.razorpay_order_id:
        return ReconciliationResult(
            classification=DiscrepancyClassification.PAYMENT_ORDER_IDENTITY_UNKNOWN,
            payment_identity_status="UNKNOWN",
            amount_status="UNKNOWN",
            currency_status="UNKNOWN",
            provider_state=payment.status,
            merchant_state="UNKNOWN" if not order else order.status
        )
    
    # At this point, identity is verified.
    
    # Validate merchant status early to fail safely on unknown states
    if order.status not in ("UNPAID", "PAID"):
        raise ValueError(f"Invalid merchant order status: {order.status}. Expected UNPAID or PAID.")

    # 2. Provider State Check
    if payment.status != "captured" or not payment.captured:
        return ReconciliationResult(
            classification=DiscrepancyClassification.PAYMENT_NOT_CAPTURED,
            payment_identity_status="VERIFIED",
            amount_status="MATCH" if payment.amount == order.expected_amount else "MISMATCH",
            currency_status="MATCH" if payment.currency == order.currency else "MISMATCH",
            provider_state=payment.status,
            merchant_state=order.status
        )
    
    # 3. Currency Check
    if payment.currency != order.currency:
        return ReconciliationResult(
            classification=DiscrepancyClassification.CAPTURED_PAYMENT_CURRENCY_MISMATCH,
            payment_identity_status="VERIFIED",
            amount_status="MATCH" if payment.amount == order.expected_amount else "MISMATCH",
            currency_status="MISMATCH",
            provider_state=payment.status,
            merchant_state=order.status
        )

    # 4. Amount Check
    if payment.amount != order.expected_amount:
        return ReconciliationResult(
            classification=DiscrepancyClassification.CAPTURED_PAYMENT_AMOUNT_MISMATCH,
            payment_identity_status="VERIFIED",
            amount_status="MISMATCH",
            currency_status="MATCH",
            provider_state=payment.status,
            merchant_state=order.status
        )

    # 5. Merchant State Check
    if order.status == "UNPAID":
        return ReconciliationResult(
            classification=DiscrepancyClassification.CAPTURED_PAYMENT_STALE_ORDER,
            payment_identity_status="VERIFIED",
            amount_status="MATCH",
            currency_status="MATCH",
            provider_state=payment.status,
            merchant_state=order.status
        )
    else:  # order.status == "PAID"
        return ReconciliationResult(
            classification=DiscrepancyClassification.CONSISTENT,
            payment_identity_status="VERIFIED",
            amount_status="MATCH",
            currency_status="MATCH",
            provider_state=payment.status,
            merchant_state=order.status
        )
