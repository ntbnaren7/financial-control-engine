from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.storage.postgres.models import Base
from src.domain.governance.models import (
    ControlPlaneState,
    AutomationState,
    ActionBudget,
    BudgetPeriod,
    OperatorAction,
    OperatorActionType
)

class SubstrateControlPlaneStateRecord(Base):
    __tablename__ = 'v2_control_plane_state'
    id = Column(String, primary_key=True, default="GLOBAL")
    automation_state = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    updated_by = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(Integer, nullable=False, default=1)

    def to_domain(self) -> ControlPlaneState:
        return ControlPlaneState(
            id=self.id, # type: ignore
            automation_state=AutomationState(self.automation_state), # type: ignore
            reason=self.reason, # type: ignore
            updated_by=self.updated_by, # type: ignore
            updated_at=self.updated_at, # type: ignore
            version=self.version # type: ignore
        )

    @classmethod
    def from_domain(cls, state: ControlPlaneState) -> "SubstrateControlPlaneStateRecord":
        return cls(
            id=state.id,
            automation_state=state.automation_state.value,
            reason=state.reason,
            updated_by=state.updated_by,
            updated_at=state.updated_at,
            version=state.version
        )

class SubstrateActionBudgetRecord(Base):
    __tablename__ = 'v2_action_budgets'
    budget_id = Column(String, primary_key=True)
    target_action = Column(String, nullable=False, index=True)
    period = Column(String, nullable=False)
    count_limit = Column(Integer, nullable=False)
    monetary_limit = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    count_used = Column(Integer, nullable=False, default=0)
    monetary_used = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(Integer, nullable=False, default=1)

    def to_domain(self) -> ActionBudget:
        return ActionBudget(
            budget_id=self.budget_id, # type: ignore
            target_action=self.target_action, # type: ignore
            period=BudgetPeriod(self.period), # type: ignore
            count_limit=self.count_limit, # type: ignore
            monetary_limit=self.monetary_limit, # type: ignore
            currency=self.currency, # type: ignore
            count_used=self.count_used, # type: ignore
            monetary_used=self.monetary_used, # type: ignore
            updated_at=self.updated_at, # type: ignore
            version=self.version # type: ignore
        )

    @classmethod
    def from_domain(cls, budget: ActionBudget) -> "SubstrateActionBudgetRecord":
        return cls(
            budget_id=budget.budget_id,
            target_action=budget.target_action,
            period=budget.period.value,
            count_limit=budget.count_limit,
            monetary_limit=budget.monetary_limit,
            currency=budget.currency,
            count_used=budget.count_used,
            monetary_used=budget.monetary_used,
            updated_at=budget.updated_at,
            version=budget.version
        )

class SubstrateOperatorActionRecord(Base):
    __tablename__ = 'v2_operator_actions'
    action_id = Column(String, primary_key=True)
    incident_id = Column(String, nullable=False, index=True)
    operator_id = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    resulting_intent_id = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)

    def to_domain(self) -> OperatorAction:
        return OperatorAction(
            action_id=self.action_id, # type: ignore
            incident_id=self.incident_id, # type: ignore
            operator_id=self.operator_id, # type: ignore
            action_type=OperatorActionType(self.action_type), # type: ignore
            reason=self.reason, # type: ignore
            resulting_intent_id=self.resulting_intent_id, # type: ignore
            timestamp=self.timestamp # type: ignore
        )

    @classmethod
    def from_domain(cls, action: OperatorAction) -> "SubstrateOperatorActionRecord":
        return cls(
            action_id=action.action_id,
            incident_id=action.incident_id,
            operator_id=action.operator_id,
            action_type=action.action_type.value,
            reason=action.reason,
            resulting_intent_id=action.resulting_intent_id,
            timestamp=action.timestamp
        )

class PostgresGovernanceRepository:
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def get_control_plane_state(self, state_id: str = "GLOBAL") -> ControlPlaneState:
        with self.session_maker() as session:
            record = session.query(SubstrateControlPlaneStateRecord).filter_by(id=state_id).first()
            if not record:
                # Default state is ENABLED
                return ControlPlaneState(id=state_id)
            return record.to_domain()

    def update_control_plane_state_occ(self, new_state: ControlPlaneState) -> bool:
        """
        Atomically update the global control plane state using OCC.
        Returns True on success, False if concurrent modification occurred.
        """
        with self.session_maker() as session:
            record = session.query(SubstrateControlPlaneStateRecord).filter_by(id=new_state.id).first()
            if not record:
                if new_state.version != 1:
                    return False
                new_record = SubstrateControlPlaneStateRecord.from_domain(new_state)
                session.add(new_record)
                try:
                    session.commit()
                    return True
                except IntegrityError:
                    session.rollback()
                    return False
            
            if record.version != new_state.version:
                return False
                
            updated = session.query(SubstrateControlPlaneStateRecord).filter(
                SubstrateControlPlaneStateRecord.id == new_state.id,
                SubstrateControlPlaneStateRecord.version == new_state.version
            ).update({
                'automation_state': new_state.automation_state.value,
                'reason': new_state.reason,
                'updated_by': new_state.updated_by,
                'updated_at': datetime.now(timezone.utc),
                'version': new_state.version + 1
            })
            session.commit()
            return updated > 0

    def get_budget(self, budget_id: str) -> Optional[ActionBudget]:
        with self.session_maker() as session:
            record = session.query(SubstrateActionBudgetRecord).filter_by(budget_id=budget_id).first()
            return record.to_domain() if record else None
            
    def save_budget(self, budget: ActionBudget) -> None:
        """Initializes or overwrites a budget."""
        with self.session_maker() as session:
            record = session.query(SubstrateActionBudgetRecord).filter_by(budget_id=budget.budget_id).first()
            if record:
                record.count_limit = budget.count_limit
                record.monetary_limit = budget.monetary_limit
                record.count_used = budget.count_used
                record.monetary_used = budget.monetary_used
                record.updated_at = budget.updated_at
                record.version = budget.version
            else:
                session.add(SubstrateActionBudgetRecord.from_domain(budget))
            session.commit()

    def update_budget_occ(self, budget: ActionBudget) -> bool:
        """
        Update the budget using OCC.
        """
        with self.session_maker() as session:
            updated = session.query(SubstrateActionBudgetRecord).filter(
                SubstrateActionBudgetRecord.budget_id == budget.budget_id,
                SubstrateActionBudgetRecord.version == budget.version
            ).update({
                'count_used': budget.count_used,
                'monetary_used': budget.monetary_used,
                'updated_at': datetime.now(timezone.utc),
                'version': budget.version + 1
            })
            session.commit()
            return updated > 0

    def save_operator_action(self, action: OperatorAction) -> None:
        """Immutable save of an operator action."""
        with self.session_maker() as session:
            session.add(SubstrateOperatorActionRecord.from_domain(action))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                
    def get_operator_actions_for_incident(self, incident_id: str) -> List[OperatorAction]:
        with self.session_maker() as session:
            records = session.query(SubstrateOperatorActionRecord).filter_by(incident_id=incident_id).order_by(SubstrateOperatorActionRecord.timestamp.asc()).all()
            return [r.to_domain() for r in records]
