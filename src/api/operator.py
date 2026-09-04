"""
Operator actions router — retry, resolve, and pause automation.

All actions:
1. Are persisted as immutable OperatorAction records before any state change.
2. Go through the real state machine (assert_valid_transition enforced by repository).
3. RETRY does NOT bypass the Governance Gate — it re-queues the incident
   for the normal worker loop by transitioning back to INVESTIGATING.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime, timezone

from src.api.deps import get_incident_repo, get_governance_repo
from src.storage.postgres_substrate import PostgresActiveIncidentRepository, ActiveIncidentIdempotencyRecord
from src.storage.postgres_governance import PostgresGovernanceRepository
from src.domain.governance.models import OperatorAction, OperatorActionType, AutomationState, ControlPlaneState
from src.domain.investigation.lifecycle import IncidentState, IncidentStateMachine, InvalidStateTransitionError

router = APIRouter(prefix="/incidents", tags=["operator"])

ESCALATED_STATES = {
    "ESCALATED_PAUSED_BY_KILL_SWITCH", "ESCALATED_BUDGET_EXHAUSTED",
    "ESCALATED_POLICY_BLOCKED", "ESCALATED_MISSING_EVIDENCE",
    "ESCALATED_MUTATION_FAILED", "ESCALATED_CONVERGENCE_FAILED",
    "ESCALATED_UNKNOWN", "ESCALATED",
}


class OperatorActionRequest(BaseModel):
    operator_id: str = "operator"
    reason: str
    discrepancy_reason: Optional[str] = None


def _get_incident_or_404(
    session,
    incident_id: str,
    discrepancy_reason: Optional[str],
) -> ActiveIncidentIdempotencyRecord:
    q = session.query(ActiveIncidentIdempotencyRecord).filter(
        ActiveIncidentIdempotencyRecord.active_subject == incident_id
    )
    if discrepancy_reason:
        q = q.filter(ActiveIncidentIdempotencyRecord.discrepancy_reason == discrepancy_reason)
    record = q.order_by(ActiveIncidentIdempotencyRecord.created_at.desc()).first()
    if not record:
        raise HTTPException(status_code=404, detail="Incident not found")
    return record


@router.post("/{incident_id}/retry")
def retry_incident(
    incident_id: str,
    body: OperatorActionRequest,
    incident_repo: PostgresActiveIncidentRepository = Depends(get_incident_repo),
    governance_repo: PostgresGovernanceRepository = Depends(get_governance_repo),
):
    """
    Retry an escalated incident.

    Transitions the incident back to INVESTIGATING so the worker loop
    picks it up and re-runs the full control loop (including Governance Gate).
    This does NOT bypass any safety boundaries.
    """
    with incident_repo.session_maker() as session:
        record = _get_incident_or_404(session, incident_id, body.discrepancy_reason)
        current_state_val = record.state.value if hasattr(record.state, "value") else str(record.state)

        if current_state_val not in ESCALATED_STATES:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot retry incident in state '{current_state_val}'. Only escalated incidents can be retried."
            )

        # Validate transition
        try:
            IncidentStateMachine.assert_valid_transition(record.state, IncidentState.INVESTIGATING)  # type: ignore
        except InvalidStateTransitionError as e:
            raise HTTPException(status_code=422, detail=str(e))

        # Persist operator action record (immutable audit trail)
        operator_action = OperatorAction(
            incident_id=incident_id,
            operator_id=body.operator_id,
            action_type=OperatorActionType.RETRY_ACTUATION,
            reason=body.reason,
        )
        governance_repo.save_operator_action(operator_action)

        # Transition back to INVESTIGATING (worker will pick it up)
        record.state = IncidentState.INVESTIGATING  # type: ignore
        record.lease_owner = None  # type: ignore
        record.lease_expires_at = None  # type: ignore
        session.commit()

    return {
        "incident_id": incident_id,
        "action": "RETRY",
        "new_state": "INVESTIGATING",
        "operator_id": body.operator_id,
        "message": "Incident re-queued for investigation. Worker will pick it up and re-run the full control loop.",
    }


@router.post("/{incident_id}/resolve")
def resolve_incident(
    incident_id: str,
    body: OperatorActionRequest,
    incident_repo: PostgresActiveIncidentRepository = Depends(get_incident_repo),
    governance_repo: PostgresGovernanceRepository = Depends(get_governance_repo),
):
    """
    Manually resolve an escalated incident.

    Used when an operator has verified the discrepancy is handled out-of-band
    (e.g., manual refund issued). Persists audit record of the override.
    """
    with incident_repo.session_maker() as session:
        record = _get_incident_or_404(session, incident_id, body.discrepancy_reason)
        current_state_val = record.state.value if hasattr(record.state, "value") else str(record.state)

        if current_state_val == "RESOLVED":
            raise HTTPException(status_code=422, detail="Incident is already resolved.")

        # Validate transition
        try:
            IncidentStateMachine.assert_valid_transition(record.state, IncidentState.RESOLVED)  # type: ignore
        except InvalidStateTransitionError as e:
            raise HTTPException(status_code=422, detail=str(e))

        operator_action = OperatorAction(
            incident_id=incident_id,
            operator_id=body.operator_id,
            action_type=OperatorActionType.RESOLVE,
            reason=body.reason,
        )
        governance_repo.save_operator_action(operator_action)

        record.state = IncidentState.RESOLVED  # type: ignore
        record.lease_owner = None  # type: ignore
        record.lease_expires_at = None  # type: ignore
        session.commit()

    return {
        "incident_id": incident_id,
        "action": "RESOLVE",
        "new_state": "RESOLVED",
        "operator_id": body.operator_id,
        "message": "Incident marked as resolved by operator.",
    }


@router.post("/{incident_id}/escalate")
def escalate_incident(
    incident_id: str,
    body: OperatorActionRequest,
    incident_repo: PostgresActiveIncidentRepository = Depends(get_incident_repo),
    governance_repo: PostgresGovernanceRepository = Depends(get_governance_repo),
):
    """Force-escalate an in-progress incident (e.g., operator suspects data issue)."""
    with incident_repo.session_maker() as session:
        record = _get_incident_or_404(session, incident_id, body.discrepancy_reason)
        current_state_val = record.state.value if hasattr(record.state, "value") else str(record.state)
        current_state = IncidentState(current_state_val)

        # Enforce valid transition
        IncidentStateMachine.assert_valid_transition(current_state, IncidentState.ESCALATED_UNKNOWN)

        operator_action = OperatorAction(
            incident_id=incident_id,
            operator_id=body.operator_id,
            action_type=OperatorActionType.ESCALATE,
            reason=body.reason,
        )
        governance_repo.save_operator_action(operator_action)

        record.state = IncidentState.ESCALATED_UNKNOWN  # type: ignore
        record.lease_owner = None  # type: ignore
        record.lease_expires_at = None  # type: ignore
        session.commit()

    return {
        "incident_id": incident_id,
        "action": "ESCALATE",
        "new_state": "ESCALATED_UNKNOWN",
        "operator_id": body.operator_id,
    }


# ── Automation kill switch shortcut ──────────────────────────────────────────

class KillSwitchRequest(BaseModel):
    operator_id: str = "operator"
    reason: Optional[str] = None


@router.post("/automation/pause")
def pause_automation(
    body: KillSwitchRequest,
    governance_repo: PostgresGovernanceRepository = Depends(get_governance_repo),
):
    """Pause global automation (kill switch). New actuations will be blocked at the Governance Gate."""
    current = governance_repo.get_control_plane_state()
    updated = ControlPlaneState(
        id=current.id,
        automation_state=AutomationState.PAUSED,
        reason=body.reason or "Paused by operator",
        updated_by=body.operator_id,
        version=current.version,
    )
    success = governance_repo.update_control_plane_state_occ(updated)
    if not success:
        raise HTTPException(status_code=409, detail="Concurrent update — please retry.")
    return {"automation_state": "PAUSED", "reason": body.reason}


@router.post("/automation/resume")
def resume_automation(
    body: KillSwitchRequest,
    governance_repo: PostgresGovernanceRepository = Depends(get_governance_repo),
):
    """Resume global automation."""
    current = governance_repo.get_control_plane_state()
    updated = ControlPlaneState(
        id=current.id,
        automation_state=AutomationState.ENABLED,
        reason=body.reason,
        updated_by=body.operator_id,
        version=current.version,
    )
    success = governance_repo.update_control_plane_state_occ(updated)
    if not success:
        raise HTTPException(status_code=409, detail="Concurrent update — please retry.")
    return {"automation_state": "ENABLED", "reason": body.reason}
