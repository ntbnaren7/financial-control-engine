import json
import uuid
import pprint
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from src.storage.repository import EvidenceRepository
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.orchestration.financial_orchestrator import FinancialControlOrchestrator
from typing import Dict, Any, Tuple

def _utcnow():
    return datetime.now(timezone.utc)

def _dt(age_hours: int = 0):
    return _utcnow() - timedelta(hours=age_hours)

def create_intent(intent_id: str, amount: str, currency: str = "INR", age_hours: int = 2) -> Tuple[str, Dict[str, Any]]:
    return ("internal_oms", {
        "refund_intent_id": intent_id,
        "provider_payment_id": f"pay_{uuid.uuid4()}",
        "amount": amount,
        "currency": currency,
        "merchant_reference": f"ref_{intent_id}",
        "created_at": _dt(age_hours).isoformat()
    })

def create_webhook(intent_id: str, amount_paise: int, event: str = "refund.processed", currency: str = "INR", age_hours: int = 1) -> Tuple[str, Dict[str, Any]]:
    return ("razorpay_webhook", {
        "event": event,
        "payload": {
            "refund": {
                "entity": {
                    "id": f"rfnd_{intent_id}",
                    "receipt": intent_id,
                    "amount": amount_paise,
                    "currency": currency,
                    "status": "refunded" if "processed" in event else "processing",
                    "created_at": _dt(age_hours).timestamp()
                }
            }
        }
    })

def create_api_response(intent_id: str, status: str, confidence: str, amount_paise: int = 50000, age_hours: int = 0) -> Tuple[str, Dict[str, Any]]:
    return ("razorpay_api", {
        "id": f"rfnd_{intent_id}",
        "receipt": intent_id,
        "status": status,
        "amount": amount_paise,
        "currency": "INR",
        "query_confidence": confidence,
        "created_at": _dt(age_hours).timestamp()
    })

def main():
    print("==========================================================")
    print(" Financial Control Engine: Phase C Substrate Batch Demo")
    print("==========================================================\n")
    
    # 1. Initialize Substrate Dependencies
    import os
    db_file = "demo_substrate.db"
    if os.path.exists(db_file):
        os.remove(db_file)
    repo = EvidenceRepository(db_path=db_file)
    state_engine = StateEngine()
    setattr(state_engine, 'ordering_policy', TemporalOrderingPolicy())
    orchestrator = FinancialControlOrchestrator(evidence_repo=repo, state_engine=state_engine)
    
    # 2. Generate Heterogeneous Evidence Records
    # We will simulate 8 distinct adversarial/happy paths
    records = []
    
    # Scenario 1: Matching refund -> MATCH
    records.append(create_intent("ref_1", "500.00"))
    records.append(create_webhook("ref_1", 50000))

    # Scenario 2: Authoritative absence -> ABSENT_EXECUTION
    records.append(create_intent("ref_2", "1200.00"))
    records.append(create_api_response("ref_2", status="failed", confidence="AUTHORITATIVE_NOT_EXECUTED"))

    # Scenario 3: No authoritative evidence -> EPISTEMIC_STALEMATE
    records.append(create_intent("ref_3", "750.00"))

    # Scenario 4: Wrong amount -> VALUE_MISMATCH
    records.append(create_intent("ref_4", "1000.00"))
    records.append(create_webhook("ref_4", 90000)) # Under-refunded

    # Scenario 5: Wrong currency -> CURRENCY_MISMATCH
    records.append(create_intent("ref_5", "500.00", currency="INR"))
    records.append(create_webhook("ref_5", 50000, currency="USD"))

    # Scenario 6: Duplicate refund -> EXCESS_EFFECT
    records.append(create_intent("ref_6", "300.00"))
    records.append(create_webhook("ref_6", 30000))
    # Second duplicate execution (we modify the id so it looks like a distinct provider execution)
    dup_source, dup_payload = create_webhook("ref_6", 30000)
    dup_payload["payload"]["refund"]["entity"]["id"] = "rfnd_dup_2"
    records.append((dup_source, dup_payload))

    # Scenario 7: Verified orphan -> ORPHANED_EXECUTION
    # Provider evidence without internal intent
    records.append(create_webhook("orphan_7", 25000))

    # Scenario 8: Ambiguous correlation (Temporal Violation) -> Rejected Correlation
    # Intent is 1 hour old, but refund webhook supposedly happened 24 hours ago
    records.append(create_intent("ref_8", "200.00", age_hours=1))
    records.append(create_webhook("ref_8", 20000, age_hours=24))

    print(f"Ingesting {len(records)} heterogeneous raw records into the Phase C Substrate...\n")

    # 3. Process records through the pipeline
    cases = orchestrator.ingest_and_generate_cases(records)
    
    # 4. Display Results
    print("==========================================================")
    print(f" Phase C Generated {len(cases)} Reconciliation Cases")
    print("==========================================================\n")
    
    for i, case in enumerate(cases):
        print(f"Case {i + 1}:")
        
        # Display Correlation
        ctx = case.correlation_context
        correlations = [f"{r.provider_evidence.source} ({r.status.value})" for r in ctx.results if r.provider_evidence]
        intent_status = "Present" if ctx.intent else "Missing (Orphan)"
        
        print(f"  [Evidence Layer] Intent: {intent_status} | Provider Records Correlated: {len(correlations)}")
        if correlations:
            print(f"                   Details: {', '.join(correlations)}")
            
        # Display V1 Result
        res = case.reconciliation_result
        if res:
            print(f"  [V1 Classification] Discrepancy Type: {res.discrepancy_type.value}")
            print(f"                      Actionable: {res.is_actionable}")
            if res.observed_amount is not None:
                print(f"                      Observed Amount: {res.observed_amount}")
        else:
            print("  [V1 Classification] None (Unresolved/Rejected Context)")
            
        print("-" * 58)

    # Prove that the ambiguous correlation generated a stalemate since the provider record was rejected
    ambiguous_case = next((c for c in cases if c.correlation_context.intent and c.correlation_context.intent.payload.get("intent_id") == "ref_8"), None)
    if ambiguous_case:
        print("\nNote on Scenario 8 (Temporal Violation):")
        print("  The provider record was rejected from correlation bounds.")
        print("  Therefore, V1 only saw the intent, treating it as missing evidence.")
        if ambiguous_case.reconciliation_result:
            print(f"  Result: {ambiguous_case.reconciliation_result.discrepancy_type.value}")
        else:
            print("  Result: None")

if __name__ == '__main__':
    main()
