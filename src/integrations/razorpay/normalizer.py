from typing import Any, Dict
from src.domain.core.models import Observation, CorrelationKeys
from datetime import datetime, timezone
import uuid

class RazorpayV2Normalizer:
    @staticmethod
    def normalize_refund(raw_payload: Dict[str, Any], evidence_id: str) -> Observation:
        """Translates a raw Razorpay refund payload into a canonical V2 Observation."""
        provider_reference = raw_payload.get("id", "UNKNOWN")
        payment_id = raw_payload.get("payment_id")
        receipt = raw_payload.get("receipt")
        status = raw_payload.get("status", "UNKNOWN").upper()
        amount = raw_payload.get("amount", 0)
        currency = raw_payload.get("currency", "INR")
        created_at_ts = raw_payload.get("created_at")

        observed_at = datetime.fromtimestamp(created_at_ts, tz=timezone.utc) if created_at_ts else datetime.now(timezone.utc)

        return Observation(
            provider="razorpay",
            provider_reference=provider_reference,
            observation_type="API_REFUND",
            observed_state=status,
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
