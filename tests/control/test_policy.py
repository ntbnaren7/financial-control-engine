from src.evidence.models import EntityType
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from src.state.models import ReconstructedState, KnowledgeState, ObservedFinancialState, ExecutionState
from src.integrations.provider import ProviderQueryConfidence
from src.domain.refunds.models import Refund
from src.control.policy import evaluate_refund_eligibility, ActionDecision

def utcnow():
    return datetime.now(timezone.utc)

def test_m4_high_confidence_but_unknown_state_is_rejected():
    """
    Scenario A: M4 claims HIGH confidence while deterministic state remains UNKNOWN 
    (must result in NO_ACTION).
    """
    # M4's high confidence is simulated by the incident existing and investigation 
    # proposing a refund. But the Control Plane only looks at deterministic state.
    state = ReconstructedState(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.UNKNOWN, # Deterministic state is UNKNOWN
        execution=None,
        observation_ids=("obs_123",),
        reconstructed_at=utcnow()
    )
    
    refund_intent = Refund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="INR",
        business_reason="test"
    )
    
    decision = evaluate_refund_eligibility(
        reconstructed_state=state,
        provider_query_confidence=ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED,
        refund_intent=refund_intent,
        incident_id="inc_456"
    )
    
    assert decision.decision == ActionDecision.NO_ACTION
    assert "Knowledge state is not VERIFIED" in decision.reason

def test_concrete_financial_state_rejects_refund():
    """
    If there is already a concrete financial state (e.g. refund in processing), 
    we cannot authorize another execution of the same intent.
    """
    state = ReconstructedState(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observed_financial_state=ObservedFinancialState.PROCESSING,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.EXECUTED,
        observation_ids=("obs_123",),
        reconstructed_at=utcnow()
    )
    
    refund_intent = Refund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="INR",
        business_reason="test"
    )
    
    decision = evaluate_refund_eligibility(
        reconstructed_state=state,
        provider_query_confidence=ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED,
        refund_intent=refund_intent,
        incident_id="inc_456"
    )
    
    assert decision.decision == ActionDecision.NO_ACTION
    assert "concrete financial state already exists" in decision.reason

def test_non_authoritative_query_rejects_refund():
    """
    If the provider query was not authoritative, the refund must be rejected.
    """
    state = ReconstructedState(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.NOT_EXECUTED,
        observation_ids=("obs_123",),
        reconstructed_at=utcnow()
    )
    
    refund_intent = Refund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="INR",
        business_reason="test"
    )
    
    decision = evaluate_refund_eligibility(
        reconstructed_state=state,
        provider_query_confidence=ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY,
        refund_intent=refund_intent,
        incident_id="inc_456"
    )
    
    assert decision.decision == ActionDecision.NO_ACTION
    assert "Provider query confidence is ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY" in decision.reason
