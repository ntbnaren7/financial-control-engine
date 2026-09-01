from enum import Enum
from dataclasses import dataclass
from typing import List

from src.investigation.result import InvestigationResult, InvestigationStatus
from src.investigation.models import (
    V0HypothesisType,
    EvidenceItem,
    EvidenceType,
    ProviderPaymentContent,
    WebhookCapturedContent,
    MerchantProcessingContent,
    StateTransitionCoverageContent
)
from src.merchant.models import MerchantOrder
from src.reconciliation.models import VerifiedDiscrepancy

from src.control.provenance import AuthorizationProvenance

class ActionDecision(str, Enum):
    ALLOW_REPAIR = "ALLOW_REPAIR"
    NO_ACTION = "NO_ACTION"

@dataclass
class ControlDecision:
    decision: ActionDecision
    reason: str
    provenance: AuthorizationProvenance | None = None

def evaluate_repair_eligibility(
    discrepancy: VerifiedDiscrepancy,
    investigation_result: InvestigationResult,
    evidence: List[EvidenceItem],
    merchant_order: MerchantOrder
) -> ControlDecision:
    """
    Control Plane: A deterministic function that independently evaluates
    repair eligibility for the CAPTURED_PAYMENT_STALE_ORDER hero case.
    The LLM is treated as an advisory reasoning layer, not an authorization layer.
    """

    # 1. Base facts extracted regardless of decision
    incident_id = discrepancy.id if hasattr(discrepancy, 'id') else f"disc_{discrepancy.payment_id or discrepancy.order_id}"
    m3_desc = discrepancy.description
    
    top_sel = None
    if investigation_result.proposal and investigation_result.proposal.selections:
        top_sel = next((s for s in investigation_result.proposal.selections if s.rank == 1), None)
    
    m4_hypo = top_sel.hypothesis_id.value if top_sel else None
    sem_val = investigation_result.status.value
    
    # 2. Independent Evidence Verification facts
    payment_captured = False
    webhook_exists = False
    processing_processed = False
    transition_coverage_complete = False

    for ev in evidence:
        if ev.type == EvidenceType.E_PROVIDER_PAYMENT:
            if isinstance(ev.content, ProviderPaymentContent) and ev.content.captured:
                payment_captured = True
        elif ev.type == EvidenceType.E_WEBHOOK_CAPTURED:
            webhook_exists = True
        elif ev.type == EvidenceType.E_MERCHANT_PROCESSING:
            if isinstance(ev.content, MerchantProcessingContent) and ev.content.status == "PROCESSED":
                processing_processed = True
        elif ev.type == EvidenceType.E_STATE_TRANSITION_COVERAGE:
            if isinstance(ev.content, StateTransitionCoverageContent) and ev.content.coverage.value == "COMPLETE":
                transition_coverage_complete = True
                
    verified_facts = {
        "payment_captured": payment_captured,
        "webhook_exists": webhook_exists,
        "processing_processed": processing_processed,
        "transition_coverage_complete": transition_coverage_complete
    }
    
    def _reject(reason: str) -> ControlDecision:
        prov = AuthorizationProvenance(
            incident_id=incident_id,
            m3_discrepancy=m3_desc,
            m4_hypothesis=m4_hypo,
            semantic_validation=sem_val,
            verified_facts=verified_facts,
            control_rule="STRICT_ADMISSIBILITY",
            fresh_merchant_state=merchant_order.status,
            atomic_precondition="UPDATE WHERE status='UNPAID'",
            authorized=False,
            reason=reason
        )
        return ControlDecision(ActionDecision.NO_ACTION, reason, prov)

    # 3. Rule Evaluations
    if investigation_result.status != InvestigationStatus.ACCEPTED:
        return _reject("Investigation is not ACCEPTED (failed semantic validation or other error).")
    
    if not investigation_result.proposal:
        return _reject("Investigation produced no proposal.")

    if not top_sel:
        return _reject("Proposal missing rank-1 hypothesis.")

    if top_sel.hypothesis_id == V0HypothesisType.EVIDENCE_INSUFFICIENT:
        return _reject("AI concluded EVIDENCE_INSUFFICIENT (H5). Escalating.")

    if top_sel.hypothesis_id != V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED:
        return _reject(f"Hypothesis {top_sel.hypothesis_id.value} does not have an automated repair path.")

    if "CAPTURED_PAYMENT_STALE_ORDER" not in discrepancy.description:
        return _reject("M3 Discrepancy is not CAPTURED_PAYMENT_STALE_ORDER.")

    if merchant_order.status != "UNPAID":
        return _reject(f"Merchant order is in state '{merchant_order.status}', expected 'UNPAID'.")

    if not payment_captured:
        return _reject("Evidence does not confirm Provider Payment is CAPTURED.")
    if not webhook_exists:
        return _reject("Evidence does not confirm Webhook was received.")
    if not processing_processed:
        return _reject("Evidence does not confirm Processing was PROCESSED.")
    if not transition_coverage_complete:
        return _reject("Evidence does not establish COMPLETE state transition coverage.")

    # All preconditions satisfied.
    reason = "All preconditions satisfied for H3 automatic repair."
    prov = AuthorizationProvenance(
        incident_id=incident_id,
        m3_discrepancy=m3_desc,
        m4_hypothesis=m4_hypo,
        semantic_validation=sem_val,
        verified_facts=verified_facts,
        control_rule="STRICT_ADMISSIBILITY",
        fresh_merchant_state=merchant_order.status,
        atomic_precondition="UPDATE WHERE status='UNPAID'",
        authorized=True,
        reason=reason
    )
    return ControlDecision(ActionDecision.ALLOW_REPAIR, reason, prov)
