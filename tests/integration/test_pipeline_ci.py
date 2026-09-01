import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
import uuid
import hmac
import hashlib
import json
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.future import select

from src.api.main import app
from src.evidence.db import AsyncSessionLocal, engine
from src.evidence.models import Base as EvidenceBase
from src.evidence.models import ProviderObservation
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

@pytest.mark.asyncio
async def test_webhook_to_resolution_pipeline_ci():
    """
    CI Integration Test:
    Mocks the LLM and tests the end-to-end wiring from Webhook -> M3 -> M4 -> Control -> Action -> Verifier.
    """
    
    # Setup DB Tables
    async with engine.begin() as conn:
        await conn.run_sync(EvidenceBase.metadata.create_all)
        await conn.run_sync(MerchantBase.metadata.create_all)
        
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        
        # 1. Seed DB with required preconditions
        async with AsyncSessionLocal() as session:
            # Seed MerchantOrder as UNPAID
            merchant_ord = MerchantOrder(
                merchant_order_id=f"mo_{order_id}",
                razorpay_order_id=order_id,
                expected_amount=5000,
                currency="INR",
                status="UNPAID"
            )
            # Seed Processing Observation (PROCESSED)
            obs_proc = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_proc_{uuid.uuid4().hex[:8]}",
                event_type="processing",
                payload={"order_id": order_id, "payment_id": payment_id, "status": "PROCESSED"}
            )
            # Seed Payment Observation (CAPTURED)
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

        # 2. Prepare the Webhook Payload (Payment Captured)
        payload_dict = {
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
        
        payload_bytes = json.dumps(payload_dict).encode()
        signature = generate_signature(payload_bytes, settings.webhook_secret)
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        
        headers = {
            "x-razorpay-signature": signature,
            "x-razorpay-event-id": event_id,
            "Content-Type": "application/json"
        }

        # 3. Mock the LLM output (M4) to return H3 Admissible
        mock_selections = [
            HypothesisSelection(
                hypothesis_id=V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED,
                rank=1, rationale="Mocked", confidence_band=ConfidenceBand.HIGH
            ),
            HypothesisSelection(hypothesis_id=V0HypothesisType.EVIDENCE_INSUFFICIENT, rank=2, rationale="", confidence_band=ConfidenceBand.LOW),
            HypothesisSelection(hypothesis_id=V0HypothesisType.WEBHOOK_NOT_OBSERVED, rank=3, rationale="", confidence_band=ConfidenceBand.LOW),
            HypothesisSelection(hypothesis_id=V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED, rank=4, rationale="", confidence_band=ConfidenceBand.LOW),
            HypothesisSelection(hypothesis_id=V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH, rank=5, rationale="", confidence_band=ConfidenceBand.LOW),
        ]
        mock_proposal = InvestigationProposal(
            eligibility=InvestigationEligibility.ELIGIBLE,
            overall_confidence=ConfidenceBand.HIGH,
            selections=mock_selections
        )
        mock_result = InvestigationResult(status=InvestigationStatus.ACCEPTED, proposal=mock_proposal)

        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_result):
            # 4. Trigger Webhook
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/webhooks/razorpay", content=payload_bytes, headers=headers)
                
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        
        # 5. Verify the full pipeline executed and successfully updated the MerchantOrder to PAID
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MerchantOrder).where(MerchantOrder.razorpay_order_id == order_id)
            )
            updated_order = result.scalar_one_or_none()
            assert updated_order is not None
            assert updated_order.status == "PAID", "The order should have been repaired autonomously."
            
        print(f"\nCI Integration test passed! Pipeline successfully triggered and repaired order {order_id}.")
    finally:
        # Teardown DB Tables
        async with engine.begin() as conn:
            pass
