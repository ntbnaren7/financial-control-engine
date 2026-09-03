import pytest
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple

from src.storage.repository import EvidenceRepository
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.orchestration.financial_orchestrator import FinancialControlOrchestrator
from src.reconciliation.models import DiscrepancyType
from src.domain.correlation.models import CorrelationStatus

@pytest.fixture
def orchestrator(tmp_path):
    repo = EvidenceRepository(db_path=str(tmp_path / "test.db"))
    state_engine = StateEngine()
    setattr(state_engine, 'ordering_policy', TemporalOrderingPolicy())
    return FinancialControlOrchestrator(evidence_repo=repo, state_engine=state_engine)

def create_internal_intent(intent_id: str, amount: str, currency: str = "INR", age_hours: int = 2) -> Tuple[str, Dict[str, Any]]:
    return (
        "internal_oms",
        {
            "refund_intent_id": intent_id,
            "provider_payment_id": f"pay_{intent_id}",
            "amount": amount,
            "currency": currency,
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
        }
    )

def create_razorpay_webhook(intent_id: str, amount_paise: int, event: str = "refund.processed", age_hours: int = 1, currency: str = "INR") -> Tuple[str, Dict[str, Any]]:
    return (
        "razorpay_webhook",
        {
            "event": event,
            "payload": {
                "refund": {
                    "entity": {
                        "id": f"rfnd_{intent_id}",
                        "receipt": intent_id,
                        "amount": amount_paise,
                        "currency": currency,
                        "status": "refunded" if "processed" in event else "processing",
                        "created_at": (datetime.now(timezone.utc) - timedelta(hours=age_hours)).timestamp()
                    }
                }
            }
        }
    )

def create_razorpay_api_not_found(intent_id: str) -> Tuple[str, Dict[str, Any]]:
    # A mocked query result indicating we asked Razorpay and it confidently said NO.
    return (
        "razorpay_api",
        {
            "id": f"unknown_{intent_id}",
            "receipt": intent_id,
            "status": "NOT_EXECUTED", # Simulating AUTHORITATIVE_NOT_EXECUTED
            "query_confidence": "AUTHORITATIVE_NOT_EXECUTED",
            "created_at": datetime.now(timezone.utc).timestamp()
        }
    )

def test_happy_path_match(orchestrator):
    records = [
        create_internal_intent("ref_123", "500.00"),
        create_razorpay_webhook("ref_123", 50000)
    ]
    cases = orchestrator.ingest_and_generate_cases(records)
    assert len(cases) == 1
    case = cases[0]
    
    assert case.correlation_context.results[0].status == CorrelationStatus.CORRELATED
    assert case.reconciliation_result.discrepancy_type == DiscrepancyType.MATCH

def test_authoritative_absence(orchestrator):
    records = [
        create_internal_intent("ref_absence", "100.00", age_hours=24), # Past SLA
        create_razorpay_api_not_found("ref_absence")
    ]
    cases = orchestrator.ingest_and_generate_cases(records)
    assert len(cases) == 1
    case = cases[0]
    
    assert case.reconciliation_result.discrepancy_type == DiscrepancyType.ABSENT_EXECUTION

def test_insufficient_evidence_epistemic_stalemate(orchestrator):
    records = [
        create_internal_intent("ref_stale", "100.00", age_hours=24), # Past SLA, but NO provider records
    ]
    cases = orchestrator.ingest_and_generate_cases(records)
    assert len(cases) == 1
    case = cases[0]
    
    assert case.reconciliation_result.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE

def test_orphaned_execution(orchestrator):
    records = [
        create_razorpay_webhook("orphan_456", 20000) # Provider record only
    ]
    cases = orchestrator.ingest_and_generate_cases(records)
    assert len(cases) == 1
    case = cases[0]
    
    # UNMATCHED Correlation
    assert case.correlation_context.results[0].status == CorrelationStatus.UNMATCHED
    # Classified as ORPHANED_EXECUTION by V1
    assert case.reconciliation_result.discrepancy_type == DiscrepancyType.ORPHANED_EXECUTION

def test_wrong_amount_value_mismatch(orchestrator):
    records = [
        create_internal_intent("ref_val", "500.00"),
        create_razorpay_webhook("ref_val", 40000) # 400 instead of 500
    ]
    cases = orchestrator.ingest_and_generate_cases(records)
    assert len(cases) == 1
    case = cases[0]
    
    assert case.reconciliation_result.discrepancy_type == DiscrepancyType.VALUE_MISMATCH
    assert case.correlation_context.results[0].amount_check is False

def test_wrong_currency_mismatch(orchestrator):
    records = [
        create_internal_intent("ref_curr", "500.00", currency="INR"),
        create_razorpay_webhook("ref_curr", 50000, currency="USD")
    ]
    cases = orchestrator.ingest_and_generate_cases(records)
    assert len(cases) == 1
    case = cases[0]
    
    assert case.reconciliation_result.discrepancy_type == DiscrepancyType.CURRENCY_MISMATCH
    assert case.correlation_context.results[0].currency_check is False

def test_duplicate_refund_excess_effect(orchestrator):
    records = [
        create_internal_intent("ref_dup", "500.00"),
        create_razorpay_webhook("ref_dup", 50000),
        create_razorpay_webhook("ref_dup", 50000, event="refund.processed") # Simulating a second distinct execution
    ]
    # Tweak the second webhook so it has a different entity ID to be counted as a second execution
    records[2][1]["payload"]["refund"]["entity"]["id"] = "rfnd_dup_2"
    
    cases = orchestrator.ingest_and_generate_cases(records)
    assert len(cases) == 1
    case = cases[0]
    
    assert case.reconciliation_result.discrepancy_type == DiscrepancyType.EXCESS_EFFECT

def test_temporal_violation_rejects_correlation(orchestrator):
    # Intent created 1 hour ago
    intent = create_internal_intent("ref_temp", "500.00", age_hours=1)
    # Provider refund supposedly created 24 hours ago (before intent existed!)
    provider = create_razorpay_webhook("ref_temp", 50000, age_hours=24)
    
    records = [intent, provider]
    cases = orchestrator.ingest_and_generate_cases(records)
    
    assert len(cases) == 1
    case = cases[0]
    
    assert case.correlation_context.results[0].status == CorrelationStatus.TEMPORAL_VIOLATION
    assert case.correlation_context.results[0].temporal_check is False
    # Since they violated temporal rules, V1 doesn't see them as a valid MATCH
    # Actually, in our orchestrator, does a temporal violation still get passed to V1?
    # Yes, it passes the evidence. The StateEngine might reject it or V1 classifies it.
    # We should assert that the correlation engine flagged it.
