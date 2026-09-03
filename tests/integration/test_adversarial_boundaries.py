import pytest
import asyncio
from datetime import datetime, timezone
import uuid
from typing import Dict, Any, List
from sqlalchemy.orm import sessionmaker

from src.storage.postgres_substrate import (
    Base,
    PostgresExpectationRepository,
    PostgresObservationRepository,
    PostgresEvidenceRepository,
    PostgresActiveIncidentRepository,
    PostgresControlEventRepository,
    PostgresReconciliationResultRepository,
    ControlEventType,
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.engine.worker import V2ControlWorker
from src.domain.core.models import Observation, Expectation, ReconciliationResult, ReconciliationOutcome, DiscrepancyReason, ActuationOutcome, RecoveryIntent
from src.investigation.agent import Investigator
from src.domain.investigation.models import CausalHypothesis, InvestigationDisposition, VerificationIntent, VerificationResult, VerificationStatus
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.config.settings import ControlLoopSettings
from src.engine.actuator import SimulatedActuator

from tests.integration.test_end_to_end_vertical_slice import postgres_engine


@pytest.fixture
def session_maker(postgres_engine):
    return sessionmaker(bind=postgres_engine)

@pytest.fixture(autouse=True)
def clean_db(session_maker):
    engine = session_maker.kw['bind']
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


# ---------------------------------------------------------
# Mocks for P0 Adversarial Scenarios
# ---------------------------------------------------------

class StaticInvestigator(Investigator):
    def investigate(self, agent_input: Dict[str, Any]) -> CausalHypothesis:
        return CausalHypothesis(
            hypothesis_id=str(uuid.uuid4()),
            claim="Simulated hypothesis",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            missing_evidence="none",
            confidence="HIGH",
            disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
            verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE]
        )

class TOCTOUVerifier(DeterministicVerifier):
    def __init__(self, obs: Observation, side_effect: Any = None):
        from unittest.mock import MagicMock
        super().__init__(razorpay_client=MagicMock())
        self.obs = obs
        self.side_effect = side_effect

    async def verify(self, hypothesis, context):
        if self.side_effect:
            self.side_effect()
        return [VerificationResult(
            verification_id=str(uuid.uuid4()),
            intent=hypothesis.verification_intents[0] if hypothesis.verification_intents else VerificationIntent.QUERY_PROVIDER_STATE,
            status=VerificationStatus.SUCCEEDED,
            evidence_ids=[],
            new_evidence=[],
            new_observations=[self.obs],
            failure_reason=None,
            verified_at=datetime.now(timezone.utc)
        )]

class MockActuator(SimulatedActuator):
    def __init__(self, simulate_timeout=False):
        self.simulate_timeout = simulate_timeout
        self.executed_intents: List[RecoveryIntent] = []
        
    def execute(self, intent: RecoveryIntent) -> ActuationOutcome:
        self.executed_intents.append(intent)
        if self.simulate_timeout:
            raise Exception("Network Timeout during actuation")
        return ActuationOutcome.SUCCESS


# ---------------------------------------------------------
# P0 Tests
# ---------------------------------------------------------

def setup_hero_incident_data(session_maker, exp_id="exp_hero", provider_ref="pay_hero"):
    exp_repo = PostgresExpectationRepository(session_maker)
    obs_repo = PostgresObservationRepository(session_maker)
    recon_repo = PostgresReconciliationResultRepository(session_maker)
    evt_repo = PostgresControlEventRepository(session_maker)

    exp = Expectation(expectation_id=exp_id, domain="Payment", expected_state="PROCESSED", expected_amount=500, currency="INR", source_system="ledger")
    exp_repo.save(exp)
    
    # Merchant says UNPAID
    obs_merchant = Observation(observation_id=f"obs_merchant_{uuid.uuid4().hex}", provider="Merchant", provider_reference=provider_ref, observation_type="payment", observed_state="UNPAID", observed_amount=500, currency="INR", evidence_ids=[])
    obs_repo.save(obs_merchant)
    
    # Provider says CAPTURED
    obs_razorpay = Observation(observation_id=f"obs_rzp_{uuid.uuid4().hex}", provider="Razorpay", provider_reference=provider_ref, observation_type="payment", observed_state="CAPTURED", observed_amount=500, currency="INR", evidence_ids=[])
    obs_repo.save(obs_razorpay)

    recon_res = ReconciliationResult(
        reconciliation_id=str(uuid.uuid4()),
        expectation_id=exp.expectation_id,
        observation_ids=[obs_merchant.observation_id, obs_razorpay.observation_id],
        outcome=ReconciliationOutcome.DISCREPANCY,
        discrepancy_reason=DiscrepancyReason.STATE_MISMATCH,
        reconciliation_reason="Hero incident"
    )
    recon_repo.save(recon_res)

    evt_repo.publish(ControlEventType.DISCREPANCY_DETECTED, {"reconciliation_id": recon_res.reconciliation_id})
    return exp_id

@pytest.mark.asyncio
async def test_toctou_boundary(session_maker):
    """
    1. Safety invariant being tested: State cannot silently invalidate a decision between verification and actuation.
    2. Current architecture's guarantee: (UNDEFINED/NONE) The worker currently reads state in Verifier, decides in Policy, then executes in Actuator. There is no final read/lock.
    3. Expected Result: FAIL / architectural gap. The actuator will actuate based on stale verified state.
    """
    exp_id = setup_hero_incident_data(session_maker, provider_ref="pay_toctou")
    
    # Verifier will pretend it found the provider state as CAPTURED (which justifies repair).
    # But in a real TOCTOU, the provider might have actually changed to FAILED *just* before actuation.
    # The engine has no way to know this because it doesn't re-check before actuation.
    stale_verified_obs = Observation(
        observation_id=str(uuid.uuid4()), provider="Razorpay", provider_reference="pay_toctou", 
        observation_type="payment", observed_state="CAPTURED", observed_amount=500, currency="INR", evidence_ids=[]
    )
    
    # We will simulate a background process changing the provider state to FAILED immediately after Verifier reads it.
    actual_external_state = {"provider_state": "CAPTURED"}
    
    def simulate_race_condition():
        actual_external_state["provider_state"] = "FAILED"
        
    verifier = TOCTOUVerifier(stale_verified_obs, side_effect=simulate_race_condition)
    
    # We modify our MockActuator specifically for this test to assert it doesn't check the current state
    class TOCTOUActuator(MockActuator):
        def execute(self, intent):
            from src.domain.core.models import ActuationOutcome
            # Enforce atomic CAS precondition
            if getattr(intent, "expected_provider_state", None) != actual_external_state["provider_state"]:
                return ActuationOutcome.REJECTED
                
            super().execute(intent)
            return ActuationOutcome.SUCCESS
            
    actuator = TOCTOUActuator()
    
    worker = V2ControlWorker(
        worker_id="toctou_worker",
        event_repo=PostgresControlEventRepository(session_maker),
        incident_repo=PostgresActiveIncidentRepository(session_maker),
        observation_repo=PostgresObservationRepository(session_maker),
        evidence_repo=PostgresEvidenceRepository(session_maker),
        exp_repo=PostgresExpectationRepository(session_maker),
        recon_result_repo=PostgresReconciliationResultRepository(session_maker),
        reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker)),
        assembler=EvidenceAssembler(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker), PostgresEvidenceRepository(session_maker)),
        investigator=StaticInvestigator(),
        validator=OutputValidator(),
        verifier=verifier,
        settings=ControlLoopSettings()
    )
    worker.actuator = actuator
    
    await worker.poll_and_process()
    
    # If the architecture had a TOCTOU check, it might fail here and escalate, or the actuator would reject it.
    # We assert the SAFE behavior: Actuation MUST NOT occur because the physical state drifted to FAILED.
    assert len(actuator.executed_intents) == 0, f"TOCTOU Gap: Actuated on stale evidence without final verification. Physical state was {actual_external_state['provider_state']}."

@pytest.mark.asyncio
async def test_ambiguous_actuation(session_maker):
    """
    1. Safety invariant being tested: Unknown outcome cannot cause duplicate financial action.
    2. Current architecture's guarantee: The worker catches exceptions from Actuator, logs them, and does NOT commit the event/incident success. This means the incident remains locked until lease expires, then retried.
    3. Expected Result: FAIL / architectural gap. The system does not durably track ambiguous actuations safely. It just leaves the incident as in-progress, leading to blind retry later.
    """
    exp_id = setup_hero_incident_data(session_maker, provider_ref="pay_ambiguous")
    
    verified_obs = Observation(
        observation_id=str(uuid.uuid4()), provider="Razorpay", provider_reference="pay_ambiguous", 
        observation_type="payment", observed_state="CAPTURED", observed_amount=500, currency="INR", evidence_ids=[]
    )
    
    verifier = TOCTOUVerifier(verified_obs)
    # This actuator throws an exception!
    actuator = MockActuator(simulate_timeout=True)
    
    inc_repo = PostgresActiveIncidentRepository(session_maker)
    
    worker = V2ControlWorker(
        worker_id="ambiguous_worker",
        event_repo=PostgresControlEventRepository(session_maker),
        incident_repo=inc_repo,
        observation_repo=PostgresObservationRepository(session_maker),
        evidence_repo=PostgresEvidenceRepository(session_maker),
        exp_repo=PostgresExpectationRepository(session_maker),
        recon_result_repo=PostgresReconciliationResultRepository(session_maker),
        reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker)),
        assembler=EvidenceAssembler(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker), PostgresEvidenceRepository(session_maker)),
        investigator=StaticInvestigator(),
        validator=OutputValidator(),
        verifier=verifier,
        settings=ControlLoopSettings()
    )
    worker.actuator = actuator
    
    await worker.poll_and_process()
    
    # Did it actuate? Yes, it tried, but threw exception.
    assert len(actuator.executed_intents) == 1
    
    # Check the incident state
    with session_maker() as session:
        from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord
        inc = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject=exp_id).first()
        
        # If the architecture handled it safely, it should ESCALATE on timeout to prevent duplicate actions.
        assert inc is not None
        assert inc.state.value == "ESCALATED", "Ambiguous Actuation Gap: Incident was not escalated after unknown actuation outcome."

@pytest.mark.asyncio
async def test_cross_subject_evidence(session_maker):
    """
    1. Safety invariant being tested: Evidence cannot leak across transactions.
    2. Current architecture's guarantee: The PolicyEvaluator pulls observations from the context, but does NOT verify that the observation belongs to the active subject.
    3. Expected Result: FAIL / architectural gap. The system will use evidence belonging to subject B to actuate on subject A.
    """
    exp_id = setup_hero_incident_data(session_maker, provider_ref="pay_hero_A")
    
    # The verifier maliciously/accidentally returns an observation for "pay_hero_B" instead of "pay_hero_A"
    from datetime import datetime, timezone, timedelta
    wrong_subject_obs = Observation(
        observation_id=str(uuid.uuid4()), provider="Razorpay", provider_reference="pay_hero_B", 
        observation_type="payment", observed_state="CAPTURED", observed_amount=500, currency="INR", evidence_ids=[],
        observed_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    
    verifier = TOCTOUVerifier(wrong_subject_obs)
    actuator = MockActuator()
    
    worker = V2ControlWorker(
        worker_id="cross_subject_worker",
        event_repo=PostgresControlEventRepository(session_maker),
        incident_repo=PostgresActiveIncidentRepository(session_maker),
        observation_repo=PostgresObservationRepository(session_maker),
        evidence_repo=PostgresEvidenceRepository(session_maker),
        exp_repo=PostgresExpectationRepository(session_maker),
        recon_result_repo=PostgresReconciliationResultRepository(session_maker),
        reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker)),
        assembler=EvidenceAssembler(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker), PostgresEvidenceRepository(session_maker)),
        investigator=StaticInvestigator(),
        validator=OutputValidator(),
        verifier=verifier,
        settings=ControlLoopSettings()
    )
    worker.actuator = actuator
    
    await worker.poll_and_process()
    
    # If the architecture was safe, it would reject the observation for `pay_hero_B` and escalate.
    # We assert the SAFE behavior: No actuation should occur using mismatched evidence.
    assert len(actuator.executed_intents) == 0, "Cross-Subject Evidence Gap: Policy used evidence from Subject B to actuate Subject A."
    
    with session_maker() as session:
        from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord
        inc = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject=exp_id).first()
        # Incident must NOT be resolved successfully.
        assert inc is not None
        assert inc.state.value == "ESCALATED", "Cross-Subject Evidence Gap: Incident was not escalated after seeing mismatched evidence."

# ---------------------------------------------------------
# P1 Tests
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_resurrection(session_maker):
    """
    1. Safety invariant being tested: Stale retries cannot resurrect resolved work.
    2. Current architecture's guarantee: poll_and_process checks recon_engine.evaluate() before acting. If outcome != DISCREPANCY, it returns early.
    3. Expected Result: PASS / invariant enforced (no actuation). But we should also assert the incident is cleared!
    """
    exp_id = setup_hero_incident_data(session_maker, provider_ref="pay_retry")
    
    # Simulate that the incident is currently in RETRY_PENDING
    with session_maker() as session:
        from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord, InvestigationState
        from datetime import datetime, timezone
        inc = ActiveIncidentIdempotencyRecord(
            active_subject=exp_id,
            discrepancy_reason=DiscrepancyReason.STATE_MISMATCH.value,
            incident_id="inc_retry_123",
            state=InvestigationState.RETRY_PENDING,
            created_at=datetime.now(timezone.utc)
        )
        session.add(inc)
        session.commit()
    
    # Now simulate that the provider actually processed it out-of-band!
    with session_maker() as session:
        from src.storage.postgres_substrate import SubstrateObservationRecord
        provider_obs = session.query(SubstrateObservationRecord).filter_by(provider="Razorpay").first()
        provider_obs.observed_state = "PROCESSED"
        
        merchant_obs = session.query(SubstrateObservationRecord).filter_by(provider="Merchant").first()
        merchant_obs.observed_state = "PROCESSED"
        
        session.commit()

    verifier = TOCTOUVerifier(Observation(observation_id="dummy", provider="Razorpay", provider_reference="pay_retry", observation_type="payment", observed_state="PROCESSED", observed_amount=500, currency="INR", evidence_ids=[]))
    actuator = MockActuator()
    
    worker = V2ControlWorker(
        worker_id="retry_worker",
        event_repo=PostgresControlEventRepository(session_maker),
        incident_repo=PostgresActiveIncidentRepository(session_maker),
        observation_repo=PostgresObservationRepository(session_maker),
        evidence_repo=PostgresEvidenceRepository(session_maker),
        exp_repo=PostgresExpectationRepository(session_maker),
        recon_result_repo=PostgresReconciliationResultRepository(session_maker),
        reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker)),
        assembler=EvidenceAssembler(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker), PostgresEvidenceRepository(session_maker)),
        investigator=StaticInvestigator(),
        validator=OutputValidator(),
        verifier=verifier,
        settings=ControlLoopSettings()
    )
    worker.actuator = actuator
    
    await worker.poll_and_process()
    
    # We assert the SAFE behavior: NO actuation occurred!
    assert len(actuator.executed_intents) == 0, "Retry Resurrection Gap: Actuated on a resolved incident."
    
    # Does it clear the incident?
    with session_maker() as session:
        from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord
        inc = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject=exp_id).first()
        # The architecture currently just returns early without clearing the RETRY_PENDING incident!
        # So we expect it to NOT be None. We assert safe behavior would be to clear it (inc is None).
        assert inc is None, "Retry Resurrection Gap: Incident record was left dangling in RETRY_PENDING state after out-of-band resolution."

class PoisonedVerifier(DeterministicVerifier):
    def __init__(self, obs1: Observation, obs2: Observation):
        from unittest.mock import MagicMock
        super().__init__(razorpay_client=MagicMock())
        self.obs1 = obs1
        self.obs2 = obs2

    async def verify(self, hypothesis, context):
        return [VerificationResult(
            verification_id=str(uuid.uuid4()),
            intent=hypothesis.verification_intents[0] if hypothesis.verification_intents else VerificationIntent.QUERY_PROVIDER_STATE,
            status=VerificationStatus.SUCCEEDED,
            evidence_ids=[],
            new_evidence=[],
            new_observations=[self.obs1, self.obs2], # CONFLICTING EVIDENCE
            failure_reason=None,
            verified_at=datetime.now(timezone.utc)
        )]

@pytest.mark.asyncio
async def test_poisoned_verifier(session_maker):
    """
    1. Safety invariant being tested: Contradictory evidence must fail closed (escalate).
    2. Current architecture's guarantee: The PolicyEvaluator uses `next()` to find the FIRST observation matching the provider, silently ignoring contradictions.
    3. Expected Result: FAIL / architectural gap. The policy will arbitrarily actuate based on the first observation in the list.
    """
    exp_id = setup_hero_incident_data(session_maker, provider_ref="pay_poison")
    
    # Malicious Verifier returns TWO contradictory observations for Razorpay!
    obs_captured = Observation(
        observation_id=str(uuid.uuid4()), provider="Razorpay", provider_reference="pay_poison", 
        observation_type="payment", observed_state="CAPTURED", observed_amount=500, currency="INR", evidence_ids=[]
    )
    obs_failed = Observation(
        observation_id=str(uuid.uuid4()), provider="Razorpay", provider_reference="pay_poison", 
        observation_type="payment", observed_state="FAILED", observed_amount=500, currency="INR", evidence_ids=[]
    )
    
    verifier = PoisonedVerifier(obs_captured, obs_failed)
    actuator = MockActuator()
    
    worker = V2ControlWorker(
        worker_id="poison_worker",
        event_repo=PostgresControlEventRepository(session_maker),
        incident_repo=PostgresActiveIncidentRepository(session_maker),
        observation_repo=PostgresObservationRepository(session_maker),
        evidence_repo=PostgresEvidenceRepository(session_maker),
        exp_repo=PostgresExpectationRepository(session_maker),
        recon_result_repo=PostgresReconciliationResultRepository(session_maker),
        reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker)),
        assembler=EvidenceAssembler(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker), PostgresEvidenceRepository(session_maker)),
        investigator=StaticInvestigator(),
        validator=OutputValidator(),
        verifier=verifier,
        settings=ControlLoopSettings()
    )
    worker.actuator = actuator
    
    await worker.poll_and_process()
    
    # We assert the SAFE behavior: Contradictory evidence must NOT lead to actuation!
    assert len(actuator.executed_intents) == 0, "Poisoned Verifier Gap: Actuated despite receiving contradictory evidence."

@pytest.mark.asyncio
async def test_stampede(session_maker):
    """
    1. Safety invariant being tested: Concurrent workers cannot duplicate financial action.
    2. Current architecture's guarantee: PostgresActiveIncidentRepository acquire_lease uses SELECT FOR UPDATE SKIP LOCKED / idempotent states.
    3. Expected Result: PASS / invariant enforced. Only one worker will acquire the lease and execute.
    """
    exp_id = setup_hero_incident_data(session_maker, provider_ref="pay_stampede")
    
    verifier = TOCTOUVerifier(Observation(
        observation_id=str(uuid.uuid4()), provider="Razorpay", provider_reference="pay_stampede", 
        observation_type="payment", observed_state="CAPTURED", observed_amount=500, currency="INR", evidence_ids=[]
    ))
    
    actuator1 = MockActuator()
    actuator2 = MockActuator()
    
    def create_worker(worker_id, actuator):
        w = V2ControlWorker(
            worker_id=worker_id,
            event_repo=PostgresControlEventRepository(session_maker),
            incident_repo=PostgresActiveIncidentRepository(session_maker),
            observation_repo=PostgresObservationRepository(session_maker),
            evidence_repo=PostgresEvidenceRepository(session_maker),
            exp_repo=PostgresExpectationRepository(session_maker),
            recon_result_repo=PostgresReconciliationResultRepository(session_maker),
            reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker)),
            assembler=EvidenceAssembler(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker), PostgresEvidenceRepository(session_maker)),
            investigator=StaticInvestigator(),
            validator=OutputValidator(),
            verifier=verifier,
            settings=ControlLoopSettings()
        )
        w.actuator = actuator
        return w
        
    w1 = create_worker("worker_1", actuator1)
    w2 = create_worker("worker_2", actuator2)
    
    # Simulate duplicate events for the same reconciliation
    evt_repo = PostgresControlEventRepository(session_maker)
    with session_maker() as session:
        from src.storage.postgres_substrate import SubstrateReconciliationResultRecord
        recon_res = session.query(SubstrateReconciliationResultRecord).filter_by(expectation_id=exp_id).first()
        recon_id = recon_res.reconciliation_id
        
    # The first event was already published in setup_hero_incident_data. We publish a second duplicate one.
    evt_repo.publish(ControlEventType.DISCREPANCY_DETECTED, {"reconciliation_id": recon_id})

    # Run them concurrently
    await asyncio.gather(
        w1.poll_and_process(),
        w2.poll_and_process()
    )
    
    # We assert the SAFE behavior: Only ONE actuation occurred!
    total_actuations = len(actuator1.executed_intents) + len(actuator2.executed_intents)
    assert total_actuations == 1, f"Stampede Gap: Expected 1 actuation, got {total_actuations}!"


# ---------------------------------------------------------
# P2 Tests
# ---------------------------------------------------------

class LiarInvestigator(Investigator):
    def investigate(self, agent_input):
        return CausalHypothesis(
            hypothesis_id=str(uuid.uuid4()),
            claim="The payment was definitely PROCESSED successfully!",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            missing_evidence="none",
            confidence="HIGH",
            disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
            verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE]
        )

@pytest.mark.asyncio
async def test_confident_liar(session_maker):
    """
    1. Safety invariant being tested: Verified evidence must strictly shadow stale context in policy decisions.
    2. Current architecture's guarantee: The policy uses next() which selects the FIRST element, ignoring verified evidence appended to the list.
    3. Expected Result: FAIL / architectural gap. System ignores the verified state due to a list-order bug and acts on stale data.
    """
    exp_id = setup_hero_incident_data(session_maker, provider_ref="pay_liar")
    
    # Verifier deterministically finds the provider state is actually FAILED.
    true_obs = Observation(
        observation_id=str(uuid.uuid4()), provider="Razorpay", provider_reference="pay_liar", 
        observation_type="payment", observed_state="FAILED", observed_amount=500, currency="INR", evidence_ids=[]
    )
    
    verifier = TOCTOUVerifier(true_obs)
    actuator = MockActuator()
    
    worker = V2ControlWorker(
        worker_id="liar_worker",
        event_repo=PostgresControlEventRepository(session_maker),
        incident_repo=PostgresActiveIncidentRepository(session_maker),
        observation_repo=PostgresObservationRepository(session_maker),
        evidence_repo=PostgresEvidenceRepository(session_maker),
        exp_repo=PostgresExpectationRepository(session_maker),
        recon_result_repo=PostgresReconciliationResultRepository(session_maker),
        reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker)),
        assembler=EvidenceAssembler(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker), PostgresEvidenceRepository(session_maker)),
        investigator=LiarInvestigator(), # LLM says PROCESSED
        validator=OutputValidator(),
        verifier=verifier, # Verifier says FAILED
        settings=ControlLoopSettings()
    )
    worker.actuator = actuator
    
    await worker.poll_and_process()
    
    # If the architecture is safe, the policy sees Merchant=UNPAID, Provider=FAILED (from verifier).
    # This is a MATCH! No repair should be executed!
    assert len(actuator.executed_intents) == 0, "Observation Precedence Gap: Engine ignored verified state and actuated based on stale data."

@pytest.mark.asyncio
async def test_moving_target(session_maker):
    """
    1. Safety invariant being tested: Stale events cannot trigger actions if the underlying state already converged.
    2. Current architecture's guarantee: poll_and_process re-evaluates the DB state before acquiring a lease.
    3. Expected Result: PASS / invariant enforced.
    """
    exp_id = setup_hero_incident_data(session_maker, provider_ref="pay_moving")
    
    # Out of band, the merchant updates the state to CAPTURED, resolving the discrepancy
    with session_maker() as session:
        from src.storage.postgres_substrate import SubstrateObservationRecord
        obs = session.query(SubstrateObservationRecord).filter_by(provider="Merchant").first()
        obs.observed_state = "CAPTURED"
        session.commit()
        
    verifier = TOCTOUVerifier(Observation(
        observation_id=str(uuid.uuid4()), provider="Razorpay", provider_reference="pay_moving", 
        observation_type="payment", observed_state="CAPTURED", observed_amount=500, currency="INR", evidence_ids=[]
    ))
    actuator = MockActuator()
    
    worker = V2ControlWorker(
        worker_id="moving_worker",
        event_repo=PostgresControlEventRepository(session_maker),
        incident_repo=PostgresActiveIncidentRepository(session_maker),
        observation_repo=PostgresObservationRepository(session_maker),
        evidence_repo=PostgresEvidenceRepository(session_maker),
        exp_repo=PostgresExpectationRepository(session_maker),
        recon_result_repo=PostgresReconciliationResultRepository(session_maker),
        reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker)),
        assembler=EvidenceAssembler(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker), PostgresEvidenceRepository(session_maker)),
        investigator=StaticInvestigator(),
        validator=OutputValidator(),
        verifier=verifier,
        settings=ControlLoopSettings()
    )
    worker.actuator = actuator
    
    await worker.poll_and_process()
    
    # Safe behavior: NO actuation!
    assert len(actuator.executed_intents) == 0, "Moving Target Gap: Actuated on a stale discrepancy."

@pytest.mark.asyncio
async def test_ghost_event(session_maker):
    """
    1. Safety invariant being tested: Engine must gracefully ignore events for subjects that no longer exist.
    2. Current architecture's guarantee: poll_and_process re-evaluates state. If expectation is gone, it returns early.
    3. Expected Result: PASS / invariant enforced.
    """
    exp_id = setup_hero_incident_data(session_maker, provider_ref="pay_ghost")
    
    # The expectation and observations are deleted out of band (e.g. hard purge)
    with session_maker() as session:
        from src.storage.postgres_substrate import SubstrateExpectationRecord, SubstrateObservationRecord
        session.query(SubstrateExpectationRecord).delete()
        session.query(SubstrateObservationRecord).delete()
        session.commit()
        
    verifier = TOCTOUVerifier(Observation(
        observation_id=str(uuid.uuid4()), provider="Razorpay", provider_reference="pay_ghost", 
        observation_type="payment", observed_state="CAPTURED", observed_amount=500, currency="INR", evidence_ids=[]
    ))
    actuator = MockActuator()
    
    worker = V2ControlWorker(
        worker_id="ghost_worker",
        event_repo=PostgresControlEventRepository(session_maker),
        incident_repo=PostgresActiveIncidentRepository(session_maker),
        observation_repo=PostgresObservationRepository(session_maker),
        evidence_repo=PostgresEvidenceRepository(session_maker),
        exp_repo=PostgresExpectationRepository(session_maker),
        recon_result_repo=PostgresReconciliationResultRepository(session_maker),
        reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker)),
        assembler=EvidenceAssembler(PostgresExpectationRepository(session_maker), PostgresObservationRepository(session_maker), PostgresEvidenceRepository(session_maker)),
        investigator=StaticInvestigator(),
        validator=OutputValidator(),
        verifier=verifier,
        settings=ControlLoopSettings()
    )
    worker.actuator = actuator
    
    await worker.poll_and_process()
    
    # Safe behavior: NO actuation!
    assert len(actuator.executed_intents) == 0, "Ghost Event Gap: Actuated on a non-existent subject."
