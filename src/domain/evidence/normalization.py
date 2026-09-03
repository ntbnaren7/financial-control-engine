from typing import Any, Dict, Protocol
from datetime import datetime, timezone
import uuid

from .models import Evidence

class EvidenceNormalizer(Protocol):
    """
    Protocol for normalizing raw payloads into the Evidence schema.
    """
    def normalize(self, raw_payload: Dict[str, Any], provenance: Dict[str, Any]) -> Evidence:
        ...

class InternalRefundIntentNormalizer:
    def normalize(self, raw_payload: Dict[str, Any], provenance: Dict[str, Any]) -> Evidence:
        """
        Normalizes an internal refund intent (from OMS or similar).
        """
        return Evidence(
            evidence_id=str(uuid.uuid4()),
            source="internal_oms",
            entity_id=raw_payload["refund_intent_id"],
            timestamp=datetime.fromisoformat(raw_payload["created_at"]) if "created_at" in raw_payload else datetime.now(timezone.utc),
            evidence_type="REFUND_INTENT",
            payload=raw_payload,
            provenance=provenance
        )

class RazorpayWebhookNormalizer:
    def normalize(self, raw_payload: Dict[str, Any], provenance: Dict[str, Any]) -> Evidence:
        """
        Normalizes a Razorpay webhook event.
        """
        event_type = raw_payload.get("event", "UNKNOWN")
        entity = raw_payload.get("payload", {}).get("refund", {}).get("entity", {})
        
        entity_id = entity.get("id", "UNKNOWN")
        created_at_ts = entity.get("created_at")
        
        if created_at_ts:
            timestamp = datetime.fromtimestamp(created_at_ts, tz=timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)
            
        # Map Razorpay event types to standard evidence types if needed, or keep raw.
        # Let's keep it close to the raw for now.
        evidence_type = f"RAZORPAY_{event_type.upper()}"
        
        return Evidence(
            evidence_id=str(uuid.uuid4()),
            source="razorpay_webhook",
            entity_id=entity_id,
            timestamp=timestamp,
            evidence_type=evidence_type,
            payload=raw_payload,
            provenance=provenance
        )

class RazorpayApiNormalizer:
    def normalize(self, raw_payload: Dict[str, Any], provenance: Dict[str, Any]) -> Evidence:
        """
        Normalizes a Razorpay API response (e.g., from fetch_refunds).
        """
        entity_id = raw_payload.get("id", "UNKNOWN")
        created_at_ts = raw_payload.get("created_at")
        
        if created_at_ts:
            timestamp = datetime.fromtimestamp(created_at_ts, tz=timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)
            
        status = raw_payload.get("status", "UNKNOWN").upper()
        evidence_type = f"RAZORPAY_API_REFUND_{status}"
        
        return Evidence(
            evidence_id=str(uuid.uuid4()),
            source="razorpay_api",
            entity_id=entity_id,
            timestamp=timestamp,
            evidence_type=evidence_type,
            payload=raw_payload,
            provenance=provenance
        )
