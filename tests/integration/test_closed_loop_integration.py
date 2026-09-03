import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid

from src.reconciliation.models import ExpectedRefund, DiscrepancyType
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.recovery.outbox import TransactionalOutbox, ConcurrencyError, OutboxStatus
from src.control.closed_loop import ClosedLoopCoordinator, ObservationStore
from src.domain.incidents.models import Incident, IncidentState
from src.evidence.models import ProviderObservation, EntityType
from src.integrations.provider import ProviderQueryConfidence, ProviderMutationOutcome

class InMemoryObservationStore:
    def __init__(self):
        self._observations = []
        
    def get_for_entity(self, entity_type: EntityType, entity_id: str):
        return [obs for obs in self._observations if obs.entity_type == entity_type.value and obs.entity_id == entity_id]
        
    def add(self, observation: ProviderObservation):
        self._observations.append(observation)

class AsyncMockProviderAdapter:
    def __init__(self):
        self.queries = []
        self.dispatches = []
        self.mock_confidence = ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED
        self.mock_mutation = ProviderMutationOutcome.ACCEPTED_EXECUTED
        
    async def query_refund_status(self, payment_id: str, idempotency_key: str, receipt: str):
        self.queries.append({"payment_id": payment_id, "idempotency_key": idempotency_key, "receipt": receipt})
        return self.mock_confidence
        
    async def dispatch_refund(self, action, refund):
        self.dispatches.append({"action": action, "refund": refund})
        return self.mock_mutation

@pytest.fixture
def store():
    return InMemoryObservationStore()

@pytest.fixture
def adapter():
    return AsyncMockProviderAdapter()

@pytest.fixture
def coordinator(store, adapter):
    outbox = TransactionalOutbox()
    engine = StateEngine()
    ordering = TemporalOrderingPolicy()
    return ClosedLoopCoordinator(engine, ordering, outbox, adapter, store)

@pytest.mark.asyncio
async def test_path_1_safe_recovery_happy_path(coordinator, store):
    """Path 1: SLA expired, 0 observations -> ABSENT_EXECUTION -> Outbox -> RESOLVED"""
    now = datetime.now(timezone.utc)
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="USD",
        created_at=now - timedelta(seconds=600),
        sla_seconds=300
    )
    
    incident, escalation = await coordinator.run_cycle(expectation, now)
    assert incident is not None
    assert incident.discrepancy_type == DiscrepancyType.ABSENT_EXECUTION
    assert incident.lifecycle_state == IncidentState.MONITORING
    assert len(coordinator.outbox.get_pending_messages()) == 1
    
    # Simulate Outbox Dispatcher success
    obs = ProviderObservation(
        provider="razorpay",
        event_id="evt_123",
        entity_type=EntityType.REFUND_INTENT.value,
        entity_id=expectation.refund_intent_id,
        event_type="DISPATCH_RESULT",
        payload={"status": "REFUNDED", "provider_timestamp": (now + timedelta(seconds=1)).isoformat()}
    )
    store.add(obs)
    
    # Run cycle #2: Should resolve the incident
    resolved_incident, escalation = await coordinator.run_cycle(expectation, now + timedelta(seconds=1), incident)
    assert resolved_incident.lifecycle_state == IncidentState.RESOLVED

@pytest.mark.asyncio
async def test_path_3_unsafe_discrepancies_containment(coordinator, store):
    """Path 3: Contradictory terminality escalates."""
    now = datetime.now(timezone.utc)
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="USD",
        created_at=now - timedelta(seconds=600)
    )
    
    # Inject FAILED observation
    obs = ProviderObservation("mock", "1", EntityType.REFUND_INTENT.value, expectation.refund_intent_id, "evt", {"status": "FAILED"})
    store.add(obs)
    
    incident, escalation = await coordinator.run_cycle(expectation, now)
    
    assert incident is not None
    assert incident.discrepancy_type == DiscrepancyType.CONTRADICTORY_TERMINALITY
    assert incident.lifecycle_state == IncidentState.ESCALATED
    assert escalation is not None
    assert escalation.reason == "Provider recorded terminal failure for mutation"

@pytest.mark.asyncio
async def test_stale_match_observation_cannot_resolve_incident(coordinator, store):
    now = datetime.now(timezone.utc)
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="USD",
        created_at=now - timedelta(seconds=600)
    )
    
    obs = ProviderObservation("mock", "1", EntityType.REFUND_INTENT.value, expectation.refund_intent_id, "evt", {"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value})
    store.add(obs)
    incident, _ = await coordinator.run_cycle(expectation, now)
    
    assert incident.lifecycle_state == IncidentState.MONITORING
    
    # Add a MATCH observation
    stale_time = now - timedelta(seconds=1)
    obs2 = ProviderObservation("mock", "2", EntityType.REFUND_INTENT.value, expectation.refund_intent_id, "evt", {"status": "REFUNDED"})
    store.add(obs2)
    
    resolved_incident, _ = await coordinator.run_cycle(expectation, stale_time, incident)
    assert resolved_incident.lifecycle_state == IncidentState.MONITORING

@pytest.mark.asyncio
async def test_unverified_provider_success_does_not_resolve_incident(coordinator, store, adapter):
    now = datetime.now(timezone.utc)
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="USD",
        created_at=now - timedelta(seconds=600)
    )
    
    obs = ProviderObservation("mock", "1", EntityType.REFUND_INTENT.value, expectation.refund_intent_id, "evt", {"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value})
    store.add(obs)
    incident, _ = await coordinator.run_cycle(expectation, now)
    
    resolved_incident, _ = await coordinator.run_cycle(expectation, now + timedelta(seconds=1), incident)
    assert resolved_incident.lifecycle_state == IncidentState.MONITORING

@pytest.mark.asyncio
async def test_unknown_state_cannot_authorize_mutation(coordinator, store, adapter):
    now = datetime.now(timezone.utc)
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="USD",
        created_at=now - timedelta(seconds=600)
    )
    
    adapter.mock_confidence = ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY
    
    incident, _ = await coordinator.run_cycle(expectation, now)
    
    assert incident.lifecycle_state == IncidentState.ESCALATED
    assert incident.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE
    assert len(coordinator.outbox.get_pending_messages()) == 0

@pytest.mark.asyncio
async def test_idempotency_key_invariant_across_retries(coordinator, store, adapter):
    now = datetime.now(timezone.utc)
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="USD",
        created_at=now - timedelta(seconds=600)
    )
    
    obs = ProviderObservation("mock", "1", EntityType.REFUND_INTENT.value, expectation.refund_intent_id, "evt", {"query_confidence": ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value})
    store.add(obs)
    
    await coordinator.run_cycle(expectation, now)
    msgs = coordinator.outbox.get_pending_messages()
    assert len(msgs) == 1
    key1 = msgs[0].action.idempotency_key
    
    # Try publishing again
    with pytest.raises(ConcurrencyError):
        coordinator.outbox.publish_action(msgs[0].action)

from src.integrations.razorpay.outbox_dispatcher import AsyncOutboxDispatcher

@pytest.mark.asyncio
async def test_razorpay_async_closed_loop_execution(coordinator, store, adapter):
    """
    Test the full async loop with OutboxDispatcher:
    1. Incident opens as ABSENT_EXECUTION.
    2. Action is written to Outbox.
    3. Dispatcher reads from Outbox and calls provider adapter.
    4. Dispatcher writes success observation to store.
    5. Coordinator cycle 2 resolves the incident.
    """
    now = datetime.now(timezone.utc)
    expectation = ExpectedRefund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="USD",
        created_at=now - timedelta(seconds=600),
        sla_seconds=300
    )
    
    # Cycle 1
    incident, _ = await coordinator.run_cycle(expectation, now)
    assert incident.discrepancy_type == DiscrepancyType.ABSENT_EXECUTION
    assert len(coordinator.outbox.get_pending_messages()) == 1
    
    # Run dispatcher processing step
    dispatcher = AsyncOutboxDispatcher(coordinator.outbox, adapter, store)
    dispatcher._running = True
    await dispatcher._process_pending_messages()
    
    assert len(coordinator.outbox.get_pending_messages()) == 0
    # Provider mutation mock is ACCEPTED_EXECUTED, so observation should be added
    obs = store.get_for_entity(EntityType.REFUND_INTENT, expectation.refund_intent_id)
    assert len(obs) == 2
    assert obs[-1].event_type == "DISPATCH_RESULT"
    assert obs[-1].payload["status"] == "REFUNDED"
    
    # Cycle 2
    resolved_incident, _ = await coordinator.run_cycle(expectation, now + timedelta(seconds=1), incident)
    assert resolved_incident.lifecycle_state == IncidentState.RESOLVED
