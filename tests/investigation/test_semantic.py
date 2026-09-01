from src.investigation.models import (
    InvestigationProposal,
    InvestigationEligibility,
    ConfidenceBand,
    HypothesisSelection,
    V0HypothesisType,
    EvidenceCoverage,
    EvidenceItem,
    EvidenceType,
    WebhookCapturedContent,
    ProcessingCoverageContent
)
from src.investigation.semantic import validate_semantic_admissibility

def create_mock_proposal(rank_1_hypothesis: V0HypothesisType) -> InvestigationProposal:
    selections = [
        HypothesisSelection(
            hypothesis_id=rank_1_hypothesis,
            rank=1,
            rationale="Test",
            confidence_band=ConfidenceBand.HIGH
        )
    ]
    # Fill remaining to make it valid length if needed by other validators, though semantic only checks rank 1
    rank = 2
    for h in V0HypothesisType:
        if h != rank_1_hypothesis:
            selections.append(
                HypothesisSelection(
                    hypothesis_id=h,
                    rank=rank,
                    rationale="Test",
                    confidence_band=ConfidenceBand.LOW
                )
            )
            rank += 1
            
    return InvestigationProposal(
        eligibility=InvestigationEligibility.ELIGIBLE,
        overall_confidence=ConfidenceBand.HIGH,
        selections=selections
    )

def test_webhook_not_observed_rejected_when_present():
    proposal = create_mock_proposal(V0HypothesisType.WEBHOOK_NOT_OBSERVED)
    evidence = [
        EvidenceItem(
            id="EV-1", 
            type=EvidenceType.E_WEBHOOK_CAPTURED, 
            content=WebhookCapturedContent(present=True)
        )
    ]
    
    result = validate_semantic_admissibility(proposal, evidence)
    assert not result.is_admissible
    assert len(result.errors) > 0
    assert "WEBHOOK_NOT_OBSERVED is contradicted" in result.errors[0]

def test_webhook_not_observed_accepted_when_absent():
    proposal = create_mock_proposal(V0HypothesisType.WEBHOOK_NOT_OBSERVED)
    evidence = [
        EvidenceItem(
            id="EV-1", 
            type=EvidenceType.E_WEBHOOK_CAPTURED, 
            content=WebhookCapturedContent(present=False)
        )
    ]
    
    result = validate_semantic_admissibility(proposal, evidence)
    assert result.is_admissible

def test_webhook_not_observed_accepted_when_evidence_missing():
    proposal = create_mock_proposal(V0HypothesisType.WEBHOOK_NOT_OBSERVED)
    # No webhook evidence provided
    evidence = []
    
    result = validate_semantic_admissibility(proposal, evidence)
    assert result.is_admissible

def test_processed_state_not_updated_rejected_when_processing_count_zero():
    proposal = create_mock_proposal(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
    evidence = [
        EvidenceItem(
            id="EV-1", 
            type=EvidenceType.E_PROCESSING_COVERAGE, 
            content=ProcessingCoverageContent(coverage=EvidenceCoverage.COMPLETE, processing_count=0)
        )
    ]
    
    result = validate_semantic_admissibility(proposal, evidence)
    assert not result.is_admissible
    assert len(result.errors) > 0
    assert "WEBHOOK_PROCESSED_STATE_NOT_UPDATED is contradicted" in result.errors[0]

def test_processed_state_not_updated_accepted_when_processing_count_non_zero():
    proposal = create_mock_proposal(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
    evidence = [
        EvidenceItem(
            id="EV-1", 
            type=EvidenceType.E_PROCESSING_COVERAGE, 
            content=ProcessingCoverageContent(coverage=EvidenceCoverage.COMPLETE, processing_count=1)
        )
    ]
    
    result = validate_semantic_admissibility(proposal, evidence)
    assert result.is_admissible

def test_processed_state_not_updated_accepted_when_coverage_missing():
    proposal = create_mock_proposal(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
    evidence = []
    
    result = validate_semantic_admissibility(proposal, evidence)
    assert result.is_admissible

def test_webhook_observed_not_processed_accepted_when_webhook_present():
    proposal = create_mock_proposal(V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED)
    evidence = [
        EvidenceItem(
            id="EV-1", 
            type=EvidenceType.E_WEBHOOK_CAPTURED, 
            content=WebhookCapturedContent(present=True)
        )
    ]
    
    result = validate_semantic_admissibility(proposal, evidence)
    assert result.is_admissible

def test_processed_state_not_updated_accepted_when_processing_coverage_unknown():
    proposal = create_mock_proposal(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
    evidence = [
        EvidenceItem(
            id="EV-1", 
            type=EvidenceType.E_PROCESSING_COVERAGE, 
            content=ProcessingCoverageContent(coverage=EvidenceCoverage.UNKNOWN, processing_count=0)
        )
    ]
    
    result = validate_semantic_admissibility(proposal, evidence)
    assert result.is_admissible
