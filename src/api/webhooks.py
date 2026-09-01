import json
from fastapi import APIRouter, Request, Header, HTTPException, status, BackgroundTasks
from sqlalchemy.exc import IntegrityError

from src.evidence.db import AsyncSessionLocal
from src.evidence.models import ProviderObservation
from src.integrations.razorpay.config import settings
from src.integrations.razorpay.webhook import verify_signature
from src.orchestration.pipeline import run_investigation_pipeline

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_razorpay_signature: str = Header(None),
    x_razorpay_event_id: str = Header(None)
):
    if not x_razorpay_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")
    if not x_razorpay_event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing event ID")
        
    raw_body = await request.body()
    
    # 1. Verify signature BEFORE parsing or saving
    is_valid = verify_signature(
        payload_body=raw_body,
        signature=x_razorpay_signature,
        secret=settings.webhook_secret
    )
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
        
    # 2. Parse payload after authentication
    try:
        payload_json = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    event_type = payload_json.get("event", "unknown")
    
    # 3. Persist observation (handle duplicates via DB constraint)
    observation = ProviderObservation(
        provider="razorpay",
        event_id=x_razorpay_event_id,
        event_type="webhook",
        payload=payload_json
    )
    
    async with AsyncSessionLocal() as session:
        session.add(observation)
        try:
            await session.commit()
        except IntegrityError:
            # Duplicate event_id for this provider.
            await session.rollback()
            return {"status": "ok", "message": "duplicate event"}
            
    background_tasks.add_task(run_investigation_pipeline, str(observation.id))
            
    return {"status": "ok"}
