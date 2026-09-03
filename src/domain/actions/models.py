from enum import Enum
from dataclasses import dataclass, field
import uuid
from datetime import datetime, timezone

def utcnow():
    return datetime.now(timezone.utc)

class ActionType(str, Enum):
    STATE_REPAIR = "STATE_REPAIR"
    EVENT_REPROCESS = "EVENT_REPROCESS"
    PROVIDER_STATUS_QUERY = "PROVIDER_STATUS_QUERY"
    CONTROLLED_REFUND = "CONTROLLED_REFUND"

class ActionStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

@dataclass
class Action:
    action_type: ActionType
    idempotency_key: str
    incident_id: str
    payload: dict = field(default_factory=dict)
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: ActionStatus = ActionStatus.PENDING
    created_at: datetime = field(default_factory=utcnow)
