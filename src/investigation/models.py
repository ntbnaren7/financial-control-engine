from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Any

# ==========================================
# 1. Hypothesis Vocabulary
# ==========================================
class V0HypothesisType(str, Enum):
    WEBHOOK_NOT_OBSERVED = "WEBHOOK_NOT_OBSERVED"
    WEBHOOK_OBSERVED_NOT_PROCESSED = "WEBHOOK_OBSERVED_NOT_PROCESSED"
    WEBHOOK_PROCESSED_STATE_NOT_UPDATED = "WEBHOOK_PROCESSED_STATE_NOT_UPDATED"
    PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH = "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"

# ==========================================
# 2. Evidence Vocabulary
# ==========================================
class EvidenceType(str, Enum):
    # Provider evidence
    E_PROVIDER_PAYMENT = "E_PROVIDER_PAYMENT"
    E_PROVIDER_ORDER = "E_PROVIDER_ORDER"

    # Webhook evidence
    E_WEBHOOK_CAPTURED = "E_WEBHOOK_CAPTURED"
    E_WEBHOOK_AUTHENTICATION = "E_WEBHOOK_AUTHENTICATION"

    # Merchant evidence
    E_MERCHANT_ORDER_STATE = "E_MERCHANT_ORDER_STATE"
    E_MERCHANT_PROCESSING = "E_MERCHANT_PROCESSING"
    E_MERCHANT_STATE_TRANSITION = "E_MERCHANT_STATE_TRANSITION"

    # Coverage evidence
    E_WEBHOOK_COVERAGE = "E_WEBHOOK_COVERAGE"
    E_PROCESSING_COVERAGE = "E_PROCESSING_COVERAGE"
    E_STATE_TRANSITION_COVERAGE = "E_STATE_TRANSITION_COVERAGE"

    # Investigation metadata
    E_OBSERVATION_TIMESTAMP = "E_OBSERVATION_TIMESTAMP"
    E_SOURCE_PROVENANCE = "E_SOURCE_PROVENANCE"

class EvidenceCoverage(str, Enum):
    """
    Authoritative completeness of the evidence observation layer.

    COMPLETE  — The observation layer has full coverage. Absence of a record
                means the event definitively did not occur.
    PARTIAL   — The observation layer has partial coverage. Absence of a record
                is inconclusive.
    UNKNOWN   — Coverage completeness cannot be determined. Absence of a record
                does not establish absence of the event.
    """
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"

# ==========================================
# 3. Model Output Contract
# ==========================================
class ConfidenceBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class HypothesisSelection(BaseModel):
    hypothesis_id: V0HypothesisType
    rank: int = Field(..., description="Rank of the hypothesis (1 is highest)")
    rationale: str = Field(..., description="Explanation of why this hypothesis was selected")
    confidence_band: ConfidenceBand = Field(..., description="Confidence in this selection (HIGH, MEDIUM, LOW)")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="List of evidence IDs supporting this hypothesis")
    contradicting_evidence_ids: List[str] = Field(default_factory=list, description="List of evidence IDs contradicting this hypothesis")
    missing_evidence_types: List[EvidenceType] = Field(default_factory=list, description="List of evidence types that are missing and required to confirm")


class InvestigationEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"

class InvestigationProposal(BaseModel):
    eligibility: InvestigationEligibility = Field(..., description="Whether this discrepancy is eligible for an M4 causal investigation")
    overall_confidence: ConfidenceBand = Field(..., description="Overall confidence in this investigation")
    selections: List[HypothesisSelection] = Field(..., min_length=5, max_length=5, description="Must contain exactly 5 selections, one for each hypothesis type.")

# ==========================================
# 4. Production Engine Input Structure
# ==========================================
class WebhookCapturedContent(BaseModel):
    present: bool

class ProcessingCoverageContent(BaseModel):
    coverage: EvidenceCoverage
    processing_count: int

class EvidenceItem(BaseModel):
    id: str = Field(..., description="Stable evidence ID (e.g., EV-001)")
    type: EvidenceType
    content: Any = Field(..., description="The actual evidence data/metadata, can be strongly typed (e.g. WebhookCapturedContent) or raw dict.")

class DiscrepancyContext(BaseModel):
    case_id: str
    description: str
    provider_status: str
    merchant_status: str
    amount_match: bool
    currency_match: bool
    identity_verified: bool

# ==========================================
# 5. Hypothesis Semantics Contract
# ==========================================
class HypothesisDefinition(BaseModel):
    """
    Formal contract for a single causal hypothesis.

    These definitions are the single source of truth for hypothesis semantics.
    Both the LLM prompt and any future tooling must read from HYPOTHESIS_DEFINITIONS
    rather than duplicating descriptions.
    """
    hypothesis_id: V0HypothesisType
    meaning: str
    supporting_conditions: List[str]
    disqualifying_conditions: List[str]
    uncertainty_note: str


HYPOTHESIS_DEFINITIONS: dict[V0HypothesisType, HypothesisDefinition] = {
    V0HypothesisType.WEBHOOK_NOT_OBSERVED: HypothesisDefinition(
        hypothesis_id=V0HypothesisType.WEBHOOK_NOT_OBSERVED,
        meaning=(
            "The provider webhook was not received or recorded by the system."
        ),
        supporting_conditions=[
            "No webhook observation record exists for this order.",
            "Coverage of the webhook ingestion layer is authoritative and COMPLETE.",
        ],
        disqualifying_conditions=[
            "A webhook observation record exists (webhook_present=True).",
        ],
        uncertainty_note=(
            "If webhook coverage is UNKNOWN or PARTIAL, the absence of a record does not "
            "establish that no webhook was delivered. Consider EVIDENCE_INSUFFICIENT."
        ),
    ),

    V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED: HypothesisDefinition(
        hypothesis_id=V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED,
        meaning=(
            "A webhook was received, but the system did not successfully process it."
        ),
        supporting_conditions=[
            "A webhook observation record exists (webhook_present=True).",
            "No authoritative processing record exists for this webhook.",
        ],
        disqualifying_conditions=[
            "Authoritative COMPLETE coverage establishes that the webhook was processed.",
        ],
        uncertainty_note=(
            "If processing coverage is UNKNOWN or PARTIAL, the absence of a processing "
            "record means this hypothesis is not contradicted — not that it is confirmed. "
            "Both this hypothesis and EVIDENCE_INSUFFICIENT remain plausible."
        ),
    ),

    V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED: HypothesisDefinition(
        hypothesis_id=V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED,
        meaning=(
            "The webhook was processed, but the merchant state was not subsequently updated to reflect it."
        ),
        supporting_conditions=[
            "Webhook observation record exists (webhook_present=True).",
            "A processing record exists (processing_count > 0).",
            "Merchant state remains inconsistent despite processing.",
        ],
        disqualifying_conditions=[
            "Coverage is COMPLETE and processing_count is 0 — meaning processing definitively did not occur.",
        ],
        uncertainty_note=(
            "If merchant state transition coverage is UNKNOWN, the absence of a state update "
            "record does not confirm this hypothesis. Consider EVIDENCE_INSUFFICIENT."
        ),
    ),

    V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH: HypothesisDefinition(
        hypothesis_id=V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH,
        meaning=(
            "No causal event failure occurred in the processing chain, but the provider and "
            "merchant represent the final state differently (e.g. naming, timing, or semantic "
            "differences in status strings)."
        ),
        supporting_conditions=[
            "Processing chain completed successfully end-to-end.",
            "Amounts and currency match.",
            "The discrepancy is in state label or representation only, not in a missing event.",
        ],
        disqualifying_conditions=[
            "Authoritative evidence directly establishes an upstream event failure incompatible "
            "with a pure representation mismatch (e.g. authoritative evidence the webhook was "
            "never received, or that processing definitively did not occur). "
            "Note: this is an evidence-level constraint — do not use it to assert that another "
            "hypothesis is causally correct.",
        ],
        uncertainty_note=(
            "Only rank this highly when the processing chain appears complete and the mismatch "
            "is purely semantic. Do not rank it highly when upstream failures remain unresolved."
        ),
    ),

    V0HypothesisType.EVIDENCE_INSUFFICIENT: HypothesisDefinition(
        hypothesis_id=V0HypothesisType.EVIDENCE_INSUFFICIENT,
        meaning=(
            "The available evidence cannot sufficiently distinguish among the competing hypotheses."
        ),
        supporting_conditions=[
            "Evidence is missing, coverage is PARTIAL or UNKNOWN, or multiple hypotheses remain "
            "equally plausible given the observed facts.",
            "No single hypothesis is clearly supported over the others by authoritative evidence.",
        ],
        disqualifying_conditions=[
            "Authoritative evidence clearly and unambiguously establishes one of the other hypotheses.",
        ],
        uncertainty_note=(
            "EVIDENCE_INSUFFICIENT is not a fallback for missing evidence only. Even with significant "
            "evidence present, if competing causes cannot be distinguished from each other, "
            "EVIDENCE_INSUFFICIENT is the correct rank-1 selection."
        ),
    ),
}
