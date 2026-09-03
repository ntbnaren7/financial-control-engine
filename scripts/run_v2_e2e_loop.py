import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage.postgres.models import Base
from src.storage.postgres_substrate import (
    PostgresExpectationRepository,
    PostgresObservationRepository,
    PostgresEvidenceRepository,
    PostgresActiveIncidentRepository,
    PostgresControlEventRepository,
    PostgresReconciliationResultRepository,
    ControlEventType,
    SubstrateReconciliationResultRecord
)
from src.domain.core.models import (
    Expectation, Observation, CorrelationKeys, BusinessStatus, ReconciliationOutcome
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.investigation.agent import Investigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.engine.worker import V2ControlWorker
from src.integrations.razorpay.client import RazorpayClient
from src.domain.investigation.models import CausalHypothesis, InvestigationDisposition, VerificationIntent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_loop")

async def main():
    logger.info("Initializing in-memory Substrate...")
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionMaker = sessionmaker(bind=engine)
    
    exp_repo = PostgresExpectationRepository(SessionMaker)
    obs_repo = PostgresObservationRepository(SessionMaker)
    ev_repo = PostgresEvidenceRepository(SessionMaker)
    inc_repo = PostgresActiveIncidentRepository(SessionMaker)
    evt_repo = PostgresControlEventRepository(SessionMaker)
    recon_repo = PostgresReconciliationResultRepository(SessionMaker)
    
    recon_engine = V2ReconciliationEngine(exp_repo, obs_repo)
    assembler = EvidenceAssembler(exp_repo, obs_repo, ev_repo)
    
    # Mock LLM Investigator to return deterministic hypothesis
    logger.info("Mocking A3 Investigator for deterministic E2E test...")
    investigator = MagicMock(spec=Investigator)
    investigator.investigate = MagicMock(return_value=CausalHypothesis(
        hypothesis_id="hyp_123",
        claim="The provider processed it later.",
        supporting_evidence_ids=[],
        contradicting_evidence_ids=[],
        missing_evidence="Need provider state.",
        confidence="HIGH",
        disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
        verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE]
    ))
    
    validator = OutputValidator()
    
    # Mock Razorpay HTTP client
    logger.info("Mocking Razorpay Provider API...")
    client = MagicMock(spec=RazorpayClient)
    client.get_payment_refunds = AsyncMock()
    
    class MockRefund:
        def __init__(self, id, payment_id, receipt, status, amount, currency, created_at):
            self.id = id
            self.payment_id = payment_id
            self.receipt = receipt
            self.status = status
            self.amount = amount
            self.currency = currency
            self.created_at = created_at
        def model_dump(self):
            return {
                "id": self.id,
                "payment_id": self.payment_id,
                "receipt": self.receipt,
                "status": self.status,
                "amount": self.amount,
                "currency": self.currency,
                "created_at": self.created_at
            }
            
    client.get_payment_refunds.return_value = [
        MockRefund("rfnd_123", "pay_123", "rcpt_123", "processed", 2000, "INR", int(datetime.now(timezone.utc).timestamp()) + 3600)
    ]
    
    verifier = DeterministicVerifier(razorpay_client=client)
    
    worker = V2ControlWorker(
        worker_id="worker_1",
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
        verifier=verifier
    )
    
    # Seed data
    logger.info("Seeding conflicting expectation and observation...")
    now = datetime.now(timezone.utc)
    exp = Expectation(
        expectation_id="exp_1",
        domain="REFUND",
        expected_state="PROCESSED",
        expected_amount=2000,
        currency="INR",
        source_system="OMS",
        business_status=BusinessStatus.OPEN,
        correlation_keys=CorrelationKeys(provider="razorpay", provider_ref="pay_123", internal_ref="rcpt_123"),
        created_at=now
    )
    exp_repo.save(exp)
    
    obs = Observation(
        observation_id="obs_1",
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="PAYMENT_STATUS",
        observed_state="CAPTURED", # Discrepancy!
        observed_amount=2000,
        currency="INR",
        evidence_ids=[],
        correlation_keys=CorrelationKeys(provider_ref="pay_123"),
        observed_at=now,
        ingestion_event_id="evt_1"
    )
    obs_repo.save(obs)
    
    # Trigger
    evt_repo.publish(ControlEventType.OBSERVATION_INGESTED, {})
    
    logger.info("Starting Control Loop Cycle 1: Ingestion -> Detection")
    await worker.poll_and_process()
    
    logger.info("Starting Control Loop Cycle 2: Assembly -> Explanation -> Verification -> Persist")
    await worker.poll_and_process()
    
    logger.info("Starting Control Loop Cycle 3: Re-reconciliation")
    await worker.poll_and_process()
    
    # Assert Outcome
    with SessionMaker() as session:
        records = session.query(SubstrateReconciliationResultRecord).order_by(SubstrateReconciliationResultRecord.created_at.desc()).all()
        assert len(records) > 0
        latest_result = records[0]
        logger.info(f"Final Reconciliation Outcome: {latest_result.outcome}")
        assert latest_result.outcome == ReconciliationOutcome.MATCH
        logger.info("SUCCESS: The control loop successfully self-healed the discrepancy!")

if __name__ == "__main__":
    asyncio.run(main())
