from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
import pytest

from src.evidence.models import EntityType, ProviderObservation
from src.integrations.provider import ProviderQueryConfidence
from src.reconciliation.engine import reconcile
from src.reconciliation.models import DiscrepancyType, ExpectedRefund, ReconciliationResult
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.state.models import ExecutionState, KnowledgeState, ObservedFinancialState, ReconstructedState


@pytest.fixture
def base_expectation():
    created_at = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    return ExpectedRefund(
        expectation_id="exp_001",
        refund_intent_id="ref_abc123",
        provider_payment_id="pay_xyz789",
        amount=Decimal("500.00"),
        currency="INR",
        created_at=created_at,
        sla_seconds=300,  # Deadline is 12:05:00
        source_system="OMS",
        business_reason="Customer Cancellation",
        originating_trace_id="trace_001",
    )


# ── Test 1: Valid refund → MATCH ─────────────────────────────────────────────
def test_reconciliation_valid_refund_match(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=120)  # 12:02:00
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=ObservedFinancialState.REFUNDED,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.EXECUTED,
        observation_ids=("obs_1",),
        reconstructed_at=t_eval,
    )

    result = reconcile(
        expectation=base_expectation,
        reconstructed_state=state,
        reconciliation_timestamp=t_eval,
        observed_amount=Decimal("500.00"),
        observed_currency="INR",
    )

    assert result.discrepancy_type == DiscrepancyType.MATCH
    assert result.is_clean_match is True
    assert result.is_actionable is False
    assert result.intent_id == "ref_abc123"
    assert result.expectation_id == "exp_001"
    assert result.observed_amount == Decimal("500.00")
    assert result.observed_currency == "INR"


# ── Test 2: Valid refund with amount mismatch → VALUE_MISMATCH ───────────────
def test_reconciliation_amount_mismatch(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=120)
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=ObservedFinancialState.REFUNDED,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.EXECUTED,
        observation_ids=("obs_1",),
        reconstructed_at=t_eval,
    )

    result = reconcile(
        expectation=base_expectation,
        reconstructed_state=state,
        reconciliation_timestamp=t_eval,
        observed_amount=Decimal("400.00"),  # Expected is 500.00
        observed_currency="INR",
    )

    assert result.discrepancy_type == DiscrepancyType.VALUE_MISMATCH
    assert result.is_clean_match is False
    assert result.is_actionable is False  # Requires human escalation, not automated mutation
    assert result.requires_investigation is True


# ── Test 3: Valid refund with currency mismatch → CURRENCY_MISMATCH ──────────
def test_reconciliation_currency_mismatch(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=120)
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=ObservedFinancialState.REFUNDED,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.EXECUTED,
        observation_ids=("obs_1",),
        reconstructed_at=t_eval,
    )

    result = reconcile(
        expectation=base_expectation,
        reconstructed_state=state,
        reconciliation_timestamp=t_eval,
        observed_amount=Decimal("500.00"),
        observed_currency="USD",  # Expected is INR
    )

    assert result.discrepancy_type == DiscrepancyType.CURRENCY_MISMATCH
    assert result.is_clean_match is False
    assert result.is_actionable is False


# ── Test 4: Before SLA with unresolved provider state → IN_FLIGHT_PENDING ────
def test_reconciliation_before_sla_unresolved_in_flight_pending(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=60)  # 12:01:00 < 12:05:00
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        execution=None,
        observation_ids=(),
        reconstructed_at=t_eval,
    )

    result = reconcile(
        expectation=base_expectation,
        reconstructed_state=state,
        reconciliation_timestamp=t_eval,
    )

    assert result.discrepancy_type == DiscrepancyType.IN_FLIGHT_PENDING
    assert result.is_actionable is False
    assert result.is_clean_match is False


# ── Test 5: After SLA + UNKNOWN → EPISTEMIC_STALEMATE ────────────────────────
def test_reconciliation_after_sla_unknown_epistemic_stalemate(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=360)  # 12:06:00 >= 12:05:00
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        execution=None,
        observation_ids=(),
        reconstructed_at=t_eval,
    )

    result = reconcile(
        expectation=base_expectation,
        reconstructed_state=state,
        reconciliation_timestamp=t_eval,
    )

    assert result.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE
    assert result.is_actionable is True  # Actionable via diagnostic query probe
    assert result.is_clean_match is False


# ── Test 6: After SLA + CONTRADICTED → EPISTEMIC_STALEMATE ───────────────────
def test_reconciliation_after_sla_contradicted_epistemic_stalemate(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=400)
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.CONTRADICTED,
        execution=None,
        observation_ids=("obs_a", "obs_b"),
        reconstructed_at=t_eval,
    )

    result = reconcile(
        expectation=base_expectation,
        reconstructed_state=state,
        reconciliation_timestamp=t_eval,
    )

    assert result.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE
    assert result.observed_knowledge_state == KnowledgeState.CONTRADICTED


# ── Test 7: After SLA + VERIFIED + NOT_EXECUTED → ABSENT_EXECUTION ───────────
def test_reconciliation_after_sla_verified_not_executed_absent_execution(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=400)  # Past deadline
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.NOT_EXECUTED,
        observation_ids=("obs_authoritative_probe",),
        reconstructed_at=t_eval,
    )

    result = reconcile(
        expectation=base_expectation,
        reconstructed_state=state,
        reconciliation_timestamp=t_eval,
    )

    assert result.discrepancy_type == DiscrepancyType.ABSENT_EXECUTION
    assert result.is_actionable is True  # Actionable for V1 Control Policy evaluation
    assert result.observed_knowledge_state == KnowledgeState.VERIFIED


# ── Test 8: Multiple matching executions → EXCESS_EFFECT ─────────────────────
def test_reconciliation_multiple_executions_excess_effect(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=200)
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=ObservedFinancialState.REFUNDED,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.EXECUTED,
        observation_ids=("obs_1", "obs_2"),
        reconstructed_at=t_eval,
    )

    result = reconcile(
        expectation=base_expectation,
        reconstructed_state=state,
        reconciliation_timestamp=t_eval,
        observed_amount=Decimal("500.00"),
        matching_executions_count=2,  # Cardinality violation!
    )

    assert result.discrepancy_type == DiscrepancyType.EXCESS_EFFECT
    assert result.is_actionable is False  # Emergency containment, no mutation
    assert result.requires_investigation is True


# ── Test 9: Provider execution with no internal expectation → ORPHANED_EXECUTION
def test_reconciliation_orphaned_execution():
    t_eval = datetime(2026, 9, 3, 14, 0, 0, tzinfo=timezone.utc)
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_rogue_999",
        observed_financial_state=ObservedFinancialState.REFUNDED,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.EXECUTED,
        observation_ids=("obs_ext_1",),
        reconstructed_at=t_eval,
    )

    result = reconcile(
        expectation=None,
        reconstructed_state=state,
        reconciliation_timestamp=t_eval,
        observed_amount=Decimal("120.00"),
        observed_currency="INR",
    )

    assert result.discrepancy_type == DiscrepancyType.ORPHANED_EXECUTION
    assert result.expectation_id is None
    assert result.intent_id == "ref_rogue_999"
    assert result.is_actionable is False


# ── Test 10: Determinism: Identical inputs produce identical output ──────────
def test_reconciliation_determinism(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=600)
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.NOT_EXECUTED,
        observation_ids=("obs_1",),
        reconstructed_at=t_eval,
    )

    res1 = reconcile(base_expectation, state, t_eval)
    res2 = reconcile(base_expectation, state, t_eval)

    assert res1 == res2
    assert hash(res1) == hash(res2)


# ── Test 11: Reconciler never accesses system clock or performs I/O ──────────
def test_reconciliation_zero_clock_access(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=100)
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        execution=None,
        observation_ids=(),
        reconstructed_at=t_eval,
    )

    # Patch datetime.now and builtins.open to guarantee no clock access and no I/O
    with patch("src.reconciliation.engine.datetime") as mock_dt, patch("builtins.open") as mock_open:
        # reconcile only uses the passed reconciliation_timestamp
        res = reconcile(base_expectation, state, t_eval)
        assert mock_dt.now.called is False
        assert mock_open.called is False
        assert res.discrepancy_type == DiscrepancyType.IN_FLIGHT_PENDING


# ── Test 12: Identity fields are preserved exactly ───────────────────────────
def test_reconciliation_identity_preservation(base_expectation):
    t_eval = base_expectation.created_at + timedelta(seconds=100)
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=ObservedFinancialState.REFUNDED,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.EXECUTED,
        observation_ids=("obs_id_unique_123",),
        reconstructed_at=t_eval,
    )

    res = reconcile(base_expectation, state, t_eval)
    assert res.expectation_id == base_expectation.expectation_id
    assert res.intent_id == base_expectation.intent_id
    assert res.reconstructed_state_ids == ("obs_id_unique_123",)


# ── Adversarial Property: UNKNOWN NEVER produces ABSENT_EXECUTION ────────────
@pytest.mark.parametrize("seconds_past_deadline", [1, 60, 3600, 86400])
def test_adversarial_unknown_never_produces_absent_execution(base_expectation, seconds_past_deadline):
    t_eval = base_expectation.reconciliation_deadline() + timedelta(seconds=seconds_past_deadline)
    
    # State with UNKNOWN knowledge state
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ref_abc123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        execution=None,
        observation_ids=(),
        reconstructed_at=t_eval,
    )

    res = reconcile(base_expectation, state, t_eval)
    assert res.discrepancy_type != DiscrepancyType.ABSENT_EXECUTION
    assert res.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE


# ── Adversarial Property: QUERY_FAILURE → UNKNOWN → EPISTEMIC_STALEMATE ──────
def test_adversarial_query_failure_produces_epistemic_stalemate(base_expectation):
    """
    Demonstrates integration with StateEngine:
    A failed query (QUERY_FAILED) leaves ReconstructedState in UNKNOWN.
    Reconciler must produce EPISTEMIC_STALEMATE past deadline.
    """
    engine = StateEngine()
    ordering_policy = TemporalOrderingPolicy()
    t_eval = base_expectation.reconciliation_deadline() + timedelta(seconds=30)

    # Ingest query failure observation
    obs = ProviderObservation(
        provider="razorpay",
        event_id="evt_query_fail",
        entity_type=EntityType.REFUND_INTENT.value,
        entity_id=base_expectation.intent_id,
        event_type="REFUND_STATUS_QUERY",
        payload={"query_confidence": ProviderQueryConfidence.QUERY_FAILED.value},
    )

    state = engine.reconstruct_state(
        entity_type=EntityType.REFUND_INTENT,
        entity_id=base_expectation.intent_id,
        observations=[obs],
        reconstructed_at=t_eval,
        ordering_policy=ordering_policy,
    )

    assert state.knowledge_state == KnowledgeState.UNKNOWN
    res = reconcile(base_expectation, state, t_eval)
    assert res.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE


# ── Adversarial Property: AMBIGUOUS_DISPATCH → UNKNOWN → NO_AUTOMATIC_RETRY ──
def test_adversarial_ambiguous_dispatch_does_not_permit_automatic_retry(base_expectation):
    """
    An ambiguous dispatch (network timeout) leaves state UNKNOWN.
    Reconciler emits EPISTEMIC_STALEMATE.
    The discrepancy cannot be passed to evaluate_refund_eligibility as an absent refund,
    preventing any duplicate mutation!
    """
    t_eval = base_expectation.reconciliation_deadline() + timedelta(seconds=60)
    state = ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id=base_expectation.intent_id,
        observed_financial_state=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        execution=None,
        observation_ids=(),
        reconstructed_at=t_eval,
    )

    res = reconcile(base_expectation, state, t_eval)
    assert res.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE
    assert res.discrepancy_type != DiscrepancyType.ABSENT_EXECUTION
    # Since it is not ABSENT_EXECUTION, the upstream pipeline routes it to
    # uncertainty probe, NOT to evaluate_refund_eligibility.
