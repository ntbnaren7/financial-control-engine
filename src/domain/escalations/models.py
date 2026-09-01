from dataclasses import dataclass, field
import uuid
from datetime import datetime, timezone
from typing import List

def utcnow():
    return datetime.now(timezone.utc)

@dataclass
class Escalation:
    incident_id: str
    entity_type: str
    entity_id: str
    escalation_reason: str
    detected_discrepancy: str
    system_hypothesis: str
    confidence_level: str
    missing_evidence: List[str]
    operator_action_required: str
    escalation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=utcnow)
