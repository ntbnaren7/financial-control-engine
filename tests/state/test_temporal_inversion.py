import pytest
from datetime import datetime, timezone, timedelta
import uuid

from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.state.models import KnowledgeState, ObservedFinancialState
from src.evidence.models import ProviderObservation, EntityType
from src.integrations.provider import ProviderQueryConfidence

def create_obs(payload: dict, age_seconds: int, provider_sequence: int = 0, provider_timestamp: str = None) -> ProviderObservation:
    # Use ingestion timestamp derived from age_seconds
    ingestion_time = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    
    _payload = payload.copy()
    if provider_sequence:
        _payload["provider_sequence"] = provider_sequence
    if provider_timestamp:
        _payload["provider_timestamp"] = provider_timestamp

    return ProviderObservation(
        entity_type=EntityType.PAYMENT.value,
        entity_id="pay_123",
        id=uuid.uuid4(),
        provider="razorpay",
        event_id=str(uuid.uuid4()),
        event_type="test",
        payload=_payload,
        created_at=ingestion_time
    )

def test_temporal_inversion_provider_timestamp():
    """
    Proves that causal order (based on provider_timestamp) supersedes ingestion time.
    A (older provider timestamp) arriving AFTER B (newer provider timestamp).
    """
    engine = StateEngine()
    policy = TemporalOrderingPolicy()
    now = datetime.now(timezone.utc)

    # Observation A: NOT_EXECUTED, occurred at 10:00, but ingested at 10:05 (age=0)
    obs_A = create_obs(
        {"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value},
        age_seconds=0, 
        provider_timestamp="2026-01-01T10:00:00Z"
    )

    # Observation B: REFUNDED, occurred at 10:02, but ingested at 10:01 (age=5)
    obs_B = create_obs(
        {"status": "REFUNDED"},
        age_seconds=5,
        provider_timestamp="2026-01-01T10:02:00Z"
    )

    # Reconstruct A -> B
    res1 = engine.reconstruct_state(
        EntityType.PAYMENT, "pay_123", [obs_A, obs_B], now, policy
    )
    # Reconstruct B -> A
    res2 = engine.reconstruct_state(
        EntityType.PAYMENT, "pay_123", [obs_B, obs_A], now, policy
    )

    # Both should conclude REFUNDED, because B (REFUNDED) is causally after A (NOT_EXECUTED)
    assert res1.observed_financial_state == ObservedFinancialState.REFUNDED
    assert res1.knowledge_state == KnowledgeState.VERIFIED
    
    assert res2.observed_financial_state == ObservedFinancialState.REFUNDED
    assert res2.knowledge_state == KnowledgeState.VERIFIED


def test_temporal_inversion_provider_sequence():
    """
    Proves that causal order (based on provider_sequence) supersedes provider_timestamp.
    """
    engine = StateEngine()
    policy = TemporalOrderingPolicy()
    now = datetime.now(timezone.utc)

    # obs_A: REFUNDED, sequence 5, timestamp 10:10
    obs_A = create_obs(
        {"status": "REFUNDED"},
        age_seconds=10, 
        provider_sequence=5,
        provider_timestamp="2026-01-01T10:10:00Z"
    )

    # obs_B: NOT_EXECUTED, sequence 6, timestamp 10:00 (provider clock skew)
    obs_B = create_obs(
        {"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value},
        age_seconds=5,
        provider_sequence=6,
        provider_timestamp="2026-01-01T10:00:00Z"
    )

    res1 = engine.reconstruct_state(
        EntityType.PAYMENT, "pay_123", [obs_A, obs_B], now, policy
    )
    res2 = engine.reconstruct_state(
        EntityType.PAYMENT, "pay_123", [obs_B, obs_A], now, policy
    )

    # Sequence 6 > Sequence 5. So B is later. B is NOT_EXECUTED.
    # We previously saw A (REFUNDED). 
    # This is a contradiction: concrete state then NOT_EXECUTED.
    assert res1.observed_financial_state is None
    assert res1.knowledge_state == KnowledgeState.CONTRADICTED

    assert res2.observed_financial_state is None
    assert res2.knowledge_state == KnowledgeState.CONTRADICTED


def test_ingestion_time_fallback():
    """
    When no sequence or provider timestamp is available, it relies on ingestion time (age_seconds).
    """
    engine = StateEngine()
    policy = TemporalOrderingPolicy()
    now = datetime.now(timezone.utc)

    obs_A = create_obs({"status": "REFUNDED"}, age_seconds=10) # older ingestion
    obs_B = create_obs({"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value}, age_seconds=2) # newer ingestion

    res1 = engine.reconstruct_state(
        EntityType.PAYMENT, "pay_123", [obs_A, obs_B], now, policy
    )
    res2 = engine.reconstruct_state(
        EntityType.PAYMENT, "pay_123", [obs_B, obs_A], now, policy
    )

    assert res1.observed_financial_state is None
    assert res1.knowledge_state == KnowledgeState.CONTRADICTED
    
    assert res2.observed_financial_state is None
    assert res2.knowledge_state == KnowledgeState.CONTRADICTED
