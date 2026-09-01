from typing import List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum

from src.investigation.models import (
    V0HypothesisType,
    EvidenceType,
    ConfidenceBand,
    InvestigationEligibility,
    HypothesisSelection,
    InvestigationProposal,
    EvidenceItem,
)

# ==========================================
# Evaluation-Specific Structures
# ==========================================
class DiscrepancyContext(BaseModel):
    provider_status: str
    merchant_status: str
    amount_match: bool
    currency_match: bool
    identity_verified: bool
class InvestigationStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    M4_INELIGIBLE = "M4_INELIGIBLE"

class EvaluationCase(BaseModel):
    case_id: str
    description: str
    group: str
    discrepancy: DiscrepancyContext
    evidence: List[EvidenceItem]
    
    # The deterministic expected outcome (for scoring the model)
    expected_eligibility: InvestigationEligibility
    expected_overall_status: InvestigationStatus 
    expected_top_hypothesis: Optional[V0HypothesisType]
    requires_missing_evidence: bool = False

