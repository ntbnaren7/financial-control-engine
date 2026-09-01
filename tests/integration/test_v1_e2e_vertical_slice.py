from src.evidence.models import EntityType
import pytest
from decimal import Decimal
import uuid
from datetime import datetime, timezone

from src.evidence.models import ProviderObservation
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.domain.incidents.models import Incident
from src.control.policy import evaluate_refund_eligibility, ActionDecision
from src.domain.refunds.models import Refund
from src.domain.actions.models import Action, ActionType
from src.recovery.registry import ActionRegistry
from src.recovery.outbox import TransactionalOutbox
from tests.integration.test_v1_e2e_crash_recovery import IndependentProviderDouble, process_outbox_message_with_simulated_dispatch
from src.state.models import ReconstructedState, KnowledgeState, ObservedFinancialState

def test_full_vertical_slice_to_independent_verification():
    """
    Demonstrate the complete application flow:
    webhook/query → ProviderObservation → StateEngine → M3 → Incident → M4 (simulated) 
    → Control Plane → Refund Intent → Action → Outbox → Provider 
    → ProviderObservation → StateEngine → Independent Verification.
    """
    
    # 1. External webhook arrives suggesting payment is missing, or query returns NOT_FOUND
    obs_initial = ProviderObservation(
        entity_type=EntityType.PAYMENT.value,
        entity_id="pay_123",
        id=uuid.uuid4(),
        provider="mock_provider",
        event_id="q_1",
        event_type="query.result",
        payload={"query_confidence": "AUTHORITATIVE_NOT_EXECUTED"},
        created_at=datetime.now(timezone.utc)
    )
    
    # 2. StateEngine Reconstructs
    engine = StateEngine()
    state_initial = engine.reconstruct_state(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observations=[obs_initial], reconstructed_at=datetime.now(timezone.utc), ordering_policy=TemporalOrderingPolicy())
    
    assert state_initial.knowledge_state == KnowledgeState.VERIFIED
    assert state_initial.observed_financial_state is None
    
    # 3. M3 (Discrepancy Detection) creates Incident
    # We simulate the M3 boundary here: internal ledger says user paid, provider says nothing.
    incident = Incident(
        incident_id=str(uuid.uuid4())
    )
    
    # 4. M4 (Semantic Evaluator) hypothesizes a refund is due (Simulated)
    # The output of M4 is passing the intent to the Control Plane for verification.
    
    # 5. Control Plane authorizes
    refund_intent = Refund(
        provider_payment_id="pay_vertical",
        amount=Decimal("100.00"),
        currency="USD",
        refund_intent_id=incident.incident_id,
        business_reason="test"
    )
    
    decision = evaluate_refund_eligibility(
        reconstructed_state=state_initial,
        provider_query_confidence=obs_initial.payload["query_confidence"], # mapping mock
        refund_intent=refund_intent,
        incident_id=incident.incident_id
    )
    assert decision.decision == ActionDecision.ALLOW_REFUND
    
    # 6. Refund Intent -> Action -> Outbox
    registry = ActionRegistry()
    outbox = TransactionalOutbox()
    action = Action(
        action_type=ActionType.CONTROLLED_REFUND,
        idempotency_key=refund_intent.get_provider_idempotency_key(),
        incident_id=incident.incident_id
    )
    saved_action = registry.record_action_attempt(action)
    outbox.publish_action(saved_action)
    
    pending_msg = outbox.get_pending_messages()[0]
    
    # 7. Provider Mock execution
    provider = IndependentProviderDouble()
    obs_final = process_outbox_message_with_simulated_dispatch(
        outbox, pending_msg, provider, refund_intent.get_provider_idempotency_key()
    )
    assert obs_final is not None
    
    # 8. StateEngine reconstructs final state
    state_final = engine.reconstruct_state(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observations=[obs_initial, obs_final], reconstructed_at=datetime.now(timezone.utc), ordering_policy=TemporalOrderingPolicy()
    )
    
    # 9. Independent Verification of Financial Propositions
    assert state_final.knowledge_state == KnowledgeState.VERIFIED
    assert state_final.observed_financial_state == ObservedFinancialState.REFUNDED
    
    # Verify FCE's understanding matches Provider's ground truth independently
    assert len(provider.effects) == 1
    effect = provider.effects[0]
    
    # Proposition: Same intent
    assert effect.intent_id == incident.incident_id
    # Proposition: Same amount
    assert Decimal(effect.amount) == refund_intent.amount
    # Proposition: Same currency
    assert effect.currency == refund_intent.currency
    
    # Proposition: Exactly one proving observation exists for the effect
    proving_obs = [o_id for o_id in state_final.observation_ids if str(obs_final.id) == o_id]
    assert len(proving_obs) == 1
    
    # Proposition: No contradictory observations
    assert state_final.knowledge_state != KnowledgeState.CONTRADICTED
