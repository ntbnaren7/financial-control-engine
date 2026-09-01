from typing import Optional
from decimal import Decimal
from dataclasses import dataclass, field
import uuid
import hashlib

@dataclass
class Refund:
    provider_payment_id: str
    amount: Decimal
    currency: str
    refund_intent_id: str
    business_reason: str = ""
    refund_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def create_new(cls, provider_payment_id: str, amount: Decimal, currency: str, business_reason: str) -> "Refund":
        """
        Convenience constructor for new intents.
        The generated refund_intent_id must be persisted by the caller.
        """
        return cls(
            provider_payment_id=provider_payment_id,
            amount=amount,
            currency=currency,
            refund_intent_id=str(uuid.uuid4()),
            business_reason=business_reason
        )

    def get_provider_idempotency_key(self) -> str:
        """
        Derives the provider-facing idempotency key strictly from the stable refund_intent_id.
        """
        key_content = f"{self.provider_payment_id}_REFUND_{self.refund_intent_id}"
        return hashlib.sha256(key_content.encode('utf-8')).hexdigest()
