import pytest
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any
from unittest.mock import MagicMock

from src.domain.investigation.lifecycle import IncidentState
from src.domain.core.models import (
    Observation,
    Expectation,
    CanonicalStatus,
    BusinessStatus,
    CorrelationKeys,
    DiscrepancyReason,
    ReconciliationResult,
    ReconciliationOutcome,
)
from src.storage.postgres_substrate import (
    ActiveIncidentIdempotencyRecord,
    SubstrateReconciliationResultRecord,
    PostgresActiveIncidentRepository,
    PostgresExpectationRepository,
    PostgresObservationRepository,
    PostgresEvidenceRepository,
    PostgresControlEventRepository,
    PostgresReconciliationResultRepository,
    PostgresActuationRepository,
    ControlEventType,
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.engine.worker import V2ControlWorker
from src.investigation.agent import Investigator
from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationIntent,
    VerificationResult,
    VerificationStatus,
)
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.config.settings import ControlLoopSettings

from tests.integration.test_end_to_end_vertical_slice import (
    postgres_engine,
    session_maker,
    clean_db,
    MockDeterministicVerifier,
    MockInvestigator,
)


def test_backoff_admission_gate(session_maker):
    """
    Test A — Backoff admission gate:
    An incident in INVESTIGATING state with next_retry_at in the future
    CANNOT be acquired by acquire_lease().
    Once next_retry_at has elapsed, acquire_lease() succeeds.
    """
    inc_repo = PostgresActiveIncidentRepository(session_maker)
    active_subject = f"exp_gate_{uuid.uuid4()}"
    discrepancy_reason = "STATE_MISMATCH"
    now = datetime.now(timezone.utc)

    # Seed incident with backoff in the future (+60s)
    with session_maker() as session:
        inc = ActiveIncidentIdempotencyRecord(
            active_subject=active_subject,
            discrepancy_reason=discrepancy_reason,
            incident_id=f"inc_{uuid.uuid4()}",
            state=IncidentState.INVESTIGATING,
            lease_owner=None,
            lease_expires_at=None,
            retry_count=1,
            next_retry_at=now + timedelta(seconds=60),
            version=1,
            created_at=now,
        )
        session.add(inc)
        session.commit()

    # 1. Attempt lease acquisition before backoff expires -> MUST BE REJECTED
    leased = inc_repo.acquire_lease(active_subject, discrepancy_reason, "worker_1", ttl_seconds=30)
    assert leased is None, "Expected acquire_lease to reject acquisition when next_retry_at > now"

    # Verify state in database is untouched
    with session_maker() as session:
        record = session.query(ActiveIncidentIdempotencyRecord).filter_by(
            active_subject=active_subject,
            discrepancy_reason=discrepancy_reason,
        ).one()
        assert record.lease_owner is None
        assert record.state == IncidentState.INVESTIGATING

    # 2. Advance backoff so that next_retry_at is now in the past
    with session_maker() as session:
        record = session.query(ActiveIncidentIdempotencyRecord).filter_by(
            active_subject=active_subject,
            discrepancy_reason=discrepancy_reason,
        ).one()
        record.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        session.commit()

    # 3. Attempt lease acquisition after backoff expires -> MUST SUCCEED
    leased = inc_repo.acquire_lease(active_subject, discrepancy_reason, "worker_1", ttl_seconds=30)
    assert leased is not None, "Expected acquire_lease to succeed when next_retry_at <= now"
    assert str(leased.lease_owner) == "worker_1"


def test_matured_retry_autonomous_discovery(session_maker):
    """
    Test B — Matured retry admission:
    When an incident has state = INVESTIGATING, no active lease, and next_retry_at <= now,
    acquire_matured_retries() autonomously discovers and claims it.
    No control event is required in v2_control_events.
    """
    inc_repo = PostgresActiveIncidentRepository(session_maker)
    evt_repo = PostgresControlEventRepository(session_maker)
    active_subject = f"exp_mature_{uuid.uuid4()}"
    discrepancy_reason = "AMOUNT_MISMATCH"
    now = datetime.now(timezone.utc)

    # Verify event queue is empty
    assert evt_repo.count_pending() == 0

    with session_maker() as session:
        inc = ActiveIncidentIdempotencyRecord(
            active_subject=active_subject,
            discrepancy_reason=discrepancy_reason,
            incident_id=f"inc_{uuid.uuid4()}",
            state=IncidentState.INVESTIGATING,
            lease_owner=None,
            lease_expires_at=None,
            retry_count=1,
            next_retry_at=now - timedelta(seconds=10),  # Matured retry
            version=1,
            created_at=now,
        )
        session.add(inc)
        session.commit()

    # Discover and claim matured retries
    claimed = inc_repo.acquire_matured_retries(worker_id="worker_mature", ttl_seconds=30, limit=5)
    assert len(claimed) == 1, f"Expected 1 claimed retry, got {len(claimed)}"
    assert str(claimed[0].active_subject) == active_subject
    assert str(claimed[0].lease_owner) == "worker_mature"
    assert claimed[0].lease_expires_at is not None

    # Verify in database
    with session_maker() as session:
        record = session.query(ActiveIncidentIdempotencyRecord).filter_by(
            active_subject=active_subject,
            discrepancy_reason=discrepancy_reason,
        ).one()
        assert record.lease_owner == "worker_mature"
        assert record.lease_expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_autonomous_retry_execution_end_to_end(session_maker):
    """
    Test C — Complete autonomous retry lifecycle:
    1. Initial failure in verification triggers schedule_retry().
    2. Incident is persisted in INVESTIGATING state with next_retry_at in the future.
    3. Triggering control event is marked PROCESSED. No pending events remain.
    4. Worker polling cycle runs during backoff window -> does NOT re-run incident.
    5. When next_retry_at matures, worker's autonomous polling discovers incident.
    6. Investigation and verification resume autonomously without any manual event injection.
    7. Incident completes resolution cleanly.
    """
    test_id = uuid.uuid4().hex[:8]
    exp_id = f"exp_{test_id}"
    obs_id = f"obs_{test_id}"
    recon_id = f"rec_{test_id}"
    now = datetime.now(timezone.utc)

    exp_repo = PostgresExpectationRepository(session_maker)
    obs_repo = PostgresObservationRepository(session_maker)
    recon_repo = PostgresReconciliationResultRepository(session_maker)
    evt_repo = PostgresControlEventRepository(session_maker)
    inc_repo = PostgresActiveIncidentRepository(session_maker)
    ev_repo = PostgresEvidenceRepository(session_maker)
    act_repo = PostgresActuationRepository(session_maker)

    # 1. Seed Expectation and Discrepant Observation
    exp = Expectation(
        expectation_id=exp_id,
        domain="REFUND",
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=5000,
        currency="INR",
        source_system="OMS",
        business_status=BusinessStatus.OPEN,
        correlation_keys=CorrelationKeys(provider="razorpay", provider_ref=f"pay_{test_id}"),
        created_at=now,
    )
    obs = Observation(
        observation_id=obs_id,
        provider="razorpay",
        provider_reference=f"pay_{test_id}",
        observation_type="refund",
        canonical_status=CanonicalStatus.FAILED,
        observed_amount=5000,
        currency="INR",
        evidence_ids=[],
        correlation_keys=CorrelationKeys(provider_ref=f"pay_{test_id}"),
        observed_at=now,
    )
    exp_repo.save(exp)
    obs_repo.save(obs)

    recon_res = ReconciliationResult(
        reconciliation_id=recon_id,
        expectation_id=exp_id,
        observation_ids=[obs_id],
        outcome=ReconciliationOutcome.DISCREPANCY,
        discrepancy_reason=DiscrepancyReason.STATE_MISMATCH,
        reconciliation_reason="State mismatch: expected SETTLED got FAILED",
        created_at=now,
    )
    recon_repo.save(recon_res)

    # Initial Verifier: Fails verification to force a retry
    class FailingVerificationVerifier(DeterministicVerifier):
        def __init__(self):
            super().__init__(razorpay_provider=None)  # type: ignore
            self.should_fail = True

        async def verify(self, hypothesis, context):
            if self.should_fail:
                return [
                    VerificationResult(
                        verification_id=uuid.uuid4().hex,
                        intent=VerificationIntent.QUERY_PROVIDER_STATE,
                        status=VerificationStatus.FAILED,
                        failure_reason="Simulated provider query failure",
                        new_evidence=[],
                        new_observations=[],
                        evidence_ids=[],
                        verified_at=datetime.now(timezone.utc),
                    )
                ]
            # On retry, verification succeeds with updated SETTLED observation
            matching_obs = Observation(
                observation_id=f"obs_settled_{test_id}",
                provider="razorpay",
                provider_reference=f"pay_{test_id}",
                observation_type="refund",
                canonical_status=CanonicalStatus.SETTLED,
                observed_amount=5000,
                currency="INR",
                evidence_ids=[],
                correlation_keys=CorrelationKeys(provider_ref=f"pay_{test_id}"),
                observed_at=datetime.now(timezone.utc),
            )
            return [
                VerificationResult(
                    verification_id=uuid.uuid4().hex,
                    intent=VerificationIntent.QUERY_PROVIDER_STATE,
                    status=VerificationStatus.SUCCEEDED,
                    failure_reason=None,
                    new_evidence=[],
                    new_observations=[matching_obs],
                    evidence_ids=[],
                    verified_at=datetime.now(timezone.utc),
                )
            ]

    verifier = FailingVerificationVerifier()
    mock_razorpay = MagicMock()

    worker = V2ControlWorker(
        worker_id="worker_e2e_retry",
        event_repo=evt_repo,
        incident_repo=inc_repo,
        observation_repo=obs_repo,
        evidence_repo=ev_repo,
        exp_repo=exp_repo,
        recon_result_repo=recon_repo,
        actuation_repo=act_repo,
        reconciliation_engine=V2ReconciliationEngine(exp_repo, obs_repo),
        assembler=EvidenceAssembler(exp_repo, obs_repo, ev_repo),
        investigator=MockInvestigator(),
        validator=OutputValidator(),
        verifier=verifier,
        razorpay_provider=mock_razorpay,
        settings=ControlLoopSettings(),
    )

    # Publish initial event to trigger the control loop
    evt_repo.publish(ControlEventType.DISCREPANCY_DETECTED, {"reconciliation_id": recon_id})

    # Pass 1: Worker processes discrepancy event, verification fails, schedule_retry() called
    await worker.poll_and_process()

    # Invariants after Pass 1:
    with session_maker() as session:
        inc = session.query(ActiveIncidentIdempotencyRecord).filter_by(
            active_subject=exp_id,
            discrepancy_reason=DiscrepancyReason.STATE_MISMATCH.value,
        ).one()
        assert inc.state == IncidentState.INVESTIGATING
        assert inc.retry_count == 1
        assert inc.lease_owner is None
        assert inc.next_retry_at is not None
        assert inc.next_retry_at > datetime.now(timezone.utc)

    # Event queue is now completely empty
    assert evt_repo.count_pending() == 0

    # Pass 2: Worker poll cycle runs while next_retry_at is in the future
    # Should NOT process the incident
    await worker.poll_and_process()

    with session_maker() as session:
        inc = session.query(ActiveIncidentIdempotencyRecord).filter_by(
            active_subject=exp_id,
        ).one()
        assert inc.state == IncidentState.INVESTIGATING
        assert inc.retry_count == 1
        assert inc.lease_owner is None

    # Fast-forward time: mature next_retry_at
    with session_maker() as session:
        inc = session.query(ActiveIncidentIdempotencyRecord).filter_by(
            active_subject=exp_id,
        ).one()
        inc.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    # Configure verifier to succeed on retry
    verifier.should_fail = False

    # Pass 3: Worker runs poll_and_process() WITHOUT ANY MANUAL CONTROL EVENT
    # It must autonomously discover the matured retry and resolve it!
    await worker.poll_and_process()

    # Final Invariant: Incident autonomously reached RESOLVED
    with session_maker() as session:
        inc = session.query(ActiveIncidentIdempotencyRecord).filter_by(
            active_subject=exp_id,
        ).one()
        assert inc.state == IncidentState.RESOLVED, f"Expected RESOLVED, got {inc.state}"


def test_concurrent_retry_claim_against_real_postgres(session_maker):
    """
    Test D — Concurrent retry claim under real PostgreSQL:
    Multiple workers simultaneously attempting acquire_matured_retries()
    on the same matured incident.
    Invariants proven:
    1. Exactly ONE worker successfully acquires the lease.
    2. Other workers receive an empty list (zero claimed).
    3. The database row has lease_owner set to the single winning worker.
    """
    inc_repo = PostgresActiveIncidentRepository(session_maker)
    active_subject = f"exp_concurrent_{uuid.uuid4()}"
    discrepancy_reason = "STATE_MISMATCH"
    now = datetime.now(timezone.utc)

    # Seed single matured retry incident
    with session_maker() as session:
        inc = ActiveIncidentIdempotencyRecord(
            active_subject=active_subject,
            discrepancy_reason=discrepancy_reason,
            incident_id=f"inc_{uuid.uuid4()}",
            state=IncidentState.INVESTIGATING,
            lease_owner=None,
            lease_expires_at=None,
            retry_count=1,
            next_retry_at=now - timedelta(seconds=10),
            version=1,
            created_at=now,
        )
        session.add(inc)
        session.commit()

    def worker_poll(worker_id: str):
        repo = PostgresActiveIncidentRepository(session_maker)
        return repo.acquire_matured_retries(worker_id=worker_id, ttl_seconds=30, limit=5)

    # Run 5 concurrent workers simultaneously
    worker_ids = [f"worker_{i}" for i in range(5)]
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker_poll, w_id) for w_id in worker_ids]
        results = [f.result() for f in futures]

    # Exactly 1 worker should have claimed the incident
    successful_claims = [r for r in results if len(r) == 1]
    empty_claims = [r for r in results if len(r) == 0]

    assert len(successful_claims) == 1, f"Expected exactly 1 worker to claim lease, got {len(successful_claims)}"
    assert len(empty_claims) == 4, f"Expected 4 workers to get 0 records, got {len(empty_claims)}"

    winner_record = successful_claims[0][0]
    winner_worker_id = winner_record.lease_owner

    # Verify database state matches winner
    with session_maker() as session:
        db_record = session.query(ActiveIncidentIdempotencyRecord).filter_by(
            active_subject=active_subject,
        ).one()
        assert db_record.lease_owner == winner_worker_id
        assert db_record.lease_expires_at > datetime.now(timezone.utc)
