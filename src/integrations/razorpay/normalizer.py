from typing import Any, Dict
from src.domain.core.models import Observation, CorrelationKeys, CanonicalStatus
from datetime import datetime, timezone
import uuid

def _map_razorpay_refund_status(raw_status: str) -> CanonicalStatus:
    """Translate Razorpay refund status strings to the canonical FinOp vocabulary.

    This is the adapter boundary — provider-specific strings stop here.
    Downstream V2 code must never see raw Razorpay status strings.
    """
    normalized = (raw_status or "").upper()
    if normalized in ("PROCESSED", "CAPTURED"):
        return CanonicalStatus.SETTLED
    if normalized in ("PENDING", "CREATED", "AUTHORIZED"):
        return CanonicalStatus.PENDING
    if normalized in ("FAILED", "CANCELLED", "REFUNDED"):
        return CanonicalStatus.FAILED
    return CanonicalStatus.UNKNOWN

class RazorpayV2Normalizer:
    @staticmethod
    def normalize_refund(raw_payload: Dict[str, Any], evidence_id: str) -> Observation:
        """Translates a raw Razorpay refund payload into a canonical V2 Observation."""
        provider_reference = raw_payload.get("id", "UNKNOWN")
        payment_id = raw_payload.get("payment_id")
        receipt = raw_payload.get("receipt")
        raw_status = raw_payload.get("status", "UNKNOWN")
        amount = raw_payload.get("amount", 0)
        currency = raw_payload.get("currency", "INR")
        created_at_ts = raw_payload.get("created_at")

        observed_at = datetime.fromtimestamp(created_at_ts, tz=timezone.utc) if created_at_ts else datetime.now(timezone.utc)

        return Observation(
            provider="razorpay",
            provider_reference=provider_reference,
            observation_type="API_REFUND",
            canonical_status=_map_razorpay_refund_status(raw_status),
            observed_amount=amount,
            currency=currency,
            evidence_ids=[evidence_id],
            correlation_keys=CorrelationKeys(
                provider_ref=payment_id,
                internal_ref=receipt,
                provider="razorpay",
                domain="REFUND"
            ),
            observed_at=observed_at
        )
