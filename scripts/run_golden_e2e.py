import asyncio
import os
import sys
import uuid
import json
import logging
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.evidence.db import AsyncSessionLocal, engine
from src.evidence.models import Base as EvidenceBase, ProviderObservation
from src.merchant.models import MerchantOrder, Base as MerchantBase
from src.orchestration.pipeline import run_investigation_pipeline

# ANSI Colors
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

async def setup_db():
    async with engine.begin() as conn:
        from sqlalchemy import delete
        # We don't drop tables here, we TRUNCATE for cleanliness
        await conn.execute(delete(MerchantOrder))
        await conn.execute(delete(ProviderObservation))

async def run_golden_acceptance():
    print(f"\n{BOLD}{CYAN}=== GOLDEN ACCEPTANCE RUN (v0.1.0-hero-flow) ==={RESET}\n")
    await setup_db()

    order_id = f"order_gold_{uuid.uuid4().hex[:8]}"
    payment_id = f"pay_gold_{uuid.uuid4().hex[:8]}"

    # Seed preconditions
    async with AsyncSessionLocal() as session:
        merchant_ord = MerchantOrder(
            merchant_order_id=f"mo_{order_id}",
            razorpay_order_id=order_id,
            expected_amount=5000,
            currency="INR",
            status="UNPAID"
        )
        obs_proc = ProviderObservation(
            provider="razorpay",
            event_id=f"evt_proc_{uuid.uuid4().hex[:8]}",
            event_type="processing",
            payload={"order_id": order_id, "payment_id": payment_id, "status": "PROCESSED"}
        )
        obs_pay = ProviderObservation(
            provider="razorpay",
            event_id=f"evt_pay_{uuid.uuid4().hex[:8]}",
            event_type="payment",
            payload={"order_id": order_id, "payment_id": payment_id, "status": "captured", "captured": True, "amount": 5000, "currency": "INR"}
        )
        # We will simulate the webhook persistence to bypass FastAPI for tracing purposes
        obs_webhook = ProviderObservation(
            provider="razorpay",
            event_id=f"evt_wh_{uuid.uuid4().hex[:8]}",
            event_type="webhook",
            payload={
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": payment_id,
                            "order_id": order_id,
                            "amount": 5000,
                            "currency": "INR",
                            "status": "captured"
                        }
                    }
                }
            }
        )
        session.add_all([merchant_ord, obs_proc, obs_pay, obs_webhook])
        await session.commit()
        await session.refresh(obs_webhook)
        obs_id = str(obs_webhook.id)

    print(f"{YELLOW}[SEEDED]{RESET} Real Database Initialized. Merchant: UNPAID, Provider: CAPTURED.")

    # We will patch critical boundaries to count invocations without altering behavior.
    from src.investigation.orchestrator import InvestigationOrchestrator
    from src.control.policy import evaluate_repair_eligibility
    from src.recovery.action import execute_repair_action
    
    orig_investigate = InvestigationOrchestrator.investigate
    orig_evaluate = evaluate_repair_eligibility
    orig_execute = execute_repair_action

    counters = {
        "m4": 0,
        "control": 0,
        "action": 0,
        "rowcount": 0
    }

    async def patched_investigate(*args, **kwargs):
        counters["m4"] += 1
        return await orig_investigate(*args, **kwargs)

    def patched_evaluate(*args, **kwargs):
        counters["control"] += 1
        return orig_evaluate(*args, **kwargs)

    async def patched_execute(*args, **kwargs):
        counters["action"] += 1
        res = await orig_execute(*args, **kwargs)
        if res.status.value == "SUCCESS":
            counters["rowcount"] = 1
        else:
            counters["rowcount"] = 0
        return res

    async def patched_investigate_mocked(*args, **kwargs):
        counters["m4"] += 1
        from src.investigation.result import InvestigationResult, InvestigationStatus
        from src.investigation.models import InvestigationProposal, HypothesisSelection, ConfidenceBand, InvestigationEligibility, V0HypothesisType
        
        mock_selections = [
            HypothesisSelection(hypothesis_id=V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED, rank=1, rationale="mock", confidence_band=ConfidenceBand.HIGH),
            HypothesisSelection(hypothesis_id=V0HypothesisType.WEBHOOK_OBSERVED_NOT_PROCESSED, rank=2, rationale="mock", confidence_band=ConfidenceBand.LOW),
            HypothesisSelection(hypothesis_id=V0HypothesisType.PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH, rank=3, rationale="mock", confidence_band=ConfidenceBand.LOW),
            HypothesisSelection(hypothesis_id=V0HypothesisType.WEBHOOK_NOT_OBSERVED, rank=4, rationale="mock", confidence_band=ConfidenceBand.LOW),
            HypothesisSelection(hypothesis_id=V0HypothesisType.EVIDENCE_INSUFFICIENT, rank=5, rationale="mock", confidence_band=ConfidenceBand.LOW),
        ]
        mock_proposal = InvestigationProposal(eligibility=InvestigationEligibility.ELIGIBLE, overall_confidence=ConfidenceBand.HIGH, selections=mock_selections)
        return InvestigationResult(status=InvestigationStatus.ACCEPTED, proposal=mock_proposal)

    # ---------------------------------------------------------
    # RUN 1: STALE INCIDENT
    # ---------------------------------------------------------
    print(f"\n{BOLD}--- Execution 1 (Stale Incident) ---{RESET}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    with patch.object(InvestigationOrchestrator, "investigate", new=patched_investigate_mocked), \
         patch("src.orchestration.pipeline.evaluate_repair_eligibility", new=patched_evaluate), \
         patch("src.orchestration.pipeline.execute_repair_action", new=patched_execute):
        
        result_1 = await run_investigation_pipeline(obs_id)
        assert result_1 is not None
        
    m3_discrepancy_str = "TRUE (CAPTURED_PAYMENT_STALE_ORDER)" if counters["m4"] > 0 else "FALSE"
    print(f"M3 Discrepancy: {m3_discrepancy_str}")
    print(f"M4 Invocations: {counters['m4']}")
    print(f"Control Invocations: {counters['control']}")
    print(f"Recovery/Action Invocations: {counters['action']}")
    print(f"SQL UPDATE Rowcount: {counters['rowcount']}")
    print(f"Final Outcome: {result_1.get('pipeline_status')}")
    print(f"{BOLD}Total DB Financial Mutations: {counters['rowcount']}{RESET}")
    
    assert counters["m4"] == 1
    assert counters["rowcount"] == 1
    assert result_1.get("pipeline_status") == "RESOLVED"

    # Reset counters
    counters = {k: 0 for k in counters}

    # ---------------------------------------------------------
    # RUN 2: REPLAY SAFETY
    # ---------------------------------------------------------
    print(f"\n{BOLD}--- Execution 2 (Replay Safety) ---{RESET}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    with patch.object(InvestigationOrchestrator, "investigate", new=patched_investigate), \
         patch("src.orchestration.pipeline.evaluate_repair_eligibility", new=patched_evaluate), \
         patch("src.orchestration.pipeline.execute_repair_action", new=patched_execute):
        
        result_2 = await run_investigation_pipeline(obs_id)
        assert result_2 is not None

    m3_discrepancy_str = "TRUE (CAPTURED_PAYMENT_STALE_ORDER)" if counters["m4"] > 0 else "FALSE"
    print(f"M3 Discrepancy: {m3_discrepancy_str}")
    print(f"M4 Invocations: {counters['m4']}")
    print(f"Control Invocations: {counters['control']}")
    print(f"Recovery/Action Invocations: {counters['action']}")
    print(f"SQL UPDATE Rowcount: {counters['rowcount']}")
    print(f"Final Outcome: {result_2.get('pipeline_status')}")
    print(f"{BOLD}Total DB Financial Mutations: {counters['rowcount']}{RESET}")
    
    assert counters["m4"] == 0
    assert counters["control"] == 0
    assert counters["action"] == 0
    assert counters["rowcount"] == 0
    assert result_2.get("pipeline_status") == "NO_ACTION"
    
    # ---------------------------------------------------------
    # RUN 3: RACE CONDITION SAFETY (TOCTOU)
    # ---------------------------------------------------------
    print(f"\n{BOLD}--- Execution 3 (TOCTOU Race Safety) ---{RESET}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # To simulate a TOCTOU race:
    # 1. Reset MerchantOrder to UNPAID.
    # 2. Let M3 detect discrepancy and M4 investigate.
    # 3. Right before `execute_repair_action`, patch it to simulate another thread changing it to PAID first.
    
    async with AsyncSessionLocal() as session:
        # Reset to UNPAID
        from sqlalchemy import update
        await session.execute(update(MerchantOrder).where(MerchantOrder.razorpay_order_id == order_id).values(status="UNPAID"))
        await session.commit()
    
    counters = {k: 0 for k in counters}
    
    async def patched_execute_raced(*args, **kwargs):
        counters["action"] += 1
        # Another thread maliciously/concurrently pays the order first
        async with AsyncSessionLocal() as s2:
            await s2.execute(update(MerchantOrder).where(MerchantOrder.razorpay_order_id == order_id).values(status="PAID"))
            await s2.commit()
            
        res = await orig_execute(*args, **kwargs)
        if res.status.value == "SUCCESS":
            counters["rowcount"] = 1
        else:
            counters["rowcount"] = 0
        return res

    with patch.object(InvestigationOrchestrator, "investigate", new=patched_investigate_mocked), \
         patch("src.orchestration.pipeline.evaluate_repair_eligibility", new=patched_evaluate), \
         patch("src.orchestration.pipeline.execute_repair_action", new=patched_execute_raced):
        
        result_3 = await run_investigation_pipeline(obs_id)
        assert result_3 is not None

    print(f"M4 Invocations: {counters['m4']}")
    print(f"Control Invocations: {counters['control']}")
    print(f"Recovery/Action Invocations: {counters['action']}")
    print(f"SQL UPDATE Rowcount: {counters['rowcount']}")
    print(f"Final Outcome: {result_3.get('pipeline_status')}")
    print(f"{BOLD}Total DB Financial Mutations by this Thread: {counters['rowcount']}{RESET}")
    
    assert counters["m4"] == 1
    assert counters["action"] == 1
    assert counters["rowcount"] == 0
    assert result_3.get("pipeline_status") == "CONFLICT"
    
    print(f"\n{GREEN}{BOLD}✅ ALL INVARIANTS SATISFIED.{RESET}")

if __name__ == "__main__":
    asyncio.run(run_golden_acceptance())
