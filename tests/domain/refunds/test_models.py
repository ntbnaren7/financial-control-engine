from decimal import Decimal
from src.domain.refunds.models import Refund

def test_intent_collision_scenario():
    """
    Scenario A: Two refunds with the same payment, amount, and currency 
    but different legitimate business intents must produce different refund_intent_ids 
    and different provider idempotency keys.
    """
    payment_id = "pay_abc123"
    amount = Decimal("5000.00")
    currency = "INR"

    # Business decision 1: Refund for damaged item
    refund_intent_1 = Refund.create_new(
        provider_payment_id=payment_id,
        amount=amount,
        currency=currency,
        business_reason="Refund for damaged item"
    )

    # Business decision 2: Refund for missing item (same order, same amount)
    refund_intent_2 = Refund.create_new(
        provider_payment_id=payment_id,
        amount=amount,
        currency=currency,
        business_reason="Refund for missing item"
    )

    # Must have different intent IDs
    assert refund_intent_1.refund_intent_id != refund_intent_2.refund_intent_id

    # Must produce different provider idempotency keys (both are executable independently)
    key_1 = refund_intent_1.get_provider_idempotency_key()
    key_2 = refund_intent_2.get_provider_idempotency_key()
    
    assert key_1 != key_2

def test_intent_stability_scenario():
    """
    Scenario B: Two executions of the *same* refund intent must produce the same 
    refund_intent_id and same provider idempotency key.
    (Simulating a retry or re-loading the intent from DB)
    """
    payment_id = "pay_abc123"
    amount = Decimal("5000.00")
    currency = "INR"
    
    # Original creation of the intent
    original_refund = Refund.create_new(
        provider_payment_id=payment_id,
        amount=amount,
        currency=currency,
        business_reason="Test original"
    )

    # Worker crashes, new worker loads the exact same intent from persistence
    retried_refund = Refund(
        provider_payment_id=original_refund.provider_payment_id,
        amount=original_refund.amount,
        currency=original_refund.currency,
        refund_intent_id=original_refund.refund_intent_id,
        refund_id=original_refund.refund_id
    )

    # Must have the exact same intent ID
    assert original_refund.refund_intent_id == retried_refund.refund_intent_id

    # Must produce the exact same provider idempotency key (preventing duplicate execution)
    key_original = original_refund.get_provider_idempotency_key()
    key_retried = retried_refund.get_provider_idempotency_key()
    
    assert key_original == key_retried
