"""
Audit projection router — complete trace for a single incident.

Assembles a chronological audit timeline from:
  - ActiveIncidentIdempotencyRecord   (state history metadata)
  - SubstrateReconciliationResultRecord (the discrepancy that triggered this)
  - SubstrateEvidenceRecord            (evidence collected during investigation)
  - SubstrateActuationRecord           (what was sent to provider)
  - SubstrateOperatorActionRecord      (human interventions)
  - SubstrateObservationRecord         (final observed states)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from src.api.deps import get_incident_repo, get_actuation_repo, get_governance_repo
from src.storage.postgres_substrate import (
    PostgresActiveIncidentRepository,
    PostgresActuationRepository,
    ActiveIncidentIdempotencyRecord,
    SubstrateActuationRecord,
    SubstrateEvidenceRecord,
    SubstrateObservationRecord,
    SubstrateReconciliationResultRecord,
)
from src.storage.postgres_governance import PostgresGovernanceRepository, SubstrateOperatorActionRecord

router = APIRouter(prefix="/incidents", tags=["audit"])


@router.get("/{incident_id}/audit")
def get_audit_trace(
    incident_id: str,
    discrepancy_reason: Optional[str] = Query(None),
    incident_repo: PostgresActiveIncidentRepository = Depends(get_incident_repo),
    actuation_repo: PostgresActuationRepository = Depends(get_actuation_repo),
    governance_repo: PostgresGovernanceRepository = Depends(get_governance_repo),
):
    """
    Returns a complete audit projection for an incident:
    - Current state + metadata
    - Chronological timeline of state transitions (inferred from state + timestamps)
    - Recovery intent (from actuation record)
    - Actuation outcome
    - Evidence count
    - Operator interventions
    """
    # 1. Load incident record
    with incident_repo.session_maker() as session:
        q = session.query(ActiveIncidentIdempotencyRecord).filter(
            ActiveIncidentIdempotencyRecord.active_subject == incident_id
        )
        if discrepancy_reason:
            q = q.filter(ActiveIncidentIdempotencyRecord.discrepancy_reason == discrepancy_reason)
        incident = q.order_by(ActiveIncidentIdempotencyRecord.created_at.desc()).first()

        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        incident_state = incident.state.value if hasattr(incident.state, "value") else str(incident.state)
        disc_reason = incident.discrepancy_reason

        # 2. Load actuation record
        actuation = session.query(SubstrateActuationRecord).filter(
            SubstrateActuationRecord.execution_identity == incident_id,
        ).order_by(SubstrateActuationRecord.created_at.desc()).first()

        # 3. Load evidence count
        evidence_count = session.query(SubstrateEvidenceRecord).count()

        # 4. Load reconciliation result that triggered this
        recon = session.query(SubstrateReconciliationResultRecord).filter(
            SubstrateReconciliationResultRecord.discrepancy_reason == disc_reason
        ).order_by(SubstrateReconciliationResultRecord.created_at.asc()).first()

    # 5. Load operator actions
    operator_actions = governance_repo.get_operator_actions_for_incident(incident_id)

    # 6. Build timeline (inferred from current state + key event markers)
    STATE_ORDER = [
        "DETECTED", "INVESTIGATING", "VERIFYING", "ACTIONABLE",
        "ACTUATION_PENDING", "ACTUATING", "REOBSERVING",
    ]
    ESCALATION_STATES = [s for s in [
        "ESCALATED_PAUSED_BY_KILL_SWITCH", "ESCALATED_BUDGET_EXHAUSTED",
        "ESCALATED_POLICY_BLOCKED", "ESCALATED_MISSING_EVIDENCE",
        "ESCALATED_MUTATION_FAILED", "ESCALATED_CONVERGENCE_FAILED",
        "ESCALATED_UNKNOWN", "ESCALATED"
    ] if incident_state == s or incident_state.startswith("ESCALATED")]

    STEP_DESCRIPTIONS = {
        "DETECTED": "Reconciliation discrepancy detected",
        "INVESTIGATING": f"AI investigation: analyzing discrepancy '{disc_reason}'",
        "VERIFYING": f"Deterministic verification ({evidence_count} evidence records collected)",
        "ACTIONABLE": "Policy evaluation: recovery intent derived",
        "ACTUATION_PENDING": "Governance Gate: claim established, actuation authorized",
        "ACTUATING": "External mutation dispatched to provider",
        "REOBSERVING": "Re-observation: reading external state post-mutation",
        "RESOLVED": "Convergence confirmed — incident resolved",
        "ESCALATED_PAUSED_BY_KILL_SWITCH": "Escalated: automation paused by kill switch",
        "ESCALATED_BUDGET_EXHAUSTED": "Escalated: action budget exhausted",
        "ESCALATED_POLICY_BLOCKED": "Escalated: policy could not derive safe action",
        "ESCALATED_MISSING_EVIDENCE": "Escalated: insufficient evidence for verification",
        "ESCALATED_MUTATION_FAILED": "Escalated: external mutation rejected by provider",
        "ESCALATED_CONVERGENCE_FAILED": "Escalated: actuation sent but external state did not converge",
        "ESCALATED_UNKNOWN": "Escalated: unclassified failure",
        "ESCALATED": "Escalated: manual operator review required",
    }

    # Build the ordered timeline based on what state we know was reached
    timeline = []
    created_at_str = incident.created_at.isoformat() if incident.created_at else None

    if incident_state in ("RESOLVED", "COMPLETED"):
        # Full path through
        for step in STATE_ORDER + ["RESOLVED"]:
            timeline.append({"step": step, "at": created_at_str, "detail": STEP_DESCRIPTIONS.get(step, step)})
    elif incident_state in ESCALATION_STATES or incident_state.startswith("ESCALATED"):
        # Partial path + escalation terminal
        reachable = []
        for step in STATE_ORDER:
            reachable.append(step)
            if incident_state == step:
                break
        # Include steps up to the one before escalation
        for step in reachable[:-1] if incident_state not in STATE_ORDER else reachable:
            timeline.append({"step": step, "at": created_at_str, "detail": STEP_DESCRIPTIONS.get(step, step)})
        timeline.append({"step": incident_state, "at": created_at_str, "detail": STEP_DESCRIPTIONS.get(incident_state, f"Escalated: {incident_state}")})
    else:
        # In-progress: show steps up to current
        for step in STATE_ORDER:
            timeline.append({"step": step, "at": created_at_str, "detail": STEP_DESCRIPTIONS.get(step, step)})
            if step == incident_state:
                break

    # 7. Build actuation section
    actuation_data = None
    recovery_intent = None
    if actuation:
        act_state = actuation.state.value if hasattr(actuation.state, "value") else str(actuation.state)
        actuation_data = {
            "idempotency_key": actuation.idempotency_key,
            "state": act_state,
            "provider": actuation.provider,
            "intent_action": actuation.intent_action,
            "target_id": actuation.target_id,
            "created_at": actuation.created_at.isoformat() if actuation.created_at else None,
            "completed_at": actuation.completed_at.isoformat() if actuation.completed_at else None,
            "failure_reason": actuation.failure_reason,
        }
        # Parse recovery intent from canonical payload
        import json
        try:
            params = json.loads(actuation.mutation_parameters_canonical or "{}")
        except Exception:
            params = {}
        recovery_intent = {
            "action": actuation.intent_action,
            "target_id": actuation.target_id,
            **params,
        }

    return {
        "incident_id": incident_id,
        "discrepancy_reason": disc_reason,
        "current_state": incident_state,
        "is_terminal": incident_state in {
            "RESOLVED", "COMPLETED", "ESCALATED_PAUSED_BY_KILL_SWITCH",
            "ESCALATED_BUDGET_EXHAUSTED", "ESCALATED_POLICY_BLOCKED",
            "ESCALATED_MISSING_EVIDENCE", "ESCALATED_MUTATION_FAILED",
            "ESCALATED_CONVERGENCE_FAILED", "ESCALATED_UNKNOWN", "ESCALATED",
        },
        "created_at": created_at_str,
        "retry_count": incident.retry_count,
        "hypothesis_available": bool(incident.hypothesis_payload),
        "timeline": timeline,
        "recovery_intent": recovery_intent,
        "actuation": actuation_data,
        "evidence_count": evidence_count,
        "operator_actions": [
            {
                "action_id": a.action_id,
                "action_type": a.action_type.value if hasattr(a.action_type, "value") else str(a.action_type),
                "operator_id": a.operator_id,
                "reason": a.reason,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            }
            for a in operator_actions
        ],
        "discrepancy": {
            "reconciliation_id": recon.reconciliation_id if recon else None,
            "outcome": recon.outcome.value if recon and hasattr(recon.outcome, "value") else str(recon.outcome) if recon else None,
            "discrepancy_reason": recon.discrepancy_reason if recon else disc_reason,
        } if recon else None,
    }
