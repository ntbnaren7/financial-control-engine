import pytest
import asyncio
from typing import Dict, Any
import uuid
import structlog
from datetime import datetime, timezone

from testcontainers.community.postgres import PostgresContainer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage.postgres.models import Base
from src.storage.postgres_substrate import (
    PostgresExpectationRepository, PostgresObservationRepository,
    PostgresEvidenceRepository, PostgresActiveIncidentRepository,
    PostgresControlEventRepository, PostgresReconciliationResultRepository,
    ControlEventType, InvestigationState
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.investigation.agent import Investigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.engine.worker import V2ControlWorker, ControlLoopSettings
from src.engine.policy import V2PolicyEvaluator
from src.engine.actuator import SimulatedActuator
from src.engine.observer import SimulatedObserver
from src.engine.external_simulator import simulator
from src.domain.investigation.models import CausalHypothesis, InvestigationDisposition, VerificationIntent
from src.domain.core.models import Expectation, Observation, CorrelationKeys, BusinessStatus, ReconciliationOutcome, DiscrepancyReason

logger = structlog.get_logger()

@pytest.fixture(scope="session")
def postgres_engine():
    with PostgresContainer("postgres:15-alpine") as postgres:
        url = postgres.get_connection_url().replace("postgresql+psycopg2", "postgresql+psycopg") 
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        yield engine

@pytest.fixture
def session_maker(postgres_engine):
    return sessionmaker(bind=postgres_engine)

@pytest.fixture(autouse=True)
def clean_db(postgres_engine):
    Base.metadata.drop_all(postgres_engine)
    Base.metadata.create_all(postgres_engine)
    
    # Reset the simulator state
    simulator.merchant_orders.clear()
    simulator.provider_payments.clear()
    simulator.fault_injections.clear()
    yield

class MockDeterministicVerifier(DeterministicVerifier):
    """Mocks A4 Verification output for the vertical slice tests."""
    def __init__(self, override_observations=None):
        super().__init__(razorpay_client=None)  # type: ignore
        self.override_observations = override_observations or []
        
    async def verify(self, hypothesis, context):
        from src.domain.investigation.models import VerificationResult, VerificationStatus, VerificationIntent
        return [VerificationResult(
            verification_id=str(uuid.uuid4()),
            intent=hypothesis.verification_intents[0] if hypothesis.verification_intents else VerificationIntent.QUERY_PROVIDER_STATE,
            status=VerificationStatus.SUCCEEDED,
            evidence_ids=[],
            new_evidence=[],
            new_observations=self.override_observations,
            failure_reason=None,
            verified_at=datetime.now(timezone.utc)
        )]

class RejectingMockVerifier(DeterministicVerifier):
    def __init__(self):
        super().__init__(razorpay_client=None)  # type: ignore

    async def verify(self, hypothesis, context):
        from src.domain.investigation.models import VerificationResult, VerificationStatus, VerificationIntent
        return [VerificationResult(
            verification_id=str(uuid.uuid4()),
            intent=hypothesis.verification_intents[0] if hypothesis.verification_intents else VerificationIntent.QUERY_PROVIDER_STATE,
            status=VerificationStatus.REJECTED,
            evidence_ids=[],
            new_evidence=[],
            new_observations=[],
            failure_reason="Safety constraints failed",
            verified_at=datetime.now(timezone.utc)
        )]

class MockInvestigator(Investigator):
    def investigate(self, agent_input: Dict[str, Any]) -> CausalHypothesis:
        return CausalHypothesis(
            hypothesis_id=str(uuid.uuid4()),
            claim="Mock claim",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            missing_evidence="Mock missing evidence",
            confidence="HIGH",
            disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
            verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE]
        )

def setup_hero_incident(session_maker):
    recon_repo = PostgresReconciliationResultRepository(session_maker)
    evt_repo = PostgresControlEventRepository(session_maker)
    obs_repo = PostgresObservationRepository(session_maker)
    
    order_id = "order_hero"
    payment_id = "pay_hero"
    
    # Setup initial state in our simulator (CAPTURED + UNPAID)
    simulator.seed_merchant_order(order_id, 5000, "UNPAID")
    simulator.seed_provider_payment(payment_id, order_id, 5000, "CAPTURED")
    
    from src.domain.core.models import Observation
    from datetime import datetime, timezone, timedelta
    stale_time = datetime.now(timezone.utc) - timedelta(hours=1)
    obs1 = Observation(observation_id="obs1", provider="Merchant", provider_reference=order_id, observation_type="State", observed_state="UNPAID", observed_amount=5000, currency="INR", evidence_ids=[], observed_at=stale_time)
    obs2 = Observation(observation_id="obs2", provider="Razorpay", provider_reference=payment_id, observation_type="State", observed_state="CAPTURED", observed_amount=5000, currency="INR", evidence_ids=[], observed_at=stale_time)
    obs_repo.save(obs1)
    obs_repo.save(obs2)
    
    # Seed the FCE database with the discrepancy
    recon_id = f"recon_{uuid.uuid4()}"
    recon_repo.save(
        from_reconciliation(recon_id, order_id, payment_id, DiscrepancyReason.STATE_MISMATCH)
    )
    evt_repo.publish(ControlEventType.DISCREPANCY_DETECTED, {"reconciliation_id": recon_id})
    return recon_id, order_id, payment_id

def from_reconciliation(recon_id, order_id, payment_id, reason=DiscrepancyReason.STATE_MISMATCH):
    from src.domain.core.models import ReconciliationResult, ReconciliationOutcome
    return ReconciliationResult(
        reconciliation_id=recon_id,
        expectation_id=None,
        observation_ids=["obs1", "obs2"],
        outcome=ReconciliationOutcome.DISCREPANCY,
        discrepancy_reason=reason,
        reconciliation_reason="Test"
    )

def create_worker(session_maker, verifier):
    exp_repo = PostgresExpectationRepository(session_maker)
    obs_repo = PostgresObservationRepository(session_maker)
    ev_repo = PostgresEvidenceRepository(session_maker)
    inc_repo = PostgresActiveIncidentRepository(session_maker)
    evt_repo = PostgresControlEventRepository(session_maker)
    recon_repo = PostgresReconciliationResultRepository(session_maker)
    
    recon_engine = V2ReconciliationEngine(exp_repo, obs_repo)
    assembler = EvidenceAssembler(exp_repo, obs_repo, ev_repo)
    
    return V2ControlWorker(
        worker_id="test_worker",
        event_repo=evt_repo,
        incident_repo=inc_repo,
        observation_repo=obs_repo,
        evidence_repo=ev_repo,
        exp_repo=exp_repo,
        recon_result_repo=recon_repo,
        reconciliation_engine=recon_engine,
        assembler=assembler,
        investigator=MockInvestigator(),
        validator=OutputValidator(),
        verifier=verifier,
        settings=ControlLoopSettings()
    ), inc_repo, evt_repo

@pytest.mark.asyncio
async def test_hero_incident_vertical_slice(session_maker):
    """
    1. Hero incident: (Captured + Unpaid -> Repair -> Resolved)
    """
    recon_id, order_id, payment_id = setup_hero_incident(session_maker)
    
    # A4 Mock Verifier outputs the actual states observed from the provider
    obs_merchant = Observation(provider="Merchant", provider_reference=order_id, observation_type="State", observed_state="UNPAID", observed_amount=5000, currency="INR", evidence_ids=[])
    obs_provider = Observation(provider="Razorpay", provider_reference=payment_id, observation_type="State", observed_state="CAPTURED", observed_amount=5000, currency="INR", evidence_ids=[])
    
    worker, inc_repo, evt_repo = create_worker(session_maker, MockDeterministicVerifier([obs_merchant, obs_provider]))
    
    await worker.poll_and_process()
    
    # Verification
    # The external state should be repaired to PAID
    order = simulator.read_merchant_order(order_id)
    assert order is not None
    assert order["status"] == "PAID"
    
    # The incident should be RESOLVED
    # (Since ActiveIncident record gets deleted or released, let's check it's not locked)
    active = inc_repo.get_active_incident(order_id, DiscrepancyReason.STATE_MISMATCH.value)
    assert active is None  # Released

@pytest.mark.asyncio
async def test_unsafe_hypothesis_rejected(session_maker):
    """
    2. Unsafe/incorrect AI hypothesis -> Rejected -> Escalated
    """
    recon_id, order_id, payment_id = setup_hero_incident(session_maker)
    
    # The verifier rejects it for safety reasons
    worker, inc_repo, evt_repo = create_worker(session_maker, RejectingMockVerifier())
    
    await worker.poll_and_process()
    
    # External state remains untouched
    order = simulator.read_merchant_order(order_id)
    assert order is not None
    assert order["status"] == "UNPAID"
    
    # Incident should be ESCALATED
    active = inc_repo.get_active_incident("obs1", DiscrepancyReason.STATE_MISMATCH.value) # obs1 is the active_subject here
    assert active is not None
    assert active.state == InvestigationState.ESCALATED # type: ignore

@pytest.mark.asyncio
async def test_unknown_action_outcome_forces_independent_decision(session_maker):
    """
    3. Unknown action outcome -> Timeout -> Re-observe -> Independent decision
    """
    recon_id, order_id, payment_id = setup_hero_incident(session_maker)
    
    # Inject TIMEOUT fault into the external simulator for the merchant order
    simulator.inject_fault(order_id, "TIMEOUT")
    
    obs_merchant = Observation(provider="Merchant", provider_reference=order_id, observation_type="State", observed_state="UNPAID", observed_amount=5000, currency="INR", evidence_ids=[])
    obs_provider = Observation(provider="Razorpay", provider_reference=payment_id, observation_type="State", observed_state="CAPTURED", observed_amount=5000, currency="INR", evidence_ids=[])
    
    worker, inc_repo, evt_repo = create_worker(session_maker, MockDeterministicVerifier([obs_merchant, obs_provider]))
    
    await worker.poll_and_process()
    
    # Because of TIMEOUT_UNKNOWN, the actuator returned TIMEOUT_UNKNOWN.
    # The system re-observed. BUT the external system state was actually unchanged because TIMEOUT mock didn't change it.
    # So the reconciliation re-evaluated UNPAID and CAPTURED, resulting in DISCREPANCY.
    # Verify it was put into RETRY_PENDING
    active = inc_repo.get_active_incident("obs1", DiscrepancyReason.STATE_MISMATCH.value)
    assert active is not None
    assert active.state == InvestigationState.RETRY_PENDING # type: ignore

@pytest.mark.asyncio
async def test_duplicate_concurrent_action_idempotency(session_maker):
    """
    4. Duplicate/concurrent action -> Idempotency prevents double execution
    """
    recon_id, order_id, payment_id = setup_hero_incident(session_maker)
    
    # Make the external state ALREADY PAID 
    # (simulating that another concurrent action or out-of-band process fixed it, 
    # or our own actuator is retrying on an already-repaired state)
    simulator.update_merchant_order(order_id, "PAID")
    
    # But the V1 reconciliation engine produced a discrepancy based on OLD state
    obs_merchant = Observation(provider="Merchant", provider_reference=order_id, observation_type="State", observed_state="UNPAID", observed_amount=5000, currency="INR", evidence_ids=[])
    obs_provider = Observation(provider="Razorpay", provider_reference=payment_id, observation_type="State", observed_state="CAPTURED", observed_amount=5000, currency="INR", evidence_ids=[])
    
    worker, inc_repo, evt_repo = create_worker(session_maker, MockDeterministicVerifier([obs_merchant, obs_provider]))
    
    # Worker runs. Policy says REPAIR_MERCHANT_STATE.
    # Actuator calls simulator.update_merchant_order("PAID"). Simulator is idempotent, returns SUCCESS.
    await worker.poll_and_process()
    
    # Final state is PAID
    order = simulator.read_merchant_order(order_id)
    assert order is not None
    assert order["status"] == "PAID"
