from typing import List
from src.investigation.models import (
    InvestigationProposal, 
    EvidenceItem, 
    V0HypothesisType,
    EvidenceCoverage,
    WebhookCapturedContent,
    ProcessingCoverageContent
)

class SemanticValidationResult:
    def __init__(self):
        self.is_admissible = True
        self.errors: List[str] = []

def validate_semantic_admissibility(proposal: InvestigationProposal, evidence: List[EvidenceItem]) -> SemanticValidationResult:
    result = SemanticValidationResult()
    
    # We only care about the rank-1 hypothesis for admissibility
    top_selection = next((s for s in proposal.selections if s.rank == 1), None)
    if not top_selection:
        return result
        
    top_hypothesis = top_selection.hypothesis_id
    
    # Extract hard facts from structured evidence
    webhook_present = None
    processing_count = None
    processing_coverage = None
    
    for ev in evidence:
        if isinstance(ev.content, WebhookCapturedContent):
            webhook_present = ev.content.present
        elif isinstance(ev.content, ProcessingCoverageContent):
            processing_count = ev.content.processing_count
            processing_coverage = ev.content.coverage
            
    # Rule 1: If webhook is definitely present, the cause cannot be WEBHOOK_NOT_OBSERVED
    if top_hypothesis == V0HypothesisType.WEBHOOK_NOT_OBSERVED:
        if webhook_present is True:
            result.errors.append("Hypothesis WEBHOOK_NOT_OBSERVED is contradicted by authoritative evidence (webhook is present).")
            result.is_admissible = False
            
    # Rule 2: If we have authoritative processing coverage showing no processing happened,
    # the cause cannot be that it processed and failed to update state.
    # Only applies when coverage is authoritatively COMPLETE — not PARTIAL or UNKNOWN.
    if top_hypothesis == V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED:
        if processing_count is not None and processing_count == 0 and processing_coverage == EvidenceCoverage.COMPLETE:
            result.errors.append("Hypothesis WEBHOOK_PROCESSED_STATE_NOT_UPDATED is contradicted by authoritative evidence (coverage COMPLETE, processing count is 0).")
            result.is_admissible = False

    return result
