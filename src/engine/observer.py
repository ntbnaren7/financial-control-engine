from typing import Optional
from src.domain.core.models import Observation, CorrelationKeys
from src.engine.external_simulator import simulator
import uuid

class SimulatedObserver:
    def observe_merchant_order(self, order_id: str) -> Optional[Observation]:
        order = simulator.read_merchant_order(order_id)
        if not order:
            return None
        return Observation(
            provider="Merchant",
            provider_reference=order["id"],
            observation_type="OrderState",
            observed_state=order["status"],
            observed_amount=order["amount"],
            currency="INR",
            evidence_ids=[],
            correlation_keys=CorrelationKeys(internal_ref=order_id)
        )

    def observe_provider_payment(self, payment_id: str) -> Optional[Observation]:
        payment = simulator.read_provider_payment(payment_id)
        if not payment:
            return None
        return Observation(
            provider="Razorpay",
            provider_reference=payment["id"],
            observation_type="PaymentState",
            observed_state=payment["status"],
            observed_amount=payment["amount"],
            currency="INR",
            evidence_ids=[],
            correlation_keys=CorrelationKeys(provider_ref=payment_id, internal_ref=payment["order_id"])
        )
