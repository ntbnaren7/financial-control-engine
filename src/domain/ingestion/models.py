from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
import uuid


class PayloadProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


@dataclass
class IngestionPayload:
    """
    Immutable representation of an externally ingested raw payload.
    Provides durable persistence before any domain processing occurs.
    """
    provider: str
    event_type: str
    raw_payload: Dict[str, Any]
    payload_hash: str
    idempotency_key: str
    payload_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: PayloadProcessingStatus = PayloadProcessingStatus.PENDING
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
