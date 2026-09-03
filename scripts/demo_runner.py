"""
Financial Control Engine — Single-Case Narrative Demo

Demonstrates the full frozen core control loop on one ABSENT_EXECUTION case:

  Ingest → Reconcile → V1 → Incident → Investigate → Verify
  → Policy → Outbox → Execute → Re-observe → Reconcile → MATCH

Uses:
  - ControlRuntime / ReconciliationEngine / IncidentEngine  (frozen core)
  - ActionPolicyEngine / ActionOutbox / ActionExecutor      (frozen policy)
  - MemoryRepository                                        (Docker-free)
  - RazorpayMockTransport                                   (offline)
  - SyntheticInvestigator with REPLAY fallback              (no Ollama required)

Run:
  PYTHONPATH=. uv run python scripts/demo_runner.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone, timedelta

import httpx

from src.ingestion.pipeline import ExpectationIngester
from src.ingestion.models import IngestionStatus
from src.engine.reconciliation import ReconciliationEngine
from src.engine.incidents import IncidentEngine
from src.engine.runtime import ControlRuntime, ExpectationReceived
from src.engine.policy import ActionPolicyEngine
from src.engine.outbox import ActionOutbox
from src.engine.executor import ActionExecutor
from src.storage.memory_repo import MemoryRepository
from src.domain.incidents.models import IncidentState
from src.reconciliation.models import DiscrepancyType

from src.investigation.agent import LocalLLMInvestigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.integrations.razorpay.client import RazorpayClient

from tests.doubles.synthetic_investigator import SyntheticInvestigator
from tests.doubles.razorpay_mock_transport import RazorpayMockTransport


# ---------------------------------------------------------------------------
# Scenario: ABSENT_EXECUTION
# An internal refund expectation was raised 3 hours ago. The provider has
# never sent a webhook. SLA has elapsed → V1 classifies ABSENT_EXECUTION.
# The policy engine authorises a controlled refund. The mock provider accepts
# it. V1 re-classifies on the returned observation → MATCH.
# ---------------------------------------------------------------------------

INTENT_ID = "demo_intent_001"
PAYMENT_ID = "pay_demo_abc"
AMOUNT = 50000   # paise (Rs 500)
CURRENCY = "INR"


def _sep(title: str = "") -> None:
    width = 62
    if title:
        pad = (width - len(title) - 2) // 2
        print("-" * pad + f" {title} " + "-" * (width - pad - len(title) - 2))
    else:
        print("-" * width)


async def run_demo() -> int:
    now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    intent_time = now - timedelta(hours=3)

    print()
    print("=" * 62)
    print("  FINANCIAL CONTROL ENGINE -- DEMO")
    print("=" * 62)
    print()
    print("  Architecture : ControlRuntime -> ReconciliationEngine -> IncidentEngine")
    print("                 -> Policy -> Outbox -> Executor -> Re-reconcile")
    print("  Repository   : MemoryRepository  (Docker-free)")
    print("  Provider     : REPLAY  (RazorpayMockTransport)")
    print()

    # ------------------------------------------------------------------
    # 1. Build investigator (live Ollama if available, else replay)
    # ------------------------------------------------------------------
    use_live = "--live" in sys.argv
    if use_live:
        investigator_mode = "LIVE (qwen3:8b)"
        try:
            base_investigator = LocalLLMInvestigator(model="qwen3:8b")
        except Exception:
            investigator_mode = "REPLAY (deterministic fallback)"
            base_investigator = None
    else:
        investigator_mode = "REPLAY (deterministic — use --live for Ollama)"
        base_investigator = None

    sub_case_hints = {INTENT_ID: "C1_ABSENT_EXECUTION_REFUND_FOUND"}
    investigator = SyntheticInvestigator(base_investigator, sub_case_hints)

    print(f"  Investigator  : {investigator_mode}")
    print()

    # ------------------------------------------------------------------
    # 2. Mock provider: returns a successful refund on query
    # ------------------------------------------------------------------
    mock_transport = RazorpayMockTransport()
    mock_transport.refunds = [{
        "id": f"rfnd_demo_{INTENT_ID}",
        "entity": "refund",
        "amount": AMOUNT,
        "currency": CURRENCY,
        "payment_id": PAYMENT_ID,
        "status": "processed",
        "created_at": int(intent_time.timestamp()),
        "receipt": INTENT_ID,
    }]

    http_client = httpx.AsyncClient(
        transport=mock_transport, base_url="https://api.razorpay.com/v1"
    )
    razorpay_client = RazorpayClient(client=http_client)
    verifier = DeterministicVerifier(razorpay_client=razorpay_client)
    validator = OutputValidator()

    # ------------------------------------------------------------------
    # 3. Assemble the frozen core stack
    # ------------------------------------------------------------------
    recon_engine = ReconciliationEngine()
    incident_engine = IncidentEngine(
        reconciliation_engine=recon_engine,
        investigator=investigator,
        validator=validator,
        verifier=verifier,
    )
    runtime = ControlRuntime(
        repository=MemoryRepository(),
        reconciliation_engine=recon_engine,
        incident_engine=incident_engine,
    )
    policy = ActionPolicyEngine()
    outbox = ActionOutbox()
    executor = ActionExecutor(outbox, runtime, razorpay_client)

    # ------------------------------------------------------------------
    # 4. Ingest expectation -- no matching observation (absent execution)
    # ------------------------------------------------------------------
    _sep("INGESTION")
    exp_payload = {
        "refund_intent_id": INTENT_ID,
        "provider_payment_id": PAYMENT_ID,
        "amount": str(AMOUNT),
        "currency": CURRENCY,
        "created_at": intent_time.isoformat(),
        "sla_deadline": (intent_time + timedelta(hours=2)).isoformat(),
    }
    exp_result = ExpectationIngester.ingest(exp_payload)
    if exp_result.status != IngestionStatus.SUCCESS:
        print(f"  FAIL: Expectation ingestion failed: {exp_result.error_message}")
        return 1

    expectation = exp_result.domain_object
    assert expectation is not None, "Failed to ingest expectation"
    print(f"  OK  Expectation ingested    intent={INTENT_ID}  amount=Rs {AMOUNT/100:.2f}")
    print(f"      No provider observation (webhook never arrived)")
    print()

    await runtime.ingest_event(ExpectationReceived(expectation))

    # ------------------------------------------------------------------
    # 5. Pass 1 -- Reconcile -> V1 -> Incident -> Investigate
    # ------------------------------------------------------------------
    _sep("PASS 1: RECONCILE + INVESTIGATE")
    incidents = await runtime.run_until_drained(now)

    if not incidents:
        print("  FAIL: No incidents produced -- demo scenario not triggered.")
        return 1

    incident = incidents[0]
    assert incident.discrepancy_type is not None, "Incident missing discrepancy type"
    print(f"  V1 classification   : {incident.discrepancy_type.value}")
    print(f"  Lifecycle state     : {incident.lifecycle_state.value}")
    print()
    for entry in incident.discrepancy_history:
        print(f"  History  : {entry}")
    print()

    # ------------------------------------------------------------------
    # 6. Pass 2 -- Policy evaluation -> action authorised
    # ------------------------------------------------------------------
    _sep("PASS 2: POLICY")
    action = policy.evaluate(incident)
    if action:
        outbox.append(action)
        print(f"  OK  Action authorised   : {action.action_type.value}")
        print(f"      Idempotency key     : {action.idempotency_key}")
        print(f"      Intent              : {action.payload.get('intent_id')}")
    else:
        print("  No action authorised (incident not ESCALATED or not actionable).")
    print()

    # ------------------------------------------------------------------
    # 7. Pass 3 -- Execution (provider mutation)
    # ------------------------------------------------------------------
    _sep("PASS 3: EXECUTION")
    await executor.execute_pending()
    remaining_pending = outbox.get_pending()
    if not remaining_pending:
        print("  OK  Provider mutation executed successfully.")
    else:
        print(f"  {len(remaining_pending)} action(s) still pending.")
    print()

    # ------------------------------------------------------------------
    # 8. Pass 4 -- Re-reconcile on new observation -> MATCH
    # ------------------------------------------------------------------
    _sep("PASS 4: FINAL RECONCILE")
    final_incidents = await runtime.run_until_drained(now)

    final_incident = next(
        (i for i in final_incidents if i.refund_intent_id == INTENT_ID), None
    )
    if final_incident:
        assert final_incident.discrepancy_type is not None, "Final incident missing discrepancy type"
        print(f"  Final V1 result     : {final_incident.discrepancy_type.value}")
        print(f"  Lifecycle state     : {final_incident.lifecycle_state.value}")
    else:
        print("  (No final incident found.)")
    print()

    # ------------------------------------------------------------------
    # 9. Summary
    # ------------------------------------------------------------------
    _sep("RESULT")
    if final_incident and final_incident.discrepancy_type == DiscrepancyType.MATCH:
        print("  OK  ABSENT_EXECUTION -> MATCH")
        print()
        print("      The control loop detected missing refund, authorised execution,")
        print("      received provider confirmation, and re-classified to MATCH.")
        print("      Financial truth determined by V1 kernel.")
        print("      LLM had no classification authority.")
        rc = 0
    else:
        if final_incident and final_incident.discrepancy_type:
            final_class = final_incident.discrepancy_type.value
        else:
            final_class = "UNKNOWN"
        print(f"  Final classification: {final_class}")
        print("  (Demo scenario did not reach MATCH -- check investigator mode.)")
        rc = 1
    print()
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(run_demo()))
