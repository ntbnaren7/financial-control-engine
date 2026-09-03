from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from src.state.models import ExecutionState, KnowledgeState, ObservedFinancialState, ReconstructedState
from .models import DiscrepancyType, ExpectedRefund, FinancialExpectation, ReconciliationResult


def reconcile(
    expectation: Optional[FinancialExpectation],
    reconstructed_state: Optional[ReconstructedState],
    reconciliation_timestamp: datetime,
    observed_amount: Optional[Decimal] = None,
    observed_currency: Optional[str] = None,
    matching_executions_count: int = 1,
) -> ReconciliationResult:
    """
    Pure deterministic reconciliation function mapping an internal expectation and
    an observed provider reconstructed state to a typed ReconciliationResult.

    Hard Guarantees:
    - Side-effect free, deterministic, no network/DB calls, no system clock access.
    - UNKNOWN or absent evidence NEVER produces ABSENT_EXECUTION.
    - ABSENT_EXECUTION strictly requires deadline expiry + VERIFIED + NOT_EXECUTED.
    - CONTRADICTED strictly demotes to EPISTEMIC_STALEMATE.
    - Strict 1:1 cardinality enforced for V1; multiple executions produce EXCESS_EFFECT.
    - Classifies only; never mutates or authorizes actions directly.
    """
    if expectation is None and reconstructed_state is None:
        raise ValueError("At least one of expectation or reconstructed_state must be provided")

    if reconciliation_timestamp.tzinfo is None:
        raise ValueError("reconciliation_timestamp must be timezone-aware (UTC)")

    # ── 1. Orphaned Execution (Provider reality with no internal intent) ──────
    if expectation is None:
        assert reconstructed_state is not None
        obs_ids = reconstructed_state.observation_ids
        is_executed = (
            reconstructed_state.execution == ExecutionState.EXECUTED
            or reconstructed_state.observed_financial_state == ObservedFinancialState.REFUNDED
        )
        discrepancy = DiscrepancyType.ORPHANED_EXECUTION if is_executed else DiscrepancyType.EPISTEMIC_STALEMATE
        return ReconciliationResult(
            expectation_id=None,
            intent_id=reconstructed_state.entity_id,
            discrepancy_type=discrepancy,
            is_actionable=False,
            reconciliation_timestamp=reconciliation_timestamp,
            expected_amount=None,
            expected_currency=None,
            observed_amount=observed_amount,
            observed_currency=observed_currency,
            observed_knowledge_state=reconstructed_state.knowledge_state,
            reconstructed_state_ids=obs_ids,
            details={
                "reason": "Provider execution exists with no matching internal expectation"
                if is_executed
                else "Unmatched provider state without execution"
            },
        )

    # ── 2. Expectation with Zero Provider Evidence ────────────────────────────
    if reconstructed_state is None:
        deadline = expectation.reconciliation_deadline()
        is_past_deadline = reconciliation_timestamp >= deadline
        discrepancy = DiscrepancyType.EPISTEMIC_STALEMATE if is_past_deadline else DiscrepancyType.IN_FLIGHT_PENDING
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            intent_id=expectation.intent_id,
            discrepancy_type=discrepancy,
            is_actionable=is_past_deadline,  # Actionable via query probe once SLA expires
            reconciliation_timestamp=reconciliation_timestamp,
            expected_amount=expectation.expected_amount,
            expected_currency=expectation.currency,
            observed_amount=None,
            observed_currency=None,
            observed_knowledge_state=KnowledgeState.UNKNOWN,
            reconstructed_state_ids=(),
            details={
                "reason": "Zero provider observations recorded",
                "is_past_deadline": is_past_deadline,
                "deadline": deadline.isoformat(),
            },
        )

    # ── 3. Correlation Scope Verification ─────────────────────────────────────
    if reconstructed_state.entity_id != expectation.intent_id:
        raise ValueError(
            f"Mismatched intent correlation: expectation intent {expectation.intent_id} "
            f"does not match reconstructed_state entity {reconstructed_state.entity_id}"
        )

    obs_ids = reconstructed_state.observation_ids

    # ── 4. Cardinality Check (Strict 1:1 Invariant for V1) ─────────────────────
    is_executed = (
        reconstructed_state.execution == ExecutionState.EXECUTED
        or reconstructed_state.observed_financial_state == ObservedFinancialState.REFUNDED
    )
    if matching_executions_count > 1 and is_executed:
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            intent_id=expectation.intent_id,
            discrepancy_type=DiscrepancyType.EXCESS_EFFECT,
            is_actionable=False,  # High severity operational escalation
            reconciliation_timestamp=reconciliation_timestamp,
            expected_amount=expectation.expected_amount,
            expected_currency=expectation.currency,
            observed_amount=observed_amount,
            observed_currency=observed_currency,
            observed_knowledge_state=reconstructed_state.knowledge_state,
            reconstructed_state_ids=obs_ids,
            details={
                "reason": f"Detected {matching_executions_count} executions for single intent",
                "matching_executions_count": matching_executions_count,
            },
        )

    # ── 5. Terminal State Invariant Violations ────────────────────────────────
    if (
        reconstructed_state.knowledge_state == KnowledgeState.VERIFIED
        and reconstructed_state.observed_financial_state == ObservedFinancialState.FAILED
    ):
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            intent_id=expectation.intent_id,
            discrepancy_type=DiscrepancyType.CONTRADICTORY_TERMINALITY,
            is_actionable=False,
            reconciliation_timestamp=reconciliation_timestamp,
            expected_amount=expectation.expected_amount,
            expected_currency=expectation.currency,
            observed_amount=observed_amount,
            observed_currency=observed_currency,
            observed_knowledge_state=reconstructed_state.knowledge_state,
            reconstructed_state_ids=obs_ids,
            details={"reason": "Provider recorded terminal failure for mutation"},
        )

    # ── 6. Verified Execution Invariants (Amount, Currency, Match) ───────────
    if (
        reconstructed_state.knowledge_state == KnowledgeState.VERIFIED
        and is_executed
    ):
        eff_currency = observed_currency.strip().upper() if observed_currency else expectation.currency
        eff_amount = observed_amount if observed_amount is not None else expectation.expected_amount

        if observed_currency and observed_currency.strip().upper() != expectation.currency.strip().upper():
            return ReconciliationResult(
                expectation_id=expectation.expectation_id,
                intent_id=expectation.intent_id,
                discrepancy_type=DiscrepancyType.CURRENCY_MISMATCH,
                is_actionable=False,
                reconciliation_timestamp=reconciliation_timestamp,
                expected_amount=expectation.expected_amount,
                expected_currency=expectation.currency,
                observed_amount=eff_amount,
                observed_currency=eff_currency,
                observed_knowledge_state=reconstructed_state.knowledge_state,
                reconstructed_state_ids=obs_ids,
                details={
                    "reason": f"Currency mismatch: expected {expectation.currency} but observed {observed_currency}"
                },
            )

        if observed_amount is not None and observed_amount != expectation.expected_amount:
            return ReconciliationResult(
                expectation_id=expectation.expectation_id,
                intent_id=expectation.intent_id,
                discrepancy_type=DiscrepancyType.VALUE_MISMATCH,
                is_actionable=False,
                reconciliation_timestamp=reconciliation_timestamp,
                expected_amount=expectation.expected_amount,
                expected_currency=expectation.currency,
                observed_amount=eff_amount,
                observed_currency=eff_currency,
                observed_knowledge_state=reconstructed_state.knowledge_state,
                reconstructed_state_ids=obs_ids,
                details={
                    "reason": f"Value mismatch: expected {expectation.expected_amount} but observed {observed_amount}"
                },
            )

        # Clean match
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            intent_id=expectation.intent_id,
            discrepancy_type=DiscrepancyType.MATCH,
            is_actionable=False,
            reconciliation_timestamp=reconciliation_timestamp,
            expected_amount=expectation.expected_amount,
            expected_currency=expectation.currency,
            observed_amount=eff_amount,
            observed_currency=eff_currency,
            observed_knowledge_state=reconstructed_state.knowledge_state,
            reconstructed_state_ids=obs_ids,
            details={"reason": "Expectation satisfied by provider execution"},
        )

    # ── 7. Unexecuted States: Temporal & Epistemic Evaluation ────────────────
    deadline = expectation.reconciliation_deadline()
    is_past_deadline = reconciliation_timestamp >= deadline

    # Before SLA deadline, any unexecuted/unresolved state is IN_FLIGHT_PENDING
    if not is_past_deadline:
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            intent_id=expectation.intent_id,
            discrepancy_type=DiscrepancyType.IN_FLIGHT_PENDING,
            is_actionable=False,
            reconciliation_timestamp=reconciliation_timestamp,
            expected_amount=expectation.expected_amount,
            expected_currency=expectation.currency,
            observed_amount=observed_amount,
            observed_currency=observed_currency,
            observed_knowledge_state=reconstructed_state.knowledge_state,
            reconstructed_state_ids=obs_ids,
            details={
                "reason": "Within SLA grace period; awaiting provider execution",
                "deadline": deadline.isoformat(),
            },
        )

    # Past SLA deadline (reconciliation_timestamp >= deadline):
    # ABSENT_EXECUTION strictly requires:
    # 1. KnowledgeState == VERIFIED
    # 2. ExecutionState == NOT_EXECUTED
    # 3. observed_financial_state is None
    if (
        reconstructed_state.knowledge_state == KnowledgeState.VERIFIED
        and reconstructed_state.execution == ExecutionState.NOT_EXECUTED
        and reconstructed_state.observed_financial_state is None
    ):
        return ReconciliationResult(
            expectation_id=expectation.expectation_id,
            intent_id=expectation.intent_id,
            discrepancy_type=DiscrepancyType.ABSENT_EXECUTION,
            is_actionable=True,  # Actionable by V1 Control Policy evaluation
            reconciliation_timestamp=reconciliation_timestamp,
            expected_amount=expectation.expected_amount,
            expected_currency=expectation.currency,
            observed_amount=None,
            observed_currency=None,
            observed_knowledge_state=KnowledgeState.VERIFIED,
            reconstructed_state_ids=obs_ids,
            details={
                "reason": "SLA expired and authoritative provider lookup confirmed NOT_EXECUTED",
                "deadline": deadline.isoformat(),
            },
        )

    # If past deadline but evidence is UNKNOWN, CONTRADICTED, or non-authoritative:
    # MUST strictly remain EPISTEMIC_STALEMATE.
    return ReconciliationResult(
        expectation_id=expectation.expectation_id,
        intent_id=expectation.intent_id,
        discrepancy_type=DiscrepancyType.EPISTEMIC_STALEMATE,
        is_actionable=True,  # Actionable by diagnostic query probe
        reconciliation_timestamp=reconciliation_timestamp,
        expected_amount=expectation.expected_amount,
        expected_currency=expectation.currency,
        observed_amount=observed_amount,
        observed_currency=observed_currency,
        observed_knowledge_state=reconstructed_state.knowledge_state,
        reconstructed_state_ids=obs_ids,
        details={
            "reason": "SLA expired but provider knowledge is UNKNOWN or CONTRADICTED; proof of absence incomplete",
            "knowledge_state": reconstructed_state.knowledge_state.value,
            "deadline": deadline.isoformat(),
        },
    )
