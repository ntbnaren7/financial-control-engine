"""
D6 Acceptance Tests — Investigation Loop

Validates that the orchestration loop strictly sequences components,
does not loop infinitely, does not bypass safety layers, and delegates
all truth/resolution back to the V1 reconciliation engine.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.cases.models import ReconciliationCase
from src.domain.correlation.models import CorrelationContext
from src.domain.evidence.models import Evidence
from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationIntent,
    ValidationRejection,
    ValidationRejectionReason,
    VerificationRejection,
    VerificationRejectionReason,
)
from src.evidence.models import ProviderObservation
from src.investigation.agent import Investigator
from src.investigation.loop import InvestigationLoop
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.reconciliation.models import DiscrepancyType, ExpectedRefund, ReconciliationResult
from src.state.engine import ExecutionState, KnowledgeState, StateEngine, TemporalOrderingPolicy
from src.state.models import ReconstructedState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_investigator() -> MagicMock:
    return MagicMock(spec=Investigator)


@pytest.fixture
def mock_validator() -> MagicMock:
    return MagicMock(spec=OutputValidator)


@pytest.fixture
def mock_verifier() -> AsyncMock:
    return AsyncMock(spec=DeterministicVerifier)


@pytest.fixture
def state_engine() -> StateEngine:
    return StateEngine()


@pytest.fixture
def ordering_policy() -> TemporalOrderingPolicy:
    return TemporalOrderingPolicy()


@pytest.fixture
def investigation_loop(
    mock_investigator: MagicMock,
    mock_validator: MagicMock,
    mock_verifier: AsyncMock,
    state_engine: StateEngine,
    ordering_policy: TemporalOrderingPolicy,
) -> InvestigationLoop:
    return InvestigationLoop(
        investigator=mock_investigator,
        validator=mock_validator,
        verifier=mock_verifier,
        state_engine=state_engine,
        ordering_policy=ordering_policy,
    )


@pytest.fixture
def current_time() -> datetime.datetime:
    return datetime.datetime(2026, 9, 3, 12, 0, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def stalemate_case(current_time: datetime.datetime) -> ReconciliationCase:
    expectation = ExpectedRefund(
        refund_intent_id="ref_8",
        provider_payment_id="pay_abc123",
        amount=Decimal("200.00"),
        currency="INR",
        created_at=current_time - datetime.timedelta(hours=1),
    )
    # Give it an initial result indicating stalemate
    initial_result = ReconciliationResult(
        expectation_id=expectation.expectation_id,
        intent_id=expectation.intent_id,
        discrepancy_type=DiscrepancyType.EPISTEMIC_STALEMATE,
        is_actionable=True,
        reconciliation_timestamp=current_time,
        expected_amount=expectation.amount,
        expected_currency=expectation.currency,
        observed_amount=None,
        observed_currency=None,
        observed_knowledge_state=KnowledgeState.UNKNOWN,
        reconstructed_state_ids=(),
    )
    
    case = ReconciliationCase(
        correlation_context=CorrelationContext(),
        expectation=expectation,
        provider_observations=[],
    )
    # attach_derivatives creates a new instance, so we return that
    state = ReconstructedState(
        entity_type=expectation.entity_type,
        entity_id=expectation.intent_id,
        observed_financial_state=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        execution=None,
        observation_ids=(),
        reconstructed_at=current_time,
    )
    return case.attach_derivatives(state, initial_result)


@pytest.fixture
def dummy_hypothesis() -> CausalHypothesis:
    return CausalHypothesis.model_validate({
        "hypothesis": "Test",
        "supporting_evidence_ids": [],
        "contradicting_evidence_ids": [],
        "missing_evidence_description": "None",
        "confidence": "MEDIUM",
        "disposition": InvestigationDisposition.VERIFICATION_PROPOSED.value,
        "verification_intent": VerificationIntent.QUERY_PROVIDER_REFUND.value,
    })


@pytest.fixture
def resolved_evidence(current_time: datetime.datetime) -> Evidence:
    return Evidence(
        evidence_id="evt_123",
        source="razorpay_api",
        entity_id="ref_8",
        timestamp=current_time,
        evidence_type="RAZORPAY_API_REFUND_PROCESSED",
        payload={"status": "refunded", "id": "rfnd_abc"},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_d6_only_starts_from_stalemate(
    investigation_loop: InvestigationLoop,
    stalemate_case: ReconciliationCase,
    current_time: datetime.datetime,
    mock_investigator: MagicMock,
):
    # Alter case to MATCH
    match_result = ReconciliationResult(
        expectation_id="1", intent_id="ref_8", discrepancy_type=DiscrepancyType.MATCH,
        is_actionable=False, reconciliation_timestamp=current_time, expected_amount=Decimal("200.00"),
        expected_currency="INR", observed_amount=Decimal("200.00"), observed_currency="INR",
        observed_knowledge_state=KnowledgeState.VERIFIED, reconstructed_state_ids=()
    )
    case_match = stalemate_case.attach_derivatives(stalemate_case.reconstructed_state, match_result) # type: ignore

    result = await investigation_loop.investigate_stalemate(case_match, current_time)

    # Returns the original result without calling the investigator
    assert result is match_result
    mock_investigator.investigate.assert_not_called()


@pytest.mark.asyncio
async def test_d6_one_cycle_per_invocation(
    investigation_loop: InvestigationLoop,
    stalemate_case: ReconciliationCase,
    current_time: datetime.datetime,
    mock_investigator: MagicMock,
    mock_validator: MagicMock,
    mock_verifier: AsyncMock,
    dummy_hypothesis: CausalHypothesis,
):
    """
    D6-2 and D6-7: Does not loop recursively if the outcome remains stalemate.
    """
    mock_investigator.investigate.return_value = dummy_hypothesis
    mock_validator.validate.return_value = dummy_hypothesis
    # Verifier returns no new evidence
    mock_verifier.verify.return_value = []

    result = await investigation_loop.investigate_stalemate(stalemate_case, current_time)

    # Returns the original result, only called once
    assert result is stalemate_case.reconciliation_result
    assert mock_investigator.investigate.call_count == 1
    assert mock_verifier.verify.call_count == 1


@pytest.mark.asyncio
async def test_d6_no_llm_output_bypasses_d4_d5(
    investigation_loop: InvestigationLoop,
    stalemate_case: ReconciliationCase,
    current_time: datetime.datetime,
    mock_investigator: MagicMock,
    mock_validator: MagicMock,
    mock_verifier: AsyncMock,
    dummy_hypothesis: CausalHypothesis,
):
    mock_investigator.investigate.return_value = dummy_hypothesis
    
    # Validator rejects
    rejection = ValidationRejection(
        reason=ValidationRejectionReason.SCHEMA_INVALID,
        detail="Bad schema",
        raw_output={}
    )
    mock_validator.validate.return_value = rejection

    result = await investigation_loop.investigate_stalemate(stalemate_case, current_time)

    # D5 should not be called because D4 rejected it
    mock_verifier.verify.assert_not_called()
    assert result is stalemate_case.reconciliation_result


@pytest.mark.asyncio
async def test_d6_delegates_to_v1_for_truth(
    investigation_loop: InvestigationLoop,
    stalemate_case: ReconciliationCase,
    current_time: datetime.datetime,
    mock_investigator: MagicMock,
    mock_validator: MagicMock,
    mock_verifier: AsyncMock,
    dummy_hypothesis: CausalHypothesis,
    resolved_evidence: Evidence,
):
    """
    D6-4, D6-5, D6-6: D6 does not interpret hypothesis or resolve MATCH/ABSENT itself.
    It passes the evidence to V1, which determines the new state.
    """
    mock_investigator.investigate.return_value = dummy_hypothesis
    mock_validator.validate.return_value = dummy_hypothesis
    mock_verifier.verify.return_value = [resolved_evidence]

    result = await investigation_loop.investigate_stalemate(stalemate_case, current_time)

    # V1 (StateEngine + reconcile) processes the evidence and resolves to MATCH
    assert result is not None
    assert result.discrepancy_type == DiscrepancyType.MATCH
    assert result.observed_knowledge_state == KnowledgeState.VERIFIED


@pytest.mark.asyncio
async def test_d6_provider_failure_is_not_evidence(
    investigation_loop: InvestigationLoop,
    stalemate_case: ReconciliationCase,
    current_time: datetime.datetime,
    mock_investigator: MagicMock,
    mock_validator: MagicMock,
    mock_verifier: AsyncMock,
    dummy_hypothesis: CausalHypothesis,
):
    mock_investigator.investigate.return_value = dummy_hypothesis
    mock_validator.validate.return_value = dummy_hypothesis
    
    # Verifier fails
    rejection = VerificationRejection(
        reason=VerificationRejectionReason.PROVIDER_ERROR,
        detail="Timeout",
        hypothesis=dummy_hypothesis
    )
    mock_verifier.verify.return_value = rejection

    result = await investigation_loop.investigate_stalemate(stalemate_case, current_time)

    # Original stalemate result is returned, no mutation to V1
    assert result is stalemate_case.reconciliation_result


@pytest.mark.asyncio
async def test_d6_overarching_invariant_identical_hypothesis_text_identical_outcome(
    investigation_loop: InvestigationLoop,
    stalemate_case: ReconciliationCase,
    current_time: datetime.datetime,
    mock_investigator: MagicMock,
    mock_validator: MagicMock,
    mock_verifier: AsyncMock,
    resolved_evidence: Evidence,
):
    """
    The most important D6 property:
    Given identical trusted case + identical verifier result, D6's final 
    classification is identical regardless of what hypothesis the LLM generated.
    """
    # LLM outputs completely different prose
    hyp1 = CausalHypothesis.model_validate({
        "hypothesis": "I think it refunded.",
        "supporting_evidence_ids": [],
        "contradicting_evidence_ids": [],
        "missing_evidence_description": "None",
        "confidence": "HIGH",
        "disposition": "VERIFICATION_PROPOSED",
        "verification_intent": "QUERY_PROVIDER_REFUND"
    })
    
    hyp2 = CausalHypothesis.model_validate({
        "hypothesis": "Wait, no, it might be an error.",
        "supporting_evidence_ids": [],
        "contradicting_evidence_ids": [],
        "missing_evidence_description": "None",
        "confidence": "LOW",
        "disposition": "VERIFICATION_PROPOSED",
        "verification_intent": "QUERY_PROVIDER_REFUND"
    })

    # Run Cycle 1
    mock_investigator.investigate.return_value = hyp1
    mock_validator.validate.return_value = hyp1
    mock_verifier.verify.return_value = [resolved_evidence]
    result1 = await investigation_loop.investigate_stalemate(stalemate_case, current_time)

    # Run Cycle 2
    mock_investigator.investigate.return_value = hyp2
    mock_validator.validate.return_value = hyp2
    mock_verifier.verify.return_value = [resolved_evidence]
    result2 = await investigation_loop.investigate_stalemate(stalemate_case, current_time)

    assert result1 is not None
    assert result2 is not None
    
    # Both lead to the exact same V1 reconciliation output
    assert result1.discrepancy_type == result2.discrepancy_type == DiscrepancyType.MATCH
    assert result1.observed_knowledge_state == result2.observed_knowledge_state == KnowledgeState.VERIFIED
    # Ensure they aren't somehow the original stalemate result
    assert result1.discrepancy_type != DiscrepancyType.EPISTEMIC_STALEMATE
