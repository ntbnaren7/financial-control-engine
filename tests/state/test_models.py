from src.evidence.models import EntityType
import pytest
from datetime import datetime, timezone
from src.state.models import ObservedFinancialState, KnowledgeState, ReconstructedState

def test_observed_financial_state_has_no_unknown():
    """
    Proves that ObservedFinancialState does not contain an UNKNOWN value,
    enforcing that epistemic uncertainty cannot be materialized as a financial state.
    """
    valid_states = {state.value for state in ObservedFinancialState}
    assert "UNKNOWN" not in valid_states
    assert "UNVERIFIED" not in valid_states
    
    # Asserting concrete values exist
    assert "CAPTURED" in valid_states
    assert "REFUNDED" in valid_states
    assert "FAILED" in valid_states
    assert "PROCESSING" in valid_states
    assert "VOIDED" in valid_states

def test_knowledge_state_strict_values():
    """
    Proves that KnowledgeState only contains the 3 exact values permitted by the V1 Architecture.
    Specifically preventing 'UNVERIFIED' to ensure AI hypothesis confidence does not leak into state.
    """
    valid_states = {state.value for state in KnowledgeState}
    
    assert valid_states == {"VERIFIED", "UNKNOWN", "CONTRADICTED"}
    assert "UNVERIFIED" not in valid_states

def test_reconstructed_state_instantiation_with_none():
    """
    Proves that ReconstructedState can correctly represent the 'not established' financial state
    using None, rather than an UNKNOWN enum value.
    """
    now = datetime.now(timezone.utc)
    state = ReconstructedState(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        observation_ids=("obs_123",),
        reconstructed_at=now
    )
    
    assert state.observed_financial_state is None
    assert state.knowledge_state == KnowledgeState.UNKNOWN
    assert state.observation_ids == ("obs_123",)

def test_reconstructed_state_frozen():
    """
    Proves that ReconstructedState is immutable.
    """
    state = ReconstructedState(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observed_financial_state=ObservedFinancialState.CAPTURED,
        knowledge_state=KnowledgeState.VERIFIED,
        observation_ids=("obs_123",),
        reconstructed_at=datetime.now(timezone.utc)
    )
    
    with pytest.raises(Exception):
        state.knowledge_state = KnowledgeState.UNKNOWN  # type: ignore
