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
    PostgresReconciliationResultRepository
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.investigation.agent import LocalLLMInvestigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.integrations.razorpay.client import RazorpayClient
from src.engine.worker import V2ControlWorker
from src.observability.logging import configure_logging, get_logger
import uuid

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
    
    recon_engine = V2ReconciliationEngine(exp_repo, obs_repo)
    assembler = EvidenceAssembler(exp_repo, obs_repo, ev_repo)
    
    # Initialize real components using Dependency Injection
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
        reconciliation_engine=recon_engine,
        assembler=assembler,
        investigator=investigator,
        validator=validator,
        verifier=verifier,
        settings=settings.control_loop
    )
    
    # Run the control loop indefinitely
    await worker.poll_and_process()

if __name__ == "__main__":
    asyncio.run(main())
