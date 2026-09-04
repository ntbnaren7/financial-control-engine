from typing import Optional
from src.domain.core.models import Observation, CorrelationKeys, CanonicalStatus
from src.engine.external_simulator import simulator
from src.integrations.razorpay.provider import RazorpayProvider
from src.integrations.razorpay.client import ProviderClientError
import uuid

class SimulatedObserver:
    def __init__(self, razorpay_provider: Optional[RazorpayProvider] = None):
        self.razorpay_provider = razorpay_provider

    async def observe_merchant_order(self, order_id: str) -> Optional[Observation]:
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

    async def observe_provider_payment(self, payment_id: str) -> Optional[Observation]:
        if not self.razorpay_provider:
            return None
            
        try:
            payment = await self.razorpay_provider.get_payment(payment_id)
        except ProviderClientError:
            return None
            
        raw_status = payment.status
        if raw_status == "captured":
            status = CanonicalStatus.SETTLED
        elif raw_status == "refunded":
            status = CanonicalStatus.REFUNDED
        elif raw_status == "failed":
            status = CanonicalStatus.FAILED
        else:
            status = CanonicalStatus.UNKNOWN
            
        return Observation(
            provider="Razorpay",
            provider_reference=payment.id,
            observation_type="PAYMENT",
            canonical_status=status,
            observed_amount=payment.amount,
            currency="INR",
            evidence_ids=[],
            correlation_keys=CorrelationKeys(provider_ref=payment.id, internal_ref=payment.order_id)
        )

    async def observe_provider_refund(self, refund_id: str) -> Optional[Observation]:
        if not self.razorpay_provider:
            return None
            
        try:
            refund = await self.razorpay_provider.get_refund(refund_id)
        except ProviderClientError:
            return None
        
        status = CanonicalStatus.REFUNDED if refund.status == "processed" else CanonicalStatus.UNKNOWN
        
        return Observation(
            provider="Razorpay",
            provider_reference=refund.id,
            observation_type="REFUND",
            canonical_status=status,
            observed_amount=refund.amount,
            currency="INR",
            evidence_ids=[],
            correlation_keys=CorrelationKeys(provider_ref=refund.id, internal_ref=refund.payment_id)
        )
