import httpx
from .config import settings
from .models import RazorpayOrder, RazorpayPayment

from typing import Optional, Any

class RazorpayClient:
    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._auth = (settings.key_id, settings.key_secret)
        if client:
            self._client = client
        else:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                auth=self._auth,
                timeout=10.0
            )

    async def close(self):
        await self._client.aclose()

    async def create_order(self, amount: int, currency: str, receipt: str) -> RazorpayOrder:
        payload = {
            "amount": amount,
            "currency": currency,
            "receipt": receipt
        }
        response = await self._client.post("/orders", json=payload)
        response.raise_for_status()
        return RazorpayOrder.model_validate(response.json())

    async def get_order(self, order_id: str) -> RazorpayOrder:
        response = await self._client.get(f"/orders/{order_id}")
        response.raise_for_status()
        return RazorpayOrder.model_validate(response.json())

    async def get_payment(self, payment_id: str) -> RazorpayPayment:
        response = await self._client.get(f"/payments/{payment_id}")
        response.raise_for_status()
        return RazorpayPayment.model_validate(response.json())

    async def create_refund(
        self, 
        payment_id: str, 
        amount: int, 
        receipt: str, 
        notes: Optional[dict[str, Any]] = None, 
        idempotency_key: Optional[str] = None
    ):
        from .models import RazorpayRefund
        payload: dict[str, Any] = {
            "amount": amount,
            "receipt": receipt,
        }
        if notes:
            payload["notes"] = notes

        headers = {}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
            
        response = await self._client.post(
            f"/payments/{payment_id}/refund", 
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return RazorpayRefund.model_validate(response.json())

    async def get_refund(self, refund_id: str):
        from .models import RazorpayRefund
        response = await self._client.get(f"/refunds/{refund_id}")
        response.raise_for_status()
        return RazorpayRefund.model_validate(response.json())

    async def get_payment_refunds(self, payment_id: str):
        from .models import RazorpayRefund
        response = await self._client.get(f"/payments/{payment_id}/refunds")
        response.raise_for_status()
        data = response.json()
        return [RazorpayRefund.model_validate(item) for item in data.get("items", [])]
