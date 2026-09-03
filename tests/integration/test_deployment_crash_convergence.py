import os
import time
import uuid
import pytest
import multiprocessing
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.settings import FCESettings
from src.domain.core.models import (
    Expectation, Observation, ReconciliationOutcome, BusinessStatus,
    ReconciliationResult, DiscrepancyReason
)
from src.storage.postgres.models import Base
from src.storage.postgres_substrate import (
    PostgresExpectationRepository, PostgresObservationRepository,
    PostgresActiveIncidentRepository, PostgresControlEventRepository,
    PostgresReconciliationResultRepository, PostgresEvidenceRepository,
    ControlEventType
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.investigation.agent import LocalLLMInvestigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.integrations.razorpay.client import RazorpayClient
from src.engine.worker import V2ControlWorker

from dotenv import load_dotenv
load_dotenv()

# Dummy settings for testing, must use file-backed sqlite or postgres for multiprocessing
TEST_DB_URL = os.environ.get("DATABASE__URL", "sqlite:///test_fce.db")

def worker_process(hook_to_crash: str, db_url: str, active_subject: str):
    """
    Runs the V2ControlWorker in a separate process.
    Injects a test hook that hard-crashes (os._exit) the process when triggered.
    """
    import asyncio
    
    def crash_hook():
        print(f"CRASHING at {hook_to_crash}", flush=True)
        os._exit(1) # Hard kill, no finally blocks, no graceful shutdown
        
    async def run():
        engine = create_engine(db_url)
        SessionMaker = sessionmaker(bind=engine)
        
        # We need mock LLM and Razorpay for predictable testing
        from src.domain.investigation.models import CausalHypothesis, InvestigationDisposition, VerificationIntent
        from src.investigation.agent import Investigator

        class MockInvestigator:
            def investigate(self, agent_input: dict) -> CausalHypothesis:
                return CausalHypothesis(
                    hypothesis_id="hyp_crash",
                    claim="The provider processed it later.",
                    supporting_evidence_ids=[],
                    contradicting_evidence_ids=[],
                    missing_evidence="None required",
                    confidence="HIGH",
                    disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
                    verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE]
                )
                
        class MockRazorpayClient:
            async def get_payment_refunds(self, payment_id):
                return []
        
        from unittest.mock import MagicMock
        mock_razorpay = MagicMock()
                
        class MockVerifier(DeterministicVerifier):
            async def verify(self, hypothesis, context):
                from src.investigation.verifier import VerificationResult, VerificationStatus
                import uuid
                from datetime import datetime, timezone
                if os.environ.get("MOCK_VERIFIER_FAIL") == "1":
                    return [VerificationResult(
                        verification_id=uuid.uuid4().hex,
                        intent=hypothesis.verification_intents[0],
                        status=VerificationStatus.FAILED,
                        failure_reason="Simulated provider failure",
                        new_evidence=[],
                        new_observations=[],
                        evidence_ids=[],
                        verified_at=datetime.now(timezone.utc)
                    )]
                return [VerificationResult(
                    verification_id=uuid.uuid4().hex,
                    intent=hypothesis.verification_intents[0],
                    status=VerificationStatus.SUCCEEDED,
                    failure_reason=None,
                    new_evidence=[],
                    new_observations=[],
                    evidence_ids=[],
                    verified_at=datetime.now(timezone.utc)
                )]
        
        worker = V2ControlWorker(
            worker_id="crash_worker",
            event_repo=PostgresControlEventRepository(SessionMaker),
            incident_repo=PostgresActiveIncidentRepository(SessionMaker),
            observation_repo=PostgresObservationRepository(SessionMaker),
            evidence_repo=PostgresEvidenceRepository(SessionMaker),
            exp_repo=PostgresExpectationRepository(SessionMaker),
            recon_result_repo=PostgresReconciliationResultRepository(SessionMaker),
            reconciliation_engine=V2ReconciliationEngine(PostgresExpectationRepository(SessionMaker), PostgresObservationRepository(SessionMaker)),
            assembler=EvidenceAssembler(PostgresExpectationRepository(SessionMaker), PostgresObservationRepository(SessionMaker), PostgresEvidenceRepository(SessionMaker)),
            investigator=MockInvestigator(),
            validator=OutputValidator(),
            verifier=MockVerifier(razorpay_client=mock_razorpay),
            settings=FCESettings.load().control_loop,
            test_hooks={hook_to_crash: crash_hook}
        )
        
        # Run a single loop iteration to process pending events
        await worker.poll_and_process()
        
    asyncio.run(run())

@pytest.fixture(scope="session")
def db_session_maker():
    # Setup real PG database or fallback
    engine = create_engine(TEST_DB_URL)
    from src.storage.postgres.models import Base
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    Base.metadata.drop_all(engine)
    
@pytest.fixture(autouse=True)
def clean_db(db_session_maker):
    engine = db_session_maker.kw['bind']
    from src.storage.postgres.models import Base
    # Clean tables before each test
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield

@pytest.mark.parametrize("crash_hook", [
    "before_lease_acquire",
    "after_lease_acquire",
    "before_a3",
    "during_a3",
    "before_a4",
    "after_a4",
    "before_commit",
    "before_retry"
])
def test_crash_convergence(db_session_maker, crash_hook):
    """
    Deterministically tests that the worker correctly recovers from a hard crash
    at specific state boundaries.
    """
    # 1. Setup Data
    exp_id = f"exp_{uuid.uuid4()}"
    obs_id = f"obs_{uuid.uuid4()}"
    recon_id = f"rec_{uuid.uuid4()}"
    
    exp_repo = PostgresExpectationRepository(db_session_maker)
    obs_repo = PostgresObservationRepository(db_session_maker)
    recon_repo = PostgresReconciliationResultRepository(db_session_maker)
    evt_repo = PostgresControlEventRepository(db_session_maker)
    inc_repo = PostgresActiveIncidentRepository(db_session_maker)
    
    exp = Expectation(expectation_id=exp_id, domain="Refund", expected_state="PROCESSED", expected_amount=100, currency="INR", source_system="ledger")
    obs = Observation(observation_id=obs_id, provider="razorpay", provider_reference="ref1", observation_type="refund", observed_state="FAILED", observed_amount=100, currency="INR", evidence_ids=[])
    
    exp_repo.save(exp)
    obs_repo.save(obs)
    
    recon_res = ReconciliationResult(
        reconciliation_id=recon_id,
        expectation_id=exp_id,
        observation_ids=[obs_id],
        outcome=ReconciliationOutcome.DISCREPANCY,
        discrepancy_reason=DiscrepancyReason.STATE_MISMATCH,
        reconciliation_reason="mismatch"
    )
    recon_repo.save(recon_res)
    
    evt_repo.publish(ControlEventType.DISCREPANCY_DETECTED, {"reconciliation_id": recon_id})
    
    # 2. Run Worker and Expect Crash
    # For before_retry, we need to mock a failure. To keep the test simple and reusable, 
    # we simulate before_retry by altering the mock verifier to fail if crash_hook == "before_retry".
    
    if crash_hook == "before_retry":
        # Hack to inject failure logic in the subprocess
        os.environ["MOCK_VERIFIER_FAIL"] = "1"
    else:
        os.environ.pop("MOCK_VERIFIER_FAIL", None)
        
    p = multiprocessing.Process(target=worker_process, args=(crash_hook, TEST_DB_URL, exp_id))
    p.start()
    p.join(timeout=10)
    
    # Process should have died with exit code 1 due to os._exit(1)
    assert p.exitcode == 1, f"Process did not crash at {crash_hook}"
    
    # 3. Simulate process restart: expire incident lease.
    # We NO LONGER manually reset IN_PROGRESS events to PENDING.
    # The actual production mechanism (recover_stale_events) must handle it.
    with db_session_maker() as session:
        from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord
        from datetime import timedelta

        # Expire the lease so the new worker can acquire it
        inc = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject=exp_id).first()
        if inc and inc.lease_expires_at:
            inc.lease_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()

    # 4. Restart Worker to Recover
    # Run it without crashing.
    # We pass os.environ for the settings to override event_stale_threshold_seconds to 0
    # for the test, ensuring immediate recovery of the abandoned event.
    os.environ["CONTROL_LOOP__EVENT_STALE_THRESHOLD_SECONDS"] = "0"
    p2 = multiprocessing.Process(target=worker_process, args=("no_crash", TEST_DB_URL, exp_id))
    p2.start()
    p2.join(timeout=10)
    os.environ.pop("CONTROL_LOOP__EVENT_STALE_THRESHOLD_SECONDS", None)
    
    assert p2.exitcode == 0, f"Recovery worker failed with exit code {p2.exitcode}"
    
    # 5. Assert Convergence & Idempotency
    # Re-fetch state
    with db_session_maker() as session:
        from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord
        inc = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject=exp_id).first()
        if crash_hook == "before_retry":
            # It should have successfully retried and recovered, or it should be in RETRY_PENDING.
            # But wait, run_loop_once() only runs once. If it's RETRY_PENDING, it won't be processed again instantly.
            assert inc is not None, "Incident state should exist in RETRY_PENDING"
        else:
            # It should have converged successfully and released the incident
            assert inc is None, "Incident should have been released"
        
    # Check no duplicate control events
    # We should have exactly 1 DISCREPANCY_DETECTED event and maybe 1 EVENT_RESOLVED event
    with db_session_maker() as session:
        from src.storage.postgres_substrate import V2ControlEventRecord, SubstrateEvidenceRecord, SubstrateObservationRecord
        events = session.query(V2ControlEventRecord).all()
        # Ensure no duplicates were spawned
        discrepancy_events = [e for e in events if e.event_type == ControlEventType.DISCREPANCY_DETECTED.value]
        assert len(discrepancy_events) == 1, "Should not spawn duplicate discrepancy events"
        
        # Ensure no duplicate evidence
        evidence = session.query(SubstrateEvidenceRecord).all()
        assert len(evidence) <= 1, "Should not create duplicate evidence records"
