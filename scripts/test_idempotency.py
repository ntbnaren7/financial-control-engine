import asyncio
import os
import sys
import uuid
from sqlalchemy.future import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.evidence.db import AsyncSessionLocal, engine
from src.evidence.models import ProviderObservation
from src.merchant.models import MerchantOrder
from src.orchestration.pipeline import run_investigation_pipeline
from unittest.mock import patch
from src.investigation.result import InvestigationResult, InvestigationStatus
from src.investigation.models import InvestigationProposal, HypothesisSelection, ConfidenceBand, InvestigationEligibility, V0HypothesisType

async def main():
    order_id = f"order_real_{uuid.uuid4().hex[:8]}"
    payment_id = f"pay_real_{uuid.uuid4().hex[:8]}"
    
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

    print(f"\n[1] Seeding Discrepancy preconditions (Order: {order_id}, Payment: {payment_id})")
    async with AsyncSessionLocal() as session:
        merchant_ord = MerchantOrder(
            merchant_order_id=f"mo_{order_id}",
            razorpay_order_id=order_id,
            expected_amount=5000,
            currency="INR",
            status="UNPAID"
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
        obs_wh = ProviderObservation(
            provider="razorpay",
            event_id=f"evt_wh_{uuid.uuid4().hex[:8]}",
            event_type="webhook",
            payload={"event": "payment.captured", "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id}}}}
        )
        session.add_all([merchant_ord, obs_proc, obs_pay, obs_wh])
        await session.commit()
        
        # Get the observation ID for the payment observation
        await session.refresh(obs_pay)
        target_observation_id = str(obs_pay.id)
        print(f"    -> Seeded target observation ID: {target_observation_id}")

    with patch("src.orchestration.pipeline.InvestigationOrchestrator.investigate", return_value=mock_result):
        print("\n[2] Execution Run 1 (Should Repair)")
        res1 = await run_investigation_pipeline(target_observation_id)
        status1 = res1['pipeline_status'] if res1 else "NO_ACTION"
        print(f"    -> Result 1: {status1}")

        print("\n[3] Execution Run 2 (Should NO_ACTION/CONFLICT/Graceful)")
        res2 = await run_investigation_pipeline(target_observation_id)
        status2 = res2['pipeline_status'] if res2 else "NO_ACTION"
        print(f"    -> Result 2: {status2}")

if __name__ == "__main__":
    asyncio.run(main())
