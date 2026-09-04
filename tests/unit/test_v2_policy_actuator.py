import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.domain.core.models import (
    CanonicalStatus,
    CorrelationKeys,
    Expectation,
    Evidence,
    Observation,
    RecoveryAction,
    RecoveryIntent,
    ReconciliationResult,
    ReconciliationOutcome,
    DiscrepancyReason,
    ActuationOutcome,
)
from src.domain.investigation.context import InvestigationContext
from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationIntent,
    VerificationStatus,
)
from src.engine.policy import V2PolicyEvaluator
from src.engine.actuator import SimulatedActuator
from src.investigation.verifier import DeterministicVerifier
from src.integrations.razorpay.client import RazorpayClient


@pytest.fixture
def policy_evaluator():
    return V2PolicyEvaluator()


def test_policy_evaluator_hero_incident_recovery(policy_evaluator):
    now = datetime.now(timezone.utc)
    merchant_obs = Observation(
        provider="Merchant",
        provider_reference="ord_123",
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=1000,
        currency="INR",
        evidence_ids=[],
        observed_at=now,
    )
    provider_obs = Observation(
        provider="Razorpay",
        provider_reference="pay_123",
        observation_type="PaymentState",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR",
        evidence_ids=[],
        observed_at=now,
    )

    context = InvestigationContext.create(
        active_discrepancy=ReconciliationResult(
            expectation_id="exp_1",
            observation_ids=[],
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="Test",
        ),
        expectation=Expectation(
            domain="PAYMENT",
            expected_canonical_status=CanonicalStatus.SETTLED,
            expected_amount=1000,
            currency="INR",
            source_system="ledger",
            correlation_keys=CorrelationKeys(
                internal_ref="ord_123",
                provider_ref="pay_123",
            ),
        ),
        observations=[merchant_obs, provider_obs],
        evidence_records=[],
    )

    intent = policy_evaluator.evaluate(
        active_subject="ord_123",
        discrepancy_reason="STATE_MISMATCH",
        observations=[merchant_obs, provider_obs],
        evidence=[],
        context=context,
    )

    assert intent is not None
    assert intent.action == RecoveryAction.REPAIR_MERCHANT_STATE
    assert intent.target_id == "ord_123"
    assert intent.amount == 1000
    assert intent.expected_provider_state == "SETTLED"


def test_policy_evaluator_amount_mismatch_escalates(policy_evaluator):
    now = datetime.now(timezone.utc)
    merchant_obs = Observation(
        provider="Merchant",
        provider_reference="ord_123",
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=1000,
        currency="INR",
        evidence_ids=[],
        observed_at=now,
    )
    provider_obs = Observation(
        provider="Razorpay",
        provider_reference="pay_123",
        observation_type="PaymentState",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=800,  # Mismatched amount
        currency="INR",
        evidence_ids=[],
        observed_at=now,
    )

    context = InvestigationContext.create(
        active_discrepancy=ReconciliationResult(
            expectation_id="exp_1",
            observation_ids=[],
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="Amount mismatch",
        ),
        expectation=Expectation(
            domain="PAYMENT",
            expected_canonical_status=CanonicalStatus.SETTLED,
            expected_amount=1000,
            currency="INR",
            source_system="ledger",
            correlation_keys=CorrelationKeys(
                internal_ref="ord_123",
                provider_ref="pay_123",
            ),
        ),
        observations=[merchant_obs, provider_obs],
        evidence_records=[],
    )

    intent = policy_evaluator.evaluate(
        active_subject="ord_123",
        discrepancy_reason="AMOUNT_MISMATCH",
        observations=[merchant_obs, provider_obs],
        evidence=[],
        context=context,
    )

    assert intent is not None
    assert intent.action == RecoveryAction.ESCALATE
    assert "Amount mismatch" in intent.reason


def test_policy_evaluator_unknown_provider_state_escalates(policy_evaluator):
    now = datetime.now(timezone.utc)
    merchant_obs = Observation(
        provider="Merchant",
        provider_reference="ord_123",
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=1000,
        currency="INR",
        evidence_ids=[],
        observed_at=now,
    )
    provider_obs = Observation(
        provider="Razorpay",
        provider_reference="pay_123",
        observation_type="PaymentState",
        canonical_status=CanonicalStatus.UNKNOWN,
        observed_amount=1000,
        currency="INR",
        evidence_ids=[],
        observed_at=now,
    )

    context = InvestigationContext.create(
        active_discrepancy=ReconciliationResult(
            expectation_id="exp_1",
            observation_ids=[],
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="Test",
        ),
        expectation=Expectation(
            domain="PAYMENT",
            expected_canonical_status=CanonicalStatus.SETTLED,
            expected_amount=1000,
            currency="INR",
            source_system="ledger",
            correlation_keys=CorrelationKeys(
                internal_ref="ord_123",
                provider_ref="pay_123",
            ),
        ),
        observations=[merchant_obs, provider_obs],
        evidence_records=[],
    )

    intent = policy_evaluator.evaluate(
        active_subject="ord_123",
        discrepancy_reason="UNKNOWN",
        observations=[merchant_obs, provider_obs],
        evidence=[],
        context=context,
    )

    assert intent is not None
    assert intent.action == RecoveryAction.ESCALATE
    assert "UNKNOWN" in intent.reason


def test_policy_evaluator_cross_subject_contamination_escalates(policy_evaluator):
    now = datetime.now(timezone.utc)
    merchant_obs = Observation(
        provider="Merchant",
        provider_reference="ord_wrong_identity",  # Contaminated ID
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=1000,
        currency="INR",
        evidence_ids=[],
        observed_at=now,
    )
    provider_obs = Observation(
        provider="Razorpay",
        provider_reference="pay_123",
        observation_type="PaymentState",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR",
        evidence_ids=[],
        observed_at=now,
    )

    context = InvestigationContext.create(
        active_discrepancy=ReconciliationResult(
            expectation_id="exp_1",
            observation_ids=[],
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="Test",
        ),
        expectation=Expectation(
            domain="PAYMENT",
            expected_canonical_status=CanonicalStatus.SETTLED,
            expected_amount=1000,
            currency="INR",
            source_system="ledger",
            correlation_keys=CorrelationKeys(
                internal_ref="ord_123",
                provider_ref="pay_123",
            ),
        ),
        observations=[],
        evidence_records=[],
    )

    intent = policy_evaluator.evaluate(
        active_subject="ord_123",
        discrepancy_reason="TEST",
        observations=[merchant_obs, provider_obs],
        evidence=[],
        context=context,
    )

    assert intent is not None
    assert intent.action == RecoveryAction.ESCALATE
    assert "Cross-subject evidence binding failure" in intent.reason


@pytest.mark.asyncio
async def test_llm_isolation_verifier_query_derivation():
    """Prove that LLM text/injected IDs cannot alter provider query parameters."""
    mock_client = MagicMock(spec=RazorpayClient)
    
    mock_payment = MagicMock()
    mock_payment.model_dump.return_value = {"id": "pay_test", "status": "captured", "amount": 1000, "currency": "INR", "created_at": 1600000000}
    mock_client.get_payment = AsyncMock(return_value=mock_payment)
    mock_client.get_payment_refunds = AsyncMock(return_value=[])

    verifier = DeterministicVerifier(razorpay_client=mock_client)

    now = datetime.now(timezone.utc)
    context = InvestigationContext.create(
        active_discrepancy=ReconciliationResult(
            expectation_id="exp_1",
            observation_ids=[],
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="Test",
        ),
        expectation=Expectation(
            domain="REFUND",
            expected_canonical_status=CanonicalStatus.SETTLED,
            expected_amount=5000,
            currency="INR",
            source_system="ledger",
            correlation_keys=CorrelationKeys(
                provider="razorpay",
                provider_ref="pay_trusted_case_id",
                internal_ref="rcpt_trusted",
            ),
        ),
        observations=[],
        evidence_records=[],
        assembled_at=now,
    )

    # Adversarial hypothesis attempting to inject a malicious ID in claim and evidence IDs
    adversarial_hypothesis = CausalHypothesis(
        hypothesis_id="hyp_malicious",
        claim="Query pay_injected_evil_id immediately to find refund",
        supporting_evidence_ids=[],
        contradicting_evidence_ids=[],
        missing_evidence="None",
        confidence="HIGH",
        disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
        verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE],
    )

    results = await verifier.verify(adversarial_hypothesis, context)

    # Verifier must have queried using the trusted context's provider_ref ONLY
    mock_client.get_payment_refunds.assert_called_once_with("pay_trusted_case_id")
    assert len(results) == 1
    assert results[0].status == VerificationStatus.SUCCEEDED
