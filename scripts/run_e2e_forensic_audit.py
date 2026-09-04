#!/usr/bin/env python
import asyncio
import json
import logging
import os
import time
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
    ActiveIncidentIdempotencyRecord
)
from src.storage.postgres_governance import PostgresGovernanceRepository
from src.domain.core.models import (
    Expectation, Observation, CorrelationKeys, BusinessStatus,
    CanonicalStatus
)
from src.domain.governance.models import ActionBudget, BudgetPeriod, ControlPlaneState, AutomationState
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.engine.worker import V2ControlWorker
from src.engine.governance_gate import GovernanceGate
from src.engine.external_simulator import simulator
from src.investigation.agent import LocalLLMInvestigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.integrations.razorpay.client import RazorpayClient, ProviderClientError
from src.integrations.razorpay.models import RazorpayPayment, RazorpayRefund
from src.config.settings import FCESettings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("e2e_audit")

class SimulatedRazorpayClient(RazorpayClient):
    def __init__(self):
        pass
    
    async def get_payment(self, payment_id: str) -> RazorpayPayment:
        record = simulator.read_provider_payment(payment_id)
        if not record:
            raise ProviderClientError(f"Payment {payment_id!r} not found in simulator")
        raw_status = record.get("status", "PENDING")
        captured = raw_status == "CAPTURED"
        return RazorpayPayment(
            id=payment_id, entity="payment", amount=int(record.get("amount", 0) * 100), currency="INR",
            status=raw_status.lower(), order_id=record.get("order_id", ""), method="netbanking",
            amount_refunded=0, refund_status=None, captured=captured, created_at=int(time.time()),
        )
    async def get_payment_refunds(self, payment_id: str) -> list[RazorpayRefund]:
        return []

def setup_db(db_url):
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")
    engine = create_engine(db_url, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)

def build_real_worker(session_factory, settings):
    exp_repo = PostgresExpectationRepository(session_factory)
    obs_repo = PostgresObservationRepository(session_factory)
    ev_repo = PostgresEvidenceRepository(session_factory)
    inc_repo = PostgresActiveIncidentRepository(session_factory)
    evt_repo = PostgresControlEventRepository(session_factory)
    recon_repo = PostgresReconciliationResultRepository(session_factory)
    act_repo = PostgresActuationRepository(session_factory)
    gov_repo = PostgresGovernanceRepository(session_factory)

    recon_engine = V2ReconciliationEngine(exp_repo, obs_repo)
    assembler = EvidenceAssembler(exp_repo, obs_repo, ev_repo)

    investigator = LocalLLMInvestigator(settings.llm)
    validator = OutputValidator()
    verifier = DeterministicVerifier(razorpay_client=SimulatedRazorpayClient())
    gate = GovernanceGate(session_factory)

    return V2ControlWorker(
        worker_id="audit_worker",
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
        verifier=verifier
    )

def seed_governance(session_factory):
    gov_repo = PostgresGovernanceRepository(session_factory)
    state = ControlPlaneState(
        id="GLOBAL", automation_state=AutomationState.ENABLED, reason="Audit initialization",
        updated_by="auditor", version=1
    )
    gov_repo.update_control_plane_state_occ(state)
    
    budget_refund = ActionBudget(budget_id="budget_refund_payment", target_action="REFUND_PAYMENT", period=BudgetPeriod.DAILY, count_limit=10, monetary_limit=100000, currency="INR", count_used=0, monetary_used=0)
    budget_repair = ActionBudget(budget_id="budget_repair_merchant_state", target_action="REPAIR_MERCHANT_STATE", period=BudgetPeriod.DAILY, count_limit=10, monetary_limit=100000, currency="INR", count_used=0, monetary_used=0)
    gov_repo.save_budget(budget_refund)
    gov_repo.save_budget(budget_repair)

async def process_scenario(session_factory, worker, name, oid, pid, amount, simulator_setup, expected_state):
    logger.info(f"--- Running Scenario: {name} ---")
    simulator.reset()
    simulator_setup()

    exp_repo = PostgresExpectationRepository(session_factory)
    obs_repo = PostgresObservationRepository(session_factory)
    evt_repo = PostgresControlEventRepository(session_factory)

    keys = CorrelationKeys(provider="razorpay", provider_ref=pid, internal_ref=oid)
    now = datetime.now(timezone.utc)
    
    exp = Expectation(
        expectation_id=f"exp_{oid}", domain="PAYMENT", expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=amount, currency="INR", source_system="OMS", business_status=BusinessStatus.OPEN,
        correlation_keys=keys, created_at=now
    )
    obs = Observation(
        observation_id=f"obs_{pid}", provider="razorpay", provider_reference=pid, observation_type="PAYMENT_STATUS",
        canonical_status=CanonicalStatus.PENDING, observed_amount=amount, currency="INR", evidence_ids=[],
        correlation_keys=keys, observed_at=now, ingestion_event_id=f"evt_{pid}"
    )
    obs_merchant = Observation(
        observation_id=f"obs_{oid}", provider="merchant", provider_reference=oid, observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING, observed_amount=amount, currency="INR", evidence_ids=[],
        correlation_keys=keys, observed_at=now, ingestion_event_id=f"evt_{oid}"
    )
    
    exp_repo.save(exp)
    obs_repo.save(obs)
    obs_repo.save(obs_merchant)
    evt_repo.publish(ControlEventType.OBSERVATION_INGESTED, {"observation_id": obs.observation_id, "scenario": name})

    for _ in range(5):
        await worker.poll_and_process(limit=5)
    
    inc_repo = PostgresActiveIncidentRepository(session_factory)
    with inc_repo.session_maker() as session:
        record = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject=exp.expectation_id).first()
        actual_state = record.state.value if record else "NOT_FOUND"
        llm_hypothesis = record.hypothesis_payload if record else None
        print(f"[{name}] Result: {actual_state} (Expected: {expected_state})")
        return {
            "name": name,
            "expected": expected_state,
            "actual": actual_state,
            "llm_used": llm_hypothesis is not None
        }

async def run_audits():
    settings = FCESettings.load()
    session_factory = setup_db(settings.database.url.get_secret_value())
    worker = build_real_worker(session_factory, settings)
    seed_governance(session_factory)
    
    results = []

    # Scenario A: Happy path (Repair Merchant State)
    def setup_happy():
        simulator.seed_merchant_order("ord_A", 500, status="UNPAID")
        simulator.seed_provider_payment("pay_A", "ord_A", 500, status="CAPTURED")
    res_a = await process_scenario(session_factory, worker, "Scenario A - Happy Path", "ord_A", "pay_A", 500, setup_happy, "RESOLVED")
    results.append(res_a)
    
    # Scenario B: Policy Blocked (High Amount)
    def setup_policy():
        simulator.seed_merchant_order("ord_B", 50000, status="UNPAID")
        simulator.seed_provider_payment("pay_B", "ord_B", 50000, status="CAPTURED")
    res_b = await process_scenario(session_factory, worker, "Scenario B - Policy Blocked", "ord_B", "pay_B", 50000, setup_policy, "ESCALATED_POLICY_BLOCKED")
    results.append(res_b)
    
    # Scenario C: Budget Exhausted
    gov_repo = PostgresGovernanceRepository(session_factory)
    budget = ActionBudget(budget_id="budget_repair_merchant_state", target_action="REPAIR_MERCHANT_STATE", period=BudgetPeriod.DAILY, count_limit=0, monetary_limit=0, currency="INR", count_used=0, monetary_used=0)
    gov_repo.save_budget(budget)
    def setup_budget():
        simulator.seed_merchant_order("ord_C", 500, status="UNPAID")
        simulator.seed_provider_payment("pay_C", "ord_C", 500, status="CAPTURED")
    res_c = await process_scenario(session_factory, worker, "Scenario C - Budget Exhausted", "ord_C", "pay_C", 500, setup_budget, "ESCALATED_BUDGET_EXHAUSTED")
    results.append(res_c)
    
    # Restore budget
    budget = ActionBudget(budget_id="budget_repair_merchant_state", target_action="REPAIR_MERCHANT_STATE", period=BudgetPeriod.DAILY, count_limit=10, monetary_limit=100000, currency="INR", count_used=0, monetary_used=0)
    gov_repo.save_budget(budget)

    # Scenario D: Convergence Failure (Timeout)
    def setup_conv():
        simulator.seed_merchant_order("ord_D", 500, status="UNPAID")
        simulator.seed_provider_payment("pay_D", "ord_D", 500, status="CAPTURED")
        simulator.inject_fault("ord_D", "TIMEOUT")
    res_d = await process_scenario(session_factory, worker, "Scenario D - Convergence Failure", "ord_D", "pay_D", 500, setup_conv, "ESCALATED_CONVERGENCE_FAILED")
    results.append(res_d)
    
    # Scenario E: Clean Match
    def setup_match():
        simulator.seed_merchant_order("ord_E", 500, status="PAID")
        simulator.seed_provider_payment("pay_E", "ord_E", 500, status="CAPTURED")
        
    logger.info("--- Running Scenario E: Clean Match ---")
    simulator.reset()
    setup_match()
    exp_repo = PostgresExpectationRepository(session_factory)
    obs_repo = PostgresObservationRepository(session_factory)
    evt_repo = PostgresControlEventRepository(session_factory)
    keys = CorrelationKeys(provider="razorpay", provider_ref="pay_E", internal_ref="ord_E")
    now = datetime.now(timezone.utc)
    exp = Expectation(expectation_id="exp_ord_E", domain="PAYMENT", expected_canonical_status=CanonicalStatus.SETTLED, expected_amount=500, currency="INR", source_system="OMS", business_status=BusinessStatus.OPEN, correlation_keys=keys, created_at=now)
    obs = Observation(observation_id="obs_pay_E", provider="razorpay", provider_reference="pay_E", observation_type="PAYMENT_STATUS", canonical_status=CanonicalStatus.SETTLED, observed_amount=500, currency="INR", evidence_ids=[], correlation_keys=keys, observed_at=now, ingestion_event_id="evt_ord_E")
    exp_repo.save(exp)
    obs_repo.save(obs)
    evt_repo.publish(ControlEventType.OBSERVATION_INGESTED, {"observation_id": obs.observation_id})
    await worker.poll_and_process(limit=5)
    
    inc_repo = PostgresActiveIncidentRepository(session_factory)
    with inc_repo.session_maker() as session:
        record = session.query(ActiveIncidentIdempotencyRecord).filter_by(active_subject="exp_ord_E").first()
        actual_state = record.state.value if record else "NOT_FOUND (MATCH)"
        print(f"[Scenario E] Result: {actual_state} (Expected: NOT_FOUND (MATCH))")
        results.append({
            "name": "Scenario E - Clean Match",
            "expected": "NOT_FOUND (MATCH)",
            "actual": actual_state,
            "llm_used": False
        })
        
    with open("data/e2e_results.json", "w") as f:
        json.dump([
            {"name": r["name"], "expected": r["expected"], "actual": r["actual"], "llm_used": r["llm_used"]}
            for r in results
        ], f, indent=2)

if __name__ == "__main__":
    asyncio.run(run_audits())
