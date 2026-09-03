import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import uuid

from src.domain.core.models import (
    CanonicalStatus,
    CorrelationKeys,
    Evidence,
    FinancialEvent,
    Observation,
)
from src.engine.adapters.base_adapter import DomainAdapter


def map_razorpay_payment_status(status: Optional[str]) -> CanonicalStatus:
    """Translate raw Razorpay payment status strings to the canonical FinOp vocabulary."""
    s = (status or "").lower().strip()
    if s in ("captured", "settled", "processed"):
        return CanonicalStatus.SETTLED
    elif s in ("authorized", "created", "pending"):
        return CanonicalStatus.PENDING
    elif s in ("failed", "cancelled", "refunded"):
        return CanonicalStatus.FAILED
    return CanonicalStatus.UNKNOWN


class RazorpayPaymentAdapter(DomainAdapter):
    """Normalizes raw Razorpay payment and refund payloads into canonical V2 Observation and Evidence."""

    def normalize_payload(
        self,
        raw_payload: Dict[str, Any],
        headers: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Observation, Evidence]:
        # Razorpay webhooks wrap entities in payload.payment.entity or payload.refund.entity
        # Direct API responses provide the entity at root.
        entity = raw_payload
        event_type = raw_payload.get("event", "api_response")
        
        if "payload" in raw_payload and isinstance(raw_payload["payload"], dict):
            payload_section = raw_payload["payload"]
            if "payment" in payload_section and "entity" in payload_section["payment"]:
                entity = payload_section["payment"]["entity"]
                event_type = raw_payload.get("event", "payment.captured")
            elif "refund" in payload_section and "entity" in payload_section["refund"]:
                entity = payload_section["refund"]["entity"]
                event_type = raw_payload.get("event", "refund.processed")

        provider_ref = entity.get("id", "UNKNOWN")
        payment_id = entity.get("payment_id") or (provider_ref if "pay_" in provider_ref else None)
        order_id = entity.get("order_id")
        receipt = entity.get("receipt")
        
        raw_status = entity.get("status", "UNKNOWN")
        canonical_status = map_razorpay_payment_status(raw_status)
        amount = int(entity.get("amount", 0))
        currency = entity.get("currency", "INR")
        
        created_at_ts = entity.get("created_at")
        observed_at = (
            datetime.fromtimestamp(created_at_ts, tz=timezone.utc)
            if created_at_ts
            else datetime.now(timezone.utc)
        )

        # 1. Produce immutable audit Evidence
        serialized = json.dumps(raw_payload, sort_keys=True, default=str).encode("utf-8")
        payload_hash = hashlib.sha256(serialized).hexdigest()
        evidence_id = str(uuid.uuid4())

        evidence = Evidence(
            source="razorpay",
            source_reference=provider_ref,
            payload_hash=payload_hash,
            raw_payload_ref=f"inline:{payload_hash}",
            observed_at=observed_at,
            source_type="WEBHOOK" if "event" in raw_payload else "API_POLL",
            evidence_id=evidence_id,
        )

        # 2. Produce canonical Observation
        observation_type = "REFUND" if "rfnd_" in provider_ref or "refund" in event_type else "PAYMENT"
        
        correlation_keys = CorrelationKeys(
            internal_ref=receipt,
            provider_ref=payment_id or provider_ref,
            provider="razorpay",
            domain=observation_type,
            observation_type=observation_type,
        )

        observation = Observation(
            provider="razorpay",
            provider_reference=provider_ref,
            observation_type=observation_type,
            canonical_status=canonical_status,
            observed_amount=amount,
            currency=currency,
            evidence_ids=[evidence.evidence_id],
            correlation_keys=correlation_keys,
            observed_at=observed_at,
        )

        return observation, evidence
