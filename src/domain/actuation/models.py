import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any
import json

class ActuationState(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    TIMEOUT_UNKNOWN = "TIMEOUT_UNKNOWN"
    CONVERGED = "CONVERGED"
    ESCALATED = "ESCALATED"

@dataclass
class ActuationRecord:
    execution_identity: str
    intent_action: str
    target_id: str
    mutation_parameters_canonical: str
    idempotency_key: str
    provider: str
    state: ActuationState = ActuationState.PENDING
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get_mutation_payload(self) -> Dict[str, Any]:
        """Returns the deserialized canonical mutation payload."""
        return json.loads(self.mutation_parameters_canonical)
