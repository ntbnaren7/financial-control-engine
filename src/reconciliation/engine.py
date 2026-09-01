from typing import Optional
from src.reconciliation.models import (
    ProviderPayment, 
    MerchantOrderState, 
    VerifiedDiscrepancy,
    DiscrepancyClassification,
    ReconciliationResult
)
from src.reconciliation.classifier import reconcile_payment_and_order

class M3Engine:
    """
    Deterministic gate for M4 investigations.
    Takes arbitrary raw reconciliation inputs and guarantees that only
    genuine, classified discrepancies are emitted as a VerifiedDiscrepancy.
    """
    
    def evaluate_reconciliation(
        self, 
        payment: ProviderPayment, 
        order: Optional[MerchantOrderState]
    ) -> Optional[VerifiedDiscrepancy]:
        
        result = reconcile_payment_and_order(payment, order)
        
        if result.classification == DiscrepancyClassification.CONSISTENT:
            return None
            
        discrepancy_id = f"disc_{payment.payment_id}"
        order_id = order.razorpay_order_id if order else payment.order_id
        
        description = f"M3 identified discrepancy: {result.classification.value}"
        
        return VerifiedDiscrepancy(
            discrepancy_id=discrepancy_id,
            payment_id=payment.payment_id,
            order_id=order_id,
            description=description,
            provider_status=result.provider_state,
            merchant_status=result.merchant_state,
            amount_match=(result.amount_status == "MATCH"),
            currency_match=(result.currency_status == "MATCH"),
            identity_verified=(result.payment_identity_status == "VERIFIED")
        )
