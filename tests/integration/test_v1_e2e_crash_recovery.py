from src.evidence.models import EntityType
import pytest
from dataclasses import dataclass
from typing import Dict, List, Optional
import uuid
from decimal import Decimal
from datetime import datetime, timezone

from src.domain.refunds.models import Refund
from src.domain.actions.models import Action, ActionType
from src.recovery.registry import ActionRegistry
from src.recovery.outbox import TransactionalOutbox, OutboxMessage, OutboxStatus
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.evidence.models import ProviderObservation
from src.state.models import ReconstructedState, KnowledgeState, ObservedFinancialState

class FCECrashException(Exception):
    pass

class ProviderTransportException(Exception):
    pass

class ProviderTimeoutException(Exception):
    pass

@dataclass
class ProviderFinancialEffect:
    idempotency_key: str
    amount: str
    currency: str
    intent_id: str

class IndependentProviderDouble:
    """Models external truth independently from FCE state."""
    def __init__(self):
        self.effects: List[ProviderFinancialEffect] = []
        self.idempotency_registry: Dict[str, ProviderFinancialEffect] = {}
        
        self.simulate_fce_crash_after_acceptance = False
        self.simulate_transport_loss = False
        self.simulate_timeout = False

    def execute_refund(self, idempotency_key: str, amount: str, currency: str, intent_id: str) -> dict:
        if idempotency_key in self.idempotency_registry:
            # Idempotent response
            return {"status": "refunded", "id": "ref_123", "idempotency_hit": True}
            
        # Apply new refund effect
        effect = ProviderFinancialEffect(idempotency_key, amount, currency, intent_id)
        self.effects.append(effect)
        self.idempotency_registry[idempotency_key] = effect
        
        # Now simulate network failures (meaning effect is applied on provider, but response never reaches FCE)
        if self.simulate_timeout:
            raise ProviderTimeoutException("Provider timed out")
        if self.simulate_transport_loss:
            raise ProviderTransportException("Connection reset by peer")
        if self.simulate_fce_crash_after_acceptance:
            raise FCECrashException("Worker crashed before persisting")
            
        return {"status": "refunded", "id": "ref_123", "idempotency_hit": False}

def setup_action_and_outbox(intent_id: str, idempotency_key: str):
    registry = ActionRegistry()
    outbox = TransactionalOutbox()
    
    action = Action(
        action_type=ActionType.CONTROLLED_REFUND,
        idempotency_key=idempotency_key,
        incident_id=intent_id
    )
    
    saved_action = registry.record_action_attempt(action)
    outbox.publish_action(saved_action)
    msg = outbox.get_pending_messages()[0]
    return outbox, msg

def process_outbox_message_with_simulated_dispatch(outbox: TransactionalOutbox, msg: OutboxMessage, provider: IndependentProviderDouble, idempotency_key: str) -> Optional[ProviderObservation]:
    try:
        response = provider.execute_refund(
            idempotency_key=idempotency_key,
            amount="100.00",
            currency="USD",
            intent_id=msg.action.incident_id
        )
        
        # If we reach here, we successfully got a response. We persist observation.
        obs = ProviderObservation(
        entity_type=EntityType.PAYMENT.value,
        entity_id="pay_123",
        id=uuid.uuid4(),
            provider="mock",
            event_id=response["id"],
            event_type="refund.executed",
            payload=response,
            created_at=datetime.now(timezone.utc)
        )
        outbox.update_status(msg.message_id, OutboxStatus.DISPATCHED)
        return obs
    except (ProviderTransportException, ProviderTimeoutException):
        # Transport or timeout: mark as failed, retryable
        outbox.update_status(msg.message_id, OutboxStatus.RETRYABLE)
        return None
    except FCECrashException:
        # Worker died. Outbox message remains PENDING (or processing if we modeled that state)
        # It will be picked up by a recovery worker later.
        raise

def test_provider_acceptance_fce_crash():
    """Case A: Provider accepts, FCE crashes before persistence."""
    provider = IndependentProviderDouble()
    provider.simulate_fce_crash_after_acceptance = True
    
    intent = Refund.create_new(provider_payment_id="pay_1", amount=Decimal("100.00"), currency="USD", business_reason="test")
    idemp_key = intent.get_provider_idempotency_key()
    
    outbox, msg = setup_action_and_outbox(intent.refund_intent_id, idemp_key)
    
    # ATTEMPT 1
    with pytest.raises(FCECrashException):
        process_outbox_message_with_simulated_dispatch(outbox, msg, provider, idemp_key)
        
    assert len(provider.effects) == 1
    assert outbox.get_pending_messages()[0].message_id == msg.message_id
    
    # RECOVERY ATTEMPT
    provider.simulate_fce_crash_after_acceptance = False
    obs = process_outbox_message_with_simulated_dispatch(outbox, outbox.get_pending_messages()[0], provider, idemp_key)
    
    assert obs is not None
    assert obs.payload["idempotency_hit"] is True
    assert len(provider.effects) == 1 # Crucial assert! No double refund!

    # Verify state engine
    engine = StateEngine()
    state = engine.reconstruct_state(
        entity_type=EntityType.PAYMENT,
        entity_id="pay_123",
        observations=[obs], reconstructed_at=datetime.now(timezone.utc), ordering_policy=TemporalOrderingPolicy())
    assert state.knowledge_state == KnowledgeState.VERIFIED
    assert state.observed_financial_state == ObservedFinancialState.REFUNDED

def test_provider_acceptance_transport_loss():
    """Case B: Provider accepts, response never reaches FCE (transport loss)."""
    provider = IndependentProviderDouble()
    provider.simulate_transport_loss = True
    
    intent = Refund.create_new(provider_payment_id="pay_2", amount=Decimal("100.00"), currency="USD", business_reason="test")
    idemp_key = intent.get_provider_idempotency_key()
    outbox, msg = setup_action_and_outbox(intent.refund_intent_id, idemp_key)
    
    obs = process_outbox_message_with_simulated_dispatch(outbox, msg, provider, idemp_key)
    assert obs is None
    assert len(provider.effects) == 1
    
    provider.simulate_transport_loss = False
    
    # Retry from outbox
    retry_msg = outbox._messages[msg.message_id] # internal state for test
    obs2 = process_outbox_message_with_simulated_dispatch(outbox, retry_msg, provider, idemp_key)
    
    # The FCE dispatched twice, but provider idempotency ensures effectively-once financial effect
    assert obs2 is not None
    assert obs2.payload["idempotency_hit"] is True
    assert len(provider.effects) == 1, "Provider financial effect count = 1, despite transport loss retry"

def test_provider_acceptance_timeout():
    """Case C: Provider accepts, timeout occurs at network layer."""
    provider = IndependentProviderDouble()
    provider.simulate_timeout = True
    
    intent = Refund.create_new(provider_payment_id="pay_3", amount=Decimal("100.00"), currency="USD", business_reason="test")
    idemp_key = intent.get_provider_idempotency_key()
    outbox, msg = setup_action_and_outbox(intent.refund_intent_id, idemp_key)
    
    obs = process_outbox_message_with_simulated_dispatch(outbox, msg, provider, idemp_key)
    assert obs is None
    assert len(provider.effects) == 1
    
    provider.simulate_timeout = False
    retry_msg = outbox._messages[msg.message_id]
    obs2 = process_outbox_message_with_simulated_dispatch(outbox, retry_msg, provider, idemp_key)
    
    # The FCE dispatched twice, but provider idempotency ensures effectively-once financial effect
    assert obs2 is not None
    assert obs2.payload["idempotency_hit"] is True
    assert len(provider.effects) == 1, "Provider financial effect count = 1, despite timeout retry"
