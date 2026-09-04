import pytest
import httpx
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker

from src.config.settings import LLMSettings, ControlLoopSettings
from src.investigation.agent import LocalLLMInvestigator
from src.storage.postgres_substrate import (
    Base,
    PostgresExpectationRepository,
    PostgresObservationRepository,
    PostgresEvidenceRepository,
    PostgresActiveIncidentRepository,
    PostgresControlEventRepository,
    PostgresReconciliationResultRepository,
    PostgresActuationRepository,
    InvestigationState
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.engine.worker import V2ControlWorker
from src.domain.core.models import DiscrepancyReason
from src.investigation.validator import OutputValidator
from tests.integration.test_end_to_end_vertical_slice import setup_hero_incident, MockDeterministicVerifier, postgres_engine

def is_ollama_available():
    """Checks if the local Ollama service is running and has llama3.1."""
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=1.0)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return any(m["name"] == "llama3.1:latest" or m["name"] == "llama3.1" for m in models)
    except Exception:
        pass
    return False


@pytest.fixture
def session_maker(postgres_engine):
    return sessionmaker(bind=postgres_engine)

@pytest.fixture(autouse=True)
def clean_db(postgres_engine):
    Base.metadata.drop_all(postgres_engine)
    Base.metadata.create_all(postgres_engine)
    yield


def create_ollama_worker(session_maker):
    exp_repo = PostgresExpectationRepository(session_maker)
    obs_repo = PostgresObservationRepository(session_maker)
    ev_repo = PostgresEvidenceRepository(session_maker)
    inc_repo = PostgresActiveIncidentRepository(session_maker)
    evt_repo = PostgresControlEventRepository(session_maker)
    recon_repo = PostgresReconciliationResultRepository(session_maker)
    act_repo = PostgresActuationRepository(session_maker)
    
    recon_engine = V2ReconciliationEngine(exp_repo, obs_repo)
    assembler = EvidenceAssembler(exp_repo, obs_repo, ev_repo)
    
    settings = LLMSettings(
        model_name="llama3.1",
        base_url="http://localhost:11434",
        timeout_seconds=30.0
    )
    
    # Real LLM Investigator
    investigator = LocalLLMInvestigator(settings)
    
    validator = OutputValidator()
    verifier = MockDeterministicVerifier()
    
    return V2ControlWorker(
        worker_id="ollama_worker",
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


@pytest.mark.asyncio
async def test_end_to_end_with_real_ollama(session_maker):
    """
    Tests the full vertical slice using the REAL Ollama investigator.
    If Ollama is not running, the test is explicitly skipped.
    """
    if not is_ollama_available():
        pytest.skip("Ollama is not running or llama3.1 is not available. Skipping real LLM integration test.")
        
    recon_id, order_id, payment_id = setup_hero_incident(session_maker)
    worker, inc_repo, evt_repo = create_ollama_worker(session_maker)
    
    await worker.poll_and_process()
    
    # Check that we reached a conclusion. Since we use a real LLM, it might hallucinate or propose verification.
    # In either case, the control loop should NOT crash. It will either ESCALATE (if hallucinated)
    # or progress to VERIFYING -> RESOLVED (if it correctly outputs a valid hypothesis and our mock verifier passes).
    active = inc_repo.get_active_incident("obs1", DiscrepancyReason.STATE_MISMATCH.value)
    
    # Assert it either cleanly resolved (None) or correctly escalated
    if active is not None:
        assert active.state == InvestigationState.ESCALATED
