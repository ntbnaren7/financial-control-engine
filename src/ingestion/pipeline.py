import uuid
from typing import Any, Dict
from datetime import datetime, timezone
from decimal import Decimal

from src.reconciliation.models import ExpectedRefund
from src.evidence.models import ProviderObservation
from .models import IngestionResult, IngestionStatus

def parse_iso8601(timestamp_str: str) -> datetime:
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        raise ValueError(f"Invalid ISO8601 timestamp: {timestamp_str}") from e

class ExpectationIngester:
    @staticmethod
    def ingest(payload: Dict[str, Any]) -> IngestionResult:
        try:
            # Minimal required fields for ExpectedRefund
            required_keys = ["refund_intent_id", "provider_payment_id", "amount", "currency", "created_at"]
            for key in required_keys:
                if key not in payload:
                    return IngestionResult(
                        status=IngestionStatus.SCHEMA_ERROR,
                        error_message=f"Missing required field: {key}"
                    )
            
            created_at = parse_iso8601(payload["created_at"])
            
            domain_object = ExpectedRefund(
                refund_intent_id=str(payload["refund_intent_id"]),
                provider_payment_id=str(payload["provider_payment_id"]),
                amount=Decimal(str(payload["amount"])),
                currency=str(payload["currency"]).strip().upper(),
                created_at=created_at,
                sla_seconds=int(payload.get("sla_seconds", 3600)),
                source_system=str(payload.get("source_system", "OMS")),
                business_reason=str(payload.get("business_reason", ""))
            )
            return IngestionResult(status=IngestionStatus.SUCCESS, domain_object=domain_object)
        except Exception as e:
            return IngestionResult(status=IngestionStatus.MALFORMED_PAYLOAD, error_message=str(e))

class ObservationIngester:
    @staticmethod
    def ingest(payload: Dict[str, Any]) -> IngestionResult:
        try:
            required_keys = ["provider", "event_id", "entity_type", "entity_id", "event_type", "payload", "created_at"]
            for key in required_keys:
                if key not in payload:
                    return IngestionResult(
                        status=IngestionStatus.SCHEMA_ERROR,
                        error_message=f"Missing required field: {key}"
                    )
            
            created_at = parse_iso8601(payload["created_at"])
            
            payload_copy = dict(payload["payload"])
            
            # Map raw provider status or pre-annotated synthetic fields to the standard V1 fields 
            # (status or query_confidence) that StateEngine parses.
            raw_status = (payload_copy.get("status") or "").lower()
            if raw_status == "processed":
                payload_copy["status"] = "REFUNDED"
            elif raw_status in ("failed", "cancelled"):
                payload_copy["status"] = "FAILED"
            elif raw_status == "not_found":
                payload_copy["query_confidence"] = "AUTHORITATIVE_NOT_EXECUTED"
            else:
                fs = payload_copy.get("financial_state")
                ks = payload_copy.get("knowledge_state")
                ex = payload_copy.get("execution_state")
                if ks == "VERIFIED" and fs:
                    payload_copy["status"] = fs
                elif ks == "VERIFIED" and ex == "NOT_EXECUTED" and not fs:
                    payload_copy["query_confidence"] = "AUTHORITATIVE_NOT_EXECUTED"

            domain_object = ProviderObservation(
                provider=str(payload["provider"]),
                event_id=str(payload["event_id"]),
                entity_type=str(payload["entity_type"]),
                entity_id=str(payload["entity_id"]),
                event_type=str(payload["event_type"]),
                payload=payload_copy, 
                id=uuid.UUID(payload.get("id")) if payload.get("id") else uuid.uuid4(),
                created_at=created_at
            )
            return IngestionResult(status=IngestionStatus.SUCCESS, domain_object=domain_object)
        except Exception as e:
            return IngestionResult(status=IngestionStatus.MALFORMED_PAYLOAD, error_message=str(e))
