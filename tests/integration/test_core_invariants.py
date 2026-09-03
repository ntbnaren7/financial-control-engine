import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
from typing import Dict, Any, List

from src.reconciliation.models import ExpectedRefund, DiscrepancyType
from src.evidence.models import ProviderObservation, EntityType
from src.storage.memory_repo import MemoryRepository
from src.engine.reconciliation import ReconciliationEngine
from src.engine.incidents import IncidentEngine
from src.engine.runtime import ControlRuntime, ExpectationReceived, ObservationReceived
from src.engine.policy import ActionPolicyEngine
from src.engine.outbox import ActionOutbox, ActionStatus
from src.engine.executor import ActionExecutor
from src.investigation.agent import LocalLLMInvestigator
from tests.doubles.synthetic_investigator import SyntheticInvestigator
from tests.doubles.batch_mock_transport import BatchMockTransport
from src.integrations.razorpay.client import RazorpayClient
import httpx

def get_now():
    return datetime.now(timezone.utc)

@pytest.fixture(scope="session")
def postgres_engine():
    from testcontainers.community.postgres import PostgresContainer
    from sqlalchemy import create_engine
    from src.storage.postgres.models import Base
    
    with PostgresContainer("postgres:16-alpine") as postgres:
        url = postgres.get_connection_url()
        # Testcontainers defaults to psycopg2. Force psycopg3 driver.
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
        if "postgresql://" in url:
            url = url.replace("postgresql://", "postgresql+psycopg://")
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        yield engine

@pytest.fixture
def session_factory(postgres_engine):
    from sqlalchemy.orm import sessionmaker
    from src.storage.postgres.models import Base
    # Clear tables between tests for independence
    with postgres_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    return sessionmaker(bind=postgres_engine)

@pytest.fixture
def environment(session_factory):
    class TestEnvironment:
        def __init__(self, session_factory):
            self.now = get_now()
            
            from src.storage.postgres.postgres_repo import PostgresRepository
            from src.storage.postgres.incident_repo import PostgresIncidentRepository
            from src.storage.postgres.outbox import PostgresActionOutbox

            self.repo = PostgresRepository(session_factory)
            self.recon_engine = ReconciliationEngine()
            
            # Simple Investigator that doesn't actually call Ollama for tests
            # We just need it to not crash. 
            self.investigator = SyntheticInvestigator(fallback_investigator=None, sub_case_hints={})
            
            # Validator / Verifier not strictly needed if we bypass them or mock them,
            # but IncidentEngine requires them in signature.
            from src.investigation.validator import OutputValidator
            from src.investigation.verifier import DeterministicVerifier
            self.validator = OutputValidator()
            
            self.routes = {}
            self.transport = BatchMockTransport(self.routes)
            self.http_client = httpx.AsyncClient(transport=self.transport, base_url="https://api.razorpay.com/v1")
            self.razorpay_client = RazorpayClient(client=self.http_client)
            self.verifier = DeterministicVerifier(razorpay_client=self.razorpay_client)
            
            # Using PostgresIncidentRepository
            incident_repo = PostgresIncidentRepository(session_factory)
            self.incident_engine = IncidentEngine(
                reconciliation_engine=self.recon_engine,
                investigator=self.investigator,
                validator=self.validator,
                verifier=self.verifier,
            )
            # Override internal repo for IncidentEngine
            self.incident_engine._repo = incident_repo # type: ignore
            
            self.runtime = ControlRuntime(
                repository=self.repo, # type: ignore
                reconciliation_engine=self.recon_engine,
                incident_engine=self.incident_engine
            )
            
            self.policy = ActionPolicyEngine()
            self.outbox = PostgresActionOutbox(session_factory)
            self.executor = ActionExecutor(self.outbox, self.runtime, self.razorpay_client) # type: ignore

        def create_expectation(self, intent_id: str, amount: str = "500.00", age_hours: int = 2) -> ExpectedRefund:
            return ExpectedRefund(
                refund_intent_id=intent_id,
                provider_payment_id=f"pay_{intent_id}",
                amount=Decimal(amount),
                currency="INR",
                created_at=self.now - timedelta(hours=age_hours)
            )

        def create_observation(self, intent_id: str, amount: float = 500.00, status: str = "processed", age_hours: int = 1) -> ProviderObservation:
            return ProviderObservation(
                provider="razorpay",
                event_id=f"evt_{uuid.uuid4().hex[:8]}",
                entity_type=EntityType.REFUND_INTENT.value,
                entity_id=intent_id,
                event_type="refund.processed" if status == "processed" else "refund.processing",
                payload={
                    "amount": amount,
                    "currency": "INR",
                    "status": "refunded" if status == "processed" else status,
                    "created_at": (self.now - timedelta(hours=age_hours)).timestamp(),
                    "execution_state": "EXECUTED" if status == "processed" else "NOT_EXECUTED"
                },
                created_at=self.now
            )

    return TestEnvironment(session_factory)


# --- Invariant Group 1: Deterministic Ordering & Deduplication ---

@pytest.mark.asyncio
async def test_1_duplicate_expectation(environment):
    env = environment
    exp1 = env.create_expectation("dup_exp")
    
    # Send exactly the same expectation twice
    await env.runtime.ingest_event(ExpectationReceived(exp1))
    await env.runtime.ingest_event(ExpectationReceived(exp1))
    
    incidents = await env.runtime.run_until_drained(env.now)
    # Should result in 1 incident of ABSENT_EXECUTION (because SLA expired, no observations)
    assert len(incidents) == 1
    assert incidents[0].refund_intent_id == "dup_exp"
    assert incidents[0].discrepancy_type == DiscrepancyType.ABSENT_EXECUTION

@pytest.mark.asyncio
async def test_2_duplicate_observation(environment):
    env = environment
    exp = env.create_expectation("dup_obs")
    obs = env.create_observation("dup_obs")
    
    await env.runtime.ingest_event(ExpectationReceived(exp))
    await env.runtime.ingest_event(ObservationReceived(obs))
    await env.runtime.ingest_event(ObservationReceived(obs)) # Duplicate!
    
    incidents = await env.runtime.run_until_drained(env.now)
    
    # Two identical observations should not cause EXCESS_EFFECT if they represent the exact same execution 
    # Actually, if they have the exact same event_id and payload, V1 will deduplicate them or treat as same.
    assert len(incidents) == 0

@pytest.mark.asyncio
async def test_3_observation_before_expectation(environment):
    env = environment
    exp = env.create_expectation("obs_first")
    obs = env.create_observation("obs_first")
    
    # Fire observation first
    await env.runtime.ingest_event(ObservationReceived(obs))
    incidents = await env.runtime.run_until_drained(env.now)
    assert len(incidents) == 1
    assert incidents[0].discrepancy_type == DiscrepancyType.ORPHANED_EXECUTION
    
    # Now fire expectation
    await env.runtime.ingest_event(ExpectationReceived(exp))
    incidents = await env.runtime.run_until_drained(env.now)
    assert len(incidents) == 1
    # Should resolve to MATCH
    assert incidents[0].discrepancy_type == DiscrepancyType.MATCH

@pytest.mark.asyncio
async def test_4_expectation_before_observation(environment):
    env = environment
    exp = env.create_expectation("exp_first")
    obs = env.create_observation("exp_first")
    
    await env.runtime.ingest_event(ExpectationReceived(exp))
    incidents = await env.runtime.run_until_drained(env.now)
    assert incidents[0].discrepancy_type == DiscrepancyType.ABSENT_EXECUTION
    
    await env.runtime.ingest_event(ObservationReceived(obs))
    incidents = await env.runtime.run_until_drained(env.now)
    assert incidents[0].discrepancy_type == DiscrepancyType.MATCH

@pytest.mark.asyncio
async def test_5_multiple_observations_for_one_intent(environment):
    env = environment
    exp = env.create_expectation("multi_obs")
    obs1 = env.create_observation("multi_obs", status="processing")
    obs2 = env.create_observation("multi_obs", status="processed")
    
    await env.runtime.ingest_event(ExpectationReceived(exp))
    await env.runtime.ingest_event(ObservationReceived(obs1))
    await env.runtime.ingest_event(ObservationReceived(obs2))
    
    incidents = await env.runtime.run_until_drained(env.now)
    assert len(incidents) == 0

@pytest.mark.asyncio
async def test_6_orphan_observation(environment):
    env = environment
    obs = env.create_observation("orphan")
    
    await env.runtime.ingest_event(ObservationReceived(obs))
    incidents = await env.runtime.run_until_drained(env.now)
    
    assert incidents[0].discrepancy_type == DiscrepancyType.ORPHANED_EXECUTION

@pytest.mark.asyncio
async def test_7_interleaved_independent_intents(environment):
    env = environment
    exp_a = env.create_expectation("A")
    obs_a = env.create_observation("A")
    exp_b = env.create_expectation("B")
    
    await env.runtime.ingest_event(ExpectationReceived(exp_a))
    await env.runtime.ingest_event(ExpectationReceived(exp_b))
    await env.runtime.ingest_event(ObservationReceived(obs_a))
    
    incidents = await env.runtime.run_until_drained(env.now)
    assert len(incidents) == 1
    assert incidents[0].refund_intent_id == "B"
    assert incidents[0].discrepancy_type == DiscrepancyType.ABSENT_EXECUTION

# --- Invariant Group 2: Action & Execution Safety ---

@pytest.mark.asyncio
async def test_8_duplicate_authorization(environment):
    env = environment
    exp = env.create_expectation("dup_auth")
    await env.runtime.ingest_event(ExpectationReceived(exp))
    incidents = await env.runtime.run_until_drained(env.now)
    
    action1 = env.policy.evaluate(incidents[0])
    action2 = env.policy.evaluate(incidents[0])
    
    assert action1 is not None and action2 is not None
    assert action1.idempotency_key == action2.idempotency_key
    
    env.outbox.append(action1)
    env.outbox.append(action2) # Duplicate submission!
    
    pending = env.outbox.get_pending()
    assert len(pending) == 1

@pytest.mark.asyncio
async def test_9_duplicate_executor_invocation(environment):
    env = environment
    exp = env.create_expectation("dup_exec")
    await env.runtime.ingest_event(ExpectationReceived(exp))
    incidents = await env.runtime.run_until_drained(env.now)
    
    action = env.policy.evaluate(incidents[0])
    env.outbox.append(action)
    
    # Run executor concurrently
    await asyncio.gather(
        env.executor.execute_pending(),
        env.executor.execute_pending()
    )
    
    route = env.transport._routes.get("pay_dup_exec", {})
    mutated = route.get("mutated_refunds", [])
    assert len(mutated) == 1

@pytest.mark.asyncio
async def test_10_mutation_and_replay_idempotency(environment):
    env = environment
    exp = env.create_expectation("replay")
    await env.runtime.ingest_event(ExpectationReceived(exp))
    incidents = await env.runtime.run_until_drained(env.now)
    
    action = env.policy.evaluate(incidents[0])
    env.outbox.append(action)
    await env.executor.execute_pending()
    
    new_outbox = ActionOutbox()
    new_executor = ActionExecutor(new_outbox, env.runtime, env.razorpay_client)
    
    action_replay = env.policy.evaluate(incidents[0])
    new_outbox.append(action_replay)
    
    await new_executor.execute_pending()
    assert new_outbox._actions[action_replay.idempotency_key].status == ActionStatus.SUCCESS

@pytest.mark.asyncio
async def test_11_verification_before_local_success(environment):
    env = environment
    exp = env.create_expectation("webhook_fast")
    await env.runtime.ingest_event(ExpectationReceived(exp))
    incidents = await env.runtime.run_until_drained(env.now)
    
    action = env.policy.evaluate(incidents[0])
    env.outbox.append(action)
    
    # Webhook arrives
    obs = env.create_observation("webhook_fast")
    await env.runtime.ingest_event(ObservationReceived(obs))
    incidents = await env.runtime.run_until_drained(env.now)
    
    assert incidents[0].discrepancy_type == DiscrepancyType.MATCH
    
    await env.executor.execute_pending()

@pytest.mark.asyncio
async def test_12_stale_incident_cannot_authorize(environment):
    env = environment
    exp = env.create_expectation("stale_auth")
    await env.runtime.ingest_event(ExpectationReceived(exp))
    incidents = await env.runtime.run_until_drained(env.now)
    assert incidents[0].discrepancy_type == DiscrepancyType.ABSENT_EXECUTION
    
    obs = env.create_observation("stale_auth")
    await env.runtime.ingest_event(ObservationReceived(obs))
    incidents = await env.runtime.run_until_drained(env.now)
    assert incidents[0].discrepancy_type == DiscrepancyType.MATCH
    
    action = env.policy.evaluate(incidents[0])
    assert action is None

@pytest.mark.asyncio
async def test_13_match_cannot_authorize(environment):
    env = environment
    exp = env.create_expectation("match_auth")
    obs = env.create_observation("match_auth")
    await env.runtime.ingest_event(ExpectationReceived(exp))
    await env.runtime.ingest_event(ObservationReceived(obs))
    incidents = await env.runtime.run_until_drained(env.now)
    
    assert len(incidents) == 0

@pytest.mark.asyncio
async def test_14_executor_no_arbitrary_path(environment):
    env = environment
    import inspect
    sig = inspect.signature(env.executor.execute_pending)
    assert len(sig.parameters) == 0

# --- Invariant Group 3: Generic Runtime Loop ---

@pytest.mark.asyncio
async def test_15_continuous_independent_event_feed(environment):
    env = environment
    produced_events = []
    
    async def producer():
        for i in range(5):
            exp = env.create_expectation(f"stream_{i}")
            await env.runtime.ingest_event(ExpectationReceived(exp))
            produced_events.append(f"stream_{i}")
            await asyncio.sleep(0.01)
            
            obs = env.create_observation(f"stream_{i}")
            await env.runtime.ingest_event(ObservationReceived(obs))
            await asyncio.sleep(0.01)
            
    async def consumer():
        matched = 0
        for _ in range(15):
            incidents = await env.runtime.run_until_drained(env.now)
            matched = sum(1 for i in incidents if i.discrepancy_type == DiscrepancyType.MATCH)
            if matched == 5:
                break
            await asyncio.sleep(0.01)
        return matched

    producer_task = asyncio.create_task(producer())
    consumer_task = asyncio.create_task(consumer())
    
    await producer_task
    matched = await consumer_task
    assert matched == 5
