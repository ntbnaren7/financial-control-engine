"""
Governance router — kill switch and budget status.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.api.deps import get_governance_repo
from src.storage.postgres_governance import PostgresGovernanceRepository
from src.domain.governance.models import AutomationState, ControlPlaneState

router = APIRouter(prefix="/governance", tags=["governance"])


class ControlPlaneUpdateRequest(BaseModel):
    automation_state: str  # "ENABLED" or "PAUSED"
    reason: Optional[str] = None
    operator_id: str = "operator"


@router.get("/control-plane")
def get_control_plane(repo: PostgresGovernanceRepository = Depends(get_governance_repo)):
    """Get the global automation state (kill switch status)."""
    state = repo.get_control_plane_state()
    return {
        "automation_state": state.automation_state.value,
        "is_paused": state.automation_state == AutomationState.PAUSED,
        "reason": state.reason,
        "updated_by": state.updated_by,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        "version": state.version,
    }


@router.post("/control-plane")
def update_control_plane(
    body: ControlPlaneUpdateRequest,
    repo: PostgresGovernanceRepository = Depends(get_governance_repo),
):
    """
    Toggle automation state (kill switch).
    Uses OCC — if a concurrent update races, returns 409.
    """
    try:
        new_auto_state = AutomationState(body.automation_state)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid automation_state: {body.automation_state}. Use ENABLED or PAUSED.")

    current = repo.get_control_plane_state()
    updated = ControlPlaneState(
        id=current.id,
        automation_state=new_auto_state,
        reason=body.reason,
        updated_by=body.operator_id,
        version=current.version,
    )
    success = repo.update_control_plane_state_occ(updated)
    if not success:
        raise HTTPException(status_code=409, detail="Concurrent update conflict — please retry.")

    return {
        "automation_state": new_auto_state.value,
        "is_paused": new_auto_state == AutomationState.PAUSED,
        "reason": body.reason,
        "updated_by": body.operator_id,
    }


@router.get("/budgets")
def list_budgets(repo: PostgresGovernanceRepository = Depends(get_governance_repo)):
    """List all action budgets with current usage and remaining capacity."""
    from src.storage.postgres_governance import SubstrateActionBudgetRecord

    with repo.session_maker() as session:
        records = session.query(SubstrateActionBudgetRecord).all()

    return {
        "budgets": [
            {
                "budget_id": r.budget_id,
                "target_action": r.target_action,
                "period": r.period,
                "currency": r.currency,
                "count_limit": r.count_limit,
                "count_used": r.count_used,
                "count_remaining": r.count_limit - r.count_used,
                "monetary_limit": r.monetary_limit,
                "monetary_used": r.monetary_used,
                "monetary_remaining": r.monetary_limit - r.monetary_used,
                "count_pct_used": round(r.count_used / r.count_limit * 100, 1) if r.count_limit > 0 else 0,
                "monetary_pct_used": round(r.monetary_used / r.monetary_limit * 100, 1) if r.monetary_limit > 0 else 0,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in records
        ]
    }
