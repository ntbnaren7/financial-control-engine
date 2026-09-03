import httpx
from .models import RazorpayOrder, RazorpayPayment
from src.config.settings import RazorpaySettings

from typing import Optional, Any

class ProviderNetworkError(Exception):
    """Raised on timeouts, connection errors, and 5xx server errors (retryable)."""
    pass

class ProviderClientError(Exception):
    """Raised on 4xx errors like validation, not found, unauth (deterministic)."""
    pass

class RazorpayClient:
    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self, settings: RazorpaySettings, client: Optional[httpx.AsyncClient] = None):
        # Unmask the secret only at the HTTP client boundary
        self._auth = (settings.key_id, settings.key_secret.get_secret_value())
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

    def _handle_response(self, response: httpx.Response):
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 or e.response.status_code == 429:
                raise ProviderNetworkError(f"Provider server error {e.response.status_code}: {e.response.text}")
            else:
                raise ProviderClientError(f"Provider client error {e.response.status_code}: {e.response.text}")
        return response.json()

    async def _safe_request(self, method: str, url: str, **kwargs) -> Any:
        try:
            response = await self._client.request(method, url, **kwargs)
            return self._handle_response(response)
        except httpx.RequestError as e:
            raise ProviderNetworkError(f"Network error communicating with provider: {str(e)}")

    async def create_order(self, amount: int, currency: str, receipt: str) -> RazorpayOrder:
        payload = {
            "amount": amount,
            "currency": currency,
            "receipt": receipt
        }
        data = await self._safe_request("POST", "/orders", json=payload)
        return RazorpayOrder.model_validate(data)

    async def get_order(self, order_id: str) -> RazorpayOrder:
        data = await self._safe_request("GET", f"/orders/{order_id}")
        return RazorpayOrder.model_validate(data)

    async def get_payment(self, payment_id: str) -> RazorpayPayment:
        data = await self._safe_request("GET", f"/payments/{payment_id}")
        return RazorpayPayment.model_validate(data)

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
            
        data = await self._safe_request(
            "POST",
            f"/payments/{payment_id}/refund", 
            json=payload,
            headers=headers
        )
        return RazorpayRefund.model_validate(data)

    async def get_refund(self, refund_id: str):
        from .models import RazorpayRefund
        data = await self._safe_request("GET", f"/refunds/{refund_id}")
        return RazorpayRefund.model_validate(data)

    async def get_payment_refunds(self, payment_id: str):
        from .models import RazorpayRefund
        data = await self._safe_request("GET", f"/payments/{payment_id}/refunds")
        return [RazorpayRefund.model_validate(item) for item in data.get("items", [])]
