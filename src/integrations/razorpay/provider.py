from typing import Protocol, Optional, Any, List
from src.integrations.razorpay.models import RazorpayOrder, RazorpayPayment, RazorpayRefund

class RazorpayProvider(Protocol):
    """
    Core interface for interacting with Razorpay.
    Implementations include the live RazorpayClient and a deterministic MockRazorpayProvider for local/demo testing.
    """

    async def create_order(self, amount: int, currency: str, receipt: str) -> RazorpayOrder:
        ...

    async def get_order(self, order_id: str) -> RazorpayOrder:
        ...

    async def get_payment(self, payment_id: str) -> RazorpayPayment:
        ...

    async def create_refund(
        self, 
        payment_id: str, 
        amount: int, 
        receipt: str, 
        notes: Optional[dict[str, Any]] = None, 
        idempotency_key: Optional[str] = None
    ) -> RazorpayRefund:
        ...

    async def get_refund(self, refund_id: str) -> RazorpayRefund:
        ...

    async def get_payment_refunds(self, payment_id: str) -> List[RazorpayRefund]:
        ...
