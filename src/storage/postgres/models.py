from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, DateTime, Integer, JSON, Boolean, Enum as SQLEnum, text, Index
from sqlalchemy.orm import declarative_base

from src.reconciliation.models import DiscrepancyType
from src.domain.incidents.models import IncidentState
from src.domain.actions.models import ActionType, ActionStatus

Base = declarative_base()

class ExpectationRecord(Base):
    __tablename__ = 'expectations'

    expectation_id = Column(String, primary_key=True)
    refund_intent_id = Column(String, nullable=False, unique=True, index=True)
    provider_payment_id = Column(String, nullable=False)
    amount = Column(String, nullable=False) # Store Decimal as string to avoid precision loss
    currency = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    sla_seconds = Column(Integer, nullable=False)
    source_system = Column(String, nullable=False)
    business_reason = Column(String, nullable=False)
    originating_trace_id = Column(String, nullable=False)

class ObservationRecord(Base):
    __tablename__ = 'observations'

    id = Column(String, primary_key=True)
    provider = Column(String, nullable=False)
    event_id = Column(String, nullable=False, unique=True, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

class IncidentRecord(Base):
    __tablename__ = 'incidents'

    incident_id = Column(String, primary_key=True)
    refund_intent_id = Column(String, nullable=True, unique=True, index=True) # Must be unique since 1 incident per intent
    lifecycle_state = Column(SQLEnum(IncidentState), nullable=False)
    
    expectation_id = Column(String, nullable=True)
    provider_payment_id = Column(String, nullable=True)
    discrepancy_type = Column(SQLEnum(DiscrepancyType), nullable=True)
    discrepancy_instance_id = Column(String, nullable=True)
    discrepancy_history = Column(JSON, nullable=False, default=list)
    reconciliation_timestamp = Column(DateTime(timezone=True), nullable=True)
    reconstructed_state_ids = Column(JSON, nullable=False, default=list)
    evidence_references = Column(JSON, nullable=False, default=list)
    severity = Column(String, nullable=False, default="LOW")
    provenance = Column(JSON, nullable=True)

    next_evaluation_at = Column(DateTime(timezone=True), nullable=True)
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    monitoring_reason = Column(String, nullable=True)
    query_count = Column(Integer, nullable=False, default=0)

class ActionRecord(Base):
    __tablename__ = 'actions'

    action_id = Column(String, primary_key=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    action_type = Column(SQLEnum(ActionType), nullable=False)
    incident_id = Column(String, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(SQLEnum(ActionStatus), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
