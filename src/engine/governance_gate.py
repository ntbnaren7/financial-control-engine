import structlog
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.domain.core.models import RecoveryIntent, RecoveryAction
from src.domain.actuation.models import ActuationRecord, ActuationState
from src.domain.governance.models import AutomationState
from src.domain.governance.gate import GovernanceGateDecision, GateDecision
from src.storage.postgres_substrate import (
    ActiveIncidentIdempotencyRecord,
    SubstrateActuationRecord,
)
from src.domain.investigation.lifecycle import IncidentState
from src.storage.postgres_governance import (
    SubstrateControlPlaneStateRecord,
    SubstrateActionBudgetRecord
)
from src.engine.actuation_key import generate_canonical_payload, generate_idempotency_key

logger = structlog.get_logger()

class GovernanceGate:
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def evaluate_and_claim(
        self,
        intent: RecoveryIntent,
        execution_identity: str,
        discrepancy_reason: str,
        incident_version: int,
        budget_id: str,
        budget_amount: int
    ) -> GateDecision:
        """
        Atomically evaluates governance rules and establishes the actuation claim.
        Must be the ONLY path into actuation to guarantee authoritativeness.
        """
        # 1. Build canonical mutation payload
        payload = {}
        if intent.action == RecoveryAction.REFUND_PAYMENT:
            if intent.amount is not None:
                payload["amount"] = intent.amount
            if intent.currency is not None:
                payload["currency"] = intent.currency
        elif intent.action == RecoveryAction.REPAIR_MERCHANT_STATE:
            payload["expected_provider_state"] = intent.expected_provider_state

        canonical_str = generate_canonical_payload(payload)

        # 2. Deterministic idempotency key
        idempotency_key = generate_idempotency_key(
            execution_identity=execution_identity,
            intent_action=intent.action.value,
            target_id=intent.target_id,
            canonical_payload=canonical_str,
        )

        with self.session_maker() as session:
            try:
                # 1. Kill switch
                cp_record = session.query(SubstrateControlPlaneStateRecord).with_for_update().filter_by(id="GLOBAL").first()
                if cp_record and cp_record.automation_state != AutomationState.ENABLED.value:
                    return GateDecision(status=GovernanceGateDecision.BLOCKED_BY_KILL_SWITCH, reason="Automation is paused")

                # 2. Budget
                budget = session.query(SubstrateActionBudgetRecord).with_for_update().filter_by(budget_id=budget_id).first()
                if not budget:
                    return GateDecision(status=GovernanceGateDecision.BLOCKED_BY_BUDGET, reason="Budget not found")
                    
                domain_budget = budget.to_domain()
                if not domain_budget.can_consume(budget_amount):
                    return GateDecision(status=GovernanceGateDecision.BLOCKED_BY_BUDGET, reason="Budget exhausted")
                
                # Consume budget locally and update record
                domain_budget.consume(budget_amount)
                budget.count_used = domain_budget.count_used
                budget.monetary_used = domain_budget.monetary_used
                budget.updated_at = domain_budget.updated_at
                budget.version = domain_budget.version

                # 3. Actuation Claim (Update Incident State OCC)
                incident = session.query(ActiveIncidentIdempotencyRecord).filter(
                    ActiveIncidentIdempotencyRecord.active_subject == execution_identity,
                    ActiveIncidentIdempotencyRecord.discrepancy_reason == discrepancy_reason,
                    ActiveIncidentIdempotencyRecord.version == incident_version
                ).update({
                    'state': IncidentState.ACTUATION_PENDING.value,
                    'version': ActiveIncidentIdempotencyRecord.version + 1
                })
                
                if incident == 0:
                    return GateDecision(status=GovernanceGateDecision.CLAIM_FAILED, reason="Incident OCC claim failed")

                # 4. Save PENDING actuation record
                provider_name = "razorpay" if intent.action == RecoveryAction.REFUND_PAYMENT else "merchant"
                record = ActuationRecord(
                    execution_identity=execution_identity,
                    intent_action=intent.action.value,
                    target_id=intent.target_id,
                    mutation_parameters_canonical=canonical_str,
                    idempotency_key=idempotency_key,
                    provider=provider_name,
                    state=ActuationState.PENDING,
                )
                
                db_record = SubstrateActuationRecord(
                    record_id=record.record_id,
                    execution_identity=record.execution_identity,
                    intent_action=record.intent_action,
                    target_id=record.target_id,
                    mutation_parameters_canonical=record.mutation_parameters_canonical,
                    idempotency_key=record.idempotency_key,
                    provider=record.provider,
                    state=record.state.value,
                    created_at=record.created_at,
                    updated_at=record.updated_at
                )
                session.add(db_record)
                
                session.commit()
                return GateDecision(status=GovernanceGateDecision.ALLOWED, reason="Claimed", actuation_record=record)
            except IntegrityError:
                session.rollback()
                return GateDecision(status=GovernanceGateDecision.CLAIM_FAILED, reason="Integrity error during claim")
            except Exception as e:
                session.rollback()
                logger.error(f"GovernanceGate error: {str(e)}")
                raise
