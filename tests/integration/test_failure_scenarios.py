import pytest
import asyncio
from datetime import datetime, timezone
import uuid
from typing import Dict, Any
from sqlalchemy.orm import sessionmaker

from src.storage.postgres_substrate import (
    Base,
    PostgresExpectationRepository,
    PostgresObservationRepository,
    PostgresEvidenceRepository,
    PostgresActiveIncidentRepository,
    PostgresControlEventRepository,
    PostgresReconciliationResultRepository,
    PostgresActuationRepository,
    ControlEventType,
    InvestigationState
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.engine.worker import V2ControlWorker
from src.domain.core.models import Observation, DiscrepancyReason
from src.investigation.agent import Investigator, InvestigatorError
from src.domain.investigation.models import CausalHypothesis, InvestigationDisposition, VerificationIntent, VerificationResult, VerificationStatus
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.config.settings import ControlLoopSettings

# We use the existing setup methods from the vertical slice tests
from tests.integration.test_end_to_end_vertical_slice import setup_hero_incident, MockDeterministicVerifier, postgres_engine

class TransientInvestigatorError(InvestigatorError):
    pass

class FailingInvestigator(Investigator):
    def investigate(self, agent_input: Dict[str, Any]) -> CausalHypothesis:
        raise TransientInvestigatorError("Simulated network timeout connecting to LLM")

class HallucinatingInvestigator(Investigator):
    def investigate(self, agent_input: Dict[str, Any]) -> CausalHypothesis:
        # Returns a valid schema but references fake evidence (hallucination)
        return CausalHypothesis(
            hypothesis_id=str(uuid.uuid4()),
            claim="Hallucinated claim",
            supporting_evidence_ids=["fake_evidence_id_123"],  # Will fail validation
            contradicting_evidence_ids=[],
            missing_evidence="none",
            confidence="HIGH",
            disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
            verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE]
        )

class ProviderTimeoutVerifier(DeterministicVerifier):
    def __init__(self):
        super().__init__(razorpay_client=None) # type: ignore

    async def verify(self, hypothesis, context):
        return [VerificationResult(
            verification_id=str(uuid.uuid4()),
            intent=hypothesis.verification_intents[0] if hypothesis.verification_intents else VerificationIntent.QUERY_PROVIDER_STATE,
            status=VerificationStatus.FAILED,
            evidence_ids=[],
            new_evidence=[],
            new_observations=[],
            failure_reason="Provider API timed out",
            verified_at=datetime.now(timezone.utc)
        )]

def create_worker_with_overrides(session_maker, investigator, verifier):
    exp_repo = PostgresExpectationRepository(session_maker)
    obs_repo = PostgresObservationRepository(session_maker)
    ev_repo = PostgresEvidenceRepository(session_maker)
    inc_repo = PostgresActiveIncidentRepository(session_maker)
    evt_repo = PostgresControlEventRepository(session_maker)
    recon_repo = PostgresReconciliationResultRepository(session_maker)
    act_repo = PostgresActuationRepository(session_maker)
    
    recon_engine = V2ReconciliationEngine(exp_repo, obs_repo)
    assembler = EvidenceAssembler(exp_repo, obs_repo, ev_repo)
    validator = OutputValidator()
    
    return V2ControlWorker(
        worker_id="test_worker_failure",
        event_repo=evt_repo,
        incident_repo=inc_repo,
        observation_repo=obs_repo,
        evidence_repo=ev_repo,
        exp_repo=exp_repo,
        recon_result_repo=recon_repo,
        actuation_repo=act_repo,
        reconciliation_engine=recon_engine,
        assembler=assembler,
        investigator=investigator,
        validator=validator,
        verifier=verifier,
        settings=ControlLoopSettings()
    ), inc_repo, evt_repo


@pytest.fixture
def session_maker(postgres_engine):
    return sessionmaker(bind=postgres_engine)

@pytest.fixture(autouse=True)
def clean_db(postgres_engine):
    Base.metadata.drop_all(postgres_engine)
    Base.metadata.create_all(postgres_engine)
    yield


@pytest.mark.asyncio
async def test_investigator_unavailable_forces_retry(session_maker):
    """
    Simulates the LLM being offline (OllamaConnectionError / TransientInvestigatorError).
    The system should cleanly back off and schedule a retry.
    No financial conclusions should be made.
    """
    recon_id, order_id, payment_id = setup_hero_incident(session_maker)
    worker, inc_repo, evt_repo = create_worker_with_overrides(
        session_maker, FailingInvestigator(), MockDeterministicVerifier()
    )
    
    await worker.poll_and_process()
    
    active = inc_repo.get_active_incident("obs1", DiscrepancyReason.STATE_MISMATCH.value)
    assert active is not None
    assert active.state == InvestigationState.RETRY_PENDING
    assert active.hypothesis_payload is None


@pytest.mark.asyncio
async def test_hallucinated_hypothesis_rejected_and_escalated(session_maker):
    """
    Simulates the LLM outputting a hallucination (invalid evidence ID).
    OutputValidator rejects it -> Engine ESCALATES immediately (no retries).
    """
    recon_id, order_id, payment_id = setup_hero_incident(session_maker)
    worker, inc_repo, evt_repo = create_worker_with_overrides(
        session_maker, HallucinatingInvestigator(), MockDeterministicVerifier()
    )
    
    await worker.poll_and_process()
    
    # ValidationRejection forces an ESCALATE (which updates the state to ESCALATED, but doesn't delete the row)
    active = inc_repo.get_active_incident("obs1", DiscrepancyReason.STATE_MISMATCH.value)
    assert active is not None
    assert active.state == InvestigationState.ESCALATED


@pytest.mark.asyncio
async def test_provider_verification_fails_forces_retry(session_maker):
    """
    Simulates the verifier failing to query the provider (e.g. timeout).
    Status is FAILED -> Engine safely transitions to RETRY_PENDING.
    """
    recon_id, order_id, payment_id = setup_hero_incident(session_maker)
    
    from tests.integration.test_end_to_end_vertical_slice import MockInvestigator
    worker, inc_repo, evt_repo = create_worker_with_overrides(
        session_maker, MockInvestigator(), ProviderTimeoutVerifier()
    )
    
    await worker.poll_and_process()
    
    active = inc_repo.get_active_incident("obs1", DiscrepancyReason.STATE_MISMATCH.value)
    assert active is not None
    assert active.state == InvestigationState.RETRY_PENDING
    assert active.hypothesis_payload is not None
