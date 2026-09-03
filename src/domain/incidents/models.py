from enum import Enum
from typing import Optional, TYPE_CHECKING
from datetime import datetime, timezone
from dataclasses import dataclass, field, replace
import uuid

from src.reconciliation.models import DiscrepancyType

if TYPE_CHECKING:
    from src.reconciliation.models import ReconciliationResult

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
    
    # Phase A: Discrepancy details
    expectation_id: Optional[str] = None
    refund_intent_id: Optional[str] = None
    provider_payment_id: Optional[str] = None
    discrepancy_type: Optional[DiscrepancyType] = None
    discrepancy_instance_id: Optional[str] = None
    discrepancy_history: list[str] = field(default_factory=list)
    reconciliation_timestamp: Optional[datetime] = None
    reconstructed_state_ids: list[str] = field(default_factory=list)
    evidence_references: list[str] = field(default_factory=list)
    severity: str = "LOW"
    provenance: Optional[dict] = None

    # Monitoring metadata
    next_evaluation_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    monitoring_reason: Optional[str] = None
    query_count: int = 0

    def transition_to(self, new_state: IncidentState, reason: Optional[str] = None) -> "Incident":
        """Immutable transition to a new lifecycle state."""
        return replace(
            self, 
            lifecycle_state=new_state, 
            monitoring_reason=reason if reason is not None else self.monitoring_reason
        )

    def resolve(self, reconciliation_result: "ReconciliationResult", proving_observation_id: Optional[str] = None) -> "Incident":
        """
        Safely transition to RESOLVED if correlation holds.
        Raises ValueError if correlation constraints fail.
        """
        if reconciliation_result.intent_id != self.refund_intent_id:
            raise ValueError(f"Intent ID mismatch: {reconciliation_result.intent_id} != {self.refund_intent_id}")
        if self.expectation_id and reconciliation_result.expectation_id != self.expectation_id:
            raise ValueError(f"Expectation ID mismatch: {reconciliation_result.expectation_id} != {self.expectation_id}")
        if self.reconciliation_timestamp and reconciliation_result.reconciliation_timestamp < self.reconciliation_timestamp:
            raise ValueError("Stale reconciliation result")
        if proving_observation_id and proving_observation_id not in reconciliation_result.reconstructed_state_ids:
            raise ValueError("Proving observation ID missing from reconstructed state")
            
        return replace(self, lifecycle_state=IncidentState.RESOLVED)

    def escalate(self, reason: str) -> "EscalationArtifact":
        """Generates an EscalationArtifact."""
        return EscalationArtifact(
            incident_id=self.incident_id,
            reason=reason,
            evidence_references=self.evidence_references,
            provenance={"source": "incident_escalation", "original_discrepancy": self.discrepancy_type.value if self.discrepancy_type else None}
        )

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
