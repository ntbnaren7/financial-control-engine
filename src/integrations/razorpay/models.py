from pydantic import BaseModel
from typing import Optional

class RazorpayOrder(BaseModel):
    id: str
    entity: str
    amount: int
    amount_paid: int
    amount_due: int
    currency: str
    receipt: Optional[str] = None
    status: str
    attempts: int
    created_at: int

class RazorpayPayment(BaseModel):
    id: str
    entity: str
    amount: int
    currency: str
    status: str
    order_id: str
    method: str
    amount_refunded: int
    refund_status: Optional[str] = None
    captured: bool
    description: Optional[str] = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    error_source: Optional[str] = None
    error_step: Optional[str] = None
    error_reason: Optional[str] = None
    created_at: int

class RazorpayRefund(BaseModel):
    id: str
    entity: str
    amount: int
    currency: str
    payment_id: str
    status: str
    receipt: Optional[str] = None
    notes: Optional[dict] = None
    created_at: int
    batch_id: Optional[str] = None
    speed_processed: Optional[str] = None
    speed_requested: Optional[str] = None

class RazorpayWebhookEvent(BaseModel):
    event: str
    contains: list[str]
    payload: dict
    created_at: int
    account_id: str
