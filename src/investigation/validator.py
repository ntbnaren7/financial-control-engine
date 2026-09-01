from typing import List
from src.investigation.models import InvestigationProposal, V0HypothesisType

class ValidationResult:
    def __init__(self):
        self.is_valid = True
        self.errors: List[str] = []

def validate_proposal_invariants(proposal: InvestigationProposal, supplied_evidence_ids: List[str]) -> ValidationResult:
    result = ValidationResult()
    supplied_ids_set = set(supplied_evidence_ids)
    
    # 1. Fixed Cardinality Check
    if len(proposal.selections) != len(V0HypothesisType):
        result.errors.append(f"Proposal must contain exactly {len(V0HypothesisType)} selections (one for each vocabulary item), but found {len(proposal.selections)}.")
        result.is_valid = False
        return result

    seen_ranks = set()
    seen_hypotheses = set()
    
    for selection in proposal.selections:
        if selection.hypothesis_id in seen_hypotheses:
            result.errors.append(f"Duplicate hypothesis ID: {selection.hypothesis_id.value}")
            result.is_valid = False
        seen_hypotheses.add(selection.hypothesis_id)
        
        if selection.rank in seen_ranks:
            result.errors.append(f"Duplicate rank: {selection.rank}")
            result.is_valid = False
        seen_ranks.add(selection.rank)
        
        if selection.rank < 1 or selection.rank > len(V0HypothesisType):
            result.errors.append(f"Invalid rank {selection.rank}. Must be in [1, {len(V0HypothesisType)}]")
            result.is_valid = False
            
        all_referenced_ids = selection.supporting_evidence_ids + selection.contradicting_evidence_ids
        
        for ev_id in all_referenced_ids:
            if ev_id not in supplied_ids_set:
                result.errors.append(f"Hallucinated evidence ID referenced: {ev_id} (not in supplied evidence)")
                result.is_valid = False
                
        supp_set = set(selection.supporting_evidence_ids)
        contra_set = set(selection.contradicting_evidence_ids)
        
        intersection = supp_set.intersection(contra_set)
        if intersection:
            result.errors.append(f"Evidence IDs {list(intersection)} cannot be both supporting and contradicting")
            result.is_valid = False

        if len(selection.supporting_evidence_ids) != len(supp_set):
            result.errors.append(f"Duplicate evidence IDs found in supporting evidence for {selection.hypothesis_id.value}")
            result.is_valid = False
            
        if len(selection.contradicting_evidence_ids) != len(contra_set):
            result.errors.append(f"Duplicate evidence IDs found in contradicting evidence for {selection.hypothesis_id.value}")
            result.is_valid = False
            
        missing_types_set = set(selection.missing_evidence_types)
        if len(selection.missing_evidence_types) != len(missing_types_set):
            result.errors.append(f"Duplicate evidence types found in missing evidence for {selection.hypothesis_id.value}")
            result.is_valid = False

    # Check that all vocabulary items are present
    missing_vocabs = set(V0HypothesisType) - seen_hypotheses
    if missing_vocabs:
        result.errors.append(f"Missing hypotheses in proposal: {[v.value for v in missing_vocabs]}")
        result.is_valid = False

    return result
