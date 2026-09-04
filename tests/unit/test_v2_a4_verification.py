import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.domain.investigation.context import InvestigationContext
from src.domain.core.models import Expectation, Observation, CorrelationKeys, ReconciliationResult, ReconciliationOutcome, DiscrepancyReason, CanonicalStatus
from src.domain.investigation.models import CausalHypothesis, InvestigationDisposition, VerificationIntent, VerificationStatus, VerificationRejectionReason
from src.integrations.razorpay.client import RazorpayClient, ProviderNetworkError
from src.investigation.verifier import DeterministicVerifier

@pytest.fixture
def mock_razorpay_client():
    client = MagicMock(spec=RazorpayClient)
    client.get_payment_refunds = AsyncMock()
    
    mock_payment = MagicMock()
    mock_payment.model_dump.return_value = {"id": "pay_test", "status": "captured", "amount": 1000, "currency": "INR", "created_at": 1600000000}
    client.get_payment = AsyncMock(return_value=mock_payment)
    return client

@pytest.fixture
def sample_hypothesis():
    return CausalHypothesis(
        hypothesis_id="hyp_1",
        claim="The provider processed it later.",
        supporting_evidence_ids=[],
        contradicting_evidence_ids=[],
        missing_evidence="Need provider state.",
        confidence="HIGH",
        disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
        verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE]
    )

@pytest.fixture
def sample_context():
    now = datetime.now(timezone.utc)
    return InvestigationContext.create(
        active_discrepancy=ReconciliationResult(
            expectation_id="intent_1",
            observation_ids=[],
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="Test",
            discrepancy_reason=DiscrepancyReason.AMOUNT_MISMATCH
        ),
        expectation=Expectation(
            domain="REFUND",
            expected_canonical_status=CanonicalStatus.SETTLED,
            expected_amount=2000,
            currency="INR",
            source_system="OMS",
            correlation_keys=CorrelationKeys(
                provider="razorpay",
                provider_ref="pay_123",
                internal_ref="rcpt_123"
            )
        ),
        observations=[],
        evidence_records=[],
        assembled_at=now
    )

@pytest.mark.asyncio
async def test_verifier_success(mock_razorpay_client, sample_hypothesis, sample_context):
    class MockRefund:
        def __init__(self, id, payment_id, receipt, status, amount, currency, created_at):
            self.id = id
            self.payment_id = payment_id
            self.receipt = receipt
            self.status = status
            self.amount = amount
            self.currency = currency
            self.created_at = created_at
        def model_dump(self):
            return {
                "id": self.id,
                "payment_id": self.payment_id,
                "receipt": self.receipt,
                "status": self.status,
                "amount": self.amount,
                "currency": self.currency,
                "created_at": self.created_at
            }

    mock_razorpay_client.get_payment_refunds.return_value = [
        MockRefund("rfnd_123", "pay_123", "rcpt_123", "processed", 2000, "INR", 1600000000)
    ]
    
    verifier = DeterministicVerifier(razorpay_provider=mock_razorpay_client)
    
    results = await verifier.verify(sample_hypothesis, sample_context)
    assert len(results) == 1
    result = results[0]
    
    assert result.status == VerificationStatus.SUCCEEDED
    assert len(result.evidence_ids) == 1
    assert len(result.new_observations) == 1
    
    obs = result.new_observations[0]
    assert obs.provider == "razorpay"
    assert obs.canonical_status == CanonicalStatus.SETTLED
    assert obs.observed_amount == 2000

@pytest.mark.asyncio
async def test_verifier_missing_parameters(mock_razorpay_client, sample_hypothesis):
    now = datetime.now(timezone.utc)
    bad_context = InvestigationContext.create(
        active_discrepancy=ReconciliationResult(
            expectation_id="intent_1",
            observation_ids=[],
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="Test"
        ),
        expectation=Expectation(
            domain="REFUND",
            expected_canonical_status=CanonicalStatus.SETTLED,
            expected_amount=2000,
            currency="INR",
            source_system="OMS",
            correlation_keys=CorrelationKeys(
                provider="razorpay",
                internal_ref="rcpt_123" # missing provider_ref
            )
        ),
        observations=[],
        evidence_records=[],
        assembled_at=now
    )
    
    verifier = DeterministicVerifier(razorpay_provider=mock_razorpay_client)
    results = await verifier.verify(sample_hypothesis, bad_context)
    
    assert len(results) == 1
    result = results[0]
    assert result.status == VerificationStatus.REJECTED
    assert result.failure_reason == VerificationRejectionReason.MISSING_PARAMETERS.value
    mock_razorpay_client.get_payment_refunds.assert_not_called()

@pytest.mark.asyncio
async def test_verifier_network_failure(mock_razorpay_client, sample_hypothesis, sample_context):
    mock_razorpay_client.get_payment_refunds.side_effect = ProviderNetworkError("Timeout")
    
    verifier = DeterministicVerifier(razorpay_provider=mock_razorpay_client)
    results = await verifier.verify(sample_hypothesis, sample_context)
    
    assert len(results) == 1
    result = results[0]
    assert result.status == VerificationStatus.FAILED
    assert result.failure_reason == "Timeout"
