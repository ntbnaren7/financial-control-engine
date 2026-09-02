from src.evidence.models import EntityType
import pytest
import threading
from decimal import Decimal
from datetime import datetime, timezone

from src.state.models import ReconstructedState, KnowledgeState, ExecutionState
from src.integrations.provider import ProviderQueryConfidence
from src.domain.refunds.models import Refund
from src.control.policy import evaluate_refund_eligibility, ActionDecision
from src.domain.actions.models import Action, ActionType
from src.recovery.registry import ActionRegistry, ActionConcurrencyError

def test_concurrent_authorization_race():
    """
    Two workers simultaneously evaluate the identical refund intent.
    Both correctly read VERIFIED + AUTHORITATIVE_NOT_EXECUTED.
    Both attempt to dispatch the action.
    Prove that concurrent workers cannot both commit an independently executable 
    financial action for the same refund_intent_id.
    """
    
    # 1. Identical setup for both workers
    state = ReconstructedState(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observed_financial_state=None,
        knowledge_state=KnowledgeState.VERIFIED,
        execution=ExecutionState.NOT_EXECUTED,
        observation_ids=("obs_1",),
        reconstructed_at=datetime.now(timezone.utc)
    )
    
    refund_intent = Refund.create_new(
        provider_payment_id="pay_race_auth",
        amount=Decimal("100.00"),
        currency="USD",
        business_reason="test_concurrency"
    )
    
    registry = ActionRegistry()
    barrier = threading.Barrier(2)
    
    results = []
    exceptions = []
    
    def worker_logic():
        # Step A: Evaluate eligibility
        decision = evaluate_refund_eligibility(
            reconstructed_state=state,
            provider_query_confidence=ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED,
            refund_intent=refund_intent,
            incident_id="inc_auth_race"
        )
        
        if decision.decision == ActionDecision.ALLOW_REFUND:
            action = Action(
                action_type=ActionType.CONTROLLED_REFUND,
                idempotency_key=refund_intent.get_provider_idempotency_key(),
                incident_id="inc_auth_race"
            )
            
            # Step B: Wait for other worker so they try to commit at the exact same moment
            barrier.wait()
            
            # Step C: Attempt to commit to FCE database
            try:
                saved_action = registry.record_action_attempt(action)
                results.append(saved_action)
            except ActionConcurrencyError as e:
                exceptions.append(e)
                
    t1 = threading.Thread(target=worker_logic)
    t2 = threading.Thread(target=worker_logic)
    
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    # Assertions
    # Both workers should have evaluated to ALLOW_REFUND because the state was VERIFIED before commit
    # However, only one must succeed in committing the action.
    assert len(results) == 1, "Only one worker can successfully authorize and persist the action"
    assert len(exceptions) == 1, "The second worker must receive a database conflict/concurrency error"
    
    saved = registry.get_action_by_idempotency_key(refund_intent.get_provider_idempotency_key())
    assert saved is not None
