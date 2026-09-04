import asyncio
import logging
import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys

from src.config.settings import FCESettings
from src.storage.postgres_substrate import (
    PostgresExpectationRepository,
    PostgresObservationRepository,
    PostgresEvidenceRepository,
    PostgresActiveIncidentRepository,
    PostgresControlEventRepository,
    PostgresReconciliationResultRepository,
    PostgresActuationRepository
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.investigation.agent import LocalLLMInvestigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.integrations.razorpay.client import RazorpayClient
from src.engine.worker import V2ControlWorker
from src.ingestion.worker import IngestionWorker
from src.storage.postgres_ingestion import PostgresIngestionRepository
from src.observability.logging import configure_logging, get_logger
import uuid
import os
from typing import Dict, Any, Optional

from src.domain.investigation.models import (
    CausalHypothesis, 
    InvestigationDisposition, 
    VerificationIntent, 
    VerificationResult,
    VerificationStatus
)
from src.domain.investigation.context import InvestigationContext
import datetime

class MockInvestigator:
    def investigate(self, agent_input: Dict[str, Any]) -> CausalHypothesis:
        return CausalHypothesis(
            hypothesis_id="mock_hyp",
            claim="Mock claim for validation",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            missing_evidence="none",
            confidence="HIGH",
            disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
            verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE]
        )

class MockVerifier:
    def __init__(self, razorpay_client=None):
        pass
    async def verify(self, hypothesis: CausalHypothesis, context: InvestigationContext) -> list[VerificationResult]:
        import asyncio
        await asyncio.sleep(2)
        return [
            VerificationResult(
                verification_id="mock_ver_id",
                intent=VerificationIntent.QUERY_PROVIDER_STATE,
                status=VerificationStatus.SUCCEEDED,
                evidence_ids=[],
                new_evidence=[],
                new_observations=[],
                verified_at=datetime.datetime.now(datetime.timezone.utc)
            )
        ]

async def main():
    # Load configuration
    settings = FCESettings.load()
    
    # Configure Observability
    configure_logging()
    logger = get_logger("fce.worker_main")
    worker_id = str(getattr(settings, "worker_id", uuid.uuid4().hex))
    logger.info("Initializing FCE V2 Worker...", worker_id=worker_id)
    
    # Initialize Substrate (PostgreSQL)
    try:
        engine = create_engine(settings.database.url.get_secret_value(), pool_size=10, max_overflow=20)
        SessionMaker = sessionmaker(bind=engine)
        logger.info("Connected to PostgreSQL substrate.")
    except Exception as e:
        logger.error("Failed to connect to database.", error=str(e))
        sys.exit(1)
        
    exp_repo = PostgresExpectationRepository(SessionMaker)
    obs_repo = PostgresObservationRepository(SessionMaker)
    ev_repo = PostgresEvidenceRepository(SessionMaker)
    inc_repo = PostgresActiveIncidentRepository(SessionMaker)
    evt_repo = PostgresControlEventRepository(SessionMaker)
    recon_repo = PostgresReconciliationResultRepository(SessionMaker)
    act_repo = PostgresActuationRepository(SessionMaker)
    ingestion_repo = PostgresIngestionRepository(SessionMaker)
    
    recon_engine = V2ReconciliationEngine(exp_repo, obs_repo)
    assembler = EvidenceAssembler(exp_repo, obs_repo, ev_repo)
    
    # Initialize real components using Dependency Injection
    mock_mode = os.environ.get("FCE_MOCK_MODE") == "1"
    
    if mock_mode:
        logger.warning("FCE_MOCK_MODE=1: Using deterministic mocks for LLM and Verifier")
        investigator = MockInvestigator()
        
        # We need a mock razorpay client to pass to MockVerifier if we use it, 
        # or we just instantiate MockVerifier with a dummy or None. 
        # But MockVerifier accepts razorpay_client but doesn't strictly use it if we mock everything.
        from unittest.mock import AsyncMock
        mock_rzp = AsyncMock()
        verifier = MockVerifier(razorpay_client=mock_rzp)
        validator = OutputValidator()
    else:
        investigator = LocalLLMInvestigator(settings=settings.llm)
        validator = OutputValidator()
        razorpay_client = RazorpayClient(settings=settings.razorpay)
        verifier = DeterministicVerifier(razorpay_client=razorpay_client)
    
    worker = V2ControlWorker(
        worker_id=worker_id,
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
        verifier=verifier, # type: ignore
        settings=settings.control_loop
    )
    
    def _on_obs_persisted(obs):
        from src.storage.postgres_substrate import ControlEventType
        evt_repo.publish(
            event_type=ControlEventType.OBSERVATION_INGESTED,
            payload={"observation_id": obs.observation_id}
        )

    ingestion_worker = IngestionWorker(
        worker_id=worker_id,
        ingestion_repo=ingestion_repo,
        observation_repo=obs_repo,
        evidence_repo=ev_repo,
        on_observation_persisted=_on_obs_persisted
    )
    
    # Run the control loop indefinitely
    while True:
        ingestion_worker.process_batch(limit=10)
        await worker.poll_and_process()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
