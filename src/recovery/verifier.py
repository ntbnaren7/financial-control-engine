from enum import Enum
from dataclasses import dataclass
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.merchant.models import MerchantOrder
from src.evidence.models import ProviderObservation

class VerificationStatus(str, Enum):
    RESOLVED = "RESOLVED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    ERROR = "ERROR"

@dataclass
class VerificationResult:
    status: VerificationStatus
    message: str

async def verify_resolution(
    session: AsyncSession,
    merchant_order_id_pk: str,
    payment_id: str
) -> VerificationResult:
    """
    Independent Verification: Re-queries the database with a fresh read post-action
    to confirm the discrepancy is resolved (Provider == CAPTURED, Merchant == PAID).
    """
    try:
        # 1. Fresh read of the MerchantOrder
        result = await session.execute(
            select(MerchantOrder).where(MerchantOrder.id == merchant_order_id_pk)
        )
        merchant_order = result.scalar_one_or_none()
        
        if not merchant_order:
            return VerificationResult(VerificationStatus.ERROR, f"MerchantOrder {merchant_order_id_pk} not found during verification.")
        
        if merchant_order.status != "PAID":
            return VerificationResult(
                VerificationStatus.VERIFICATION_FAILED, 
                f"MerchantOrder {merchant_order_id_pk} status is '{merchant_order.status}', expected 'PAID'."
            )
            
        # 2. Fresh read of the ProviderObservation for the payment
        # Assuming event_type == 'payment' and payload contains the status.
        result = await session.execute(
            select(ProviderObservation)
            .where(
                # In this simplified spike, we're finding the most recent payment observation for this payment_id
                ProviderObservation.payload['payment_id'].as_string() == payment_id,
                ProviderObservation.event_type == 'payment'
            )
            .order_by(ProviderObservation.created_at.desc())
            .limit(1)
        )
        payment_obs = result.scalar_one_or_none()
        
        if not payment_obs:
            return VerificationResult(VerificationStatus.ERROR, f"ProviderObservation for payment {payment_id} not found during verification.")
            
        payment_status = payment_obs.payload.get("status")
        if payment_status != "captured":
            return VerificationResult(
                VerificationStatus.VERIFICATION_FAILED,
                f"Provider payment {payment_id} status is '{payment_status}', expected 'captured'."
            )
            
        return VerificationResult(VerificationStatus.RESOLVED, "Verification successful. Discrepancy resolved.")
        
    except Exception as e:
        return VerificationResult(VerificationStatus.ERROR, str(e))
