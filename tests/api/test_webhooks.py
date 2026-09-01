from src.evidence.models import EntityType
import pytest
pytestmark = [pytest.mark.postgres, pytest.mark.legacy]

import pytest
import hmac
import hashlib
import json
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from src.api.main import app
from src.evidence.db import AsyncSessionLocal
from src.evidence.models import ProviderObservation
from src.integrations.razorpay.config import settings

def generate_signature(payload: dict, secret: str) -> str:
    body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    return hmac.new(
        key=secret.encode('utf-8'),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()

import pytest_asyncio



@pytest.mark.asyncio
async def test_valid_webhook_delivery():
    payload = {
        "entity": "event",
        "account_id": "acc_123",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {"payment": {"entity": {"id": "pay_test"}}}
    }
    
    signature = generate_signature(payload, settings.webhook_secret)
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/webhooks/razorpay",
            json=payload,
            headers={
                "X-Razorpay-Signature": signature,
                "X-Razorpay-Event-Id": "event_valid_123"
            }
        )
        
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    
    # Verify DB persistence
    async with AsyncSessionLocal() as session:
        stmt = select(ProviderObservation).where(ProviderObservation.event_id == "event_valid_123")
        result = await session.execute(stmt)
        obs = result.scalar_one_or_none()
        
        assert obs is not None
        assert obs.provider == "razorpay"
        assert obs.event_type == "webhook"
        assert obs.payload == payload

@pytest.mark.asyncio
async def test_invalid_signature():
    payload = {"event": "payment.captured"}
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/webhooks/razorpay",
            json=payload,
            headers={
                "X-Razorpay-Signature": "invalid_signature",
                "X-Razorpay-Event-Id": "event_invalid_sig"
            }
        )
        
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid signature"}
    
    # Verify not persisted
    async with AsyncSessionLocal() as session:
        stmt = select(ProviderObservation).where(ProviderObservation.event_id == "event_invalid_sig")
        result = await session.execute(stmt)
        assert result.scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_duplicate_webhook_delivery():
    payload = {"event": "payment.captured"}
    signature = generate_signature(payload, settings.webhook_secret)
    headers = {
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": "event_dup_123"
    }
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # First delivery
        response1 = await ac.post("/api/webhooks/razorpay", json=payload, headers=headers)
        assert response1.status_code == 200
        
        # Second delivery (Duplicate)
        response2 = await ac.post("/api/webhooks/razorpay", json=payload, headers=headers)
        assert response2.status_code == 200
        assert response2.json() == {"status": "ok", "message": "duplicate event"}
        
    # Verify exactly one row in DB
    async with AsyncSessionLocal() as session:
        stmt = select(ProviderObservation).where(ProviderObservation.event_id == "event_dup_123")
        result = await session.execute(stmt)
        observations = result.scalars().all()
        
        assert len(observations) == 1

import asyncio

@pytest.mark.asyncio
async def test_concurrent_duplicate_webhook_delivery():
    payload = {"event": "payment.captured"}
    signature = generate_signature(payload, settings.webhook_secret)
    headers = {
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": "event_concurrent_dup_123"
    }
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Fire 5 identical requests concurrently
        tasks = [
            ac.post("/api/webhooks/razorpay", json=payload, headers=headers)
            for _ in range(5)
        ]
        
        responses = await asyncio.gather(*tasks)
        
        # All should return 200 OK
        for resp in responses:
            assert resp.status_code == 200
            
    # Verify exactly one row in DB due to the unique constraint
    async with AsyncSessionLocal() as session:
        stmt = select(ProviderObservation).where(ProviderObservation.event_id == "event_concurrent_dup_123")
        result = await session.execute(stmt)
        observations = result.scalars().all()
        
        assert len(observations) == 1
