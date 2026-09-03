"""
D5 Acceptance Tests — DeterministicVerifier

Acceptance criteria:
  D5-1  Exhausted disposition rejected
  D5-2  Valid intent executes correct read-only query
  D5-3  Query parameter comes only from trusted case
  D5-4  LLM-supplied IDs cannot influence query (strong isolation invariant)
  D5-5  Unknown/unsupported capability cannot execute
  D5-6  Provider response passes through Phase C normalization
  D5-7  No direct ProviderObservation construction
  D5-8  No mutation APIs/imports
  D5-9  Provider failure cannot manufacture evidence
  D5-10 Verifier doesn't perform V1 classification
"""

from __future__ import annotations

import importlib
import sys
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from datetime import datetime
from decimal import Decimal

from src.domain.cases.models import ReconciliationCase
from src.domain.correlation.models import CorrelationContext
from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationIntent,
    VerificationRejection,
    VerificationRejectionReason,
)
from src.domain.evidence.models import Evidence
from src.integrations.razorpay.client import RazorpayClient
from src.investigation.verifier import DeterministicVerifier
from src.reconciliation.models import ExpectedRefund

# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_razorpay_client() -> AsyncMock:
    client = AsyncMock(spec=RazorpayClient)
    return client


@pytest.fixture
def verifier(mock_razorpay_client: AsyncMock) -> DeterministicVerifier:
    return DeterministicVerifier(razorpay_client=mock_razorpay_client)


@pytest.fixture
def trusted_case() -> ReconciliationCase:
    return ReconciliationCase(
        correlation_context=CorrelationContext(),
        expectation=ExpectedRefund(
            refund_intent_id="ref_8",
            provider_payment_id="pay_abc123",
            amount=Decimal("200.00"),
            currency="INR",
            created_at=datetime.fromisoformat("2026-09-03T06:00:00+00:00"),
        ),
        provider_observations=[],
    )


def make_hypothesis(
    intent: VerificationIntent | None,
    disposition: InvestigationDisposition = InvestigationDisposition.VERIFICATION_PROPOSED,
    **kwargs: Any,
) -> CausalHypothesis:
    data = {
        "hypothesis": kwargs.get("hypothesis", "Default hypothesis"),
        "supporting_evidence_ids": kwargs.get("supporting_evidence_ids", []),
        "contradicting_evidence_ids": kwargs.get("contradicting_evidence_ids", []),
        "missing_evidence_description": "Default missing evidence",
        "confidence": "MEDIUM",
        "disposition": disposition.value,
        "verification_intent": intent.value if intent else None,
    }
    return CausalHypothesis.model_validate(data)


# Dummy model for Razorpay refund response
class DummyRazorpayRefund:
    def __init__(self, **kwargs: Any):
        self.kwargs = kwargs
        self.receipt = kwargs.get("receipt", "ref_8")

    def model_dump(self) -> dict[str, Any]:
        return self.kwargs


class DummyRazorpayPayment:
    def __init__(self, **kwargs: Any):
        self.kwargs = kwargs

    def model_dump(self) -> dict[str, Any]:
        return self.kwargs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_d5_1_exhausted_disposition_rejected(
    verifier: DeterministicVerifier, trusted_case: ReconciliationCase
):
    hypothesis = make_hypothesis(
        intent=None, disposition=InvestigationDisposition.INVESTIGATION_EXHAUSTED
    )
    result = await verifier.verify(hypothesis, trusted_case)

    assert isinstance(result, VerificationRejection)
    assert result.reason == VerificationRejectionReason.EXHAUSTED


@pytest.mark.asyncio
async def test_d5_2_valid_intent_executes_correct_read_only_query(
    verifier: DeterministicVerifier, mock_razorpay_client: AsyncMock, trusted_case: ReconciliationCase
):
    hypothesis = make_hypothesis(intent=VerificationIntent.QUERY_PROVIDER_REFUND)
    mock_razorpay_client.get_payment_refunds.return_value = [
        DummyRazorpayRefund(id="rfnd_123", status="processed", receipt="ref_8")
    ]

    result = await verifier.verify(hypothesis, trusted_case)

    # Executed read-only query
    mock_razorpay_client.get_payment_refunds.assert_called_once_with("pay_abc123")
    mock_razorpay_client.create_refund.assert_not_called()

    # Returns evidence
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], Evidence)


@pytest.mark.asyncio
async def test_d5_3_query_parameter_comes_only_from_trusted_case(
    verifier: DeterministicVerifier, mock_razorpay_client: AsyncMock, trusted_case: ReconciliationCase
):
    hypothesis = make_hypothesis(intent=VerificationIntent.QUERY_PROVIDER_PAYMENT)
    mock_razorpay_client.get_payment.return_value = DummyRazorpayPayment(id="pay_abc123", status="captured")

    await verifier.verify(hypothesis, trusted_case)

    # payment_id must match the case expectation exactly
    mock_razorpay_client.get_payment.assert_called_once_with("pay_abc123")


@pytest.mark.asyncio
async def test_d5_4_llm_supplied_ids_cannot_influence_query(
    verifier: DeterministicVerifier, mock_razorpay_client: AsyncMock, trusted_case: ReconciliationCase
):
    """
    Strong isolation invariant:
    Changing every LLM-controlled textual field produces exactly the same provider query.
    """
    mock_razorpay_client.get_payment_refunds.return_value = []

    # LLM A
    hyp_a = make_hypothesis(
        intent=VerificationIntent.QUERY_PROVIDER_REFUND,
        hypothesis="refund was executed late",
        supporting_evidence_ids=["evt_1"],
    )
    await verifier.verify(hyp_a, trusted_case)

    # LLM B
    hyp_b = make_hypothesis(
        intent=VerificationIntent.QUERY_PROVIDER_REFUND,
        hypothesis="refund was actually for another customer",
        supporting_evidence_ids=["evt_2"],
    )
    await verifier.verify(hyp_b, trusted_case)

    # LLM C (attempting to inject an ID)
    hyp_c = make_hypothesis(
        intent=VerificationIntent.QUERY_PROVIDER_REFUND,
        hypothesis="query ref_999",
        supporting_evidence_ids=["ref_999"],
    )
    await verifier.verify(hyp_c, trusted_case)

    # The verifier MUST have called the provider exactly 3 times,
    # and EVERY TIME it must have used "pay_abc123" from the case.
    assert mock_razorpay_client.get_payment_refunds.call_count == 3
    for call in mock_razorpay_client.get_payment_refunds.call_args_list:
        assert call[0][0] == "pay_abc123"


@pytest.mark.asyncio
async def test_d5_5_unknown_or_unsupported_capability_cannot_execute(
    verifier: DeterministicVerifier, mock_razorpay_client: AsyncMock, trusted_case: ReconciliationCase
):
    # Bypass Pydantic validation to simulate an unsupported intent reaching the verifier
    hypothesis = make_hypothesis(intent=VerificationIntent.QUERY_PROVIDER_REFUND)
    hypothesis.verification_intent = "SOME_NEW_INTENT"  # type: ignore

    result = await verifier.verify(hypothesis, trusted_case)

    assert isinstance(result, VerificationRejection)
    assert result.reason == VerificationRejectionReason.EXHAUSTED
    assert "Unsupported" in result.detail
    mock_razorpay_client.get_payment_refunds.assert_not_called()
    mock_razorpay_client.get_payment.assert_not_called()


@pytest.mark.asyncio
async def test_d5_6_provider_response_passes_through_phase_c_normalization(
    verifier: DeterministicVerifier, mock_razorpay_client: AsyncMock, trusted_case: ReconciliationCase
):
    hypothesis = make_hypothesis(intent=VerificationIntent.QUERY_PROVIDER_PAYMENT)
    
    # Return a raw dict-like structure from the mock client
    mock_razorpay_client.get_payment.return_value = DummyRazorpayPayment(
        id="pay_abc123", status="captured", created_at=1710000000
    )

    result = await verifier.verify(hypothesis, trusted_case)

    assert isinstance(result, list)
    evidence = result[0]
    
    # Phase C normalization converts the raw response to Evidence
    assert isinstance(evidence, Evidence)
    assert evidence.source == "razorpay_api"
    assert evidence.evidence_type == "RAZORPAY_API_REFUND_CAPTURED"
    assert evidence.payload["id"] == "pay_abc123"


def test_d5_7_no_direct_provider_observation_construction():
    """
    Verifier must return Evidence for V1 to ingest, not construct
    ProviderObservation itself (which is V1's job).
    """
    mod = importlib.import_module("src.investigation.verifier")
    with open(mod.__file__) as f:  # type: ignore[arg-type]
        source = f.read()

    assert "ProviderObservation(" not in source
    assert "from src.evidence.models import ProviderObservation" not in source


def test_d5_8_no_mutation_apis_or_imports():
    """
    Static check: verifier.py must not import mutation or execution modules.
    """
    mod = importlib.import_module("src.investigation.verifier")
    with open(mod.__file__) as f:  # type: ignore[arg-type]
        source = f.read()

    forbidden = (
        "src.control",
        "src.outbox",
        "create_incident",
        "execute_refund",
        "mutate",
        "commit_outbox",
    )
    for prefix in forbidden:
        assert prefix not in source, f"verifier.py must not import/reference '{prefix}'"

    # RazorpayClient's mutation methods should not be called
    assert "create_refund" not in source
    assert "create_order" not in source


@pytest.mark.asyncio
async def test_d5_9_provider_failure_cannot_manufacture_evidence(
    verifier: DeterministicVerifier, mock_razorpay_client: AsyncMock, trusted_case: ReconciliationCase
):
    hypothesis = make_hypothesis(intent=VerificationIntent.QUERY_PROVIDER_REFUND)
    mock_razorpay_client.get_payment_refunds.side_effect = httpx.HTTPError("Timeout")

    result = await verifier.verify(hypothesis, trusted_case)

    assert isinstance(result, VerificationRejection)
    assert result.reason == VerificationRejectionReason.PROVIDER_ERROR
    assert "Timeout" in result.detail


def test_d5_10_verifier_does_not_perform_v1_classification():
    """
    Verifier must not import ReconstructedState or ReconciliationResult,
    as it does not classify state.
    """
    mod = importlib.import_module("src.investigation.verifier")
    with open(mod.__file__) as f:  # type: ignore[arg-type]
        source = f.read()

    assert "ReconstructedState" not in source
    assert "ReconciliationResult" not in source
    assert "src.reconciliation" not in source
    assert "src.state" not in source
