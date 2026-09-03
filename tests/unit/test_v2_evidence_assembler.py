from datetime import datetime, timezone
import pytest

from src.domain.core.models import (
    Expectation, 
    Observation, 
    Evidence, 
    ReconciliationResult, 
    ReconciliationOutcome, 
    DiscrepancyReason, 
    CorrelationKeys
)
from src.engine.evidence_assembler import EvidenceAssembler

class MockExpectationRepo:
    def __init__(self, exps):
        self.exps = {e.expectation_id: e for e in exps}
    def get(self, id):
        return self.exps.get(id)

class MockObservationRepo:
    def __init__(self, obs):
        self.obs = {o.observation_id: o for o in obs}
    def get(self, id):
        return self.obs.get(id)

class MockEvidenceRepo:
    def __init__(self, evs):
        self.evs = {e.evidence_id: e for e in evs}
    def get_by_ids(self, ids):
        return [self.evs[id] for id in ids if id in self.evs]

def test_evidence_assembler():
    # Setup
    exp = Expectation(
        domain="Refund",
        expected_state="PROCESSED",
        expected_amount=500,
        currency="INR",
        source_system="merchant",
        correlation_keys=CorrelationKeys(internal_ref="r_123")
    )
    
    ev1 = Evidence(
        source="razorpay",
        source_reference="rfnd_123",
        payload_hash="abc",
        raw_payload_ref="s3://123",
        observed_at=datetime.now(timezone.utc),
        ingested_at=datetime.now(timezone.utc)
    )
    
    obs = Observation(
        provider="razorpay",
        provider_reference="rfnd_123",
        observation_type="REFUND",
        observed_state="PROCESSED",
        observed_amount=450,
        currency="INR",
        evidence_ids=[ev1.evidence_id],
        ingestion_event_id="evt_123",
        observed_at=datetime.now(timezone.utc)
    )
    
    result = ReconciliationResult(
        expectation_id=exp.expectation_id,
        observation_ids=[obs.observation_id],
        outcome=ReconciliationOutcome.DISCREPANCY,
        reconciliation_reason="Amounts do not match",
        discrepancy_reason=DiscrepancyReason.AMOUNT_MISMATCH
    )
    
    assembler = EvidenceAssembler(
        MockExpectationRepo([exp]), # type: ignore
        MockObservationRepo([obs]), # type: ignore
        MockEvidenceRepo([ev1]) # type: ignore
    )
    
    # Act
    context = assembler.assemble(result)
    
    # Assert
    assert context.active_discrepancy == result
    assert context.expectation == exp
    assert len(context.observations) == 1
    assert context.observations[0] == obs
    assert len(context.evidence_records) == 1
    assert context.evidence_records[0] == ev1
    assert context.context_id is not None
