import pytest
from datetime import datetime, timezone, timedelta
import uuid

from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.state.models import KnowledgeState, ObservedFinancialState
from src.evidence.models import ProviderObservation, EntityType
from src.integrations.provider import ProviderQueryConfidence

def create_obs(entity_type: EntityType, entity_id: str, payload: dict, age_seconds: int) -> ProviderObservation:
    return ProviderObservation(
        entity_type=entity_type.value,
        entity_id=entity_id,
        id=uuid.uuid4(),
        provider="razorpay",
        event_id=str(uuid.uuid4()),
        event_type="test",
        payload=payload,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    )

def test_case1_cross_entity_no_contamination():
    """
    Case 1:
    PAYMENT:p1 -> REFUNDED
    REFUND_INTENT:ri1 -> NOT_EXECUTED
    """
    obs_pay = create_obs(
        EntityType.PAYMENT, "p1", 
        {"status": "REFUNDED"}, age_seconds=10
    )
    obs_ri = create_obs(
        EntityType.REFUND_INTENT, "ri1", 
        {"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value}, age_seconds=5
    )
    
    engine = StateEngine()
    
    pay_state = engine.reconstruct_state(
        entity_type=EntityType.PAYMENT,
        entity_id="p1",
        observations=[obs_pay],
        reconstructed_at=datetime.now(timezone.utc),
        ordering_policy=TemporalOrderingPolicy()
    )
    assert pay_state.observed_financial_state == ObservedFinancialState.REFUNDED
    assert pay_state.knowledge_state == KnowledgeState.VERIFIED
    
    ri_state = engine.reconstruct_state(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ri1",
        observations=[obs_ri],
        reconstructed_at=datetime.now(timezone.utc),
        ordering_policy=TemporalOrderingPolicy()
    )
    assert ri_state.observed_financial_state is None
    assert ri_state.knowledge_state == KnowledgeState.VERIFIED


def test_case2_intent_independence():
    """
    Case 2:
    REFUND_INTENT:ri1 -> NOT_EXECUTED
    REFUND_INTENT:ri2 -> EXECUTED (REFUNDED)
    """
    obs_ri1 = create_obs(
        EntityType.REFUND_INTENT, "ri1", 
        {"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value}, age_seconds=10
    )
    obs_ri2 = create_obs(
        EntityType.REFUND_INTENT, "ri2", 
        {"status": "REFUNDED"}, age_seconds=5
    )
    
    engine = StateEngine()
    
    ri1_state = engine.reconstruct_state(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ri1",
        observations=[obs_ri1],
        reconstructed_at=datetime.now(timezone.utc),
        ordering_policy=TemporalOrderingPolicy()
    )
    assert ri1_state.observed_financial_state is None
    assert ri1_state.knowledge_state == KnowledgeState.VERIFIED
    
    ri2_state = engine.reconstruct_state(
        entity_type=EntityType.REFUND_INTENT,
        entity_id="ri2",
        observations=[obs_ri2],
        reconstructed_at=datetime.now(timezone.utc),
        ordering_policy=TemporalOrderingPolicy()
    )
    assert ri2_state.observed_financial_state == ObservedFinancialState.REFUNDED
    assert ri2_state.knowledge_state == KnowledgeState.VERIFIED


def test_case3_no_automatic_contradiction_between_intent_and_payment():
    """
    Case 3:
    REFUND_INTENT:ri1 -> NOT_EXECUTED
    PAYMENT:p1 -> REFUNDED
    
    Even if passed into a theoretical global evaluation, the engine should raise an error 
    if observations from different entities are mixed, enforcing proposition scope.
    """
    obs_pay = create_obs(
        EntityType.PAYMENT, "p1", 
        {"status": "REFUNDED"}, age_seconds=10
    )
    obs_ri1 = create_obs(
        EntityType.REFUND_INTENT, "ri1", 
        {"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value}, age_seconds=5
    )
    
    engine = StateEngine()
    
    with pytest.raises(ValueError) as exc:
        engine.reconstruct_state(
            entity_type=EntityType.PAYMENT,
            entity_id="p1",
            observations=[obs_pay, obs_ri1],
            reconstructed_at=datetime.now(timezone.utc),
            ordering_policy=TemporalOrderingPolicy()
        )
    
    assert "mismatched entity scope" in str(exc.value)
