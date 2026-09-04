import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

class AutomationState(str, Enum):
    ENABLED = "ENABLED"
    PAUSED = "PAUSED"

@dataclass
class ControlPlaneState:
    """
    Durable global automation state that controls whether the autonomous loop
    is allowed to execute actuations.
    """
    id: str = "GLOBAL"  # Singleton for global state
    automation_state: AutomationState = AutomationState.ENABLED
    reason: Optional[str] = None
    updated_by: str = "SYSTEM"
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

class BudgetPeriod(str, Enum):
    HOURLY = "HOURLY"
    DAILY = "DAILY"
    
@dataclass
class ActionBudget:
    """
    Atomic budget enforcing dual-dimension limits (count and monetary)
    on automated actuations.
    """
    budget_id: str
    target_action: str  # e.g. "REFUND_PAYMENT"
    period: BudgetPeriod
    count_limit: int
    monetary_limit: int
    currency: str
    
    count_used: int = 0
    monetary_used: int = 0
    
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def can_consume(self, amount: int) -> bool:
        """Determines if the budget allows consuming the specified amount."""
        return (self.count_used + 1 <= self.count_limit) and \
               (self.monetary_used + amount <= self.monetary_limit)

    def consume(self, amount: int) -> None:
        """Mutates the budget. Must be persisted via OCC/Atomic update."""
        if not self.can_consume(amount):
            raise ValueError("Budget exhausted")
        self.count_used += 1
        self.monetary_used += amount
        self.updated_at = datetime.now(timezone.utc)

class OperatorActionType(str, Enum):
    ESCALATE = "ESCALATE"
    RETRY_ACTUATION = "RETRY_ACTUATION"
    OVERRIDE_POLICY = "OVERRIDE_POLICY"
    RESOLVE = "RESOLVE"
    
@dataclass(frozen=True)
class OperatorAction:
    """
    Immutable audit record of a human operator intervening in an incident.
    """
    incident_id: str
    operator_id: str
    action_type: OperatorActionType
    reason: str
    resulting_intent_id: Optional[str] = None
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
