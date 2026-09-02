from enum import Enum
from dataclasses import dataclass
from typing import Optional
from src.control.provenance import AuthorizationProvenance

class ActionDecision(str, Enum):
    ALLOW_REFUND = "ALLOW_REFUND"
    NO_ACTION = "NO_ACTION"
    ESCALATE = "ESCALATE"

@dataclass
class ControlDecision:
    decision: ActionDecision
    reason: str
    provenance: Optional[AuthorizationProvenance] = None

from src.state.models import ReconstructedState, KnowledgeState
from src.integrations.provider import ProviderQueryConfidence
from src.domain.refunds.models import Refund

def evaluate_refund_eligibility(
    reconstructed_state: ReconstructedState,
    provider_query_confidence: ProviderQueryConfidence,
    refund_intent: Refund,
    incident_id: str
) -> ControlDecision:
    """
    Control Plane: A deterministic function that independently evaluates
    refund eligibility for a specific refund intent.
    """
    def _reject(reason: str) -> ControlDecision:
        prov = AuthorizationProvenance(
            incident_id=incident_id,
            control_rule="REFUND_ELIGIBILITY",
            verified_facts={
                "knowledge_state": reconstructed_state.knowledge_state.value if reconstructed_state.knowledge_state else "UNKNOWN",
                "provider_query_confidence": provider_query_confidence.value
            },
            atomic_precondition="NONE",
            authorized=False,
            reason=reason
        )
        return ControlDecision(ActionDecision.NO_ACTION, reason, prov)

    if reconstructed_state.knowledge_state != KnowledgeState.VERIFIED:
        return _reject("Knowledge state is not VERIFIED. Epistemic uncertainty prohibits financial mutation.")

    if reconstructed_state.observed_financial_state is not None:
        return _reject("A concrete financial state already exists for this intent. Non-execution is not verified.")

    if provider_query_confidence != ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED:
        return _reject(f"Provider query confidence is {provider_query_confidence}, expected AUTHORITATIVE_NOT_EXECUTED.")

    # In a real implementation, you'd also check:
    # 1. refund_intent.amount <= payment.refundable_amount
    # 2. refund_intent.currency == payment.currency
    # 3. no_prior_action_succeeded_for_intent(refund_intent.refund_intent_id)

    reason = "All preconditions satisfied for CONTROLLED_REFUND."
    prov = AuthorizationProvenance(
        incident_id=incident_id,
        control_rule="REFUND_ELIGIBILITY",
        verified_facts={
            "knowledge_state": reconstructed_state.knowledge_state.value,
            "provider_query_confidence": provider_query_confidence.value
        },
        atomic_precondition="NONE",
        authorized=True,
        reason=reason
    )
    return ControlDecision(ActionDecision.ALLOW_REFUND, reason, prov)
