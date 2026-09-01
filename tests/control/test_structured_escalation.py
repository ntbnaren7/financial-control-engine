import pytest
from src.control.policy import evaluate_repair_eligibility, ActionDecision
from src.investigation.result import InvestigationResult, InvestigationStatus
from src.investigation.models import (
    InvestigationProposal,
    HypothesisSelection,
    V0HypothesisType,
    EvidenceItem,
    EvidenceType,
    ProviderPaymentContent,
    WebhookCapturedContent,
    MerchantProcessingContent,
    StateTransitionCoverageContent,
    InvestigationEligibility,
    ConfidenceBand
)
from src.merchant.models import MerchantOrder
from src.reconciliation.models import VerifiedDiscrepancy

def test_escalation_artifact_produced_for_insufficient_evidence():
    """
    Prove that genuine human-intervention-required case -> structured escalation artifact.
    Prove that ordinary NO_ACTION does not automatically become escalation.
    Prove escalation does not authorize a financial action.
    """
    discrepancy = VerifiedDiscrepancy(
        discrepancy_id="disc_123",
        payment_id="pay_123",
        order_id="ord_123",
        description="CAPTURED_PAYMENT_STALE_ORDER",
        provider_status="captured",
        merchant_status="UNPAID",
        amount_match=True,
        currency_match=True,
        identity_verified=True
    )
    
    # 1. Genuine Escalation Case (EVIDENCE_INSUFFICIENT)
    result_escalate = InvestigationResult(
        status=InvestigationStatus.ACCEPTED,
        proposal=InvestigationProposal(
            eligibility=InvestigationEligibility.ELIGIBLE,
            overall_confidence=ConfidenceBand.HIGH,
            selections=[
                    HypothesisSelection(
                        rank=1,
                        hypothesis_id=V0HypothesisType.EVIDENCE_INSUFFICIENT,
                        confidence=0.9,
                        reasoning="Missing webhook data completely",
                        rationale="Not enough evidence",
                        confidence_band="HIGH"
                    ),
                    HypothesisSelection(rank=2, hypothesis_id=V0HypothesisType.WEBHOOK_NOT_OBSERVED, rationale="", confidence_band=ConfidenceBand.LOW),
                    HypothesisSelection(rank=3, hypothesis_id=V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED, rationale="", confidence_band=ConfidenceBand.LOW),
                    HypothesisSelection(rank=4, hypothesis_id=V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED, rationale="", confidence_band=ConfidenceBand.LOW),
                    HypothesisSelection(rank=5, hypothesis_id=V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH, rationale="", confidence_band=ConfidenceBand.LOW),          ]
        )
    )
    
    order = MerchantOrder(
        merchant_order_id="m_ord_123",
        razorpay_order_id="ord_123",
        status="UNPAID",
        expected_amount=100,
        currency="INR"
    )
    decision = evaluate_repair_eligibility(discrepancy, result_escalate, [], order)
    
    assert decision.decision == ActionDecision.ESCALATE
    assert decision.escalation_artifact is not None
    assert decision.escalation_artifact.incident_id == "disc_pay_123"
    assert decision.escalation_artifact.proposition_scope == "pay_123"
    assert decision.provenance is not None
    assert decision.provenance.authorized is False
    
    # 2. Ordinary NO_ACTION Case (e.g. wrong state)
    result_no_action = InvestigationResult(
        status=InvestigationStatus.ACCEPTED,
        proposal=InvestigationProposal(
            eligibility=InvestigationEligibility.ELIGIBLE,
            overall_confidence=ConfidenceBand.HIGH,
            selections=[
                    HypothesisSelection(
                        rank=1,
                        hypothesis_id=V0HypothesisType.WEBHOOK_NOT_OBSERVED,
                        confidence=0.9,
                        reasoning="No webhook received",
                        rationale="Clear evidence of missing webhook",
                        confidence_band="HIGH"
                    ),
                    HypothesisSelection(rank=2, hypothesis_id=V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED, rationale="", confidence_band=ConfidenceBand.LOW),
                    HypothesisSelection(rank=3, hypothesis_id=V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED, rationale="", confidence_band=ConfidenceBand.LOW),
                    HypothesisSelection(rank=4, hypothesis_id=V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH, rationale="", confidence_band=ConfidenceBand.LOW),
                    HypothesisSelection(rank=5, hypothesis_id=V0HypothesisType.EVIDENCE_INSUFFICIENT, rationale="", confidence_band=ConfidenceBand.LOW),          ]
        )
    )
    
    # Order is PAID, so it's not eligible for repair -> ordinary NO_ACTION
    order_paid = MerchantOrder(
        merchant_order_id="m_ord_123_paid",
        razorpay_order_id="ord_123",
        status="PAID",
        expected_amount=100,
        currency="INR"
    )
    decision_no_action = evaluate_repair_eligibility(discrepancy, result_no_action, [], order_paid)
    
    assert decision_no_action.decision == ActionDecision.NO_ACTION
    assert decision_no_action.escalation_artifact is None
    assert decision_no_action.provenance is not None
    assert decision_no_action.provenance.authorized is False
