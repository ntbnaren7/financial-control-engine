from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
import uuid

class IncidentState(str, Enum):
    OPEN = "OPEN"
    MONITORING = "MONITORING"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

@dataclass
class Incident:
    incident_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    lifecycle_state: IncidentState = IncidentState.OPEN
    
    # Monitoring metadata
    next_evaluation_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    monitoring_reason: Optional[str] = None
    query_count: int = 0

@dataclass
class EscalationArtifact:
    """
    A structured escalation outcome when automated resolution cannot safely proceed.
    Escalation is a human-review outcome, NOT authorization for a financial action.
    """
    incident_id: str
    reason: str
    proposition_scope: Optional[str] = None
    evidence_references: list[str] = field(default_factory=list)
    knowledge_state: Optional[str] = None
    blocked_policy_conditions: list[str] = field(default_factory=list)
    recommended_action: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: Optional[dict] = None
