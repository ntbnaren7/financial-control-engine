from src.evidence.models import EntityType
import pytest
from datetime import datetime, timezone, timedelta
import uuid

from src.evidence.models import ProviderObservation
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.state.models import KnowledgeState, ObservedFinancialState
from src.integrations.provider import ProviderQueryConfidence

def create_obs(payload: dict, age_seconds: int) -> ProviderObservation:
    return ProviderObservation(
        entity_type=EntityType.PAYMENT.value,
        entity_id="pay_123",
        id=uuid.uuid4(),
        provider="razorpay",
        event_id=str(uuid.uuid4()),
        event_type="test",
        payload=payload,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    )

def test_stale_observation_followed_by_fresh():
    """
    Scenario A: Stale provider observation followed by a fresh observation.
    The StateEngine must sort chronologically and respect the most recent valid state.
    """
    obs_stale = create_obs({"status": "processing"}, age_seconds=100)
    obs_fresh = create_obs({"status": "captured"}, age_seconds=10)
    
    engine = StateEngine()
    
    result = engine.reconstruct_state(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observations=[obs_fresh, obs_stale],
        reconstructed_at=datetime.now(timezone.utc),
        ordering_policy=TemporalOrderingPolicy()
    )
    
    assert result.observed_financial_state == ObservedFinancialState.CAPTURED
    assert result.knowledge_state == KnowledgeState.VERIFIED

def test_engine_contradictory_trusted_claims():
    """
    Scenario B: We think it's refunded, but later the provider authoritatively says it's not executed.
    This creates an epistemic contradiction.
    """
    obs_webhook = create_obs({"status": "refunded"}, age_seconds=100)
    obs_auth = create_obs({"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value}, age_seconds=10)
    
    engine = StateEngine()
    result = engine.reconstruct_state(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observations=[obs_auth, obs_webhook],
        reconstructed_at=datetime.now(timezone.utc),
        ordering_policy=TemporalOrderingPolicy()
    )
    
    # We asserted it happened, but later observed it never happened.
    assert result.knowledge_state == KnowledgeState.CONTRADICTED
def test_contradictory_trusted_observations():
    """
    Scenario C: Contradictory trusted observations yielding CONTRADICTED.
    Two terminal states reported for the same entity.
    """
    obs_1 = create_obs({"status": "captured"}, age_seconds=50)
    obs_2 = create_obs({"status": "failed"}, age_seconds=10)
    
    engine = StateEngine()
    result = engine.reconstruct_state(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observations=[obs_1, obs_2],
        reconstructed_at=datetime.now(timezone.utc),
        ordering_policy=TemporalOrderingPolicy()
    )
    
    assert result.knowledge_state == KnowledgeState.CONTRADICTED

def test_no_observations_yields_unknown():
    engine = StateEngine()
    result = engine.reconstruct_state(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observations=[],
        reconstructed_at=datetime.now(timezone.utc),
        ordering_policy=TemporalOrderingPolicy()
    )
    
    assert result.observed_financial_state is None
    assert result.knowledge_state == KnowledgeState.UNKNOWN
