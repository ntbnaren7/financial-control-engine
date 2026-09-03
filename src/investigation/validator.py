"""
D4 — OutputValidator

Responsibility: Gate the untrusted CausalHypothesis before it reaches the
Deterministic Verifier.  Three sequential checks are performed; the first
failure short-circuits and returns a ValidationRejection.

Check order:
  1. Schema integrity    — Pydantic structure and cross-field consistency.
                          (Largely already enforced by D3 parse, but this
                          validator accepts raw dicts too, so re-validation
                          is explicit and intentional.)
  2. Evidence reference  — every supporting/contradicting evidence_id must
                          appear in the bounded agent_input produced by D2.
  3. Intent allowlist    — verification_intent must be a member of the
                          permitted_verification_intents set from the same
                          agent_input.  The allowlist comes from D2/the
                          hardcoded VerificationIntent enum; the LLM never
                          expands it.

Contract (strict):
  INPUT   raw dict (LLM output) + agent_input dict (D2 product).
          No ReconciliationCase, repository, provider client, or V1 object.
  OUTPUT  CausalHypothesis on success, ValidationRejection on any failure.
  NO LLM calls, NO provider calls, NO database access.
  NO mutation of any shared state.
  PURE FUNCTION: same inputs → same output, always.
"""

from __future__ import annotations

from typing import Any, Dict, Set, Union

from pydantic import ValidationError

from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    ValidationRejection,
    ValidationRejectionReason,
    VerificationIntent,
)

# ---------------------------------------------------------------------------
# Public type alias for the validator return
# ---------------------------------------------------------------------------

ValidationResult = Union[CausalHypothesis, ValidationRejection]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_known_evidence_ids(agent_input: Dict[str, Any]) -> Set[str]:
    """
    Extract every evidence_id present in the D2 agent_input.

    Covers both correlated_observations and unmatched_observations.
    This is the complete set the LLM was allowed to see; any referenced
    ID that is not in this set is a hallucination.
    """
    ids: Set[str] = set()
    for key in ("correlated_observations", "unmatched_observations"):
        for obs in agent_input.get(key, []):
            ev_id = obs.get("evidence_id")
            if ev_id:
                ids.add(ev_id)
    return ids


def _collect_permitted_intents(agent_input: Dict[str, Any]) -> Set[str]:
    """
    Extract the permitted_verification_intents list from the D2 agent_input.

    This list is the hardcoded Phase D allowlist injected by the formatter;
    the LLM cannot extend it.
    """
    return set(agent_input.get("permitted_verification_intents", []))


# ---------------------------------------------------------------------------
# OutputValidator
# ---------------------------------------------------------------------------

class OutputValidator:
    """
    Stateless gatekeeper between the untrusted LLM output and the
    Deterministic Verifier.

    Usage:
        validator = OutputValidator()
        result = validator.validate(raw_llm_output_dict, agent_input_dict)
        match result:
            case CausalHypothesis():   ...  # proceed to verifier
            case ValidationRejection(): ... # reject, log, surface to operator
    """

    def validate(
        self,
        raw_output: Dict[str, Any],
        agent_input: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate *raw_output* against *agent_input*.

        Parameters
        ----------
        raw_output:
            The dict parsed directly from the LLM response.  May be
            structurally invalid; this method handles that case.
        agent_input:
            The bounded dict produced by InputFormatter (D2).  Treated as
            the trusted source of truth for permissible evidence_ids and
            verification intents.

        Returns
        -------
        CausalHypothesis     if all three checks pass.
        ValidationRejection  on the first failing check.
        """
        # --- Check 1: Schema -------------------------------------------
        schema_result = self._check_schema(raw_output)
        if isinstance(schema_result, ValidationRejection):
            return schema_result
        hypothesis = schema_result  # type: CausalHypothesis

        # --- Check 2: Evidence reference --------------------------------
        reference_result = self._check_evidence_references(hypothesis, agent_input)
        if reference_result is not None:
            return reference_result

        # --- Check 3: Intent allowlist ----------------------------------
        allowlist_result = self._check_intent_allowlist(hypothesis, agent_input)
        if allowlist_result is not None:
            return allowlist_result

        return hypothesis

    # ------------------------------------------------------------------ #
    # Check 1 — Schema integrity                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_schema(raw_output: Dict[str, Any]) -> ValidationResult:
        """
        Attempt to construct a CausalHypothesis from the raw dict.

        Catches Pydantic ValidationError and wraps it in a ValidationRejection.
        This re-validates even if D3 already parsed the object, because:
          a) D4 accepts raw dicts from alternative code paths.
          b) Explicit re-validation makes the audit boundary unambiguous.
        """
        try:
            return CausalHypothesis.model_validate(raw_output)
        except ValidationError as exc:
            return ValidationRejection(
                reason=ValidationRejectionReason.SCHEMA_INVALID,
                detail=str(exc),
                raw_output=raw_output,
            )

    # ------------------------------------------------------------------ #
    # Check 2 — Evidence reference existence                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_evidence_references(
        hypothesis: CausalHypothesis,
        agent_input: Dict[str, Any],
    ) -> ValidationRejection | None:
        """
        Verify that every evidence_id referenced in supporting_evidence_ids
        and contradicting_evidence_ids exists in the agent_input.

        An ID that does not exist in the bounded case is a hallucination.
        Hallucinated IDs are rejected with INVALID_REFERENCE rather than
        silently dropped, to preserve audit visibility.

        Returns None on success (no invalid references found).
        """
        known = _collect_known_evidence_ids(agent_input)
        all_referenced = (
            hypothesis.supporting_evidence_ids
            + hypothesis.contradicting_evidence_ids
        )
        hallucinated = [eid for eid in all_referenced if eid not in known]
        if hallucinated:
            return ValidationRejection(
                reason=ValidationRejectionReason.INVALID_REFERENCE,
                detail=(
                    f"The following evidence_ids are not present in the "
                    f"bounded case and appear to be hallucinated: "
                    f"{hallucinated}"
                ),
                raw_output=hypothesis.model_dump(),
            )
        return None

    # ------------------------------------------------------------------ #
    # Check 3 — Intent allowlist                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_intent_allowlist(
        hypothesis: CausalHypothesis,
        agent_input: Dict[str, Any],
    ) -> ValidationRejection | None:
        """
        Verify that the proposed verification_intent is in the permitted set.

        When disposition is INVESTIGATION_EXHAUSTED, verification_intent is
        None and this check always passes (no intent to validate).

        The permitted set comes from agent_input["permitted_verification_intents"],
        which is the hardcoded Phase D allowlist injected by the formatter.
        The LLM cannot extend this set.

        Returns None on success.
        """
        if hypothesis.disposition == InvestigationDisposition.INVESTIGATION_EXHAUSTED:
            # No intent to validate
            return None

        intent = hypothesis.verification_intent
        if intent is None:
            # Should not be reachable (D1 model_validator catches this), but
            # included for defence-in-depth
            return ValidationRejection(
                reason=ValidationRejectionReason.INTENT_DISPOSITION_MISMATCH,
                detail=(
                    "disposition is VERIFICATION_PROPOSED but "
                    "verification_intent is None"
                ),
                raw_output=hypothesis.model_dump(),
            )

        permitted = _collect_permitted_intents(agent_input)
        if intent.value not in permitted:
            return ValidationRejection(
                reason=ValidationRejectionReason.INVALID_INTENT,
                detail=(
                    f"verification_intent '{intent.value}' is not in the "
                    f"permitted set for this case: {sorted(permitted)}"
                ),
                raw_output=hypothesis.model_dump(),
            )
        return None
