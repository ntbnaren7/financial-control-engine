import os
import sys
import pytest
import uuid
import json
import hmac
import hashlib
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from httpx import AsyncClient, ASGITransport
from sqlalchemy.future import select

from src.api.main import app
from src.evidence.db import AsyncSessionLocal, engine
from src.evidence.models import Base as EvidenceBase, ProviderObservation
from src.merchant.models import MerchantOrder, Base as MerchantBase
from src.investigation.result import InvestigationResult, InvestigationStatus
from src.investigation.models import (
    InvestigationProposal, 
    HypothesisSelection, 
    V0HypothesisType,
    ConfidenceBand,
    InvestigationEligibility
)
from src.integrations.razorpay.config import settings

def generate_signature(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

from sqlalchemy import delete

async def setup_db():
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ProviderObservation))
        await session.execute(delete(MerchantOrder))
        await session.commit()

async def teardown_db():
    pass

async def seed_db(order_id: str, payment_id: str, order_status: str = "UNPAID"):
    async with AsyncSessionLocal() as session:
        merchant_ord = MerchantOrder(
            merchant_order_id=f"mo_{order_id}",
            razorpay_order_id=order_id,
            expected_amount=5000,
            currency="INR",
            status=order_status
        )
        obs_proc = ProviderObservation(
            provider="razorpay",
            event_id=f"evt_proc_{uuid.uuid4().hex[:8]}",
            event_type="processing",
            payload={"order_id": order_id, "payment_id": payment_id, "status": "PROCESSED"}
        )
        obs_pay = ProviderObservation(
            provider="razorpay",
            event_id=f"evt_pay_{uuid.uuid4().hex[:8]}",
            event_type="payment",
            payload={"order_id": order_id, "payment_id": payment_id, "status": "captured", "captured": True, "amount": 5000, "currency": "INR"}
        )
        session.add(merchant_ord)
        session.add(obs_proc)
        session.add(obs_pay)
        await session.commit()

def create_webhook_payload(order_id: str, payment_id: str):
    return {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 5000,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }

def create_mock_m4_result(hypothesis: V0HypothesisType, status: InvestigationStatus = InvestigationStatus.ACCEPTED):
    mock_selections = [
        HypothesisSelection(hypothesis_id=hypothesis, rank=1, rationale="Mocked", confidence_band=ConfidenceBand.HIGH),
        HypothesisSelection(hypothesis_id=V0HypothesisType.EVIDENCE_INSUFFICIENT if hypothesis != V0HypothesisType.EVIDENCE_INSUFFICIENT else V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED, rank=2, rationale="", confidence_band=ConfidenceBand.LOW),
        HypothesisSelection(hypothesis_id=V0HypothesisType.WEBHOOK_NOT_OBSERVED, rank=3, rationale="", confidence_band=ConfidenceBand.LOW),
        HypothesisSelection(hypothesis_id=V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED, rank=4, rationale="", confidence_band=ConfidenceBand.LOW),
        HypothesisSelection(hypothesis_id=V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH, rank=5, rationale="", confidence_band=ConfidenceBand.LOW),
    ]
    mock_proposal = InvestigationProposal(
        eligibility=InvestigationEligibility.ELIGIBLE,
        overall_confidence=ConfidenceBand.HIGH,
        selections=mock_selections
    )
    return InvestigationResult(status=status, proposal=mock_proposal)

async def trigger_webhook(payload_dict: dict, sign: bool = True, event_id: str | None = None):
    payload_bytes = json.dumps(payload_dict).encode()
    signature = generate_signature(payload_bytes, settings.webhook_secret) if sign else "invalid_signature"
    event_id = event_id or f"evt_{uuid.uuid4().hex[:8]}"
    
    headers = {
        "x-razorpay-signature": signature,
        "x-razorpay-event-id": event_id,
        "Content-Type": "application/json"
    }
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/webhooks/razorpay", content=payload_bytes, headers=headers)

async def assert_db_status(order_id: str, expected_status: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MerchantOrder).where(MerchantOrder.razorpay_order_id == order_id))
        order = result.scalar_one_or_none()
        assert order is not None
        assert order.status == expected_status

@pytest.mark.asyncio
async def test_m3_no_discrepancy():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
    
        # DB is PAID, Provider is Captured -> No Discrepancy
        await seed_db(order_id, payment_id, "PAID")
    
        with patch("src.investigation.ai.InvestigationEngine.investigate") as mock_investigate:
            response = await trigger_webhook(create_webhook_payload(order_id, payment_id))
            assert response.status_code == 200
            mock_investigate.assert_not_called()
        
        await assert_db_status(order_id, "PAID")

    finally:
        await teardown_db()
@pytest.mark.asyncio
async def test_m4_returns_h5():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        await seed_db(order_id, payment_id)
    
        mock_res = create_mock_m4_result(V0HypothesisType.EVIDENCE_INSUFFICIENT)
        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res):
            response = await trigger_webhook(create_webhook_payload(order_id, payment_id))
            assert response.status_code == 200
        
        await assert_db_status(order_id, "UNPAID")

    finally:
        await teardown_db()
@pytest.mark.asyncio
async def test_m4_structurally_invalid():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        await seed_db(order_id, payment_id)
    
        mock_res = InvestigationResult(status=InvestigationStatus.SCHEMA_INVALID, failure_reason="Missing fields")
        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res):
            response = await trigger_webhook(create_webhook_payload(order_id, payment_id))
            assert response.status_code == 200
        
        await assert_db_status(order_id, "UNPAID")

    finally:
        await teardown_db()
@pytest.mark.asyncio
async def test_m4_semantic_contradiction():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        await seed_db(order_id, payment_id)
    
        mock_res = InvestigationResult(status=InvestigationStatus.PROPOSAL_SEMANTIC_CONFLICT, failure_reason="Contradiction")
        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res):
            response = await trigger_webhook(create_webhook_payload(order_id, payment_id))
            assert response.status_code == 200
        
        await assert_db_status(order_id, "UNPAID")

    finally:
        await teardown_db()
@pytest.mark.asyncio
async def test_merchant_already_paid():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        await seed_db(order_id, payment_id, "PAID")
    
        mock_res = create_mock_m4_result(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
    
        from src.reconciliation.models import VerifiedDiscrepancy
        dummy_discrepancy = VerifiedDiscrepancy(
            discrepancy_id="TEST",
            payment_id=payment_id,
            order_id=order_id,
            provider_status="captured",
            merchant_status="UNPAID",
            amount_match=True,
            currency_match=True,
            identity_verified=True,
            description="test"
        )
    
        with patch("src.reconciliation.engine.M3Engine.evaluate_reconciliation", return_value=dummy_discrepancy):
            with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res):
                response = await trigger_webhook(create_webhook_payload(order_id, payment_id))
                assert response.status_code == 200
            
        await assert_db_status(order_id, "PAID")

    finally:
        await teardown_db()
@pytest.mark.asyncio
async def test_conditional_update_affects_0_rows():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        await seed_db(order_id, payment_id)
    
        from src.recovery.action import ActionResult, ActionStatus
        mock_action_res = ActionResult(status=ActionStatus.CONFLICT, message="0 rows updated")
    
        mock_res = create_mock_m4_result(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
    
        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res):
            with patch("src.orchestration.pipeline.execute_repair_action", return_value=mock_action_res):
                response = await trigger_webhook(create_webhook_payload(order_id, payment_id))
                assert response.status_code == 200
            
        await assert_db_status(order_id, "UNPAID")

    finally:
        await teardown_db()
@pytest.mark.asyncio
async def test_post_action_verification_fails():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        await seed_db(order_id, payment_id)

        from src.recovery.verifier import VerificationResult, VerificationStatus
        mock_verify_res = VerificationResult(status=VerificationStatus.VERIFICATION_FAILED, message="Still UNPAID")

        mock_res = create_mock_m4_result(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)

        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res):
            with patch("src.orchestration.pipeline.verify_resolution", return_value=mock_verify_res):
                async with AsyncSessionLocal() as session:
                    obs = ProviderObservation(
                        provider="razorpay",
                        event_id=f"evt_{uuid.uuid4().hex[:8]}",
                        event_type="webhook",
                        payload=create_webhook_payload(order_id, payment_id)
                    )
                    session.add(obs)
                    await session.commit()
                    obs_id = str(obs.id)
                
                from src.orchestration.pipeline import run_investigation_pipeline
                pipeline_return = await run_investigation_pipeline(obs_id)

                assert isinstance(pipeline_return, dict)
                assert pipeline_return.get("pipeline_status") == "VERIFICATION_FAILED"
    finally:
        await teardown_db()
@pytest.mark.asyncio
async def test_duplicate_webhook():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        await seed_db(order_id, payment_id)
    
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        payload = create_webhook_payload(order_id, payment_id)
    
        mock_res = create_mock_m4_result(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res) as mock_inv:
            res1 = await trigger_webhook(payload, event_id=event_id)
            assert res1.status_code == 200
            assert mock_inv.call_count == 1
        
        await assert_db_status(order_id, "PAID")
    
        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res) as mock_inv:
            res2 = await trigger_webhook(payload, event_id=event_id)
            assert res2.status_code == 200
            assert res2.json()["message"] == "duplicate event"
            mock_inv.assert_not_called()

    finally:
        await teardown_db()
@pytest.mark.asyncio
async def test_malformed_webhook():
    await setup_db()
    try:
        payload_bytes = b"invalid json"
        signature = generate_signature(payload_bytes, settings.webhook_secret)
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
    
        headers = {
            "x-razorpay-signature": signature,
            "x-razorpay-event-id": event_id,
            "Content-Type": "application/json"
        }
    
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/webhooks/razorpay", content=payload_bytes, headers=headers)
        
        assert response.status_code == 400
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(ProviderObservation))
            assert len(result.scalars().all()) == 0

    finally:
        await teardown_db()
@pytest.mark.asyncio
async def test_invalid_signature():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        payload = create_webhook_payload(order_id, payment_id)
    
        response = await trigger_webhook(payload, sign=False)
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid signature"
    
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(ProviderObservation))
            assert len(result.scalars().all()) == 0

    finally:
        await teardown_db()

@pytest.mark.asyncio
async def test_verifier_crash_recovery():
    """
    Simulates a hard crash during the Independent Verification step, after the atomic DB mutation has committed.
    Verifies that the next reconciliation sweep correctly sees the new valid state (CAPTURED + PAID) 
    and gracefully dismisses the event without re-triggering M4 or mutating the DB again.
    """
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        await seed_db(order_id, payment_id)

        payload = create_webhook_payload(order_id, payment_id)
        mock_result = create_mock_m4_result(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)

        # 1. First run: Verifier crashes after mutation
        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_result) as mock_inv:
            with patch("src.orchestration.pipeline.verify_resolution", side_effect=Exception("Simulated hard crash in verifier!")):
                # When verifier crashes, the pipeline's exception block sets status to ERROR, 
                # but the mutation has already committed.
                try:
                    response = await trigger_webhook(payload)
                except Exception as e:
                    assert "Simulated hard crash" in str(e)

        # Verify mutation occurred despite crash
        await assert_db_status(order_id, "PAID")

        # 2. Second run: Next reconciliation sweep (simulate re-receiving webhook or scheduled sweep)
        # We need to change the event ID so it's not blocked by the idempotency duplicate check in webhook router.
        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_result) as mock_inv2:
            response2 = await trigger_webhook(payload, event_id=f"evt_retry_{uuid.uuid4().hex[:8]}")
            assert response2.status_code == 200
            
            # Since the state is now PAID (merchant) and CAPTURED (provider), M3 will see NO DISCREPANCY.
            # M4 should NEVER be called.
            mock_inv2.assert_not_called()

        # Database remains safely PAID
        await assert_db_status(order_id, "PAID")

    finally:
        await teardown_db()