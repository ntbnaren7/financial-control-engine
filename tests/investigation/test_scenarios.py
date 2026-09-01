import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.investigation.models import (
    V0HypothesisType,
    EvidenceType,
    EvidenceCoverage,
    EvidenceItem,
    WebhookCoverageContent,
    WebhookCapturedContent,
    ProcessingCoverageContent,
    MerchantProcessingContent,
    MerchantStateTransitionContent,
    StateTransitionCoverageContent,
    MerchantOrderStateContent,
    ProviderPaymentContent,
    InvestigationProposal,
    HypothesisSelection,
    ConfidenceBand,
    InvestigationEligibility,
)
from src.investigation.semantic import validate_semantic_admissibility
from src.investigation.validator import validate_proposal_invariants

def create_test_proposal(rank_1: V0HypothesisType) -> InvestigationProposal:
    selections = [
        HypothesisSelection(
            hypothesis_id=rank_1,
            rank=1,
            rationale="Test hypothesis ranking",
            confidence_band=ConfidenceBand.HIGH,
            supporting_evidence_ids=[]
        )
    ]
    rank = 2
    for h in V0HypothesisType:
        if h != rank_1:
            selections.append(
                HypothesisSelection(
                    hypothesis_id=h,
                    rank=rank,
                    rationale="Lower ranked option",
                    confidence_band=ConfidenceBand.LOW,
                    supporting_evidence_ids=[]
                )
            )
            rank += 1
            
    return InvestigationProposal(
        eligibility=InvestigationEligibility.ELIGIBLE,
        overall_confidence=ConfidenceBand.HIGH,
        selections=selections
    )

def test_scenario_01_webhook_dropped_safety():
    """SC-01: When webhook is absent and coverage is COMPLETE, WEBHOOK_NOT_OBSERVED is admissible."""
    proposal = create_test_proposal(V0HypothesisType.WEBHOOK_NOT_OBSERVED)
    evidence = [
        EvidenceItem(
            id="EV-WHCOV-01",
            type=EvidenceType.E_WEBHOOK_COVERAGE,
            content=WebhookCoverageContent(coverage=EvidenceCoverage.COMPLETE, webhook_count=0)
        )
    ]
    sem_res = validate_semantic_admissibility(proposal, evidence)
    assert sem_res.is_admissible
    
    inv_res = validate_proposal_invariants(proposal, [ev.id for ev in evidence])
    assert inv_res.is_valid

def test_scenario_02_ingested_not_processed_safety():
    """SC-02: Webhook present + processing count 0 under COMPLETE coverage."""
    proposal = create_test_proposal(V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED)
    evidence = [
        EvidenceItem(
            id="EV-WH-01",
            type=EvidenceType.E_WEBHOOK_CAPTURED,
            content=WebhookCapturedContent(present=True, event_id="wh_1")
        ),
        EvidenceItem(
            id="EV-PC-01",
            type=EvidenceType.E_PROCESSING_COVERAGE,
            content=ProcessingCoverageContent(coverage=EvidenceCoverage.COMPLETE, processing_count=0)
        )
    ]
    sem_res = validate_semantic_admissibility(proposal, evidence)
    assert sem_res.is_admissible

def test_scenario_03_processed_state_not_updated_safety():
    """SC-03: Webhook present + processed, but state transition count is 0."""
    proposal = create_test_proposal(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
    evidence = [
        EvidenceItem(
            id="EV-WH-01",
            type=EvidenceType.E_WEBHOOK_CAPTURED,
            content=WebhookCapturedContent(present=True, event_id="wh_1")
        ),
        EvidenceItem(
            id="EV-PROC-01",
            type=EvidenceType.E_MERCHANT_PROCESSING,
            content=MerchantProcessingContent(event_id="proc_1", status="PROCESSED")
        ),
        EvidenceItem(
            id="EV-PC-01",
            type=EvidenceType.E_PROCESSING_COVERAGE,
            content=ProcessingCoverageContent(coverage=EvidenceCoverage.COMPLETE, processing_count=1)
        ),
        EvidenceItem(
            id="EV-STCOV-01",
            type=EvidenceType.E_STATE_TRANSITION_COVERAGE,
            content=StateTransitionCoverageContent(coverage=EvidenceCoverage.COMPLETE, transition_count=0)
        )
    ]
    sem_res = validate_semantic_admissibility(proposal, evidence)
    assert sem_res.is_admissible

def test_scenario_07_hard_negative_rejection():
    """SC-07: Proposing WEBHOOK_NOT_OBSERVED when webhook is present MUST be rejected by semantic gate."""
    proposal = create_test_proposal(V0HypothesisType.WEBHOOK_NOT_OBSERVED)
    evidence = [
        EvidenceItem(
            id="EV-WH-01",
            type=EvidenceType.E_WEBHOOK_CAPTURED,
            content=WebhookCapturedContent(present=True, event_id="wh_1")
        )
    ]
    sem_res = validate_semantic_admissibility(proposal, evidence)
    assert not sem_res.is_admissible
    assert len(sem_res.errors) > 0
    assert "WEBHOOK_NOT_OBSERVED is contradicted" in sem_res.errors[0]

def test_scenario_processed_state_hard_negative_rejection():
    """Proposing WEBHOOK_PROCESSED_STATE_NOT_UPDATED when processing count is 0 under COMPLETE coverage MUST be rejected."""
    proposal = create_test_proposal(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
    evidence = [
        EvidenceItem(
            id="EV-PC-01",
            type=EvidenceType.E_PROCESSING_COVERAGE,
            content=ProcessingCoverageContent(coverage=EvidenceCoverage.COMPLETE, processing_count=0)
        )
    ]
    sem_res = validate_semantic_admissibility(proposal, evidence)
    assert not sem_res.is_admissible
    assert len(sem_res.errors) > 0
    assert "WEBHOOK_PROCESSED_STATE_NOT_UPDATED is contradicted" in sem_res.errors[0]
