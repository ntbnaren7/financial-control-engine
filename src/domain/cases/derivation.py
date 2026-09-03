from typing import Optional
from decimal import Decimal

from src.reconciliation.models import ExpectedRefund
from src.domain.correlation.models import CorrelationContext
from src.evidence.models import ProviderObservation

def derive_expectation(context: CorrelationContext) -> Optional[ExpectedRefund]:
    """
    Derives the V1 ExpectedRefund from the internal Evidence intent.
    Returns None if there is no internal intent (e.g. ORPHANED scenario).
    """
    if not context.intent:
        return None
        
    payload = context.intent.payload
    return ExpectedRefund(
        expectation_id=f"exp_{context.intent.entity_id}",
        refund_intent_id=context.intent.entity_id,
        provider_payment_id=payload.get("provider_payment_id", "UNKNOWN"),
        amount=Decimal(str(payload.get("amount", "0"))),
        currency=payload.get("currency", "INR"),
        created_at=context.intent.timestamp
    )

def derive_observations(context: CorrelationContext) -> list[ProviderObservation]:
    """
    Derives V1 ProviderObservations from the correlated provider evidence.
    """
    obs_list = []
    
    # We only want to derive observations from records that successfully correlated,
    # OR that are explicitly UNMATCHED (orphans).
    correlated_evidence_ids = {
        r.provider_evidence.evidence_id 
        for r in context.results 
        if (r.is_correlated() or r.status.name == "UNMATCHED") and r.provider_evidence
    }
    
    for record in context.provider_records:
        if record.evidence_id not in correlated_evidence_ids:
            continue
            
        # Flatten payload for StateEngine
        flattened_payload = {}
        if record.source == "razorpay_webhook":
            entity = record.payload.get("payload", {}).get("refund", {}).get("entity", {})
            flattened_payload["status"] = entity.get("status")
            flattened_payload["provider_timestamp"] = entity.get("created_at")
        elif record.source == "razorpay_api":
            flattened_payload["status"] = record.payload.get("status")
            flattened_payload["query_confidence"] = record.payload.get("query_confidence")
            flattened_payload["provider_timestamp"] = record.payload.get("created_at")

        obs = ProviderObservation(
            provider="razorpay", # or derive from source
            event_id=record.evidence_id,
            entity_type="REFUND_INTENT", # V1 EntityType.REFUND_INTENT
            entity_id=context.intent.entity_id if context.intent else record.entity_id, # Fallback to raw entity_id for orphans
            event_type=record.evidence_type,
            payload=flattened_payload,
            created_at=record.timestamp
        )
        obs_list.append(obs)
    return obs_list
