import hashlib
import hmac
import json
import os
from typing import Any, Dict
from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from src.domain.ingestion.models import IngestionPayload
from src.storage.postgres_ingestion import MemoryIngestionRepository

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Shared/configurable repository instance
_ingestion_repo = MemoryIngestionRepository()
DEFAULT_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_key")


def set_ingestion_repository(repo):
    global _ingestion_repo
    _ingestion_repo = repo


def get_ingestion_repository():
    return _ingestion_repo


def verify_razorpay_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Verifies Razorpay HMAC-SHA256 signature against request body."""
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/razorpay", status_code=status.HTTP_202_ACCEPTED)
async def razorpay_webhook(
    request: Request,
    response: Response,
    x_razorpay_signature: str = Header(None),
):
    raw_body = await request.body()

    # 1. Verify HMAC Signature
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", DEFAULT_WEBHOOK_SECRET)
    if not x_razorpay_signature or not verify_razorpay_signature(raw_body, x_razorpay_signature, webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing webhook signature",
        )

    # 2. Parse payload
    try:
        payload_data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload")

    # 3. Compute hash and idempotency key
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    event_type = payload_data.get("event", "unknown")
    
    # Razorpay webhooks can have an event id or entity id
    entity_id = "unknown"
    if "payload" in payload_data and isinstance(payload_data["payload"], dict):
        for section in ("payment", "refund", "order"):
            if section in payload_data["payload"] and "entity" in payload_data["payload"][section]:
                entity_id = payload_data["payload"][section]["entity"].get("id", entity_id)
                break
                
    idempotency_key = payload_data.get("event_id") or f"{event_type}:{entity_id}:{payload_hash[:16]}"

    ingestion_payload = IngestionPayload(
        provider="razorpay",
        event_type=event_type,
        raw_payload=payload_data,
        payload_hash=payload_hash,
        idempotency_key=idempotency_key,
    )

    # 4. Persist to durable ingestion substrate
    repo = get_ingestion_repository()
    saved, is_new = repo.save_payload(ingestion_payload)

    if not is_new:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "DUPLICATE",
            "payload_id": saved.payload_id,
            "message": "Payload already ingested previously",
        }

    return {
        "status": "ACCEPTED",
        "payload_id": saved.payload_id,
        "event_type": event_type,
    }
