import pytest
from datetime import datetime, timezone
from src.domain.actions.models import Action, ActionType
from src.recovery.outbox import TransactionalOutbox, OutboxDispatcher, OutboxStatus
from src.integrations.provider import ProviderQueryConfidence

class ProviderAmbiguousException(Exception):
    pass

class ProviderAdapterDouble:
    def __init__(self):
        # Independent provider state
        self.executed_intents = set()
        self.idempotency_keys = set()
        self.financial_effect_count = 0
        
        # Test controls
        self.simulate_500 = False
        self.execute_before_500 = False
        
    def dispatch_action(self, action: Action) -> bool:
        if self.simulate_500:
            if self.execute_before_500:
                self._execute(action)
            # Throw 500
            raise ProviderAmbiguousException("HTTP 500 Internal Server Error")
        
        return self._execute(action)

    def _execute(self, action: Action) -> bool:
        if action.idempotency_key in self.idempotency_keys:
            # Idempotent retry, no new financial effect
            return True
            
        self.idempotency_keys.add(action.idempotency_key)
        self.executed_intents.add(action.idempotency_key)
        self.financial_effect_count += 1
        return True
        
    def query_status(self, idempotency_key: str) -> ProviderQueryConfidence:
        if idempotency_key in self.executed_intents:
            return ProviderQueryConfidence.AUTHORITATIVE_EXECUTED
        return ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED

def test_ambiguous_provider_failure_not_executed():
    """
    Scenario A: Provider returns 500 and did NOT execute.
    Prove that FCE handles AMBIGUOUS outbox state and query resolves to NOT_EXECUTED.
    """
    provider = ProviderAdapterDouble()
    provider.simulate_500 = True
    provider.execute_before_500 = False
    
    outbox = TransactionalOutbox()
    dispatcher = OutboxDispatcher(outbox, provider)
    
    action = Action(
        action_type=ActionType.CONTROLLED_REFUND,
        idempotency_key="idemp_123",
        incident_id="inc_1"
    )
    
    outbox.publish_action(action)
    dispatcher.process_pending()
    
    # 1. Check outbox state is AMBIGUOUS
    msg = list(outbox._messages.values())[0]
    assert msg.status == OutboxStatus.AMBIGUOUS
    
    # 2. Check financial effect count
    assert provider.financial_effect_count == 0
    
    # 3. Prove that an authoritative query resolves the state to NOT_EXECUTED
    # (In the real workflow, this query drives the KnowledgeState)
    confidence = provider.query_status(action.idempotency_key)
    assert confidence == ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED

def test_ambiguous_provider_failure_executed():
    """
    Scenario B: Provider returns 500 but DID execute the financial effect.
    Prove that FCE handles AMBIGUOUS outbox state and query resolves to EXECUTED.
    """
    provider = ProviderAdapterDouble()
    provider.simulate_500 = True
    provider.execute_before_500 = True
    
    outbox = TransactionalOutbox()
    dispatcher = OutboxDispatcher(outbox, provider)
    
    action = Action(
        action_type=ActionType.CONTROLLED_REFUND,
        idempotency_key="idemp_456",
        incident_id="inc_2"
    )
    
    outbox.publish_action(action)
    dispatcher.process_pending()
    
    msg = list(outbox._messages.values())[0]
    assert msg.status == OutboxStatus.AMBIGUOUS
    
    # The provider did execute it once
    assert provider.financial_effect_count == 1
    
    # Authoritative query resolves to EXECUTED
    confidence = provider.query_status(action.idempotency_key)
    assert confidence == ProviderQueryConfidence.AUTHORITATIVE_EXECUTED
    
    # Simulate a retry due to AMBIGUOUS state
    provider.simulate_500 = False # Network recovers
    dispatcher.process_pending() # (Normally the AMBIGUOUS would be transitioned back to pending by a workflow if retry was deemed safe by policy)
    
    # Let's forcefully reset status to pending to simulate a deterministic retry
    outbox.update_status(msg.message_id, OutboxStatus.PENDING)
    dispatcher.process_pending()
    
    # Validate idempotency key prevents a duplicate financial effect
    assert provider.financial_effect_count == 1
