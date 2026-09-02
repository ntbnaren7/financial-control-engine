import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any

class EntityType(str, Enum):
    PAYMENT = "PAYMENT"
    REFUND_INTENT = "REFUND_INTENT"

def utcnow():
    return datetime.now(timezone.utc)

@dataclass
class ProviderObservation:
    provider: str
    event_id: str
    entity_type: str
    entity_id: str
    event_type: str
    payload: Dict[str, Any]
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=utcnow)
