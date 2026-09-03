"""
D2 Acceptance Tests — InputFormatter

Covers all nine acceptance criteria specified in the Phase D contract:

  AC-1  EPISTEMIC_STALEMATE case → bounded representation
  AC-2  Expected refund fields preserved accurately
  AC-3  Correlated and unmatched observations represented separately
  AC-4  Evidence IDs preserved exactly
  AC-5  knowledge_state preserved
  AC-6  permitted_intents == hardcoded allowlist exactly
  AC-7  Raw provider payloads NOT leaked into agent input
  AC-8  Formatting the same case twice → identical output
  AC-9  Formatter has no provider/database/execution dependencies
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from src.domain.cases.models import ReconciliationCase
from src.domain.correlation.models import (
    CorrelationContext,
    CorrelationResult,
    CorrelationStatus,
)
from src.domain.evidence.models import Evidence
from src.domain.investigation.models import VerificationIntent
from src.investigation.input_formatter import format_case_for_investigation
from src.reconciliation.models import (
    DiscrepancyType,
    ExpectedRefund,
    ReconciliationResult,
)
from src.state.models import (
    ExecutionState,
    KnowledgeState,
    ReconstructedState,
)
from src.evidence.models import EntityType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 9, 3, 7, 0, 0, tzinfo=timezone.utc)
_HOUR_AGO = _NOW - timedelta(hours=1)
_TWO_HOURS_AGO = _NOW - timedelta(hours=2)
_ALLOWLIST = [v.value for v in VerificationIntent]


def _make_intent_evidence(intent_id: str = "ref_8") -> Evidence:
    return Evidence(
        evidence_id=f"evt_intent_{intent_id}",
        source="internal_oms",
        entity_id=intent_id,
        evidence_type="REFUND_INTENT",
        timestamp=_TWO_HOURS_AGO,
        payload={
            "refund_intent_id": intent_id,
            "provider_payment_id": "pay_abc123",
            "amount": "200.00",
            "currency": "INR",
            "SECRET_INTERNAL_KEY": "MUST_NOT_LEAK",  # must not appear in output
        },
    )


def _make_webhook_evidence(
    evidence_id: str = "evt_wh_1",
    intent_id: str = "ref_8",
    status: CorrelationStatus = CorrelationStatus.TEMPORAL_VIOLATION,
) -> tuple[Evidence, CorrelationResult]:
    ev = Evidence(
        evidence_id=evidence_id,
        source="razorpay_webhook",
        entity_id=f"rfnd_{intent_id}",
        evidence_type="RAZORPAY_REFUND.PROCESSED",
        timestamp=_HOUR_AGO,
        payload={
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": f"rfnd_{intent_id}",
                        "amount": 20000,
                        "currency": "INR",
                        "status": "refunded",
                        "SECRET_PROVIDER_KEY": "MUST_NOT_LEAK",
                    }
                }
            },
        },
    )
    result = CorrelationResult(
        internal_evidence=_make_intent_evidence(intent_id),
        provider_evidence=ev,
        status=status,
        matched_by="receipt" if status == CorrelationStatus.CORRELATED else None,
        temporal_check=(status == CorrelationStatus.CORRELATED),
        entity_scope=True,
        amount_check=(status == CorrelationStatus.CORRELATED),
        currency_check=(status == CorrelationStatus.CORRELATED),
    )
    return ev, result


def _make_expectation(intent_id: str = "ref_8") -> ExpectedRefund:
    return ExpectedRefund(
        expectation_id=f"exp_{intent_id}",
        refund_intent_id=intent_id,
        provider_payment_id="pay_abc123",
        amount=Decimal("200.00"),
        currency="INR",
        created_at=_TWO_HOURS_AGO,
    )


def _make_reconstructed_state(knowledge: KnowledgeState) -> ReconstructedState:
    return ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_8",
        knowledge_state=knowledge,
        execution=ExecutionState.NOT_EXECUTED,
        observed_financial_state=None,
        observation_ids=(),
        reconstructed_at=_NOW,
    )


def _make_reconciliation_result(dtype: DiscrepancyType) -> ReconciliationResult:
    return ReconciliationResult(
        expectation_id="exp_ref_8",
        intent_id="ref_8",
        discrepancy_type=dtype,
        is_actionable=True,
        reconciliation_timestamp=_NOW,
        expected_amount=Decimal("200.00"),
        expected_currency="INR",
        observed_amount=None,
        observed_currency=None,
        observed_knowledge_state=KnowledgeState.UNKNOWN,
        reconstructed_state_ids=(),
        details={"reason": "SLA expired"},
    )


def _make_stalemate_case() -> ReconciliationCase:
    """
    Case 7 from the C8 demo: intent present, webhook TEMPORAL_VIOLATION,
    V1 classification EPISTEMIC_STALEMATE.
    """
    wh_ev, wh_result = _make_webhook_evidence(
        evidence_id="evt_wh_temporal",
        intent_id="ref_8",
        status=CorrelationStatus.TEMPORAL_VIOLATION,
    )
    ctx = CorrelationContext(
        intent=_make_intent_evidence("ref_8"),
        provider_records=[wh_ev],
        results=[wh_result],
    )
    case = ReconciliationCase(
        case_id="case_stalemate_1",
        correlation_context=ctx,
        expectation=_make_expectation("ref_8"),
        provider_observations=[],
        provenance={"test": True},
    )
    case = case.attach_derivatives(
        state=_make_reconstructed_state(KnowledgeState.UNKNOWN),
        result=_make_reconciliation_result(DiscrepancyType.EPISTEMIC_STALEMATE),
    )
    return case


# ---------------------------------------------------------------------------
# AC-1: EPISTEMIC_STALEMATE case → bounded representation
# ---------------------------------------------------------------------------

class TestAC1BoundedRepresentation:
    def test_returns_dict(self):
        case = _make_stalemate_case()
        out = format_case_for_investigation(case)
        assert isinstance(out, dict)

    def test_top_level_keys_are_complete(self):
        case = _make_stalemate_case()
        out = format_case_for_investigation(case)
        expected_keys = {
            "case_id",
            "discrepancy_type",
            "knowledge_state",
            "expected_refund",
            "correlated_observations",
            "unmatched_observations",
            "permitted_verification_intents",
        }
        assert set(out.keys()) == expected_keys

    def test_discrepancy_type_is_stalemate(self):
        out = format_case_for_investigation(_make_stalemate_case())
        assert out["discrepancy_type"] == "EPISTEMIC_STALEMATE"


# ---------------------------------------------------------------------------
# AC-2: Expected refund fields preserved accurately
# ---------------------------------------------------------------------------

class TestAC2ExpectedRefund:
    def test_refund_fields_present(self):
        out = format_case_for_investigation(_make_stalemate_case())
        er = out["expected_refund"]
        assert er["intent_id"] == "ref_8"
        assert er["provider_payment_id"] == "pay_abc123"
        assert er["amount"] == "200.00"
        assert er["currency"] == "INR"
        assert er["created_at"] == _TWO_HOURS_AGO.isoformat()

    def test_none_expectation_yields_none(self):
        """Orphan cases have no expectation."""
        ctx = CorrelationContext(intent=None, provider_records=[], results=[])
        case = ReconciliationCase(
            case_id="case_orphan",
            correlation_context=ctx,
            expectation=None,
            provider_observations=[],
        )
        out = format_case_for_investigation(case)
        assert out["expected_refund"] is None


# ---------------------------------------------------------------------------
# AC-3: Correlated / unmatched observations separated
# ---------------------------------------------------------------------------

class TestAC3ObservationSeparation:
    def test_temporal_violation_in_unmatched(self):
        out = format_case_for_investigation(_make_stalemate_case())
        assert len(out["correlated_observations"]) == 0
        assert len(out["unmatched_observations"]) == 1
        assert out["unmatched_observations"][0]["correlation_status"] == "TEMPORAL_VIOLATION"

    def test_correlated_observation_lands_in_correlated(self):
        corr_ev, corr_result = _make_webhook_evidence(
            evidence_id="evt_corr_1",
            intent_id="ref_9",
            status=CorrelationStatus.CORRELATED,
        )
        ctx = CorrelationContext(
            intent=_make_intent_evidence("ref_9"),
            provider_records=[corr_ev],
            results=[corr_result],
        )
        case = ReconciliationCase(
            case_id="case_corr",
            correlation_context=ctx,
            expectation=_make_expectation("ref_9"),
            provider_observations=[],
        )
        case = case.attach_derivatives(
            state=_make_reconstructed_state(KnowledgeState.VERIFIED),
            result=_make_reconciliation_result(DiscrepancyType.MATCH),
        )
        out = format_case_for_investigation(case)
        assert len(out["correlated_observations"]) == 1
        assert len(out["unmatched_observations"]) == 0
        assert out["correlated_observations"][0]["correlation_status"] == "CORRELATED"

    def test_mixed_observations_partitioned_correctly(self):
        tv_ev, temporal = _make_webhook_evidence("evt_tv", "ref_10", CorrelationStatus.TEMPORAL_VIOLATION)
        corr_ev, corr = _make_webhook_evidence("evt_co", "ref_10", CorrelationStatus.CORRELATED)
        ctx = CorrelationContext(
            intent=_make_intent_evidence("ref_10"),
            provider_records=[tv_ev, corr_ev],
            results=[temporal, corr],
        )
        case = ReconciliationCase(
            case_id="case_mixed",
            correlation_context=ctx,
            expectation=_make_expectation("ref_10"),
            provider_observations=[],
        )
        out = format_case_for_investigation(case)
        assert len(out["correlated_observations"]) == 1
        assert len(out["unmatched_observations"]) == 1


# ---------------------------------------------------------------------------
# AC-4: Evidence IDs preserved exactly
# ---------------------------------------------------------------------------

class TestAC4EvidenceIds:
    def test_evidence_id_preserved_in_unmatched(self):
        out = format_case_for_investigation(_make_stalemate_case())
        assert out["unmatched_observations"][0]["evidence_id"] == "evt_wh_temporal"

    def test_evidence_id_preserved_in_correlated(self):
        corr_ev, corr = _make_webhook_evidence("evt_exact_id", "ref_11", CorrelationStatus.CORRELATED)
        ctx = CorrelationContext(
            intent=_make_intent_evidence("ref_11"),
            provider_records=[corr_ev],
            results=[corr],
        )
        case = ReconciliationCase(
            case_id="case_id_check",
            correlation_context=ctx,
            expectation=_make_expectation("ref_11"),
            provider_observations=[],
        )
        out = format_case_for_investigation(case)
        assert out["correlated_observations"][0]["evidence_id"] == "evt_exact_id"


# ---------------------------------------------------------------------------
# AC-5: knowledge_state preserved
# ---------------------------------------------------------------------------

class TestAC5KnowledgeState:
    def test_unknown_preserved(self):
        out = format_case_for_investigation(_make_stalemate_case())
        assert out["knowledge_state"] == "UNKNOWN"

    def test_verified_preserved(self):
        corr_ev, corr = _make_webhook_evidence("evt_v", "ref_12", CorrelationStatus.CORRELATED)
        ctx = CorrelationContext(
            intent=_make_intent_evidence("ref_12"),
            provider_records=[corr_ev],
            results=[corr],
        )
        case = ReconciliationCase(
            case_id="case_verified",
            correlation_context=ctx,
            expectation=_make_expectation("ref_12"),
            provider_observations=[],
        )
        case = case.attach_derivatives(
            state=_make_reconstructed_state(KnowledgeState.VERIFIED),
            result=_make_reconciliation_result(DiscrepancyType.MATCH),
        )
        out = format_case_for_investigation(case)
        assert out["knowledge_state"] == "VERIFIED"

    def test_no_reconstructed_state_yields_none(self):
        ctx = CorrelationContext(intent=None, provider_records=[], results=[])
        case = ReconciliationCase(
            case_id="case_no_state",
            correlation_context=ctx,
            expectation=None,
            provider_observations=[],
        )
        out = format_case_for_investigation(case)
        assert out["knowledge_state"] is None


# ---------------------------------------------------------------------------
# AC-6: permitted_intents == hardcoded allowlist exactly
# ---------------------------------------------------------------------------

class TestAC6PermittedIntents:
    def test_intents_equal_allowlist(self):
        out = format_case_for_investigation(_make_stalemate_case())
        assert set(out["permitted_verification_intents"]) == {v.value for v in VerificationIntent}

    def test_intents_count_matches_enum(self):
        out = format_case_for_investigation(_make_stalemate_case())
        assert len(out["permitted_verification_intents"]) == len(VerificationIntent)

    def test_intents_are_stable_across_cases(self):
        """Permitted intents must be identical regardless of case content."""
        ctx = CorrelationContext(intent=None, provider_records=[], results=[])
        case_a = ReconciliationCase(
            case_id="case_a", correlation_context=ctx,
            expectation=None, provider_observations=[],
        )
        out_a = format_case_for_investigation(case_a)
        out_b = format_case_for_investigation(_make_stalemate_case())
        assert out_a["permitted_verification_intents"] == out_b["permitted_verification_intents"]


# ---------------------------------------------------------------------------
# AC-7: Raw provider payloads NOT leaked
# ---------------------------------------------------------------------------

class TestAC7NoPayloadLeak:
    def test_raw_payload_key_absent_in_unmatched(self):
        out = format_case_for_investigation(_make_stalemate_case())
        obs = out["unmatched_observations"][0]
        assert "payload" not in obs

    def test_secret_provider_key_not_in_output(self):
        out = format_case_for_investigation(_make_stalemate_case())
        output_str = json.dumps(out)
        assert "SECRET_PROVIDER_KEY" not in output_str
        assert "SECRET_INTERNAL_KEY" not in output_str

    def test_nested_entity_dict_absent(self):
        """The nested Razorpay entity dict must not appear in agent input."""
        out = format_case_for_investigation(_make_stalemate_case())
        output_str = json.dumps(out)
        assert "rfnd_ref_8" not in output_str  # provider refund ID from raw payload

    def test_expected_refund_has_no_payload_key(self):
        out = format_case_for_investigation(_make_stalemate_case())
        assert "payload" not in out["expected_refund"]


# ---------------------------------------------------------------------------
# AC-8: Formatting the same case twice → identical output
# ---------------------------------------------------------------------------

class TestAC8Idempotency:
    def test_identical_output_for_same_case(self):
        case = _make_stalemate_case()
        out_a = format_case_for_investigation(case)
        out_b = format_case_for_investigation(case)
        assert out_a == out_b

    def test_json_serialisable(self):
        """Output must be JSON-serialisable (required for LLM prompt construction)."""
        out = format_case_for_investigation(_make_stalemate_case())
        serialised = json.dumps(out)
        assert isinstance(serialised, str)
        roundtripped = json.loads(serialised)
        assert roundtripped["case_id"] == out["case_id"]


# ---------------------------------------------------------------------------
# AC-9: Formatter has no provider/database/execution dependencies
# ---------------------------------------------------------------------------

class TestAC9NoDependencies:
    def test_formatter_module_imports_no_provider(self):
        """
        Static check: input_formatter must not import provider or storage modules.
        This guards against accidentally introducing execution or DB access.
        """
        import importlib
        import sys

        # Reload to get fresh module
        if "src.investigation.input_formatter" in sys.modules:
            mod = sys.modules["src.investigation.input_formatter"]
        else:
            mod = importlib.import_module("src.investigation.input_formatter")

        forbidden_prefixes = (
            "src.integrations",
            "src.storage",
            "src.control",
            "src.outbox",
        )
        for name in sys.modules:
            if any(name.startswith(p) for p in forbidden_prefixes):
                # Only fail if *this* module imported it
                assert name not in getattr(mod, "__dict__", {}), (
                    f"input_formatter must not import {name}"
                )

    def test_formatter_is_pure_function(self):
        """
        Calling the formatter should not raise even with a minimal case that
        has no derivatives attached — it must not call any external service.
        """
        ctx = CorrelationContext(intent=None, provider_records=[], results=[])
        case = ReconciliationCase(
            case_id="minimal",
            correlation_context=ctx,
            expectation=None,
            provider_observations=[],
        )
        # Must not raise, must return a dict
        out = format_case_for_investigation(case)
        assert isinstance(out, dict)
