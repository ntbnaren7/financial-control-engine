from typing import Optional
from src.domain.core.models import Observation, CorrelationKeys, CanonicalStatus
from src.engine.external_simulator import simulator
import uuid

class SimulatedObserver:
    def observe_merchant_order(self, order_id: str) -> Optional[Observation]:
        order = simulator.read_merchant_order(order_id)
        if not order:
            return None
        status = CanonicalStatus.SETTLED if order.get("status") == "PAID" else CanonicalStatus.PENDING
        return Observation(
            provider="Merchant",
            provider_reference=order["id"],
            observation_type="OrderState",
            canonical_status=status,
            observed_amount=order["amount"],
            currency="INR",
            evidence_ids=[],
            correlation_keys=CorrelationKeys(internal_ref=order_id)
        )

    def observe_provider_payment(self, payment_id: str) -> Optional[Observation]:
        payment = simulator.read_provider_payment(payment_id)
        if not payment:
            return None
        raw_status = payment.get("status")
        if raw_status == "CAPTURED":
            status = CanonicalStatus.SETTLED
        elif raw_status == "REFUNDED":
            status = CanonicalStatus.REFUNDED
        else:
            status = CanonicalStatus.UNKNOWN
            
        return Observation(
            provider="Razorpay",
            provider_reference=payment["id"],
            observation_type="PAYMENT",
            canonical_status=status,
            observed_amount=payment["amount"],
            currency="INR",
            evidence_ids=[],
            correlation_keys=CorrelationKeys(provider_ref=payment_id, internal_ref=payment.get("order_id"))
        )

    def observe_provider_refund(self, refund_id: str) -> Optional[Observation]:
        # For the simulator, refunds are just state mutations on the payment record.
        # In a real integration, this would query a /refunds endpoint.
        payment = simulator.read_provider_payment(refund_id)
        if not payment:
            return None
        
        status = CanonicalStatus.REFUNDED if payment.get("status") == "REFUNDED" else CanonicalStatus.UNKNOWN
        
        return Observation(
            provider="Razorpay",
            provider_reference=payment["id"],
            observation_type="REFUND",
            canonical_status=status,
            observed_amount=payment["amount"],
            currency="INR",
            evidence_ids=[],
            correlation_keys=CorrelationKeys(provider_ref=refund_id, internal_ref=payment.get("order_id"))
        )

