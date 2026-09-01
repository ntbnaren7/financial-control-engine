import asyncio
import os
import sys
import uuid
import json
import hmac
import hashlib
import logging
from httpx import AsyncClient, ASGITransport

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.api.main import app
from src.evidence.db import AsyncSessionLocal, engine
from src.evidence.models import Base as EvidenceBase
from src.merchant.models import MerchantOrder, Base as MerchantBase
from src.evidence.models import ProviderObservation
from src.integrations.razorpay.config import settings
from sqlalchemy.future import select

def generate_signature(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

async def main():
    print("🚀 Starting E2E Demo (Webhook -> M3 -> M4 (LLM) -> Control -> Repair)")
    
    # Setup DB
    async with engine.begin() as conn:
        await conn.run_sync(EvidenceBase.metadata.create_all)
        await conn.run_sync(MerchantBase.metadata.create_all)

    try:
        order_id = f"order_real_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_real_{uuid.uuid4().hex[:8]}"
        
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
            session.add(merchant_ord)
            session.add(obs_proc)
            session.add(obs_pay)
            await session.commit()
            print("    ✅ Seeded MerchantOrder (UNPAID)")
            print("    ✅ Seeded ProviderObservations (processing, payment)")

        print("\n[2] Firing simulated Razorpay Webhook (payment.captured) to FastAPI...")
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
        event_id = f"evt_wh_{uuid.uuid4().hex[:8]}"
        
        headers = {
            "x-razorpay-signature": signature,
            "x-razorpay-event-id": event_id,
            "Content-Type": "application/json"
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/webhooks/razorpay", content=payload_bytes, headers=headers)
        
        print(f"    ✅ Webhook accepted: {response.status_code}")
        
        print("\n[3] Waiting for BackgroundTasks to complete pipeline...")
        # Since BackgroundTasks run in the same process but might take some time,
        # we'll poll the database for the order status to change to PAID.
        # But wait, httpx with ASGITransport runs background tasks immediately after returning response in the same event loop.
        # Let's wait a bit to be sure.
        max_retries = 120
        repaired = False
        
        for i in range(max_retries):
            await asyncio.sleep(1)
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(MerchantOrder).where(MerchantOrder.razorpay_order_id == order_id)
                )
                updated_order = result.scalar_one_or_none()
                if updated_order and updated_order.status == "PAID":
                    repaired = True
                    break
            print(f"    ⏳ Waiting... ({i+1}/{max_retries})", flush=True)
            
        if repaired:
            print("\n🎉 SUCCESS! E2E Demo Complete. Order was autonomously repaired by M4 + Control Plane.")
        else:
            print("\n❌ FAILED! Order was not repaired within timeout.")

    finally:
        async with engine.begin() as conn:
            await conn.run_sync(EvidenceBase.metadata.drop_all)
            await conn.run_sync(MerchantBase.metadata.drop_all)

if __name__ == "__main__":
    asyncio.run(main())
