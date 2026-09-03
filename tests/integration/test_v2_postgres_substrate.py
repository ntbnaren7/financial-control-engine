import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from src.storage.postgres.models import Base
from src.storage.postgres_substrate import PostgresObservationRepository, PostgresExpectationRepository, PostgresEvidenceRepository
from src.domain.core.models import Observation, Expectation, Evidence

@pytest.fixture
def session_maker():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)

def test_observation_delivery_idempotency(session_maker):
    repo = PostgresObservationRepository(session_maker)
    
    obs = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[],
        ingestion_event_id="webhook_msg_001"
    )
    
    repo.save(obs)
    
    # Save the exact same observation again (same ingestion_event_id)
    # The repository suppresses IntegrityError and ignores duplicates
    repo.save(obs)
    
    # We should still only have 1 in DB
    with session_maker() as session:
        from src.storage.postgres_substrate import SubstrateObservationRecord
        count = session.query(SubstrateObservationRecord).count()
        assert count == 1

def test_observation_instance_identity(session_maker):
    repo = PostgresObservationRepository(session_maker)
    
    obs1 = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSING",
        observed_amount=500,
        currency="INR",
        evidence_ids=[],
        provider_event_id="evt_001",
        ingestion_event_id="webhook_msg_001"
    )
    
    obs2 = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[],
        provider_event_id="evt_001", # Same event ID! This violates instance identity
        ingestion_event_id="webhook_msg_002"
    )
    
    repo.save(obs1)
    repo.save(obs2) # Should be ignored due to IntegrityError handling
    
    results = repo.find_by_business_identity("razorpay", "pay_123", "refund")
    assert len(results) == 1
    assert results[0].observed_state == "PROCESSING"

def test_observation_multiple_instances(session_maker):
    repo = PostgresObservationRepository(session_maker)
    
    obs1 = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSING",
        observed_amount=500,
        currency="INR",
        evidence_ids=[],
        provider_event_id="evt_001",
        ingestion_event_id="webhook_msg_001"
    )
    
    obs2 = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="refund",
        observed_state="PROCESSED",
        observed_amount=500,
        currency="INR",
        evidence_ids=[],
        provider_event_id="evt_002", # Different event ID
        ingestion_event_id="webhook_msg_002"
    )
    
    repo.save(obs1)
    repo.save(obs2)
    
    results = repo.find_by_business_identity("razorpay", "pay_123", "refund")
    assert len(results) == 2
