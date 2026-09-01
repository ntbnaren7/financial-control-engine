from enum import Enum
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

class DiscrepancyClassification(str, Enum):
    CAPTURED_PAYMENT_STALE_ORDER = "CAPTURED_PAYMENT_STALE_ORDER"
    CONSISTENT = "CONSISTENT"
    CAPTURED_PAYMENT_AMOUNT_MISMATCH = "CAPTURED_PAYMENT_AMOUNT_MISMATCH"
    CAPTURED_PAYMENT_CURRENCY_MISMATCH = "CAPTURED_PAYMENT_CURRENCY_MISMATCH"
    PAYMENT_ORDER_IDENTITY_UNKNOWN = "PAYMENT_ORDER_IDENTITY_UNKNOWN"
    PAYMENT_NOT_CAPTURED = "PAYMENT_NOT_CAPTURED"

@dataclass(frozen=True)
class ProviderPayment:
    payment_id: str
    order_id: str
    amount: int
    currency: str
    status: str
    captured: bool
    observed_at: datetime

@dataclass(frozen=True)
class MerchantOrderState:
    merchant_order_id: str
    razorpay_order_id: str
    expected_amount: int
    currency: str
    status: str

@dataclass(frozen=True)
class ReconciliationResult:
    classification: DiscrepancyClassification
    payment_identity_status: str
    amount_status: str
    currency_status: str
    provider_state: str
    merchant_state: str

@dataclass(frozen=True)
class VerifiedDiscrepancy:
    """
    Produced exclusively by the M3 deterministic engine.
    Represents a discrepancy that has been explicitly gated and verified 
    as eligible for an M4 causal investigation.
    """
    discrepancy_id: str
    payment_id: str
    order_id: str
    description: str
    provider_status: str
    merchant_status: str
    amount_match: bool
    currency_match: bool
    identity_verified: bool
