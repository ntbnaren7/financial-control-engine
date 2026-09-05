"""
Incidents router — list and detail views.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime

from src.api.deps import get_incident_repo
from src.storage.postgres_substrate import PostgresActiveIncidentRepository, ActiveIncidentIdempotencyRecord

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _record_to_dict(r: ActiveIncidentIdempotencyRecord) -> dict:
    state_val = r.state.value if hasattr(r.state, "value") else str(r.state)
    is_terminal = state_val in {
        "RESOLVED", "ESCALATED_PAUSED_BY_KILL_SWITCH", "ESCALATED_BUDGET_EXHAUSTED",
        "ESCALATED_POLICY_BLOCKED", "ESCALATED_MISSING_EVIDENCE", "ESCALATED_MUTATION_FAILED",
        "ESCALATED_CONVERGENCE_FAILED", "ESCALATED_UNKNOWN", "ESCALATED", "COMPLETED"
    }
    is_escalated = state_val.startswith("ESCALATED")
    return {
        "incident_id": r.active_subject,
        "discrepancy_reason": r.discrepancy_reason,
        "state": state_val,
        "is_terminal": is_terminal,
        "is_escalated": is_escalated,
        "retry_count": r.retry_count,
        "version": r.version,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.lease_expires_at.isoformat() if r.lease_expires_at else None,
        "hypothesis_available": bool(r.hypothesis_payload),
    }


@router.get("")
def list_incidents(
    state: Optional[str] = Query(None, description="Filter by state, e.g. ESCALATED_UNKNOWN"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    repo: PostgresActiveIncidentRepository = Depends(get_incident_repo),
):
    """List active incidents, optionally filtered by state."""
    from sqlalchemy.orm import Session
    from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord

    with repo.session_maker() as session:
        q = session.query(ActiveIncidentIdempotencyRecord)
        if state:
            q = q.filter(ActiveIncidentIdempotencyRecord.state == state)
        total = q.count()
        records = q.order_by(ActiveIncidentIdempotencyRecord.created_at.desc()).offset(offset).limit(limit).all()
        items = [_record_to_dict(r) for r in records]

    return {"total": total, "offset": offset, "limit": limit, "items": items}


@router.get("/summary")
def incident_summary(
    repo: PostgresActiveIncidentRepository = Depends(get_incident_repo),
):
    """Aggregate counts for the operator dashboard header."""
    from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord
    from sqlalchemy import func

    with repo.session_maker() as session:
        rows = session.query(
            ActiveIncidentIdempotencyRecord.state,
            func.count(ActiveIncidentIdempotencyRecord.active_subject).label("count")
        ).group_by(ActiveIncidentIdempotencyRecord.state).all()

    state_counts = {row.state if isinstance(row.state, str) else row.state.value: row.count for row in rows}

    active_states = {
        "DETECTED", "INVESTIGATING", "VERIFYING", "ACTIONABLE",
        "ACTUATION_PENDING", "ACTUATING", "REOBSERVING",
        "ACTIVE", "RETRY_PENDING"
    }
    resolved_states = {"RESOLVED", "COMPLETED"}
    escalated_states = {k for k in state_counts if k.startswith("ESCALATED")}

    active_count = sum(v for k, v in state_counts.items() if k in active_states)
    resolved_count = sum(v for k, v in state_counts.items() if k in resolved_states)
    escalated_count = sum(v for k, v in state_counts.items() if k in escalated_states)

    return {
        "active": active_count,
        "resolved": resolved_count,
        "escalated": escalated_count,
        "total": sum(state_counts.values()),
        "by_state": state_counts,
    }


from pydantic import BaseModel


class TriggerLiveRequest(BaseModel):
    payment_id: Optional[str] = None
    order_id: Optional[str] = None
    amount: Optional[int] = 4500
    currency: Optional[str] = "INR"


@router.post("/trigger-live")
async def trigger_live(
    req: Optional[TriggerLiveRequest] = None,
    repo: PostgresActiveIncidentRepository = Depends(get_incident_repo),
):
    """
    Trigger authoritative end-to-end LIVE vertical slice execution.
    Executes all 7 stages against PostgreSQL and local Ollama.
    """
    from src.services.live_slice import LiveSliceService

    service = LiveSliceService(repo.session_maker)
    payment_id = req.payment_id if req else None
    order_id = req.order_id if req else None
    amount = req.amount if (req and req.amount) else 4500
    currency = req.currency if (req and req.currency) else "INR"

    try:
        return await service.execute_live_run(
            payment_id=payment_id,
            order_id=order_id,
            amount=amount,
            currency=currency
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{incident_id}")
def get_incident(
    incident_id: str,
    discrepancy_reason: Optional[str] = Query(None),
    repo: PostgresActiveIncidentRepository = Depends(get_incident_repo),
):
    """Get a single incident by ID (active_subject)."""
    from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord

    with repo.session_maker() as session:
        q = session.query(ActiveIncidentIdempotencyRecord).filter(
            ActiveIncidentIdempotencyRecord.active_subject == incident_id
        )
        if discrepancy_reason:
            q = q.filter(ActiveIncidentIdempotencyRecord.discrepancy_reason == discrepancy_reason)
        record = q.order_by(ActiveIncidentIdempotencyRecord.created_at.desc()).first()

    if not record:
        raise HTTPException(status_code=404, detail="Incident not found")

    return _record_to_dict(record)
