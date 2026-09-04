import uuid
from typing import Optional, Any, List, Dict

from src.integrations.razorpay.provider import RazorpayProvider
from src.integrations.razorpay.models import RazorpayOrder, RazorpayPayment, RazorpayRefund
from src.integrations.razorpay.client import ProviderClientError

class MockRazorpayProvider(RazorpayProvider):
    def __init__(self):
        # We store mutable mock state here
        self._payments: Dict[str, dict] = {}
        self._refunds: Dict[str, List[dict]] = {}

    def seed_payment(self, payment_id: str, order_id: str, amount: int = 2000, status: str = "captured"):
        """Pre-seed a payment with a deterministic order_id so the normalizer's internal_ref
        matches the rest of the observation set (important for reconciliation grouping)."""
        self._payments[payment_id] = {
            "id": payment_id,
            "entity": "payment",
            "amount": amount,
            "currency": "INR",
            "status": status,
            "order_id": order_id,
            "error_code": None,
            "error_description": None,
            "created_at": 1672531200,
            "method": "upi",
            "amount_refunded": 0,
            "captured": status == "captured",
        }

    def _get_or_create_payment_state(self, payment_id: str) -> dict:
        if payment_id not in self._payments:
            # Initialize default state based on prefix
            is_scenario_a = payment_id.startswith("pay_scenario_a")
            state = {
                "id": payment_id,
                "entity": "payment",
                "amount": 2000 if is_scenario_a else 4500,
                "currency": "INR",
                "status": "captured" if is_scenario_a else "failed",
                "order_id": f"order_{uuid.uuid4().hex[:8]}",
                "error_code": None if is_scenario_a else "BAD_REQUEST_ERROR",
                "error_description": None if is_scenario_a else "Payment failed",
                "created_at": 1672531200,
                "method": "upi",
                "amount_refunded": 0,
                "captured": True if is_scenario_a else False
            }
            self._payments[payment_id] = state
        return self._payments[payment_id]

    async def create_order(self, amount: int, currency: str, receipt: str) -> RazorpayOrder:
        return RazorpayOrder(
            id=f"order_{uuid.uuid4().hex[:10]}",
            entity="order",
            amount=amount,
            amount_paid=0,
            amount_due=amount,
            currency=currency,
            receipt=receipt,
            status="created",
            attempts=0,
            created_at=1672531200
        )

    async def get_order(self, order_id: str) -> RazorpayOrder:
        return RazorpayOrder(
            id=order_id,
            entity="order",
            amount=4500,
            amount_paid=0,
            amount_due=4500,
            currency="INR",
            receipt="receipt_mock",
            status="created",
            attempts=1,
            created_at=1672531200
        )

    async def get_payment(self, payment_id: str) -> RazorpayPayment:
        if payment_id.startswith("pay_scenario_b_"):
            raise ProviderClientError("404 Not Found: The requested payment does not exist")
            
        state = self._get_or_create_payment_state(payment_id)
        return RazorpayPayment.model_validate(state)

    async def create_refund(
        self, 
        payment_id: str, 
        amount: int, 
        receipt: str, 
        notes: Optional[dict[str, Any]] = None, 
        idempotency_key: Optional[str] = None
    ) -> RazorpayRefund:
        state = self._get_or_create_payment_state(payment_id)
        
        # If this is scenario D, the refund "succeeds" but the payment state is stubbornly NOT updated to refunded
        if not payment_id.startswith("pay_scenario_d_"):
            state["status"] = "refunded"
            
        refund_id = f"rfnd_{uuid.uuid4().hex[:10]}"
        refund_data = {
            "id": refund_id,
            "entity": "refund",
            "amount": amount,
            "receipt": receipt,
            "currency": "INR",
            "payment_id": payment_id,
            "status": "processed",
            "created_at": 1672531200
        }
        
        if payment_id not in self._refunds:
            self._refunds[payment_id] = []
        self._refunds[payment_id].append(refund_data)
        
        return RazorpayRefund.model_validate(refund_data)

    async def get_refund(self, refund_id: str) -> RazorpayRefund:
        # Just mock a successful refund
        return RazorpayRefund(
            id=refund_id,
            entity="refund",
            amount=4500,
            receipt="mock_receipt",
            currency="INR",
            payment_id="pay_mock",
            status="processed",
            created_at=1672531200
        )

    async def get_payment_refunds(self, payment_id: str) -> List[RazorpayRefund]:
        if payment_id.startswith("pay_scenario_b_"):
            raise ProviderClientError("404 Not Found")
            
        refunds = self._refunds.get(payment_id, [])
        return [RazorpayRefund.model_validate(r) for r in refunds]
