import asyncio
import os
import sys
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

# Add project root to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.evidence.models import Base, ProviderObservation
from src.merchant.models import MerchantOrder
from src.evidence.db import engine as db_engine, AsyncSessionLocal as session_maker
from src.evidence.gatherer import DatabaseEvidenceGatherer
from src.reconciliation.engine import M3Engine
from src.reconciliation.models import ProviderPayment, MerchantOrderState, VerifiedDiscrepancy, DiscrepancyClassification
from src.investigation.config import LLMConfig
from src.investigation.ai import InvestigationEngine
from src.investigation.orchestrator import InvestigationOrchestrator
from src.investigation.models import (
    V0HypothesisType,
    EvidenceItem,
    EvidenceType,
    EvidenceCoverage,
    DiscrepancyContext,
    InvestigationProposal,
    HypothesisSelection,
    ConfidenceBand,
    InvestigationEligibility,
    WebhookCoverageContent,
    ProcessingCoverageContent,
    StateTransitionCoverageContent,
)
from src.investigation.result import InvestigationResult, InvestigationStatus
from src.investigation.semantic import validate_semantic_admissibility
from src.investigation.validator import validate_proposal_invariants

class ScenarioDefinition:
    def __init__(
        self,
        scenario_id: str,
        name: str,
        description: str,
        expected_top_hypothesis: Optional[V0HypothesisType],
        expected_status: InvestigationStatus,
        is_hard_negative_test: bool = False
    ):
        self.scenario_id = scenario_id
        self.name = name
        self.description = description
        self.expected_top_hypothesis = expected_top_hypothesis
        self.expected_status = expected_status
        self.is_hard_negative_test = is_hard_negative_test

async def seed_scenario_db(scenario_id: str, order_id: str, payment_id: str):
    """
    Seeds authoritative database records according to the specific scenario boundary.
    """
    async with session_maker() as session:
        if scenario_id == "SC-01":
            # Webhook Dropped (H1):
            # Payment observed, Merchant order UNPAID.
            # NO webhook rows inserted.
            obs_pay = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_pay_{uuid.uuid4().hex[:8]}",
                event_type="payment",
                payload={"order_id": order_id, "payment_id": payment_id, "amount": 5000, "currency": "INR", "status": "captured", "captured": True}
            )
            merchant_ord = MerchantOrder(
                merchant_order_id=f"mo_{uuid.uuid4().hex[:8]}",
                razorpay_order_id=order_id,
                expected_amount=5000,
                currency="INR",
                status="UNPAID"
            )
            session.add(obs_pay)
            session.add(merchant_ord)

        elif scenario_id == "SC-02":
            # Ingested Not Processed (H2):
            # Payment observed, Webhook received, Merchant order UNPAID, NO processing rows.
            obs_pay = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_pay_{uuid.uuid4().hex[:8]}",
                event_type="payment",
                payload={"order_id": order_id, "payment_id": payment_id, "amount": 5000, "currency": "INR", "status": "captured", "captured": True}
            )
            obs_wh = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_hook_{uuid.uuid4().hex[:8]}",
                event_type="webhook",
                payload={"order_id": order_id, "payment_id": payment_id}
            )
            merchant_ord = MerchantOrder(
                merchant_order_id=f"mo_{uuid.uuid4().hex[:8]}",
                razorpay_order_id=order_id,
                expected_amount=5000,
                currency="INR",
                status="UNPAID"
            )
            session.add(obs_pay)
            session.add(obs_wh)
            session.add(merchant_ord)

        elif scenario_id == "SC-03":
            # Processed State Stale (H3):
            # Payment observed, Webhook received, Processing record PROCESSED, Merchant order UNPAID, NO transition row.
            obs_pay = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_pay_{uuid.uuid4().hex[:8]}",
                event_type="payment",
                payload={"order_id": order_id, "payment_id": payment_id, "amount": 5000, "currency": "INR", "status": "captured", "captured": True}
            )
            obs_wh = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_hook_{uuid.uuid4().hex[:8]}",
                event_type="webhook",
                payload={"order_id": order_id, "payment_id": payment_id}
            )
            obs_proc = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_proc_{uuid.uuid4().hex[:8]}",
                event_type="processing",
                payload={"order_id": order_id, "payment_id": payment_id, "status": "PROCESSED"}
            )
            merchant_ord = MerchantOrder(
                merchant_order_id=f"mo_{uuid.uuid4().hex[:8]}",
                razorpay_order_id=order_id,
                expected_amount=5000,
                currency="INR",
                status="UNPAID"
            )
            session.add(obs_pay)
            session.add(obs_wh)
            session.add(obs_proc)
            session.add(merchant_ord)

        elif scenario_id == "SC-04":
            # Representation Mismatch (H4):
            # Webhook received, Processing PROCESSED, State transition to 'SETTLED', Merchant order reads 'SETTLED'
            # Provider reads 'captured'. Both amounts match.
            obs_pay = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_pay_{uuid.uuid4().hex[:8]}",
                event_type="payment",
                payload={"order_id": order_id, "payment_id": payment_id, "amount": 5000, "currency": "INR", "status": "captured", "captured": True}
            )
            obs_wh = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_hook_{uuid.uuid4().hex[:8]}",
                event_type="webhook",
                payload={"order_id": order_id, "payment_id": payment_id}
            )
            obs_proc = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_proc_{uuid.uuid4().hex[:8]}",
                event_type="processing",
                payload={"order_id": order_id, "payment_id": payment_id, "status": "PROCESSED"}
            )
            obs_st = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_st_{uuid.uuid4().hex[:8]}",
                event_type="state_transition",
                payload={"order_id": order_id, "from_status": "CREATED", "to_status": "SETTLED"}
            )
            merchant_ord = MerchantOrder(
                merchant_order_id=f"mo_{uuid.uuid4().hex[:8]}",
                razorpay_order_id=order_id,
                expected_amount=5000,
                currency="INR",
                status="SETTLED"  # Different representation than 'captured' or 'PAID'
            )
            session.add(obs_pay)
            session.add(obs_wh)
            session.add(obs_proc)
            session.add(obs_st)
            session.add(merchant_ord)

        elif scenario_id == "SC-05":
            # Unknown Ingestion Coverage (H5 Indeterminacy):
            # No webhook row. Merchant order UNPAID.
            obs_pay = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_pay_{uuid.uuid4().hex[:8]}",
                event_type="payment",
                payload={"order_id": order_id, "payment_id": payment_id, "amount": 5000, "currency": "INR", "status": "captured", "captured": True}
            )
            merchant_ord = MerchantOrder(
                merchant_order_id=f"mo_{uuid.uuid4().hex[:8]}",
                razorpay_order_id=order_id,
                expected_amount=5000,
                currency="INR",
                status="UNPAID"
            )
            session.add(obs_pay)
            session.add(merchant_ord)

        elif scenario_id == "SC-06":
            # Epistemic Indeterminacy (H5 Ambiguity):
            # Webhook received, Processing PROCESSED, Merchant order UNPAID.
            # But state transition coverage is not recorded or unknown.
            obs_pay = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_pay_{uuid.uuid4().hex[:8]}",
                event_type="payment",
                payload={"order_id": order_id, "payment_id": payment_id, "amount": 5000, "currency": "INR", "status": "captured", "captured": True}
            )
            obs_wh = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_hook_{uuid.uuid4().hex[:8]}",
                event_type="webhook",
                payload={"order_id": order_id, "payment_id": payment_id}
            )
            obs_proc = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_proc_{uuid.uuid4().hex[:8]}",
                event_type="processing",
                payload={"order_id": order_id, "payment_id": payment_id, "status": "PROCESSED"}
            )
            merchant_ord = MerchantOrder(
                merchant_order_id=f"mo_{uuid.uuid4().hex[:8]}",
                razorpay_order_id=order_id,
                expected_amount=5000,
                currency="INR",
                status="UNPAID"
            )
            session.add(obs_pay)
            session.add(obs_wh)
            session.add(obs_proc)
            session.add(merchant_ord)

        elif scenario_id == "SC-07":
            # Hard Negative Trap (Safety Gate):
            # Webhook received, processing absent.
            obs_pay = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_pay_{uuid.uuid4().hex[:8]}",
                event_type="payment",
                payload={"order_id": order_id, "payment_id": payment_id, "amount": 5000, "currency": "INR", "status": "captured", "captured": True}
            )
            obs_wh = ProviderObservation(
                provider="razorpay",
                event_id=f"evt_hook_{uuid.uuid4().hex[:8]}",
                event_type="webhook",
                payload={"order_id": order_id, "payment_id": payment_id}
            )
            merchant_ord = MerchantOrder(
                merchant_order_id=f"mo_{uuid.uuid4().hex[:8]}",
                razorpay_order_id=order_id,
                expected_amount=5000,
                currency="INR",
                status="UNPAID"
            )
            session.add(obs_pay)
            session.add(obs_wh)
            session.add(merchant_ord)

        await session.commit()

SCENARIOS = [
    ScenarioDefinition(
        scenario_id="SC-01",
        name="Webhook Dropped (H1)",
        description="No webhook observation recorded; Webhook Coverage=COMPLETE (count=0); Merchant order UNPAID.",
        expected_top_hypothesis=V0HypothesisType.WEBHOOK_NOT_OBSERVED,
        expected_status=InvestigationStatus.ACCEPTED
    ),
    ScenarioDefinition(
        scenario_id="SC-02",
        name="Ingested Not Processed (H2)",
        description="Webhook observation exists; Processing count=0 under COMPLETE coverage; Merchant order UNPAID.",
        expected_top_hypothesis=V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED,
        expected_status=InvestigationStatus.ACCEPTED
    ),
    ScenarioDefinition(
        scenario_id="SC-03",
        name="Processed State Stale (H3)",
        description="Webhook observed; Processing record exists (PROCESSED); Transition count=0 under COMPLETE coverage; Merchant order UNPAID.",
        expected_top_hypothesis=V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED,
        expected_status=InvestigationStatus.ACCEPTED
    ),
    ScenarioDefinition(
        scenario_id="SC-04",
        name="Representation Mismatch (H4)",
        description="Provider is 'captured', Merchant order is 'SETTLED', processing complete, amounts match.",
        expected_top_hypothesis=V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH,
        expected_status=InvestigationStatus.ACCEPTED
    ),
    ScenarioDefinition(
        scenario_id="SC-05",
        name="Unknown Ingestion Coverage (H5 Indeterminacy)",
        description="No webhook observation recorded, but Webhook Coverage is UNKNOWN (absence is inconclusive).",
        expected_top_hypothesis=V0HypothesisType.EVIDENCE_INSUFFICIENT,
        expected_status=InvestigationStatus.ACCEPTED
    ),
    ScenarioDefinition(
        scenario_id="SC-06",
        name="Epistemic Indeterminacy (H5 Ambiguity)",
        description="Webhook observed and processed, but state transition coverage is UNKNOWN (cannot determine if transition failed or was delayed).",
        expected_top_hypothesis=V0HypothesisType.EVIDENCE_INSUFFICIENT,
        expected_status=InvestigationStatus.ACCEPTED
    ),
    ScenarioDefinition(
        scenario_id="SC-07",
        name="Hard Negative Trap (Safety Gate)",
        description="Webhook observation is present, but model proposal asserts WEBHOOK_NOT_OBSERVED. Semantic gate must reject.",
        expected_top_hypothesis=V0HypothesisType.WEBHOOK_NOT_OBSERVED,
        expected_status=InvestigationStatus.PROPOSAL_SEMANTIC_CONFLICT,
        is_hard_negative_test=True
    ),
]

async def run_scenario(scenario: ScenarioDefinition, engine: InvestigationEngine, gatherer: DatabaseEvidenceGatherer) -> dict:
    order_id = f"ord_{scenario.scenario_id.lower()}_{uuid.uuid4().hex[:6]}"
    payment_id = f"pay_{scenario.scenario_id.lower()}_{uuid.uuid4().hex[:6]}"
    
    # 1. Seed database state
    await seed_scenario_db(scenario.scenario_id, order_id, payment_id)
    
    # 2. Trigger M3 Deterministic Gate
    merchant_status = "SETTLED" if scenario.scenario_id == "SC-04" else "UNPAID"
    payment = ProviderPayment(
        payment_id=payment_id,
        order_id=order_id,
        amount=5000,
        currency="INR",
        status="captured",
        captured=True,
        observed_at=datetime.now(timezone.utc)
    )
    order = MerchantOrderState(
        merchant_order_id=f"mo_{order_id}",
        razorpay_order_id=order_id,
        expected_amount=5000,
        currency="INR",
        status=merchant_status
    )
    m3 = M3Engine()
    try:
        discrepancy = m3.evaluate_reconciliation(payment, order)
    except ValueError:
        # Expected for non-standard representation status (e.g. 'SETTLED')
        discrepancy = None

    if not discrepancy:
        # Synthesize the VerifiedDiscrepancy context for M4 investigation
        discrepancy = VerifiedDiscrepancy(
            discrepancy_id=f"disc_{order_id}",
            payment_id=payment_id,
            order_id=order_id,
            description=f"Reconciliation discrepancy for {scenario.name}",
            provider_status="captured",
            merchant_status=merchant_status,
            amount_match=True,
            currency_match=True,
            identity_verified=True
        )

    # 3. Gather Evidence
    evidence_packet = await gatherer.gather(discrepancy)
    
    # Apply scenario-specific coverage tweaks for epistemic testing
    if scenario.scenario_id == "SC-05":
        # Override webhook coverage to UNKNOWN to test epistemic absence handling
        for ev in evidence_packet.items:
            if ev.type == EvidenceType.E_WEBHOOK_COVERAGE:
                ev.content = WebhookCoverageContent(coverage=EvidenceCoverage.UNKNOWN, webhook_count=0)

    if scenario.scenario_id == "SC-06":
        # Override state transition coverage to UNKNOWN to test epistemic ambiguity
        for ev in evidence_packet.items:
            if ev.type == EvidenceType.E_STATE_TRANSITION_COVERAGE:
                ev.content = StateTransitionCoverageContent(coverage=EvidenceCoverage.UNKNOWN, transition_count=0)

    # 4. Model Inference & Validation
    if scenario.is_hard_negative_test:
        # Inject a deliberately contradictory proposal (asserts WEBHOOK_NOT_OBSERVED despite webhook present)
        contradictory_selections = [
            HypothesisSelection(
                hypothesis_id=V0HypothesisType.WEBHOOK_NOT_OBSERVED,
                rank=1,
                rationale="Simulated hallucinatory proposal to test deterministic rejection boundary.",
                confidence_band=ConfidenceBand.HIGH,
                supporting_evidence_ids=[]
            ),
            HypothesisSelection(hypothesis_id=V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED, rank=2, rationale="", confidence_band=ConfidenceBand.LOW),
            HypothesisSelection(hypothesis_id=V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED, rank=3, rationale="", confidence_band=ConfidenceBand.LOW),
            HypothesisSelection(hypothesis_id=V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH, rank=4, rationale="", confidence_band=ConfidenceBand.LOW),
            HypothesisSelection(hypothesis_id=V0HypothesisType.EVIDENCE_INSUFFICIENT, rank=5, rationale="", confidence_band=ConfidenceBand.LOW),
        ]
        proposal = InvestigationProposal(
            eligibility=InvestigationEligibility.ELIGIBLE,
            overall_confidence=ConfidenceBand.HIGH,
            selections=contradictory_selections
        )
        
        # Test deterministic admissibility gate directly
        sem_res = validate_semantic_admissibility(proposal, evidence_packet.items)
        if not sem_res.is_admissible:
            result = InvestigationResult(
                status=InvestigationStatus.PROPOSAL_SEMANTIC_CONFLICT,
                proposal=proposal,
                validation_errors=sem_res.errors,
                failure_reason=f"PROPOSAL_SEMANTIC_CONFLICT: {sem_res.errors[0]}"
            )
        else:
            result = InvestigationResult(
                status=InvestigationStatus.ACCEPTED,
                proposal=proposal
            )
    else:
        orchestrator = InvestigationOrchestrator(engine, gatherer)
        context = DiscrepancyContext(
            case_id=discrepancy.discrepancy_id,
            description=discrepancy.description,
            provider_status=discrepancy.provider_status,
            merchant_status=discrepancy.merchant_status,
            amount_match=discrepancy.amount_match,
            currency_match=discrepancy.currency_match,
            identity_verified=discrepancy.identity_verified
        )
        result = await engine.investigate(context, evidence_packet.items)
        
        # Run semantic validation if engine produced accepted proposal
        if result.status == InvestigationStatus.ACCEPTED and result.proposal:
            sem_res = validate_semantic_admissibility(result.proposal, evidence_packet.items)
            if not sem_res.is_admissible:
                result = InvestigationResult(
                    status=InvestigationStatus.PROPOSAL_SEMANTIC_CONFLICT,
                    proposal=result.proposal,
                    validation_errors=sem_res.errors,
                    failure_reason=f"PROPOSAL_SEMANTIC_CONFLICT: {sem_res.errors[0]}"
                )

    # 5. Extract Details for Report
    top_hyp = None
    rationale = None
    if result.proposal:
        top_sel = next((s for s in result.proposal.selections if s.rank == 1), None)
        if top_sel:
            top_hyp = top_sel.hypothesis_id
            rationale = top_sel.rationale

    status_pass = (result.status == scenario.expected_status)
    hyp_pass = (top_hyp == scenario.expected_top_hypothesis) if scenario.expected_top_hypothesis else True
    overall_pass = status_pass and (hyp_pass or scenario.is_hard_negative_test)

    return {
        "scenario_id": scenario.scenario_id,
        "name": scenario.name,
        "evidence_count": len(evidence_packet.items),
        "evidence_ids": [ev.id for ev in evidence_packet.items],
        "model_top_hypothesis": top_hyp.value if top_hyp else "N/A",
        "expected_hypothesis": scenario.expected_top_hypothesis.value if scenario.expected_top_hypothesis else "N/A",
        "rationale": rationale,
        "status": result.status.value,
        "expected_status": scenario.expected_status.value,
        "failure_reason": result.failure_reason,
        "status_pass": status_pass,
        "hyp_pass": hyp_pass,
        "overall_pass": overall_pass,
    }

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Financial Control Engine Scenario Validation")
    parser.add_argument("--model", type=str, default="phi4-mini:3.8b-q4_K_M", help="Model name in Ollama")
    parser.add_argument("--scenarios", type=str, default="", help="Comma-separated list of scenario IDs to run (e.g. SC-03,SC-06)")
    args = parser.parse_args()

    print("=" * 80)
    print(f"FINANCIAL CONTROL ENGINE — SCENARIO VALIDATION HARNESS (Model: {args.model})")
    print("=" * 80)

    config = LLMConfig(
        model_name=args.model,
        base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1"),
        api_key="ollama",
        temperature=0.0
    )
    engine = InvestigationEngine(config)
    gatherer = DatabaseEvidenceGatherer(session_maker)

    target_scenarios = SCENARIOS
    if args.scenarios:
        target_ids = [s.strip() for s in args.scenarios.split(",")]
        target_scenarios = [sc for sc in SCENARIOS if sc.scenario_id in target_ids]

    results = []
    for sc in target_scenarios:
        print(f"\n▶ Running [{sc.scenario_id}] {sc.name}...")
        res = await run_scenario(sc, engine, gatherer)
        results.append(res)
        
        status_icon = "✅" if res["overall_pass"] else "❌"
        print(f"  {status_icon} Result: Status={res['status']} | Model Top={res['model_top_hypothesis']} (Expected={res['expected_hypothesis']})")
        if res["rationale"]:
            print(f"     Rationale: {res['rationale']}")
        if res["failure_reason"]:
            print(f"     Safety Gate: {res['failure_reason']}")

    await engine.client.close()

    # Summary Matrix Table
    print("\n" + "=" * 100)
    print(f"{'ID':<7} | {'Scenario Name':<35} | {'Model Top Hyp':<35} | {'Status':<25} | {'Outcome'}")
    print("-" * 100)
    for r in results:
        outcome = "PASS ✅" if r["overall_pass"] else "FAIL ❌"
        print(f"{r['scenario_id']:<7} | {r['name']:<35} | {r['model_top_hypothesis']:<35} | {r['status']:<25} | {outcome}")
    print("=" * 100)

if __name__ == "__main__":
    asyncio.run(main())
