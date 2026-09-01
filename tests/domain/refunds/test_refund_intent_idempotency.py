import pytest
from decimal import Decimal
from src.domain.refunds.models import Refund

def test_refund_intent_identity():
    # Case A: Same persisted intent -> same ID after reload
    original_intent = Refund.create_new(
        provider_payment_id="pay_1",
        amount=Decimal("100.00"),
        currency="USD",
        business_reason="Customer return"
    )
    
    # Simulate saving to DB and reloading
    reloaded_intent = Refund(
        provider_payment_id=original_intent.provider_payment_id,
        amount=original_intent.amount,
        currency=original_intent.currency,
        refund_intent_id=original_intent.refund_intent_id,
        business_reason=original_intent.business_reason
    )
    
    assert reloaded_intent.refund_intent_id == original_intent.refund_intent_id
    assert reloaded_intent.get_provider_idempotency_key() == original_intent.get_provider_idempotency_key()
    
    # Case E (part 1): Retry/reconstruction uses the same ID
    # Same ID means same idempotency key for provider
    assert original_intent.get_provider_idempotency_key() == reloaded_intent.get_provider_idempotency_key()
    
    # Case B & C: Distinct financial intents get distinct IDs even if payment is the same
    different_amount = Refund.create_new(
        provider_payment_id="pay_1",
        amount=Decimal("50.00"),
        currency="USD",
        business_reason="Customer return"
    )
    assert different_amount.refund_intent_id != original_intent.refund_intent_id
    
    different_reason = Refund.create_new(
        provider_payment_id="pay_1",
        amount=Decimal("100.00"),
        currency="USD",
        business_reason="Duplicate charge"
    )
    assert different_reason.refund_intent_id != original_intent.refund_intent_id
    
    # Case D: Different payment gets different ID
    different_payment = Refund.create_new(
        provider_payment_id="pay_2",
        amount=Decimal("100.00"),
        currency="USD",
        business_reason="Customer return"
    )
    assert different_payment.refund_intent_id != original_intent.refund_intent_id
    
    # Case E (part 2): Two independent creations of logically identical intent must not collide
    # because intent ID is created once by the system and then reused.
    second_independent_creation = Refund.create_new(
        provider_payment_id="pay_1",
        amount=Decimal("100.00"),
        currency="USD",
        business_reason="Customer return"
    )
    assert second_independent_creation.refund_intent_id != original_intent.refund_intent_id
