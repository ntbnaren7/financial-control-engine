import pytest
from datetime import datetime, timezone
from src.domain.core.models import (
    Expectation, Observation, Evidence, ReconciliationResult, DiscrepancyReason, ReconciliationOutcome
)
from src.domain.investigation.context import InvestigationContext
from src.domain.investigation.models import (
    CausalHypothesis, VerificationIntent, InvestigationDisposition, ValidationRejection, ValidationRejectionReason
)
from src.investigation.input_formatter import format_context_for_investigation
from src.investigation.validator import OutputValidator


@pytest.fixture
def sample_context() -> InvestigationContext:
    now = datetime.now(timezone.utc)
    return InvestigationContext.create(
        active_discrepancy=ReconciliationResult(
            expectation_id="intent_1",
            observation_ids=["obs_1"],
            outcome=ReconciliationOutcome.DISCREPANCY,
            reconciliation_reason="Amount mismatch detected",
            discrepancy_reason=DiscrepancyReason.AMOUNT_MISMATCH
        ),
        expectation=Expectation(
            domain="REFUND",
            expected_state="PROCESSED",
            expected_amount=2000,
            currency="INR",
            source_system="OMS",
            created_at=now
        ),
        observations=[
            Observation(
                provider="razorpay",
                provider_reference="rfnd_123",
                observation_type="REFUND_EVENT",
                observed_state="PROCESSED",
                observed_amount=1500,
                currency="INR",
                evidence_ids=["ev_1"],
                observed_at=now,
                observation_id="obs_1"
            )
        ],
        evidence_records=[
            Evidence(
                source="razorpay_webhook",
                source_reference="wh_123",
                payload_hash="hash_123",
                raw_payload_ref="s3://bucket/wh_123",
                observed_at=now,
                evidence_id="ev_1"
            ),
            Evidence(
                source="oms_database",
                source_reference="db_123",
                payload_hash="hash_456",
                raw_payload_ref="s3://bucket/db_123",
                observed_at=now,
                evidence_id="ev_2"
            )
        ],
        assembled_at=now
    )


def test_input_formatter_serializes_context_safely(sample_context):
    formatted = format_context_for_investigation(sample_context)
    
    assert "context_id" in formatted
    assert formatted["discrepancy_reason"] == "AMOUNT_MISMATCH"
    assert formatted["expectation"]["amount"] == "2000"
    assert len(formatted["observations"]) == 1
    assert formatted["observations"][0]["amount"] == "1500"
    assert len(formatted["evidence_records"]) == 2
    assert "ev_1" in [ev["evidence_id"] for ev in formatted["evidence_records"]]
    assert "QUERY_PROVIDER_STATE" in formatted["permitted_verification_intents"]


def test_validator_accepts_valid_hypothesis(sample_context):
    formatted = format_context_for_investigation(sample_context)
    validator = OutputValidator()
    
    raw_output = {
        "hypothesis_id": "hyp_1",
        "claim": "The provider refunded a partial amount.",
        "supporting_evidence_ids": ["ev_1"],
        "contradicting_evidence_ids": [],
        "missing_evidence": "API fetch of refund entity to confirm amount.",
        "confidence": "HIGH",
        "disposition": "VERIFICATION_PROPOSED",
        "verification_intents": ["QUERY_PROVIDER_STATE"]
    }
    
    result = validator.validate(raw_output, formatted)
    assert isinstance(result, CausalHypothesis)
    assert result.hypothesis_id == "hyp_1"
    assert result.verification_intents[0] == VerificationIntent.QUERY_PROVIDER_STATE


def test_validator_rejects_hallucinated_evidence(sample_context):
    formatted = format_context_for_investigation(sample_context)
    validator = OutputValidator()
    
    raw_output = {
        "hypothesis_id": "hyp_1",
        "claim": "The provider refunded a partial amount.",
        "supporting_evidence_ids": ["ev_999"],  # Hallucinated ID
        "contradicting_evidence_ids": [],
        "missing_evidence": "API fetch of refund entity to confirm amount.",
        "confidence": "HIGH",
        "disposition": "VERIFICATION_PROPOSED",
        "verification_intents": ["QUERY_PROVIDER_STATE"]
    }
    
    result = validator.validate(raw_output, formatted)
    assert isinstance(result, ValidationRejection)
    assert result.reason == ValidationRejectionReason.INVALID_REFERENCE
    assert "ev_999" in result.detail


def test_validator_rejects_invalid_intent(sample_context):
    formatted = format_context_for_investigation(sample_context)
    validator = OutputValidator()
    
    raw_output = {
        "hypothesis_id": "hyp_1",
        "claim": "The provider refunded a partial amount.",
        "supporting_evidence_ids": ["ev_1"],
        "contradicting_evidence_ids": [],
        "missing_evidence": "API fetch of refund entity to confirm amount.",
        "confidence": "HIGH",
        "disposition": "VERIFICATION_PROPOSED",
        "verification_intents": ["NOT_A_REAL_INTENT"]  # Invalid intent
    }
    
    result = validator.validate(raw_output, formatted)
    assert isinstance(result, ValidationRejection)
    assert result.reason == ValidationRejectionReason.SCHEMA_INVALID


def test_validator_rejects_empty_intents_when_proposed(sample_context):
    formatted = format_context_for_investigation(sample_context)
    validator = OutputValidator()
    
    raw_output = {
        "hypothesis_id": "hyp_1",
        "claim": "The provider refunded a partial amount.",
        "supporting_evidence_ids": ["ev_1"],
        "contradicting_evidence_ids": [],
        "missing_evidence": "API fetch of refund entity to confirm amount.",
        "confidence": "HIGH",
        "disposition": "VERIFICATION_PROPOSED",
        "verification_intents": []
    }
    
    result = validator.validate(raw_output, formatted)
    assert isinstance(result, ValidationRejection)
    assert result.reason == ValidationRejectionReason.SCHEMA_INVALID


def test_validator_allows_exhausted_investigation(sample_context):
    formatted = format_context_for_investigation(sample_context)
    validator = OutputValidator()
    
    raw_output = {
        "hypothesis_id": "hyp_1",
        "claim": "Cannot determine cause.",
        "supporting_evidence_ids": [],
        "contradicting_evidence_ids": [],
        "missing_evidence": "Need manual intervention.",
        "confidence": "LOW",
        "disposition": "INVESTIGATION_EXHAUSTED",
        "verification_intents": []
    }
    
    result = validator.validate(raw_output, formatted)
    assert isinstance(result, CausalHypothesis)
