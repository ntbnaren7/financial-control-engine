import hashlib
from datetime import datetime, timezone
from src.domain.investigation.lifecycle import IncidentState
import pytest
from uuid import uuid4
from decimal import Decimal

from src.reconciliation.models import ReconciliationResult, DiscrepancyType, ExpectedRefund
from src.state.models import KnowledgeState
from src.domain.incidents.models import Incident
from src.domain.incidents.projection import project_incident

def test_project_incident_match_returns_none():
    intent_id = str(uuid4())
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.0"),
        currency="USD",
        created_at=datetime.now(timezone.utc)
    )
    result = ReconciliationResult(
        expectation_id=expectation.expectation_id,
        intent_id=intent_id,
        discrepancy_type=DiscrepancyType.MATCH,
        is_actionable=False,
        reconciliation_timestamp=datetime.now(timezone.utc),
        expected_amount=None, expected_currency=None, observed_amount=None, observed_currency=None,
        observed_knowledge_state=KnowledgeState.VERIFIED,
        reconstructed_state_ids=("state_1",)
    )
    assert project_incident(result, expectation) is None

def test_project_incident_in_flight_pending_returns_none():
    intent_id = str(uuid4())
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.0"),
        currency="USD",
        created_at=datetime.now(timezone.utc)
    )
    result = ReconciliationResult(
        expectation_id=expectation.expectation_id,
        intent_id=intent_id,
        discrepancy_type=DiscrepancyType.IN_FLIGHT_PENDING,
        is_actionable=False,
        reconciliation_timestamp=datetime.now(timezone.utc),
        expected_amount=None, expected_currency=None, observed_amount=None, observed_currency=None,
        observed_knowledge_state=KnowledgeState.UNKNOWN,
        reconstructed_state_ids=("state_1",)
    )
    assert project_incident(result, expectation) is None

def test_project_incident_absent_execution_creates_incident():
    intent_id = str(uuid4())
    timestamp = datetime.now(timezone.utc)
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.0"),
        currency="USD",
        created_at=timestamp
    )
    result = ReconciliationResult(
        expectation_id=expectation.expectation_id,
        intent_id=intent_id,
        discrepancy_type=DiscrepancyType.ABSENT_EXECUTION,
        is_actionable=True,
        reconciliation_timestamp=timestamp,
        expected_amount=None, expected_currency=None, observed_amount=None, observed_currency=None,
        observed_knowledge_state=KnowledgeState.VERIFIED,
        reconstructed_state_ids=("state_1", "state_2"),
        details={"evidence_references": ["obs_1"]}
    )
    incident = project_incident(result, expectation)
    
    assert incident is not None
    assert incident.lifecycle_state == IncidentState.OPEN
    assert incident.expectation_id == expectation.expectation_id
    assert incident.refund_intent_id == intent_id
    assert incident.provider_payment_id == "pay_123"
    assert incident.discrepancy_type == DiscrepancyType.ABSENT_EXECUTION
    assert incident.reconciliation_timestamp == timestamp
    assert incident.reconstructed_state_ids == ["state_1", "state_2"]
    assert incident.evidence_references == ["obs_1"]
    assert incident.severity == "MEDIUM"

def test_project_incident_deterministic_identity():
    intent_id = "test_intent_123"
    discrepancy = DiscrepancyType.EPISTEMIC_STALEMATE
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.0"),
        currency="USD",
        created_at=datetime.now(timezone.utc)
    )
    result = ReconciliationResult(
        expectation_id=expectation.expectation_id,
        intent_id=intent_id,
        discrepancy_type=discrepancy,
        is_actionable=True,
        reconciliation_timestamp=datetime.now(timezone.utc),
        expected_amount=None, expected_currency=None, observed_amount=None, observed_currency=None,
        observed_knowledge_state=KnowledgeState.UNKNOWN,
        reconstructed_state_ids=("state_1",)
    )
    
    incident = project_incident(result, expectation)
    assert incident is not None
    
    expected_hash = hashlib.sha256(intent_id.encode("utf-8")).hexdigest()[:16]
    expected_incident_id = f"inc_{expected_hash}"

    assert incident.incident_id == expected_incident_id
    
    expected_disc_hash = hashlib.sha256(f"{intent_id}:{discrepancy.value}".encode("utf-8")).hexdigest()[:16]
    assert incident.discrepancy_instance_id == f"disc_{expected_disc_hash}"
