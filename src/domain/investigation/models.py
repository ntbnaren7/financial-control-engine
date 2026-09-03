"""
Domain models for Phase D: Investigative Agent.

All types in this module represent *claims* and *intents* produced by the
untrusted LLM investigator, or the pipeline metadata that surrounds them.
None of these types carry financial authority.

Authority chain reminder:
  LLM reasoning         → untrusted
  LLM output schema     → structurally constrained (Pydantic)
  Evidence references   → validated by OutputValidator
  Verification intent   → allowlisted by OutputValidator
  Query parameters      → derived from trusted ReconciliationCase by Verifier
  Provider response     → raw evidence, traverses Phase C normaliser
  Financial truth       → V1 authoritative exclusively
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# 1. Permitted verification capabilities (allowlist)
# ---------------------------------------------------------------------------

class VerificationIntent(str, Enum):
    """
    The complete, hardcoded set of read-only provider queries the verifier
    is permitted to execute.  The LLM selects a name from this list; it
    never supplies query parameters.  Parameters are derived exclusively from
    the trusted ReconciliationCase by the Deterministic Verifier.
    """
    QUERY_PROVIDER_REFUND  = "QUERY_PROVIDER_REFUND"
    QUERY_PROVIDER_PAYMENT = "QUERY_PROVIDER_PAYMENT"
    QUERY_REFUND_EVENTS    = "QUERY_REFUND_EVENTS"


# ---------------------------------------------------------------------------
# 2. Investigation disposition (separate from verification intent)
# ---------------------------------------------------------------------------

class InvestigationDisposition(str, Enum):
    """
    Terminal investigation state declared by the LLM.

    VERIFICATION_PROPOSED   – the agent believes a permitted query can
                              discriminate between competing hypotheses.
    INVESTIGATION_EXHAUSTED – the agent cannot identify any permitted
                              verification that would resolve the stalemate.

    These are conceptually distinct from executing a query and finding
    nothing (which is a verifier outcome, not an agent disposition).
    """
    VERIFICATION_PROPOSED   = "VERIFICATION_PROPOSED"
    INVESTIGATION_EXHAUSTED = "INVESTIGATION_EXHAUSTED"


# ---------------------------------------------------------------------------
# 3. Structured LLM output
# ---------------------------------------------------------------------------

class CausalHypothesis(BaseModel):
    """
    Structured output produced by the LLM investigator.

    Every field is an *untrusted claim*.  No field has direct effect on
    verification, reconciliation, policy, or authorisation.  The
    OutputValidator must accept this object before it reaches the Verifier.

    confidence:
        Informational only.  Zero effect on what the verifier executes,
        what V1 classifies, or how the case is resolved.  A HIGH-confidence
        hallucination is treated identically to a LOW-confidence one until
        deterministic evidence confirms or contradicts the hypothesis.
    """

    hypothesis: str
    """
    Concise, falsifiable explanation of why the discrepancy may have
    occurred.  Example:
        "Provider execution likely occurred but the webhook arrived outside
         the permitted correlation window."
    """

    supporting_evidence_ids: List[str]
    """
    Zero or more evidence_id values from the agent input that are consistent
    with the hypothesis.  Treated as *references*, not executable input.
    The OutputValidator checks each ID against the case's known evidence set.
    """

    contradicting_evidence_ids: List[str]
    """
    Zero or more evidence_id values that are inconsistent with the
    hypothesis.  Same validation rules as supporting_evidence_ids.
    """

    missing_evidence_description: str
    """
    Human-readable description of the evidence that would discriminate
    between the hypothesis and competing explanations.  Example:
        "Authoritative provider refund status lookup via API."
    """

    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    """
    Agent's self-assessed confidence.  Surfaced to the operator interface
    only.  Has no effect on any downstream decision.
    """

    disposition: InvestigationDisposition
    """
    Whether the agent is proposing a verification or declaring investigation
    exhausted.
    """

    verification_intent: Optional[VerificationIntent] = None
    """
    Required when disposition == VERIFICATION_PROPOSED.
    Must be None when disposition == INVESTIGATION_EXHAUSTED.
    Allowlist-validated by OutputValidator before reaching the Verifier.
    """

    @model_validator(mode="after")
    def _intent_consistent_with_disposition(self) -> "CausalHypothesis":
        if (
            self.disposition == InvestigationDisposition.VERIFICATION_PROPOSED
            and self.verification_intent is None
        ):
            raise ValueError(
                "verification_intent is required when disposition is "
                "VERIFICATION_PROPOSED"
            )
        if (
            self.disposition == InvestigationDisposition.INVESTIGATION_EXHAUSTED
            and self.verification_intent is not None
        ):
            raise ValueError(
                "verification_intent must be None when disposition is "
                "INVESTIGATION_EXHAUSTED"
            )
        return self

    @field_validator("hypothesis", "missing_evidence_description", mode="before")
    @classmethod
    def _non_empty_string(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Field must be a non-empty string")
        return v.strip()


# ---------------------------------------------------------------------------
# 4. Validation pipeline outputs
# ---------------------------------------------------------------------------

class ValidationRejectionReason(str, Enum):
    """Reason codes emitted by the OutputValidator on rejection."""
    SCHEMA_INVALID              = "SCHEMA_INVALID"
    INVALID_REFERENCE           = "INVALID_REFERENCE"   # evidence_id not in case
    INVALID_INTENT              = "INVALID_INTENT"       # intent not in allowlist
    INTENT_DISPOSITION_MISMATCH = "INTENT_DISPOSITION_MISMATCH"


class ValidationRejection(BaseModel):
    """
    Produced by the OutputValidator when a CausalHypothesis fails any of
    the three validation checks.  The Verifier never receives malformed
    agent output.
    """
    reason: ValidationRejectionReason
    detail: str
    raw_output: Optional[dict] = None
    """
    The raw LLM output dict, preserved for operator visibility and audit.
    Never used as input to any downstream system component.
    """


# ---------------------------------------------------------------------------
# 5. Verifier outputs
# ---------------------------------------------------------------------------

class VerificationRejectionReason(str, Enum):
    """Reason codes emitted by the Deterministic Verifier on rejection."""
    EXHAUSTED      = "EXHAUSTED"       # disposition == INVESTIGATION_EXHAUSTED
    PROVIDER_ERROR = "PROVIDER_ERROR"  # read-only query failed at provider


class VerificationRejection(BaseModel):
    """
    Produced by the Deterministic Verifier when it cannot or will not
    execute the requested verification.
    """
    reason: VerificationRejectionReason
    detail: str
    hypothesis: Optional[CausalHypothesis] = None
    """Preserved for operator display and audit."""
