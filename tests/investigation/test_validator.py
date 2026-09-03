"""
D4 Acceptance Tests — OutputValidator

Covers the full validation surface including adversarial cases:

Schema checks (Check 1):
  AC-4-1  Valid proposed hypothesis passes all three checks
  AC-4-2  Valid exhausted hypothesis passes all three checks
  AC-4-3  Missing required field → SCHEMA_INVALID
  AC-4-4  Invalid enum value → SCHEMA_INVALID
  AC-4-5  Cross-field violation (PROPOSED without intent) → SCHEMA_INVALID
  AC-4-6  Cross-field violation (EXHAUSTED with intent) → SCHEMA_INVALID
  AC-4-7  Empty hypothesis string → SCHEMA_INVALID

Evidence reference checks (Check 2):
  AC-4-8  All referenced IDs exist → passes
  AC-4-9  Single hallucinated supporting ID → INVALID_REFERENCE
  AC-4-10 Single hallucinated contradicting ID → INVALID_REFERENCE
  AC-4-11 Multiple hallucinated IDs → all reported
  AC-4-12 Empty evidence lists → passes (no references to validate)
  AC-4-13 Schema failure short-circuits before reference check

Intent allowlist checks (Check 3):
  AC-4-14 Valid intent in permitted set → passes
  AC-4-15 Intent not in permitted set → INVALID_INTENT
  AC-4-16 EXHAUSTED disposition skips intent check
  AC-4-17 Reference failure short-circuits before intent check
  AC-4-18 Permitted set comes from agent_input, not from LLM output

Adversarial:
  AC-4-19 LLM-injected ID that looks real but is not in case → rejected
  AC-4-20 LLM proposes intent not in Phase D capability set → rejected
  AC-4-21 Validator is a pure function (same inputs → same output)
  AC-4-22 Validator has no provider/DB/V1/mutation imports
"""

from __future__ import annotations

import importlib
import sys
from typing import Any, Dict

import pytest

from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    ValidationRejection,
    ValidationRejectionReason,
    VerificationIntent,
)
from src.investigation.validator import OutputValidator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AGENT_INPUT: Dict[str, Any] = {
    "case_id": "case_stalemate_1",
    "discrepancy_type": "EPISTEMIC_STALEMATE",
    "knowledge_state": "UNKNOWN",
    "expected_refund": {
        "intent_id": "ref_8",
        "provider_payment_id": "pay_abc123",
        "amount": "200.00",
        "currency": "INR",
        "created_at": "2026-09-03T06:00:00+00:00",
    },
    "correlated_observations": [],
    "unmatched_observations": [
        {
            "evidence_id": "evt_wh_temporal",
            "source": "razorpay_webhook",
            "evidence_type": "RAZORPAY_REFUND.PROCESSED",
            "timestamp": "2026-09-02T06:00:00+00:00",
            "correlation_status": "TEMPORAL_VIOLATION",
            "correlation_checks": {
                "matched_by": None,
                "temporal_check": False,
                "entity_scope": True,
                "amount_check": False,
                "currency_check": False,
            },
        }
    ],
    "permitted_verification_intents": [
        "QUERY_PROVIDER_REFUND",
        "QUERY_PROVIDER_PAYMENT",
        "QUERY_REFUND_EVENTS",
    ],
}

# An agent_input with a correlated observation so we can test that pool too
_AGENT_INPUT_CORRELATED: Dict[str, Any] = {
    **_AGENT_INPUT,
    "correlated_observations": [
        {
            "evidence_id": "evt_corr_1",
            "source": "razorpay_webhook",
            "evidence_type": "RAZORPAY_REFUND.PROCESSED",
            "timestamp": "2026-09-03T05:00:00+00:00",
            "correlation_status": "CORRELATED",
            "correlation_checks": {
                "matched_by": "receipt",
                "temporal_check": True,
                "entity_scope": True,
                "amount_check": True,
                "currency_check": True,
            },
        }
    ],
}

_VALID_PROPOSED: Dict[str, Any] = {
    "hypothesis": "Provider execution likely occurred but the webhook arrived outside the correlation window.",
    "supporting_evidence_ids": ["evt_wh_temporal"],
    "contradicting_evidence_ids": [],
    "missing_evidence_description": "Authoritative provider refund status lookup.",
    "confidence": "MEDIUM",
    "disposition": "VERIFICATION_PROPOSED",
    "verification_intent": "QUERY_PROVIDER_REFUND",
}

_VALID_EXHAUSTED: Dict[str, Any] = {
    "hypothesis": "Evidence is insufficient to discriminate between competing hypotheses.",
    "supporting_evidence_ids": [],
    "contradicting_evidence_ids": [],
    "missing_evidence_description": "No additional permitted query can resolve the stalemate.",
    "confidence": "LOW",
    "disposition": "INVESTIGATION_EXHAUSTED",
    "verification_intent": None,
}


@pytest.fixture
def validator() -> OutputValidator:
    return OutputValidator()


# ---------------------------------------------------------------------------
# AC-4-1  Valid proposed hypothesis passes all three checks
# AC-4-2  Valid exhausted hypothesis passes all three checks
# ---------------------------------------------------------------------------

class TestValidCases:
    def test_valid_proposed_returns_hypothesis(self, validator: OutputValidator):
        result = validator.validate(_VALID_PROPOSED, _AGENT_INPUT)
        assert isinstance(result, CausalHypothesis)

    def test_valid_proposed_disposition_preserved(self, validator: OutputValidator):
        result = validator.validate(_VALID_PROPOSED, _AGENT_INPUT)
        assert isinstance(result, CausalHypothesis)
        assert result.disposition == InvestigationDisposition.VERIFICATION_PROPOSED

    def test_valid_exhausted_returns_hypothesis(self, validator: OutputValidator):
        result = validator.validate(_VALID_EXHAUSTED, _AGENT_INPUT)
        assert isinstance(result, CausalHypothesis)

    def test_valid_exhausted_no_intent(self, validator: OutputValidator):
        result = validator.validate(_VALID_EXHAUSTED, _AGENT_INPUT)
        assert isinstance(result, CausalHypothesis)
        assert result.verification_intent is None


# ---------------------------------------------------------------------------
# Schema checks (Check 1): AC-4-3 to AC-4-7
# ---------------------------------------------------------------------------

class TestSchemaChecks:
    def test_missing_required_field_rejected(self, validator: OutputValidator):
        bad = {k: v for k, v in _VALID_PROPOSED.items() if k != "hypothesis"}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.SCHEMA_INVALID

    def test_invalid_enum_disposition_rejected(self, validator: OutputValidator):
        bad = {**_VALID_PROPOSED, "disposition": "EXECUTE_PAYMENT_NOW"}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.SCHEMA_INVALID

    def test_invalid_enum_intent_rejected(self, validator: OutputValidator):
        bad = {**_VALID_PROPOSED, "verification_intent": "DELETE_RECORD"}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.SCHEMA_INVALID

    def test_proposed_without_intent_rejected(self, validator: OutputValidator):
        bad = {**_VALID_PROPOSED, "verification_intent": None}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.SCHEMA_INVALID

    def test_exhausted_with_intent_rejected(self, validator: OutputValidator):
        bad = {**_VALID_EXHAUSTED, "verification_intent": "QUERY_PROVIDER_REFUND"}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.SCHEMA_INVALID

    def test_empty_hypothesis_string_rejected(self, validator: OutputValidator):
        bad = {**_VALID_PROPOSED, "hypothesis": "   "}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.SCHEMA_INVALID

    def test_raw_output_preserved_in_rejection(self, validator: OutputValidator):
        bad = {**_VALID_PROPOSED, "hypothesis": ""}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.raw_output is not None


# ---------------------------------------------------------------------------
# Evidence reference checks (Check 2): AC-4-8 to AC-4-13
# ---------------------------------------------------------------------------

class TestEvidenceReferenceChecks:
    def test_referenced_id_in_unmatched_passes(self, validator: OutputValidator):
        result = validator.validate(_VALID_PROPOSED, _AGENT_INPUT)
        assert isinstance(result, CausalHypothesis)

    def test_referenced_id_in_correlated_passes(self, validator: OutputValidator):
        proposed_corr = {
            **_VALID_PROPOSED,
            "supporting_evidence_ids": ["evt_corr_1"],
        }
        result = validator.validate(proposed_corr, _AGENT_INPUT_CORRELATED)
        assert isinstance(result, CausalHypothesis)

    def test_hallucinated_supporting_id_rejected(self, validator: OutputValidator):
        bad = {**_VALID_PROPOSED, "supporting_evidence_ids": ["evt_INVENTED_123"]}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.INVALID_REFERENCE
        assert "evt_INVENTED_123" in result.detail

    def test_hallucinated_contradicting_id_rejected(self, validator: OutputValidator):
        bad = {**_VALID_PROPOSED, "contradicting_evidence_ids": ["evt_FAKE_abc"]}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.INVALID_REFERENCE
        assert "evt_FAKE_abc" in result.detail

    def test_multiple_hallucinated_ids_all_reported(self, validator: OutputValidator):
        bad = {
            **_VALID_PROPOSED,
            "supporting_evidence_ids": ["fake_1", "fake_2"],
            "contradicting_evidence_ids": ["fake_3"],
        }
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.INVALID_REFERENCE
        assert "fake_1" in result.detail
        assert "fake_2" in result.detail
        assert "fake_3" in result.detail

    def test_empty_evidence_lists_pass(self, validator: OutputValidator):
        """No references → nothing to validate → passes."""
        empty_refs = {
            **_VALID_PROPOSED,
            "supporting_evidence_ids": [],
            "contradicting_evidence_ids": [],
        }
        result = validator.validate(empty_refs, _AGENT_INPUT)
        assert isinstance(result, CausalHypothesis)

    def test_schema_failure_short_circuits_before_reference_check(
        self, validator: OutputValidator
    ):
        """A schema error must not be swallowed by a subsequent reference error."""
        bad = {
            "hypothesis": "",          # invalid — empty
            "supporting_evidence_ids": ["fake_1"],
            "contradicting_evidence_ids": [],
            "missing_evidence_description": "x",
            "confidence": "HIGH",
            "disposition": "VERIFICATION_PROPOSED",
            "verification_intent": "QUERY_PROVIDER_REFUND",
        }
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.SCHEMA_INVALID  # not INVALID_REFERENCE


# ---------------------------------------------------------------------------
# Intent allowlist checks (Check 3): AC-4-14 to AC-4-18
# ---------------------------------------------------------------------------

class TestIntentAllowlistChecks:
    def test_intent_in_permitted_set_passes(self, validator: OutputValidator):
        result = validator.validate(_VALID_PROPOSED, _AGENT_INPUT)
        assert isinstance(result, CausalHypothesis)

    def test_all_three_permitted_intents_pass(self, validator: OutputValidator):
        for intent_value in _AGENT_INPUT["permitted_verification_intents"]:
            proposed = {**_VALID_PROPOSED, "verification_intent": intent_value}
            result = validator.validate(proposed, _AGENT_INPUT)
            assert isinstance(result, CausalHypothesis), (
                f"Expected pass for intent '{intent_value}', got {result}"
            )

    def test_intent_not_in_permitted_set_rejected(self, validator: OutputValidator):
        """A valid VerificationIntent enum value that is not in the case's
        permitted set should be rejected by the allowlist check."""
        restricted_input = {
            **_AGENT_INPUT,
            # Only one intent is permitted for this case
            "permitted_verification_intents": ["QUERY_PROVIDER_PAYMENT"],
        }
        # Propose a different (valid enum) intent
        proposed = {**_VALID_PROPOSED, "verification_intent": "QUERY_REFUND_EVENTS"}
        result = validator.validate(proposed, restricted_input)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.INVALID_INTENT
        assert "QUERY_REFUND_EVENTS" in result.detail

    def test_exhausted_skips_intent_check(self, validator: OutputValidator):
        """INVESTIGATION_EXHAUSTED with an empty permitted set should still pass."""
        no_intents_input = {**_AGENT_INPUT, "permitted_verification_intents": []}
        result = validator.validate(_VALID_EXHAUSTED, no_intents_input)
        assert isinstance(result, CausalHypothesis)

    def test_reference_failure_short_circuits_before_intent_check(
        self, validator: OutputValidator
    ):
        """A reference error must take priority over an intent error."""
        bad = {
            **_VALID_PROPOSED,
            "supporting_evidence_ids": ["hallucinated_id"],
            # Also give it a bad intent to see which error fires first
            "verification_intent": "QUERY_REFUND_EVENTS",
        }
        restricted_input = {
            **_AGENT_INPUT,
            "permitted_verification_intents": ["QUERY_PROVIDER_PAYMENT"],
        }
        result = validator.validate(bad, restricted_input)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.INVALID_REFERENCE  # not INVALID_INTENT

    def test_permitted_set_comes_from_agent_input_not_llm(
        self, validator: OutputValidator
    ):
        """
        The validator must source the permitted set from agent_input, not from
        the LLM output.  If the LLM somehow produces an intent that is valid
        as an enum but absent from the case's permitted list, it is rejected.
        """
        narrow_input = {
            **_AGENT_INPUT,
            "permitted_verification_intents": [],  # nothing is permitted
        }
        # LLM proposes a real intent value
        proposed = {
            **_VALID_PROPOSED,
            "supporting_evidence_ids": [],  # no references so check 2 passes
            "verification_intent": "QUERY_PROVIDER_REFUND",
        }
        result = validator.validate(proposed, narrow_input)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.INVALID_INTENT


# ---------------------------------------------------------------------------
# Adversarial cases: AC-4-19 to AC-4-22
# ---------------------------------------------------------------------------

class TestAdversarialCases:
    def test_plausible_looking_hallucinated_id_rejected(
        self, validator: OutputValidator
    ):
        """
        A hallucinated ID that follows the same naming pattern as real IDs
        must still be rejected if it's not in the bounded case.
        """
        bad = {
            **_VALID_PROPOSED,
            "supporting_evidence_ids": ["evt_wh_temporal_EXTRA"],  # plausible but fake
        }
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        assert result.reason == ValidationRejectionReason.INVALID_REFERENCE

    def test_intent_not_in_phase_d_capability_set_rejected(
        self, validator: OutputValidator
    ):
        """
        An intent that is not a VerificationIntent enum member at all is
        rejected at the schema level (Check 1), before reaching Check 3.
        """
        bad = {**_VALID_PROPOSED, "verification_intent": "WRITE_REFUND_RECORD"}
        result = validator.validate(bad, _AGENT_INPUT)
        assert isinstance(result, ValidationRejection)
        # Could be SCHEMA_INVALID (invalid enum) — the important thing is it's rejected
        assert result.reason in (
            ValidationRejectionReason.SCHEMA_INVALID,
            ValidationRejectionReason.INVALID_INTENT,
        )

    def test_validator_is_pure_function(self, validator: OutputValidator):
        """Same inputs produce the same output — no hidden state or randomness."""
        result_a = validator.validate(_VALID_PROPOSED, _AGENT_INPUT)
        result_b = validator.validate(_VALID_PROPOSED, _AGENT_INPUT)
        assert type(result_a) is type(result_b)
        if isinstance(result_a, CausalHypothesis) and isinstance(result_b, CausalHypothesis):
            assert result_a.model_dump() == result_b.model_dump()

    def test_validator_has_no_forbidden_imports(self):
        """
        Static check: validator.py must not import provider, storage,
        reconciliation, V1, or mutation modules.
        """
        import importlib as _il
        mod = _il.import_module("src.investigation.validator")
        with open(mod.__file__) as f:  # type: ignore[arg-type]
            source = f.read()

        forbidden = (
            "src.integrations",
            "src.storage",
            "src.control",
            "src.outbox",
            "src.reconciliation",
            "src.domain.cases",
            "src.domain.incidents",
        )
        for prefix in forbidden:
            assert prefix not in source, (
                f"validator.py must not import '{prefix}'"
            )
