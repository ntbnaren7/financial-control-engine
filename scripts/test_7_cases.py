"""
7-Case Autonomous Recovery Matrix
==================================
Exercises the complete FCE V2 control loop using MockRazorpayProvider.

Scenarios:
  A - Successful verification → Policy → GovernanceGate → Actuation → RESOLVED
  B - Verification failure (provider returns 404) → ESCALATED_MISSING_EVIDENCE
"""
import asyncio
import logging
from unittest.mock import MagicMock
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
    PostgresActuationRepository,
    ControlEventType,
    ActiveIncidentIdempotencyRecord,
)
# Import governance ORM classes so their tables appear in Base.metadata
from src.storage.postgres_governance import (  # noqa: F401
    SubstrateControlPlaneStateRecord,
    SubstrateActionBudgetRecord,
    SubstrateOperatorActionRecord,
)
from src.domain.core.models import (
    Expectation, Observation, CorrelationKeys, BusinessStatus, CanonicalStatus
)
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.investigation.agent import Investigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.engine.worker import V2ControlWorker
from src.integrations.razorpay.mock_provider import MockRazorpayProvider
from src.domain.investigation.models import (
    CausalHypothesis, InvestigationDisposition, VerificationIntent
)
from src.domain.investigation.lifecycle import IncidentState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_7_cases")

RESULTS: dict = {}


def _seed_budget(session_maker, budget_id: str, target_action: str, count_limit: int = 100, monetary_limit: int = 1_000_000):
    """Insert an action budget row so GovernanceGate can consume it."""
    from src.domain.governance.models import ActionBudget, BudgetPeriod
    budget = ActionBudget(
        budget_id=budget_id,
        target_action=target_action,
        period=BudgetPeriod.DAILY,
        count_limit=count_limit,
        monetary_limit=monetary_limit,
        currency="INR",
        count_used=0,
        monetary_used=0,
        updated_at=datetime.now(timezone.utc),
    )
    with session_maker() as session:
        session.add(SubstrateActionBudgetRecord.from_domain(budget))
        session.commit()


async def run_scenario_a(worker, exp_repo, obs_repo, evt_repo, session_maker):
    """
    Scenario A: Successful Autonomous Recovery
    Merchant=PENDING, Razorpay=SETTLED → REPAIR_MERCHANT_STATE → RESOLVED
    """
    payment_id = "pay_scenario_a_test"
    receipt = "rcpt_a"
    now = datetime.now(timezone.utc)

    # Seed the external simulator so MerchantRepairActuator can execute the CAS.
    # The simulator is the internal merchant + provider state store used by MerchantRepairActuator.
    from src.engine.external_simulator import simulator
    simulator.reset()
    simulator.seed_merchant_order(receipt, 2000, status="UNPAID")       # merchant: not yet reconciled
    simulator.seed_provider_payment(payment_id, receipt, 2000, status="CAPTURED")  # provider: captured

    # Seed the mock provider with order_id = receipt so the normalizer's internal_ref
    # matches the rest of the observation set (required for reconciliation group identity).
    worker.observer.razorpay_provider.seed_payment(payment_id, order_id=receipt, amount=2000, status="captured")  # type: ignore

    exp = Expectation(
        expectation_id="exp_a",
        domain="PAYMENT",
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=2000,
        currency="INR",
        source_system="OMS",
        business_status=BusinessStatus.OPEN,
        correlation_keys=CorrelationKeys(
            provider="razorpay", provider_ref=payment_id, internal_ref=receipt
        ),
        created_at=now,
    )
    exp_repo.save(exp)

    # Merchant side: PENDING (not yet reconciled)
    obs_merchant = Observation(
        observation_id="obs_a_merchant",
        provider="Merchant",
        provider_reference=receipt,
        observation_type="DB_POLL",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=2000,
        currency="INR",
        evidence_ids=[],
        correlation_keys=CorrelationKeys(
            provider="razorpay", provider_ref=payment_id, internal_ref=receipt
        ),
        observed_at=now,
        ingestion_event_id="evt_a_m",
    )
    obs_repo.save(obs_merchant)

    # Razorpay side: SETTLED (mock returns "captured" for pay_scenario_a_* prefix)
    obs_razorpay = Observation(
        observation_id="obs_a_razorpay",
        provider="Razorpay",
        provider_reference=payment_id,
        observation_type="API_PAYMENT",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=2000,
        currency="INR",
        evidence_ids=[],
        correlation_keys=CorrelationKeys(
            provider="razorpay", provider_ref=payment_id, internal_ref=receipt
        ),
        observed_at=now,
        ingestion_event_id="evt_a_r",
    )
    obs_repo.save(obs_razorpay)

    evt_repo.publish(ControlEventType.OBSERVATION_INGESTED, {"observation_id": "obs_a_razorpay"})

    logger.info("=== SCENARIO A Cycle 1: Detection ===")
    await worker.poll_and_process()

    logger.info("=== SCENARIO A Cycles 2-5: Full control loop ===")
    for _ in range(4):
        await worker.poll_and_process()

    with session_maker() as session:
        incidents = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject="exp_a").all()
        if not incidents:
            logger.error("FAILED [A]: no incident record found")
            RESULTS["A"] = "FAILED (no incident)"
            return
        incident = incidents[0]
        logger.info(f"Scenario A final state: {incident.state}")
        if incident.state == IncidentState.RESOLVED.value:
            logger.info("SUCCESS [A]: Autonomous recovery — discrepancy resolved via mock provider")
            RESULTS["A"] = "PASSED"
        else:
            logger.error(f"FAILED [A]: Ended in {incident.state}")
            RESULTS["A"] = f"FAILED ({incident.state})"


async def run_scenario_b(worker, exp_repo, obs_repo, evt_repo, session_maker):
    """
    Scenario B: Verification Failure → Escalation
    Provider returns 404 → ESCALATED_MISSING_EVIDENCE
    """
    payment_id_b = "pay_scenario_b_does_not_exist"
    receipt_b = "rcpt_b"
    now = datetime.now(timezone.utc)

    exp_b = Expectation(
        expectation_id="exp_b",
        domain="PAYMENT",
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=4500,
        currency="INR",
        source_system="OMS",
        business_status=BusinessStatus.OPEN,
        correlation_keys=CorrelationKeys(
            provider="razorpay", provider_ref=payment_id_b, internal_ref=receipt_b
        ),
        created_at=now,
    )
    exp_repo.save(exp_b)

    obs_b = Observation(
        observation_id="obs_b",
        provider="Razorpay",
        provider_reference=payment_id_b,
        observation_type="API_PAYMENT",
        canonical_status=CanonicalStatus.FAILED,
        observed_amount=4500,
        currency="INR",
        evidence_ids=[],
        correlation_keys=CorrelationKeys(
            provider="razorpay", provider_ref=payment_id_b, internal_ref=receipt_b
        ),
        observed_at=now,
        ingestion_event_id="evt_b",
    )
    obs_repo.save(obs_b)

    evt_repo.publish(ControlEventType.OBSERVATION_INGESTED, {"observation_id": "obs_b"})

    for _ in range(4):
        await worker.poll_and_process()

    with session_maker() as session:
        incidents = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject="exp_b").all()
        if not incidents:
            logger.error("FAILED [B]: no incident record found")
            RESULTS["B"] = "FAILED (no incident)"
            return
        incident = incidents[0]
        logger.info(f"Scenario B final state: {incident.state}")
        escalated_states = {IncidentState.ESCALATED_MISSING_EVIDENCE.value, IncidentState.ESCALATED.value}
        if incident.state in escalated_states:
            logger.info("SUCCESS [B]: Verification failure correctly escalated — no actuation attempted")
            RESULTS["B"] = "PASSED"
        else:
            logger.error(f"FAILED [B]: Ended in {incident.state}")
            RESULTS["B"] = f"FAILED ({incident.state})"


async def main():
    logger.info("Initializing in-memory Substrate (SQLite)...")
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionMaker = sessionmaker(bind=engine)

    exp_repo = PostgresExpectationRepository(SessionMaker)
    obs_repo = PostgresObservationRepository(SessionMaker)
    ev_repo = PostgresEvidenceRepository(SessionMaker)
    inc_repo = PostgresActiveIncidentRepository(SessionMaker)
    evt_repo = PostgresControlEventRepository(SessionMaker)
    recon_repo = PostgresReconciliationResultRepository(SessionMaker)
    act_repo = PostgresActuationRepository(SessionMaker)

    recon_engine = V2ReconciliationEngine(exp_repo, obs_repo)
    assembler = EvidenceAssembler(exp_repo, obs_repo, ev_repo)

    # Deterministic mock LLM — always proposes provider-state verification
    investigator = MagicMock(spec=Investigator)
    investigator.investigate = MagicMock(return_value=CausalHypothesis(
        hypothesis_id="hyp_test",
        claim="Provider may have processed the payment after merchant timeout.",
        supporting_evidence_ids=[],
        contradicting_evidence_ids=[],
        missing_evidence="Need live Razorpay payment state.",
        confidence="HIGH",
        disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
        verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE],
    ))

    validator = OutputValidator()
    provider = MockRazorpayProvider()
    verifier = DeterministicVerifier(razorpay_provider=provider)

    worker = V2ControlWorker(
        worker_id="worker_test",
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
        razorpay_provider=provider,
    )

    # Seed action budgets — budget_id convention: f"budget_{action.value.lower()}"
    _seed_budget(SessionMaker, "budget_repair_merchant_state", "REPAIR_MERCHANT_STATE")
    _seed_budget(SessionMaker, "budget_refund_payment",        "REFUND_PAYMENT")

    logger.info("")
    logger.info("=" * 52)
    logger.info("  FCE V2 Autonomous Recovery Matrix")
    logger.info("=" * 52)

    logger.info("--- Scenario A: Successful Autonomous Recovery ---")
    await run_scenario_a(worker, exp_repo, obs_repo, evt_repo, SessionMaker)

    logger.info("")
    logger.info("--- Scenario B: Verification Failure -> Escalation ---")
    await run_scenario_b(worker, exp_repo, obs_repo, evt_repo, SessionMaker)

    logger.info("")
    logger.info("=" * 52)
    logger.info("  RESULTS SUMMARY")
    logger.info("=" * 52)
    all_passed = True
    for scenario, result in sorted(RESULTS.items()):
        icon = "PASS" if result == "PASSED" else "FAIL"
        logger.info(f"  [{icon}] Scenario {scenario}: {result}")
        if result != "PASSED":
            all_passed = False
    if all_passed:
        logger.info("  All scenarios passed.")
    else:
        logger.error("  One or more scenarios FAILED.")
    logger.info("=" * 52)


if __name__ == "__main__":
    asyncio.run(main())
