import httpx
from datetime import datetime, timezone
import uuid
import asyncio

from src.integrations.provider import ProviderMutationOutcome, ProviderQueryConfidence
from src.evidence.models import ProviderObservation, EntityType
from src.domain.refunds.models import Refund
from src.domain.actions.models import Action, ActionType
from .client import RazorpayClient
from .webhook import verify_signature

class RazorpayProviderAdapter:
    def __init__(self, client: RazorpayClient):
        self.client = client

    async def dispatch_refund(self, action: Action, refund: Refund) -> ProviderMutationOutcome:
        """
        Executes a refund on Razorpay and returns a strict ProviderMutationOutcome.
        """
        try:
            # We use both receipt AND the idempotency header as discussed in the architecture.
            razorpay_refund = await self.client.create_refund(
                payment_id=refund.provider_payment_id,
                amount=int(refund.amount * 100), # to paise
                receipt=refund.refund_intent_id,
                notes={
                    "incident_id": action.incident_id,
                    "idempotency_key": action.idempotency_key
                },
                idempotency_key=action.idempotency_key
            )
            
            # If successful, we consider it ACCEPTED_EXECUTED or ACCEPTED_PENDING
            if razorpay_refund.status == "processed":
                return ProviderMutationOutcome.ACCEPTED_EXECUTED
            return ProviderMutationOutcome.ACCEPTED_PENDING
            
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 400:
                # E.g. payment not captured, or amount exceeds refundable
                return ProviderMutationOutcome.EXPLICITLY_REJECTED
            if status_code == 409:
                return ProviderMutationOutcome.TRANSIENT_CONFLICT
            # 5xx are ambiguous
            if status_code >= 500:
                return ProviderMutationOutcome.AMBIGUOUS_OUTCOME
            return ProviderMutationOutcome.EXPLICITLY_REJECTED
            
        except (httpx.TimeoutException, httpx.NetworkError):
            return ProviderMutationOutcome.AMBIGUOUS_OUTCOME

    async def query_refund_status(self, payment_id: str, idempotency_key: str, receipt: str) -> ProviderQueryConfidence:
        """
        Queries Razorpay to authoritatively check if a refund with the given receipt executed.
        """
        try:
            # Fetch all refunds for the payment
            refunds = await self.client.get_payment_refunds(payment_id)
            
            # In-memory filter by receipt.
            for r in refunds:
                if r.receipt == receipt:
                    return ProviderQueryConfidence.AUTHORITATIVE_EXECUTED
                    
            # If we reach here, we successfully fetched refunds and none matched our receipt.
            return ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED
            
        except (httpx.TimeoutException, httpx.NetworkError):
            return ProviderQueryConfidence.QUERY_FAILED
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                return ProviderQueryConfidence.QUERY_FAILED
            # E.g. Payment not found
            return ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY
