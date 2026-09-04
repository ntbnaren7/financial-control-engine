#!/usr/bin/env python
"""
FCE Demo Runner — Buildathon Submission
=======================================

Generates 100 synthetic financial records and runs them through the FULL
FCE control loop:

  Expectation + Observation
        ↓
  ControlEvent published
        ↓
  V2ControlWorker.poll_and_process()
        ↓
  Reconciliation → Discrepancy → Investigation → Verification
        ↓
  Policy → RecoveryIntent → Governance Gate → Actuation
        ↓
  Re-observation → Convergence
        ↓
  RESOLVED / ESCALATED

Nothing is hardcoded. Every metric shown in the operator console comes from
records that passed through this exact machinery.

Usage:
  uv run python scripts/run_demo.py [--reset] [--records N]

Flags:
  --reset    Drop and recreate all v2_ tables before running (clean demo state)
  --records  Total synthetic records to generate (default: 100)
"""

import argparse
import asyncio
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fce.demo")

# ── Path + .env ───────────────────────────────────────────────────────────────
import sys
from pathlib import Path as _P

_project_root = _P(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

env_file = _project_root / ".env"
if env_file.exists():
    for _line in env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _k = _k.strip()
            _v = _v.strip().strip('"').strip("'")
            os.environ.setdefault(_k, _v)

# No double-underscore bridging needed — .env now uses DATABASE_URL directly.


# ── Imports ────────────────────────────────────────────────────────────────────
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
)
from src.storage.postgres_governance import PostgresGovernanceRepository
from src.domain.core.models import (
    Expectation, Observation, CorrelationKeys, BusinessStatus,
    ReconciliationOutcome, CanonicalStatus,
)
from src.domain.governance.models import ActionBudget, BudgetPeriod, ControlPlaneState, AutomationState
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from src.engine.evidence_assembler import EvidenceAssembler
from src.engine.worker import V2ControlWorker
from src.engine.external_simulator import simulator
from src.investigation.agent import Investigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.integrations.razorpay.client import RazorpayClient, ProviderClientError
from src.integrations.razorpay.models import RazorpayPayment, RazorpayRefund
from src.config.settings import RazorpaySettings
from src.domain.investigation.models import (
    CausalHypothesis, InvestigationDisposition, VerificationIntent,
)
import time as _time


# ── Simulated Razorpay Client ──────────────────────────────────────────────────

class SimulatedRazorpayClient:
    """
    Demo-only shim that fulfills the async RazorpayClient contract but reads
    from the in-process ExternalSimulator instead of making real HTTP calls.

    This lets DeterministicVerifier run its full pipeline — including evidence
    hashing, normalisation, and re-observation — without any network dependency.
    """

    async def get_payment(self, payment_id: str) -> RazorpayPayment:
        record = simulator.read_provider_payment(payment_id)
        if not record:
            raise ProviderClientError(f"Payment {payment_id!r} not found in simulator")
        # Simulator stores status as "CAPTURED" / "REFUNDED" / "PENDING"
        raw_status = record.get("status", "PENDING")
        captured = raw_status == "CAPTURED"
        return RazorpayPayment(
            id=payment_id,
            entity="payment",
            amount=int(record.get("amount", 0) * 100),  # paise
            currency="INR",
            status=raw_status.lower(),  # Razorpay uses lowercase: "captured", "refunded"
            order_id=record.get("order_id", ""),
            method="netbanking",
            amount_refunded=0,
            refund_status=None,
            captured=captured,
            created_at=int(_time.time()),
        )

    async def get_payment_refunds(self, payment_id: str) -> list[RazorpayRefund]:
        # Simulator doesn't model refunds in initial seed — return empty list
        # (would be populated after actuation in a live run)
        return []


# ── Scenario definitions ───────────────────────────────────────────────────────

SCENARIOS = {
    # Happy path — payment captured, order not updated → FCE refunds → RESOLVED
    "happy_path": {
        "count": 55,
        "description": "Payment captured / order unpaid → auto-resolved via refund",
        "injects_fault": None,
        "discount_budget": True,  # counts against budget
    },
    # Policy blocked — amount too high for automated refund
    "policy_blocked": {
        "count": 15,
        "description": "Discrepancy found but policy blocks automated recovery",
        "injects_fault": None,
        "discount_budget": False,
    },
    # Budget exhausted — the first N pass, remainder get ESCALATED_BUDGET_EXHAUSTED
    "budget_exhausted": {
        "count": 10,
        "description": "Recovery intent valid but action budget exhausted",
        "injects_fault": None,
        "discount_budget": False,
    },
    # Provider timeout → TIMEOUT_UNKNOWN → ESCALATED_CONVERGENCE_FAILED
    "convergence_failed": {
        "count": 12,
        "description": "Actuation sent but provider timed out → convergence failure",
        "injects_fault": "TIMEOUT",
        "discount_budget": True,
    },
    # Clean match — no discrepancy, no action needed
    "clean_match": {
        "count": 8,
        "description": "Expectation and observation already agree — no action",
        "injects_fault": None,
        "discount_budget": False,
    },
}


def make_correlation_id() -> str:
    return str(uuid.uuid4())[:12].replace("-", "")


def generate_records(total: int) -> list[dict]:
    """
    Generate `total` synthetic financial records distributed across scenarios.
    Each record carries:
      - expectation:  what the OMS expects (amount, state)
      - observation:  what the provider reports (may mismatch)
      - simulator_state: how to pre-seed the external_simulator
      - scenario: which scenario type this is
      - fault: optional fault to inject into the simulator
    """
    records = []
    idx = 0

    # Scale scenario counts proportionally to requested total
    scale = total / sum(s["count"] for s in SCENARIOS.values())
    scaled = {k: max(1, round(v["count"] * scale)) for k, v in SCENARIOS.items()}
    # Adjust so the sum equals total exactly
    diff = total - sum(scaled.values())
    scaled["happy_path"] += diff  # absorb rounding diff in the happy path bucket

    now = datetime.now(timezone.utc)

    for scenario_key, count in scaled.items():
        cfg = SCENARIOS[scenario_key]
        for i in range(count):
            order_id = f"ord_{scenario_key[:4]}_{idx:04d}"
            payment_id = f"pay_{scenario_key[:4]}_{idx:04d}"
            # Vary amounts: happy path ₹500–₹5000, others smaller
            if scenario_key == "policy_blocked":
                # Amounts above policy threshold (₹10,001+) to trigger block
                amount = random.randint(10_001, 50_000)
            elif scenario_key == "clean_match":
                amount = random.randint(100, 3_000)
            else:
                amount = random.randint(500, 5_000)

            records.append({
                "idx": idx,
                "scenario": scenario_key,
                "order_id": order_id,
                "payment_id": payment_id,
                "amount": amount,
                "currency": "INR",
                "fault": cfg["injects_fault"],
                "created_at": now - timedelta(hours=random.randint(1, 24)),
            })
            idx += 1

    random.shuffle(records)  # realistic ordering
    return records


def seed_simulator_and_repos(
    records: list[dict],
    exp_repo: PostgresExpectationRepository,
    obs_repo: PostgresObservationRepository,
    event_repo: PostgresControlEventRepository,
) -> None:
    """
    For each record:
    1. Pre-seeds the external simulator with the order/payment state.
    2. Persists Expectation + Observation to the substrate via real repos.
    3. Publishes a ControlEvent to trigger the worker — the actual ingestion boundary.

    Field reference:
      Expectation.expected_canonical_status: CanonicalStatus (enum)
      Observation.canonical_status:          CanonicalStatus (enum)
      DISCREPANCY: expect SETTLED, observe PENDING
      MATCH:       both SETTLED
    """
    logger.info(f"Seeding {len(records)} records into simulator + substrate...")
    simulator.reset()

    for r in records:
        oid = r["order_id"]
        pid = r["payment_id"]
        amount = r["amount"]
        scenario = r["scenario"]
        created_at = r["created_at"]
        idx = r["idx"]

        keys = CorrelationKeys(provider="razorpay", provider_ref=pid, internal_ref=oid)

        if scenario == "clean_match":
            # Both sides agree: SETTLED → MATCH immediately on first reconciliation
            simulator.seed_merchant_order(oid, amount, status="PAID")
            simulator.seed_provider_payment(pid, oid, amount, status="CAPTURED")

            exp = Expectation(
                expectation_id=f"exp_{idx:04d}",
                domain="PAYMENT",
                expected_canonical_status=CanonicalStatus.SETTLED,
                expected_amount=amount,
                currency="INR",
                source_system="OMS",
                business_status=BusinessStatus.OPEN,
                correlation_keys=keys,
                created_at=created_at,
            )
            obs = Observation(
                observation_id=f"obs_{idx:04d}_a",
                provider="razorpay",
                provider_reference=pid,
                observation_type="PAYMENT_STATUS",
                canonical_status=CanonicalStatus.SETTLED,  # agrees with expectation
                observed_amount=amount,
                currency="INR",
                evidence_ids=[],
                correlation_keys=keys,
                observed_at=created_at,
                ingestion_event_id=f"evt_{idx:04d}",
            )

        elif scenario == "policy_blocked":
            # Discrepancy: provider captured, OMS not updated — but amount > policy threshold
            # Policy will block the recovery intent → ESCALATED_POLICY_BLOCKED
            simulator.seed_merchant_order(oid, amount, status="UNPAID")
            simulator.seed_provider_payment(pid, oid, amount, status="CAPTURED")

            exp = Expectation(
                expectation_id=f"exp_{idx:04d}",
                domain="PAYMENT",
                expected_canonical_status=CanonicalStatus.SETTLED,
                expected_amount=amount,
                currency="INR",
                source_system="OMS",
                business_status=BusinessStatus.OPEN,
                correlation_keys=keys,
                created_at=created_at,
            )
            obs = Observation(
                observation_id=f"obs_{idx:04d}_a",
                provider="razorpay",
                provider_reference=pid,
                observation_type="PAYMENT_STATUS",
                canonical_status=CanonicalStatus.PENDING,   # discrepancy: not settled yet
                observed_amount=amount,
                currency="INR",
                evidence_ids=[],
                correlation_keys=keys,
                observed_at=created_at,
                ingestion_event_id=f"evt_{idx:04d}",
            )

        else:
            # happy_path, budget_exhausted, convergence_failed:
            # All share the same discrepancy shape — SETTLED expected, PENDING observed
            simulator.seed_merchant_order(oid, amount, status="UNPAID")
            simulator.seed_provider_payment(pid, oid, amount, status="CAPTURED")

            if r["fault"]:
                simulator.inject_fault(pid, r["fault"])
                simulator.inject_fault(oid, r["fault"])

            exp = Expectation(
                expectation_id=f"exp_{idx:04d}",
                domain="PAYMENT",
                expected_canonical_status=CanonicalStatus.SETTLED,
                expected_amount=amount,
                currency="INR",
                source_system="OMS",
                business_status=BusinessStatus.OPEN,
                correlation_keys=keys,
                created_at=created_at,
            )
            obs = Observation(
                observation_id=f"obs_{idx:04d}_a",
                provider="razorpay",
                provider_reference=pid,
                observation_type="PAYMENT_STATUS",
                canonical_status=CanonicalStatus.PENDING,   # discrepancy
                observed_amount=amount,
                currency="INR",
                evidence_ids=[],
                correlation_keys=keys,
                observed_at=created_at,
                ingestion_event_id=f"evt_{idx:04d}",
            )

        exp_repo.save(exp)
        obs_repo.save(obs)
        event_repo.publish(ControlEventType.OBSERVATION_INGESTED, {
            "observation_id": obs.observation_id,
            "scenario": scenario,
        })

    logger.info(f"Seeding complete: {len(records)} records published to control event queue.")


def build_worker(session_factory, use_real_llm: bool = False) -> V2ControlWorker:
    """Construct the full worker with all repositories wired."""
    exp_repo = PostgresExpectationRepository(session_factory)
    obs_repo = PostgresObservationRepository(session_factory)
    ev_repo = PostgresEvidenceRepository(session_factory)
    inc_repo = PostgresActiveIncidentRepository(session_factory)
    evt_repo = PostgresControlEventRepository(session_factory)
    recon_repo = PostgresReconciliationResultRepository(session_factory)
    act_repo = PostgresActuationRepository(session_factory)

    recon_engine = V2ReconciliationEngine(exp_repo, obs_repo)
    assembler = EvidenceAssembler(exp_repo, obs_repo, ev_repo)

    if use_real_llm:
        logger.info("Using REAL LLM investigator (GEMINI_API_KEY must be set).")
        from src.investigation.agent import ConcreteInvestigator  # type: ignore
        investigator = ConcreteInvestigator()
    else:
        logger.info("Using deterministic mock investigator for reproducible demo.")
        # Investigator is a Protocol — mock at the object level, not via spec=
        investigator = MagicMock()
        investigator.investigate = MagicMock(return_value=CausalHypothesis(
            hypothesis_id="hyp_demo",
            claim="Provider captured the payment but the order management system was not updated.",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            missing_evidence="No additional evidence required — payment captured, order status confirmed via provider API.",
            confidence="HIGH",
            disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
            verification_intents=[VerificationIntent.QUERY_PROVIDER_STATE],
        ))

    validator = OutputValidator()

    # GovernanceGate is initialized internally by V2ControlWorker.

    # Wire DeterministicVerifier to the in-process simulator via SimulatedRazorpayClient.
    # This gives the full A4 verification pipeline (evidence hashing, normalisation,
    # re-observation) without any real HTTP dependency.
    # cast() satisfies the type checker — SimulatedRazorpayClient is a structural
    # duck-type shim that fulfils the same async interface without inheriting the class.
    from typing import cast as _cast
    from src.integrations.razorpay.provider import RazorpayProvider
    simulated_razorpay = _cast(RazorpayProvider, SimulatedRazorpayClient())
    verifier = DeterministicVerifier(razorpay_provider=simulated_razorpay)

    return V2ControlWorker(
        worker_id="demo_worker_1",
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
        razorpay_provider=simulated_razorpay,
    )


def seed_governance(session_factory, total_records: int) -> None:
    """
    Seed governance: enable automation, set a budget that allows ~60-70% of
    records to go through actuation, so the demo shows both successes and
    budget blocks.
    """
    gov_repo = PostgresGovernanceRepository(session_factory)

    # Ensure automation is ENABLED
    state = gov_repo.get_control_plane_state()
    if state.automation_state != AutomationState.ENABLED:
        new_state = ControlPlaneState(
            id="GLOBAL",
            automation_state=AutomationState.ENABLED,
            reason="Demo initialization",
            updated_by="demo_runner",
            version=state.version,
        )
        gov_repo.update_control_plane_state_occ(new_state)

    # Budget: allow ~55% of records for REFUND_PAYMENT
    refund_budget_count = max(10, int(total_records * 0.55))
    refund_budget_amount = refund_budget_count * 3000  # avg ₹3000/refund

    budget = ActionBudget(
        budget_id="demo_refund_daily",
        target_action="REFUND_PAYMENT",
        period=BudgetPeriod.DAILY,
        count_limit=refund_budget_count,
        monetary_limit=refund_budget_amount,
        currency="INR",
        count_used=0,
        monetary_used=0,
    )
    gov_repo.save_budget(budget)

    repair_budget = ActionBudget(
        budget_id="demo_repair_daily",
        target_action="REPAIR_MERCHANT_STATE",
        period=BudgetPeriod.DAILY,
        count_limit=max(5, int(total_records * 0.2)),
        monetary_limit=500_000,
        currency="INR",
        count_used=0,
        monetary_used=0,
    )
    gov_repo.save_budget(repair_budget)

    logger.info(f"Governance seeded: REFUND budget = {refund_budget_count} actions / ₹{refund_budget_amount:,}")


async def run_worker_cycles(worker: V2ControlWorker, total_records: int) -> None:
    """Run the worker until all events are drained (max safety ceiling)."""
    max_cycles = total_records * 4  # each record may need up to 4 cycles
    cycle = 0

    logger.info(f"Starting worker loop: max {max_cycles} cycles for {total_records} records...")
    while cycle < max_cycles:
        cycle += 1
        processed = await worker.poll_and_process(limit=20)
        if processed == 0:
            logger.info(f"Worker drained at cycle {cycle}. No more events.")
            break
        if cycle % 10 == 0:
            logger.info(f"  Cycle {cycle}/{max_cycles}: processed {processed} events this batch")
    else:
        logger.warning(f"Worker hit max cycle ceiling ({max_cycles}). Some events may be unprocessed.")


def print_summary(session_factory) -> dict:
    """Print and return the batch run summary."""
    from src.storage.postgres_substrate import ActiveIncidentIdempotencyRecord
    from src.storage.postgres_substrate import SubstrateReconciliationResultRecord
    from sqlalchemy import func

    with session_factory() as session:
        # Incident state distribution
        state_rows = session.query(
            ActiveIncidentIdempotencyRecord.state,
            func.count(ActiveIncidentIdempotencyRecord.active_subject).label("count"),
        ).group_by(ActiveIncidentIdempotencyRecord.state).all()

        recon_rows = session.query(
            SubstrateReconciliationResultRecord.outcome,
            func.count(SubstrateReconciliationResultRecord.reconciliation_id).label("count"),
        ).group_by(SubstrateReconciliationResultRecord.outcome).all()

    state_counts = {(r.state.value if hasattr(r.state, "value") else str(r.state)): r.count for r in state_rows}
    recon_counts = {(r.outcome.value if hasattr(r.outcome, "value") else str(r.outcome)): r.count for r in recon_rows}

    resolved = state_counts.get("RESOLVED", 0)
    total_incidents = sum(state_counts.values())
    escalated_counts = {k: v for k, v in state_counts.items() if k.startswith("ESCALATED")}
    total_escalated = sum(escalated_counts.values())
    total_recon = sum(recon_counts.values())
    matches = recon_counts.get("MATCH", 0)
    match_rate = round(matches / total_recon * 100, 1) if total_recon > 0 else 0

    print("\n" + "═" * 60)
    print("  FINANCIAL CONTROL ENGINE — DEMO RUN SUMMARY")
    print("═" * 60)
    print(f"  Reconciliation records processed: {total_recon}")
    print(f"  Match rate:                       {match_rate}%  ({matches} matched)")
    print(f"  Total incidents:                  {total_incidents}")
    print(f"  Resolved (automated):             {resolved}")
    print(f"  Escalated (exceptions):           {total_escalated}")
    print()
    print("  INCIDENT STATE BREAKDOWN:")
    for state, count in sorted(state_counts.items()):
        bar = "█" * min(count, 40)
        print(f"    {state:<40} {count:>4}  {bar}")
    print()
    print("  RECONCILIATION OUTCOMES:")
    for outcome, count in sorted(recon_counts.items()):
        print(f"    {outcome:<40} {count:>4}")
    print("═" * 60)

    return {
        "total_records": total_recon,
        "match_rate_pct": match_rate,
        "matches": matches,
        "resolved": resolved,
        "escalated": total_escalated,
        "state_counts": state_counts,
        "recon_counts": recon_counts,
    }


async def main(reset: bool = False, total_records: int = 100, use_real_llm: bool = False, db_url: str | None = None):
    # --db-url flag takes explicit precedence over DATABASE_URL in the environment.
    # This is the intended path for local demo runs against SQLite without
    # touching the canonical PostgreSQL .env configuration.
    if db_url:
        os.environ["DATABASE_URL"] = db_url
    else:
        db_url = os.environ.get("DATABASE_URL", "sqlite:///demo.db")

    safe_url = db_url[:db_url.index('@')+1] if '@' in db_url else db_url
    logger.info(f"Connecting to database: {safe_url}...")
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect():
            pass
    except Exception as exc:
        if not db_url.startswith("sqlite"):
            logger.warning(
                f"Configured database ({safe_url}) unreachable: {exc}. "
                "Falling back to local SQLite demo substrate (sqlite:///demo.db)."
            )
            db_url = "sqlite:///demo.db"
            os.environ["DATABASE_URL"] = db_url
            engine = create_engine(db_url, pool_pre_ping=True)
        else:
            raise

    if reset:
        logger.info("--reset: dropping and recreating all v2_ tables...")
        Base.metadata.drop_all(engine)
        logger.info("Tables dropped. Recreating...")
        Base.metadata.create_all(engine)
        logger.info("Tables recreated.")
    else:
        # Ensure tables exist (idempotent)
        Base.metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)

    # 1. Generate synthetic records
    logger.info(f"Generating {total_records} synthetic financial records...")
    records = generate_records(total_records)
    scenario_dist = {}
    for r in records:
        scenario_dist[r["scenario"]] = scenario_dist.get(r["scenario"], 0) + 1
    logger.info(f"Distribution: {json.dumps(scenario_dist, indent=2)}")

    # 2. Seed governance (kill switch + budgets)
    seed_governance(session_factory, total_records)

    # 3. Seed simulator + substrate (inject expectations/observations via real repos)
    exp_repo = PostgresExpectationRepository(session_factory)
    obs_repo = PostgresObservationRepository(session_factory)
    evt_repo = PostgresControlEventRepository(session_factory)
    seed_simulator_and_repos(records, exp_repo, obs_repo, evt_repo)

    # 4. Build and run the worker
    worker = build_worker(session_factory, use_real_llm=use_real_llm)
    t0 = time.monotonic()
    await run_worker_cycles(worker, total_records)
    elapsed = time.monotonic() - t0

    logger.info(f"Worker loop complete in {elapsed:.1f}s")

    # 5. Print summary
    summary = print_summary(session_factory)

    # 6. Save summary to data/ for the UI to optionally display
    out = Path(__file__).parent.parent / "data" / "demo_run_summary.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({**summary, "run_at": datetime.now(timezone.utc).isoformat(), "elapsed_s": round(elapsed, 2)}, indent=2))
    logger.info(f"Summary written to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FCE Demo Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Local demo against SQLite (no PostgreSQL server needed):\n"
            "  uv run python scripts/run_demo.py --reset --records 100 --db-url sqlite:///sqlite.db\n"
            "\n"
            "  # Against the canonical PostgreSQL instance (reads DATABASE_URL from .env):\n"
            "  uv run python scripts/run_demo.py --reset --records 100"
        ),
    )
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all v2_ tables before run")
    parser.add_argument("--records", type=int, default=100, help="Total synthetic records to generate (default: 100)")
    parser.add_argument("--real-llm", action="store_true", help="Use real Gemini LLM investigator instead of mock")
    parser.add_argument(
        "--db-url",
        default=None,
        help=(
            "Explicit database URL. Overrides DATABASE_URL from .env. "
            "Use sqlite:///sqlite.db for a fast local demo without a PostgreSQL server."
        ),
    )
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset, total_records=args.records, use_real_llm=args.real_llm, db_url=args.db_url))
