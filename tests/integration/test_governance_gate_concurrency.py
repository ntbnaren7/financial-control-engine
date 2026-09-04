import pytest
import threading
from src.domain.investigation.lifecycle import IncidentState
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage.postgres.models import Base
from src.storage.postgres_governance import (
    SubstrateControlPlaneStateRecord,
    SubstrateActionBudgetRecord,
)
from src.storage.postgres_substrate import (
    ActiveIncidentIdempotencyRecord,
    SubstrateActuationRecord,
    IncidentState
)
from src.domain.governance.models import AutomationState, ActionBudget, BudgetPeriod
from src.domain.governance.gate import GovernanceGateDecision
from src.engine.governance_gate import GovernanceGate
from src.domain.core.models import RecoveryIntent, RecoveryAction
from src.domain.actuation.models import ActuationState

@pytest.fixture
def db_session_maker():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)

@pytest.fixture
def setup_db(db_session_maker):
    with db_session_maker() as session:
        # Setup kill switch
        session.add(SubstrateControlPlaneStateRecord(
            id="GLOBAL",
            automation_state=AutomationState.ENABLED.value,
            updated_by="SYSTEM",
            updated_at=datetime.now(timezone.utc),
            version=1
        ))
        # Setup budget
        session.add(SubstrateActionBudgetRecord(
            budget_id="budget_refund_payment",
            target_action="REFUND_PAYMENT",
            period=BudgetPeriod.HOURLY.value,
            count_limit=10,
            monetary_limit=1000,
            currency="INR",
            count_used=0,
            monetary_used=0,
            updated_at=datetime.now(timezone.utc),
            version=1
        ))
        # Setup incident
        session.add(ActiveIncidentIdempotencyRecord(
            active_subject="inc-123",
            discrepancy_reason="AMOUNT_MISMATCH",
            incident_id="inc-123",
            state=IncidentState.INVESTIGATING.value,
            retry_count=0,
            created_at=datetime.now(timezone.utc),
            version=1
        ))
        session.add(ActiveIncidentIdempotencyRecord(
            active_subject="inc-456",
            discrepancy_reason="AMOUNT_MISMATCH",
            incident_id="inc-456",
            state=IncidentState.INVESTIGATING.value,
            retry_count=0,
            created_at=datetime.now(timezone.utc),
            version=1
        ))
        session.commit()

def test_governance_gate_success(db_session_maker, setup_db):
    gate = GovernanceGate(db_session_maker)
    intent = RecoveryIntent(action=RecoveryAction.REFUND_PAYMENT, target_id="pay_1", amount=200, currency="INR")
    
    decision = gate.evaluate_and_claim(
        intent=intent,
        execution_identity="inc-123",
        discrepancy_reason="AMOUNT_MISMATCH",
        incident_version=1,
        budget_id="budget_refund_payment",
        budget_amount=200
    )
    
    assert decision.status == GovernanceGateDecision.ALLOWED
    assert decision.actuation_record is not None
    assert decision.actuation_record.state == ActuationState.PENDING
    
    # Verify DB
    with db_session_maker() as session:
        budget = session.query(SubstrateActionBudgetRecord).filter_by(budget_id="budget_refund_payment").first()
        assert budget.count_used == 1
        assert budget.monetary_used == 200
        
        incident = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject="inc-123").first()
        assert incident.state == IncidentState.ACTUATION_PENDING.value
        assert incident.version == 2
        
        actuation = session.query(SubstrateActuationRecord).filter_by(execution_identity="inc-123").first()
        assert actuation is not None

def test_governance_gate_kill_switch_blocks(db_session_maker, setup_db):
    with db_session_maker() as session:
        session.query(SubstrateControlPlaneStateRecord).filter_by(id="GLOBAL").update({"automation_state": AutomationState.PAUSED.value})
        session.commit()
        
    gate = GovernanceGate(db_session_maker)
    intent = RecoveryIntent(action=RecoveryAction.REFUND_PAYMENT, target_id="pay_1", amount=200, currency="INR")
    
    decision = gate.evaluate_and_claim(
        intent=intent,
        execution_identity="inc-123",
        discrepancy_reason="AMOUNT_MISMATCH",
        incident_version=1,
        budget_id="budget_refund_payment",
        budget_amount=200
    )
    
    assert decision.status == GovernanceGateDecision.BLOCKED_BY_KILL_SWITCH
    
    # DB must not have budget consumed
    with db_session_maker() as session:
        budget = session.query(SubstrateActionBudgetRecord).filter_by(budget_id="budget_refund_payment").first()
        assert budget.count_used == 0

def test_governance_gate_budget_exhaustion(db_session_maker, setup_db):
    gate = GovernanceGate(db_session_maker)
    intent = RecoveryIntent(action=RecoveryAction.REFUND_PAYMENT, target_id="pay_1", amount=1200, currency="INR") # Over 1000 limit
    
    decision = gate.evaluate_and_claim(
        intent=intent,
        execution_identity="inc-123",
        discrepancy_reason="AMOUNT_MISMATCH",
        incident_version=1,
        budget_id="budget_refund_payment",
        budget_amount=1200
    )
    
    assert decision.status == GovernanceGateDecision.BLOCKED_BY_BUDGET
    
    with db_session_maker() as session:
        budget = session.query(SubstrateActionBudgetRecord).filter_by(budget_id="budget_refund_payment").first()
        assert budget.count_used == 0

def test_governance_gate_concurrency_same_actuation(db_session_maker, setup_db):
    gate = GovernanceGate(db_session_maker)
    intent = RecoveryIntent(action=RecoveryAction.REFUND_PAYMENT, target_id="pay_1", amount=200, currency="INR")
    
    # Two workers try to claim the EXACT SAME incident concurrently (stale read)
    # The first one to commit will succeed, the second one will get IntegrityError due to version bump.
    decision1 = None
    decision2 = None
    
    def worker1():
        nonlocal decision1
        decision1 = gate.evaluate_and_claim(intent, "inc-123", "AMOUNT_MISMATCH", 1, "budget_refund_payment", 200)
        
    def worker2():
        nonlocal decision2
        decision2 = gate.evaluate_and_claim(intent, "inc-123", "AMOUNT_MISMATCH", 1, "budget_refund_payment", 200)

    # Note: SQLite with :memory: doesn't truly do parallel threads easily due to GIL and locking,
    # but we can simulate the failure by running them sequentially and expecting the second to fail 
    # because it uses the old version=1.
    worker1()
    worker2()
    
    # The first one succeeds
    assert decision1.status == GovernanceGateDecision.ALLOWED # type: ignore
    # The second one fails the claim
    assert decision2.status == GovernanceGateDecision.CLAIM_FAILED # type: ignore
    
    # Budget should only be consumed ONCE
    with db_session_maker() as session:
        budget = session.query(SubstrateActionBudgetRecord).filter_by(budget_id="budget_refund_payment").first()
        assert budget.count_used == 1
        assert budget.monetary_used == 200

def test_governance_gate_concurrency_different_actuation_budget(db_session_maker, setup_db):
    gate = GovernanceGate(db_session_maker)
    intent1 = RecoveryIntent(action=RecoveryAction.REFUND_PAYMENT, target_id="pay_1", amount=800, currency="INR")
    intent2 = RecoveryIntent(action=RecoveryAction.REFUND_PAYMENT, target_id="pay_2", amount=800, currency="INR")
    
    # Worker 1 takes 800, Worker 2 takes 800 (limit is 1000)
    decision1 = gate.evaluate_and_claim(intent1, "inc-123", "AMOUNT_MISMATCH", 1, "budget_refund_payment", 800)
    
    # Worker 2 should be blocked by budget
    decision2 = gate.evaluate_and_claim(intent2, "inc-456", "AMOUNT_MISMATCH", 1, "budget_refund_payment", 800)
    
    assert decision1.status == GovernanceGateDecision.ALLOWED
    assert decision2.status == GovernanceGateDecision.BLOCKED_BY_BUDGET
    
    with db_session_maker() as session:
        budget = session.query(SubstrateActionBudgetRecord).filter_by(budget_id="budget_refund_payment").first()
        assert budget.monetary_used == 800
