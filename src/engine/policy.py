from typing import Optional
from decimal import Decimal
from src.domain.incidents.models import Incident, IncidentState
from src.reconciliation.models import DiscrepancyType
from src.domain.actions.models import Action, ActionType
import uuid

class ActionPolicyEngine:
    """
    Translates an established discrepancy into a deterministic authorized Action.
    """
    
    def evaluate(self, incident: Incident) -> Optional[Action]:
        if incident.lifecycle_state != IncidentState.ESCALATED:
            return None
            
        if incident.discrepancy_type == DiscrepancyType.ABSENT_EXECUTION:
            # The control decision: we expected a refund, but it is definitively not executed.
            # We authorize a controlled refund mutation.
            return Action(
                action_type=ActionType.CONTROLLED_REFUND,
                idempotency_key=f"refund_{incident.incident_id}",
                incident_id=incident.incident_id,
                payload={
                    "intent_id": incident.refund_intent_id,
                    "provider": "razorpay"
                }
            )
            
        return None
