import hashlib
import hmac
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.webhooks import set_ingestion_repository
from src.domain.ingestion.models import IngestionPayload
from src.domain.core.models import (
    CanonicalStatus,
    CorrelationKeys,
    Expectation,
    Observation,
    ReconciliationOutcome,
    DiscrepancyReason,
    RecoveryAction,
    RecoveryIntent,
    ActuationOutcome,
)
from src.engine.reconciliation_controls import evaluate_expectation_centric
from src.domain.investigation.context import InvestigationContext
from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationIntent,
    VerificationStatus,
)
from src.engine.adapters.razorpay_payment_adapter import RazorpayPaymentAdapter
from src.engine.actuator import SimulatedActuator
from src.engine.external_simulator import simulator
from src.engine.observer import SimulatedObserver
from src.engine.policy import V2PolicyEvaluator
from src.engine.v2_reconciliation import reconcile
from src.ingestion.worker import IngestionWorker
from src.investigation.input_formatter import format_context_for_investigation
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.storage.postgres_ingestion import MemoryIngestionRepository
from src.storage.substrate_repo import MemoryObservationRepository, MemoryEvidenceRepository


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


@pytest.fixture
def client_and_repos():
    secret = "test_webhook_secret_key"
    ingestion_repo = MemoryIngestionRepository()
    set_ingestion_repository(ingestion_repo)

    obs_repo = MemoryObservationRepository()
    ev_repo = MemoryEvidenceRepository()

    client = TestClient(app)
    return client, ingestion_repo, obs_repo, ev_repo, secret


def test_webhook_hmac_rejection(client_and_repos):
    client, _, _, _, _ = client_and_repos
    payload = {"event": "payment.captured", "id": "evt_123"}
    payload_bytes = json.dumps(payload).encode("utf-8")

    # Request with invalid signature
    response = client.post(
        "/webhooks/razorpay",
        content=payload_bytes,
        headers={"x-razorpay-signature": "bad_signature"},
    )
    assert response.status_code == 400
    assert "Invalid or missing webhook signature" in response.json()["detail"]


def test_webhook_idempotent_ingestion(client_and_repos):
    client, ingestion_repo, _, _, secret = client_and_repos
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_idempotent_1",
                    "status": "captured",
                    "amount": 25000,
                    "currency": "INR",
                }
            }
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = compute_signature(payload_bytes, secret)

    # First delivery: accepted
    r1 = client.post(
        "/webhooks/razorpay",
        content=payload_bytes,
        headers={"x-razorpay-signature": sig},
    )
    assert r1.status_code == 202
    assert r1.json()["status"] == "ACCEPTED"

    # Second delivery: duplicate detected
    r2 = client.post(
        "/webhooks/razorpay",
        content=payload_bytes,
        headers={"x-razorpay-signature": sig},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "DUPLICATE"


@pytest.mark.asyncio
async def test_full_phase8d_vertical_slice_closed_loop(client_and_repos):
    """
    Validates complete production-style flow:
    HTTP Ingress → HMAC Verification → Durable Ingestion → Worker Claim/Lease →
    Domain Normalization → Canonical Observation → Reconciliation → Discrepancy →
    Investigation → Verification → Policy → RecoveryIntent → Actuation → Re-observation → Terminal State
    """
    client, ingestion_repo, obs_repo, ev_repo, secret = client_and_repos
    payment_id = "pay_slice_8d"
    order_id = "ord_slice_8d"
    amount = 50000

    # Initialize external simulator
    simulator.reset()
    simulator.create_merchant_order(order_id, amount, "UNPAID")
    simulator.create_provider_payment(payment_id, order_id, amount, "CAPTURED")

    # 1. HTTP Ingress with HMAC signature
    raw_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "status": "captured",
                    "amount": amount,
                    "currency": "INR",
                    "created_at": 1600000000,
                }
            }
        },
    }
    raw_bytes = json.dumps(raw_payload).encode("utf-8")
    sig = compute_signature(raw_bytes, secret)

    res = client.post(
        "/webhooks/razorpay",
        content=raw_bytes,
        headers={"x-razorpay-signature": sig},
    )
    assert res.status_code == 202
    assert res.json()["status"] == "ACCEPTED"

    # 2. Worker Claim and Domain Normalization
    worker = IngestionWorker(
        worker_id="worker_slice_1",
        ingestion_repo=ingestion_repo,
        observation_repo=obs_repo,
        evidence_repo=ev_repo,
    )
    processed = worker.process_batch()
    assert processed == 1

    stored_observations = obs_repo.find_by_business_identity("razorpay", payment_id, "PAYMENT")
    assert len(stored_observations) == 1
    provider_obs = stored_observations[0]
    assert provider_obs.canonical_status == CanonicalStatus.SETTLED

    # 3. Deterministic Reconciliation
    # Merchant expectation is that order should be SETTLED, but merchant state in OMS is UNPAID
    now = datetime.now(timezone.utc)
    merchant_obs = Observation(
        provider="Merchant",
        provider_reference=order_id,
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,  # UNPAID
        observed_amount=amount,
        currency="INR",
        evidence_ids=[],
        observed_at=now,
    )

    expectation = Expectation(
        domain="PAYMENT",
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=amount,
        currency="INR",
        source_system="merchant_oms",
        correlation_keys=CorrelationKeys(
            internal_ref=order_id,
            provider_ref=payment_id,
            provider="razorpay",
        ),
    )

    initial_recon = evaluate_expectation_centric(expectation, [merchant_obs])
    assert initial_recon.outcome == ReconciliationOutcome.DISCREPANCY
    assert initial_recon.discrepancy_reason == DiscrepancyReason.STATE_MISMATCH

    # 4. Investigation Context Assembly & LLM Reasoning
    context = InvestigationContext.create(
        active_discrepancy=initial_recon,
        expectation=expectation,
        observations=[merchant_obs, provider_obs],
        evidence_records=ev_repo.get_by_ids(provider_obs.evidence_ids),
        assembled_at=now,
    )

    formatted_input = format_context_for_investigation(context)
    assert formatted_input["discrepancy_reason"] == "STATE_MISMATCH"

    # LLM outputs hypothesis proposing verification
    raw_hypothesis = {
        "hypothesis_id": "hyp_phase8d_1",
        "claim": "Payment was captured at provider but merchant remains UNPAID.",
        "supporting_evidence_ids": [provider_obs.evidence_ids[0]],
        "contradicting_evidence_ids": [],
        "missing_evidence": "Verification of payment status at Razorpay API.",
        "confidence": "HIGH",
        "disposition": "VERIFICATION_PROPOSED",
        "verification_intents": ["QUERY_PROVIDER_STATE"],
    }

    validator = OutputValidator()
    validated_hypothesis = validator.validate(raw_hypothesis, formatted_input)
    assert isinstance(validated_hypothesis, CausalHypothesis)

    # 5. Deterministic Verifier Execution
    mock_razorpay_client = MagicMock()
    mock_razorpay_client.get_payment_refunds = AsyncMock(return_value=[])

    verifier = DeterministicVerifier(razorpay_client=mock_razorpay_client)
    verification_results = await verifier.verify(validated_hypothesis, context)
    assert len(verification_results) == 1
    assert verification_results[0].status == VerificationStatus.SUCCEEDED

    # 6. Deterministic Policy Evaluation
    policy = V2PolicyEvaluator()
    intent = policy.evaluate(
        active_subject=order_id,
        discrepancy_reason="STATE_MISMATCH",
        observations=[merchant_obs, provider_obs],
        evidence=context.evidence_records,
        context=context,
    )

    assert intent is not None
    assert intent.action == RecoveryAction.REPAIR_MERCHANT_STATE
    assert intent.target_id == order_id
    assert intent.amount == amount

    # 7. Actuation Boundary
    actuator = SimulatedActuator()
    outcome = actuator.execute(intent)
    assert outcome == ActuationOutcome.SUCCESS

    # 8. Re-observation & Final Reconciliation Check
    observer = SimulatedObserver()
    final_merchant_obs = observer.observe_merchant_order(order_id)
    assert final_merchant_obs is not None
    assert final_merchant_obs.canonical_status == CanonicalStatus.SETTLED

    final_recon = reconcile(expectation, [final_merchant_obs])
    assert final_recon.outcome == ReconciliationOutcome.MATCH


def test_stale_lease_claiming_after_worker_crash(client_and_repos):
    """Failure Injection: Proves that an orphaned payload with an expired lease is reclaimed by a new worker."""
    _, ingestion_repo, obs_repo, ev_repo, _ = client_and_repos
    worker_crashed = "worker_crashed_101"
    worker_healthy = "worker_healthy_202"

    payload = IngestionPayload(
        provider="razorpay",
        event_type="payment.captured",
        raw_payload={"id": "pay_crash_test", "amount": 1000, "status": "captured"},
        payload_hash="hash_crash_test",
        idempotency_key="idemp_crash_test",
    )
    ingestion_repo.save_payload(payload)

    # Worker A claims with a short 0-second lease (already expired)
    claimed_by_a = ingestion_repo.claim_pending_payloads(worker_id=worker_crashed, limit=1, lease_seconds=-1)
    assert len(claimed_by_a) == 1
    assert claimed_by_a[0].lease_owner == worker_crashed

    # Worker B comes in after Worker A crashes and reclaims the payload
    worker_b = IngestionWorker(
        worker_id=worker_healthy,
        ingestion_repo=ingestion_repo,
        observation_repo=obs_repo,
        evidence_repo=ev_repo,
    )
    processed = worker_b.process_batch(limit=1, lease_seconds=30)
    assert processed == 1

    # Verify payload was successfully processed by Worker B
    stored = obs_repo.find_by_business_identity("razorpay", "pay_crash_test", "PAYMENT")
    assert len(stored) == 1
    assert stored[0].canonical_status == CanonicalStatus.SETTLED


def test_actuation_fault_injection_timeout():
    """Failure Injection: Simulator timeout forces independent observation and safe recovery."""
    simulator.reset()
    order_id = "ord_fault_1"
    amount = 10000
    simulator.seed_merchant_order(order_id, amount, "UNPAID")
    simulator.seed_provider_payment("pay_fault_1", order_id, amount, "CAPTURED")

    # Inject timeout fault on the merchant order target
    simulator.inject_fault(order_id, "TIMEOUT")

    actuator = SimulatedActuator()
    intent = RecoveryIntent(
        action=RecoveryAction.REPAIR_MERCHANT_STATE,
        target_id=order_id,
        amount=amount,
        expected_provider_state="SETTLED",
    )

    outcome = actuator.execute(intent)
    assert outcome == ActuationOutcome.TIMEOUT_UNKNOWN

    # Re-observation independently verifies whether state transitioned or not
    observer = SimulatedObserver()
    current_obs = observer.observe_merchant_order(order_id)
    assert current_obs is not None
    # Because it timed out, order remained UNPAID (PENDING), preventing false-positive resolution
    assert current_obs.canonical_status == CanonicalStatus.PENDING
