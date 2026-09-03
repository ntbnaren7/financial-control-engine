import sys
import os
import asyncio
from datetime import datetime, timezone, timedelta

# Ensure src is in PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import httpx

from src.storage.repository import EvidenceRepository
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.orchestration.financial_orchestrator import FinancialControlOrchestrator
from src.domain.cases.models import ReconciliationCase
from src.reconciliation.models import DiscrepancyType

from src.investigation.input_formatter import format_case_for_investigation
from src.investigation.agent import LocalLLMInvestigator
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.integrations.razorpay.client import RazorpayClient
from src.domain.investigation.models import CausalHypothesis

# We use tests infrastructure to simulate the provider API purely for the deterministic demo.
# Do NOT depend on this in production code.
from tests.doubles.razorpay_mock_transport import RazorpayMockTransport


async def run_demo():
    print("============================================================")
    print("FINANCIAL CONTROL ENGINE - PHASE E DEMO")
    print("============================================================")
    print("DEMO MODE:")
    print(" - Investigator : LIVE (Ollama qwen3:8b) with REPLAY fallback")
    print(" - Provider     : REPLAY (RazorpayMockTransport)")
    print("============================================================")

    # 1. Setup Deterministic Scenario
    print("\n1. Initializing Deterministic Scenario (EPISTEMIC_STALEMATE)")
    
    intent_time = datetime.now(timezone.utc) - timedelta(hours=3)
    
    raw_records = [
        ("internal_oms", {
            "event": "refund_intent_created",
            "refund_intent_id": "ref_demo_001",
            "provider_payment_id": "pay_xyz",
            "amount": 200, # ₹200
            "currency": "INR",
            "created_at": intent_time.isoformat()
        })
    ]
    
    # 2. Ingestion & Initial V1 Classification
    evidence_repo = EvidenceRepository()
    state_engine = StateEngine()
    orchestrator = FinancialControlOrchestrator(evidence_repo, state_engine)
    
    cases = orchestrator.ingest_and_generate_cases(raw_records)
    case = cases[0]
    
    if not case.reconciliation_result:
        print("\nDemo aborted: Case lacks reconciliation result.")
        return
        
    classification = case.reconciliation_result.discrepancy_type
    
    print("-" * 60)
    print("V1 Kernel (Initial)")
    print("-" * 60)
    print(f"Initial Classification: {classification.value}")
    print("\nWhy:")
    print("  Expected refund: ₹200")
    print("  Provider event: None (UNKNOWN state)")
    print("  Time elapsed: 3 hours (Past SLA)")
    print(f"  Case ID: {case.case_id}")
    
    if classification != DiscrepancyType.EPISTEMIC_STALEMATE:
        print("\nDemo aborted: Scenario did not yield EPISTEMIC_STALEMATE.")
        return
        
    # 3. Investigation
    print("\n───────── INVESTIGATION ─────────")
    
    print("Investigator: qwen3:8b [UNTRUSTED]")
    print("qwen3:8b is generating a hypothesis...\n")
    
    formatted_input = format_case_for_investigation(case)
    
    try:
        investigator = LocalLLMInvestigator(model="qwen3:8b")
        hypothesis = await asyncio.to_thread(investigator.investigate, formatted_input)
    except Exception as e:
        print(f"\n[yellow][MODE CHANGED] Sandbox/Network Error -> Falling back to REPLAY INVESTIGATION: {e}[/yellow]")
        hypothesis = CausalHypothesis(
            hypothesis="Provider execution likely occurred but the webhook arrived outside the permitted correlation window.",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            missing_evidence_description="Authoritative provider refund status lookup via API.",
            confidence="MEDIUM",
            disposition="VERIFICATION_PROPOSED",
            verification_intent="QUERY_PROVIDER_REFUND"
        )
        
    print("-" * 60)
    print("Local LLM Output")
    print("-" * 60)
    print("Hypothesis")
    print(f"{hypothesis.hypothesis}")
    print(f"\nSupporting evidence: {', '.join(hypothesis.supporting_evidence_ids) if hypothesis.supporting_evidence_ids else 'None'}")
    print(f"Confidence: {hypothesis.confidence} (informational only)")
    print("\nVerification intent")
    print(f"{hypothesis.verification_intent.value if hypothesis.verification_intent else 'None'}")
    
    # 4. Control Boundary (D4-D5)
    print("\n───────── CONTROL BOUNDARY ────────")
    
    validator = OutputValidator()
    validation_result = validator.validate(hypothesis.model_dump(mode="json"), formatted_input)
    
    if isinstance(validation_result, CausalHypothesis):
        print("✅ Evidence references validated")
        print("✅ Intent allowlisted")
        print("✅ Query parameters derived from trusted case")
        print("✅ LLM cannot select refund ID")
    else:
        print(f"❌ Validation failed: {validation_result.reason.value} - {validation_result.detail}")
        return

    # Simulate read-only provider call deterministically using MockTransport
    # In live mode, this would use httpx.AsyncClient() directly against Razorpay API.
    mock_transport = RazorpayMockTransport()
    # By default, mock_transport.refunds is empty, meaning the query will return zero items.
    
    http_client = httpx.AsyncClient(transport=mock_transport, base_url="https://api.razorpay.com/v1")
    razorpay_client = RazorpayClient(client=http_client)
    verifier = DeterministicVerifier(razorpay_client=razorpay_client)
    
    print("\nExecuting deterministic verification query: fetch_refunds(pay_xyz) [REPLAY]")
    
    new_evidences = await verifier.verify(hypothesis, case)
    
    if isinstance(new_evidences, list):
        print("✅ Executed read-only provider query.")
    else:
        print(f"❌ Verification rejected: {new_evidences.reason.value} - {new_evidences.detail}")
        return
        
    # 5. Phase C Normalization
    print("\n───────── PROVIDER EVIDENCE ───────")
    if len(new_evidences) == 0:
         print("Provider returned empty list -> Refund not found")
         
         # The verifier in D5 currently does not inject an "empty" observation natively if 
         # the HTTP response simply has 0 items (it just returns an empty evidence list).
         # So we inject one to explicitly record the authoritative non-execution.
         from src.evidence.models import ProviderObservation, EntityType
         import uuid
         authoritative_obs = ProviderObservation(
             entity_type=EntityType.REFUND_INTENT.value,
             entity_id=case.expectation.refund_intent_id if case.expectation else "UNKNOWN",
             id=uuid.uuid4(),
             provider="razorpay",
             event_id=str(uuid.uuid4()),
             event_type="verification.empty",
             payload={"query_confidence": "AUTHORITATIVE_NOT_EXECUTED"},
             created_at=datetime.now(timezone.utc)
         )
         case.provider_observations.append(authoritative_obs)
    else:
         for evidence in new_evidences:
             from src.evidence.models import ProviderObservation, EntityType
             import uuid
             
             obs = ProviderObservation(
                 provider="razorpay",
                 event_id=evidence.evidence_id,
                 entity_type=EntityType.REFUND_INTENT.value,
                 entity_id=case.expectation.refund_intent_id if case.expectation else evidence.entity_id,
                 event_type=evidence.evidence_type,
                 payload={"status": evidence.payload.get("status"), "query_confidence": evidence.payload.get("query_confidence"), "provider_timestamp": evidence.payload.get("created_at")},
                 created_at=evidence.timestamp,
                 id=uuid.uuid4()
             )
             case.provider_observations.append(obs)
    
    # 6. V1 Reclassification
    print("\n───────── V1 RECLASSIFICATION ─────")
    
    intent_id = case.expectation.refund_intent_id if case.expectation else "UNKNOWN"
    
    from src.evidence.models import EntityType
    reconstructed_state = state_engine.reconstruct_state(
        entity_type=EntityType.REFUND_INTENT,
        entity_id=intent_id,
        observations=case.provider_observations,
        reconstructed_at=datetime.now(timezone.utc),
        ordering_policy=TemporalOrderingPolicy()
    )
    
    from src.reconciliation.engine import reconcile
    result = reconcile(
        expectation=case.expectation,
        reconstructed_state=reconstructed_state,
        reconciliation_timestamp=datetime.now(timezone.utc),
        observed_amount=None,
        observed_currency=None,
        matching_executions_count=0
    )
    
    print("-" * 60)
    print("V1 Kernel (Updated)")
    print("-" * 60)
    print(f"Final Result: {result.discrepancy_type.value}\n")
    print("Financial truth determined by V1 kernel.")
    print("Demo flow terminated. Phase B execution deferred.")

if __name__ == "__main__":
    asyncio.run(run_demo())
