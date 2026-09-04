"""
RealRazorpayProvider
====================
Concrete adapter that satisfies the RazorpayProvider protocol by delegating to
the existing RazorpayClient HTTP wrapper.

Responsibilities:
- Thin translation layer: domain protocol <-> HTTP client.
- All retry/timeout/error-classification logic remains in RazorpayClient.
- This class NEVER hardcodes credentials. Settings are injected at construction.

Usage:
    from src.integrations.razorpay.real_provider import RealRazorpayProvider
    from src.config.settings import FCESettings

    settings = FCESettings.load()
    provider = RealRazorpayProvider(settings.razorpay)

Notes:
- ProviderClientError and ProviderNetworkError propagate unchanged from
  RazorpayClient -- callers (Verifier, Actuator, Observer) rely on those
  semantics to distinguish retryable vs. deterministic failures.
- The adapter is intentionally a pass-through so that switching between
  RealRazorpayProvider and MockRazorpayProvider has zero effect on
  downstream FCE logic.
"""

from typing import Optional, Any, List

from src.config.settings import RazorpaySettings
from src.integrations.razorpay.client import RazorpayClient
from src.integrations.razorpay.models import (
    RazorpayOrder,
    RazorpayPayment,
    RazorpayRefund,
)


class RealRazorpayProvider:
    """
    Production Razorpay provider.

    Wraps RazorpayClient and satisfies the RazorpayProvider structural protocol.
    Use this in all non-mock environments (production, staging, Test Mode validation).
    """

    def __init__(self, settings: RazorpaySettings) -> None:
        self._client = RazorpayClient(settings=settings)

    async def close(self) -> None:
        """Release the underlying httpx connection pool."""
        await self._client.close()

    # ------------------------------------------------------------------
    # RazorpayProvider protocol implementation
    # ------------------------------------------------------------------

    async def create_order(self, amount: int, currency: str, receipt: str) -> RazorpayOrder:
        return await self._client.create_order(amount, currency, receipt)

    async def get_order(self, order_id: str) -> RazorpayOrder:
        return await self._client.get_order(order_id)

    async def get_payment(self, payment_id: str) -> RazorpayPayment:
        return await self._client.get_payment(payment_id)

    async def create_refund(
        self,
        payment_id: str,
        amount: int,
        receipt: str,
        notes: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> RazorpayRefund:
        return await self._client.create_refund(
            payment_id=payment_id,
            amount=amount,
            receipt=receipt,
            notes=notes,
            idempotency_key=idempotency_key,
        )

    async def get_refund(self, refund_id: str) -> RazorpayRefund:
        return await self._client.get_refund(refund_id)

    async def get_payment_refunds(self, payment_id: str) -> List[RazorpayRefund]:
        return await self._client.get_payment_refunds(payment_id)
