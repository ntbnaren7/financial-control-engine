from src.investigation.models import InvestigationProposal, HypothesisSelection, V0HypothesisType, EvidenceType, ConfidenceBand, InvestigationEligibility
from src.investigation.validator import validate_proposal_invariants
import pytest
from pydantic import ValidationError

def _create_valid_selections():
    return [
        HypothesisSelection(
            hypothesis_id=V0HypothesisType.EVIDENCE_INSUFFICIENT,
            rank=1, rationale="", confidence_band=ConfidenceBand.HIGH,
            supporting_evidence_ids=["EV-001"], contradicting_evidence_ids=[], missing_evidence_types=[]
        ),
        HypothesisSelection(
            hypothesis_id=V0HypothesisType.WEBHOOK_NOT_OBSERVED,
            rank=2, rationale="", confidence_band=ConfidenceBand.MEDIUM,
            supporting_evidence_ids=[], contradicting_evidence_ids=[], missing_evidence_types=[]
        ),
        HypothesisSelection(
            hypothesis_id=V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED,
            rank=3, rationale="", confidence_band=ConfidenceBand.LOW,
            supporting_evidence_ids=[], contradicting_evidence_ids=[], missing_evidence_types=[]
        ),
        HypothesisSelection(
            hypothesis_id=V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED,
            rank=4, rationale="", confidence_band=ConfidenceBand.LOW,
            supporting_evidence_ids=[], contradicting_evidence_ids=[], missing_evidence_types=[]
        ),
        HypothesisSelection(
            hypothesis_id=V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH,
            rank=5, rationale="", confidence_band=ConfidenceBand.LOW,
            supporting_evidence_ids=[], contradicting_evidence_ids=[], missing_evidence_types=[]
        )
    ]

def test_valid_proposal():
    proposal = InvestigationProposal(eligibility=InvestigationEligibility.ELIGIBLE, overall_confidence=ConfidenceBand.HIGH, selections=_create_valid_selections())
    result = validate_proposal_invariants(proposal, ["EV-001"])
    assert result.is_valid, f"Expected valid, got errors: {result.errors}"

def test_nonexistent_supporting_id():
    selections = _create_valid_selections()
    selections[0].supporting_evidence_ids = ["EV-999"]
    proposal = InvestigationProposal(eligibility=InvestigationEligibility.ELIGIBLE, overall_confidence=ConfidenceBand.HIGH, selections=selections)
    
    result = validate_proposal_invariants(proposal, ["EV-001"])
    assert not result.is_valid
    assert any("EV-999" in err for err in result.errors)

def test_duplicate_hypothesis():
    selections = _create_valid_selections()
    selections[1].hypothesis_id = V0HypothesisType.EVIDENCE_INSUFFICIENT
    proposal = InvestigationProposal(eligibility=InvestigationEligibility.ELIGIBLE, overall_confidence=ConfidenceBand.HIGH, selections=selections)
    
    result = validate_proposal_invariants(proposal, ["EV-001"])
    assert not result.is_valid
    assert any("Duplicate hypothesis ID" in err for err in result.errors)

def test_duplicate_rank():
    selections = _create_valid_selections()
    selections[1].rank = 1
    proposal = InvestigationProposal(eligibility=InvestigationEligibility.ELIGIBLE, overall_confidence=ConfidenceBand.HIGH, selections=selections)
    
    result = validate_proposal_invariants(proposal, ["EV-001"])
    assert not result.is_valid
    assert any("Duplicate rank" in err for err in result.errors)

def test_rank_outside_bounds():
    selections = _create_valid_selections()
    selections[0].rank = 6
    proposal = InvestigationProposal(eligibility=InvestigationEligibility.ELIGIBLE, overall_confidence=ConfidenceBand.HIGH, selections=selections)
    
    result = validate_proposal_invariants(proposal, ["EV-001"])
    assert not result.is_valid
    assert any("Invalid rank" in err for err in result.errors)

def test_same_evidence_supporting_and_contradicting():
    selections = _create_valid_selections()
    selections[0].supporting_evidence_ids = ["EV-001"]
    selections[0].contradicting_evidence_ids = ["EV-001"]
    proposal = InvestigationProposal(eligibility=InvestigationEligibility.ELIGIBLE, overall_confidence=ConfidenceBand.HIGH, selections=selections)
    
    result = validate_proposal_invariants(proposal, ["EV-001"])
    assert not result.is_valid
    assert any("cannot be both supporting and contradicting" in err for err in result.errors)

def test_duplicate_evidence_ids_in_list():
    selections = _create_valid_selections()
    selections[0].supporting_evidence_ids = ["EV-001", "EV-001"]
    proposal = InvestigationProposal(eligibility=InvestigationEligibility.ELIGIBLE, overall_confidence=ConfidenceBand.HIGH, selections=selections)
    
    result = validate_proposal_invariants(proposal, ["EV-001"])
    assert not result.is_valid
    assert any("Duplicate evidence IDs found" in err for err in result.errors)

def test_invalid_cardinality():
    selections = _create_valid_selections()
    selections.pop()
    with pytest.raises(ValidationError):
        InvestigationProposal(eligibility=InvestigationEligibility.ELIGIBLE, overall_confidence=ConfidenceBand.HIGH, selections=selections)
