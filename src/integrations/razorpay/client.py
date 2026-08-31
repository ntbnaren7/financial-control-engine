import httpx
from .config import settings
from .models import RazorpayOrder, RazorpayPayment

class RazorpayClient:
    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self):
        self._auth = (settings.key_id, settings.key_secret)
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
