import pytest
from datetime import datetime, timezone
import threading
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage.postgres.models import Base
from src.storage.postgres_governance import PostgresGovernanceRepository
from src.domain.governance.models import (
    ControlPlaneState,
    AutomationState,
    ActionBudget,
    BudgetPeriod,
    OperatorAction,
    OperatorActionType
)

@pytest.fixture
def db_session_maker():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)

@pytest.fixture
def repo(db_session_maker):
    return PostgresGovernanceRepository(db_session_maker)

def test_control_plane_state_persistence_and_occ(repo):
    # Initialize in DB first
    repo.update_control_plane_state_occ(ControlPlaneState(id="GLOBAL", version=1))

    # Default is ENABLED
    state = repo.get_control_plane_state()
    assert state.automation_state == AutomationState.ENABLED
    
    # Save custom state
    state.automation_state = AutomationState.PAUSED
    state.reason = "Manual override"
    success = repo.update_control_plane_state_occ(state)
    assert success is True
    
    # Reload and verify
    reloaded = repo.get_control_plane_state()
    assert reloaded.automation_state == AutomationState.PAUSED
    assert reloaded.reason == "Manual override"
    assert reloaded.version == 2
    
    # Test OCC Failure
    stale_state = ControlPlaneState(
        id="GLOBAL",
        automation_state=AutomationState.ENABLED,
        version=1 # Stale, current is 2
    )
    success = repo.update_control_plane_state_occ(stale_state)
    assert success is False
    
    # Ensure state remains unchanged
    final_state = repo.get_control_plane_state()
    assert final_state.automation_state == AutomationState.PAUSED

def test_action_budget_persistence_and_occ(repo):
    budget = ActionBudget(
        budget_id="test_budget",
        target_action="REFUND_PAYMENT",
        period=BudgetPeriod.HOURLY,
        count_limit=10,
        monetary_limit=5000,
        currency="INR"
    )
    
    repo.save_budget(budget)
    
    loaded = repo.get_budget("test_budget")
    assert loaded is not None
    assert loaded.count_limit == 10
    
    # Update OCC
    loaded.consume(1000)
    success = repo.update_budget_occ(loaded)
    assert success is True
    
    # Reload and check
    reloaded = repo.get_budget("test_budget")
    assert reloaded.count_used == 1
    assert reloaded.monetary_used == 1000
    assert reloaded.version == 2
    
    # Test OCC Failure
    stale_budget = ActionBudget(
        budget_id="test_budget",
        target_action="REFUND_PAYMENT",
        period=BudgetPeriod.HOURLY,
        count_limit=10,
        monetary_limit=5000,
        currency="INR",
        count_used=2,
        version=1 # Stale, current is 2
    )
    success = repo.update_budget_occ(stale_budget)
    assert success is False
    
def test_operator_action_persistence(repo):
    action = OperatorAction(
        incident_id="inc-123",
        operator_id="user-xyz",
        action_type=OperatorActionType.ESCALATE,
        reason="Need level 2 review"
    )
    
    repo.save_operator_action(action)
    
    # Fetch
    actions = repo.get_operator_actions_for_incident("inc-123")
    assert len(actions) == 1
    assert actions[0].operator_id == "user-xyz"
    assert actions[0].action_type == OperatorActionType.ESCALATE
