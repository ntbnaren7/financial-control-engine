import pytest
from datetime import datetime, timezone
from src.domain.governance.models import (
    ControlPlaneState,
    AutomationState,
    ActionBudget,
    BudgetPeriod,
    OperatorAction,
    OperatorActionType
)

def test_control_plane_state_initialization():
    state = ControlPlaneState()
    assert state.id == "GLOBAL"
    assert state.automation_state == AutomationState.ENABLED
    assert state.version == 1
    assert state.updated_by == "SYSTEM"

def test_action_budget_consumption():
    budget = ActionBudget(
        budget_id="refund_hourly",
        target_action="REFUND_PAYMENT",
        period=BudgetPeriod.HOURLY,
        count_limit=5,
        monetary_limit=1000,
        currency="INR"
    )

    assert budget.can_consume(200) is True
    budget.consume(200)
    
    assert budget.count_used == 1
    assert budget.monetary_used == 200

    # Test count exhaustion
    for _ in range(4):
        budget.consume(100)
        
    assert budget.count_used == 5
    assert budget.monetary_used == 600
    
    assert budget.can_consume(100) is False
    with pytest.raises(ValueError, match="Budget exhausted"):
        budget.consume(100)

def test_action_budget_monetary_exhaustion():
    budget = ActionBudget(
        budget_id="refund_hourly",
        target_action="REFUND_PAYMENT",
        period=BudgetPeriod.HOURLY,
        count_limit=10,
        monetary_limit=1000,
        currency="INR"
    )

    assert budget.can_consume(1000) is True
    budget.consume(1000)
    
    assert budget.can_consume(1) is False
    with pytest.raises(ValueError, match="Budget exhausted"):
        budget.consume(1)

def test_operator_action_immutability():
    action = OperatorAction(
        incident_id="inc-123",
        operator_id="user-456",
        action_type=OperatorActionType.OVERRIDE_POLICY,
        reason="Manual approval provided by risk team"
    )
    
    assert action.incident_id == "inc-123"
    assert action.action_type == OperatorActionType.OVERRIDE_POLICY
    assert action.resulting_intent_id is None
