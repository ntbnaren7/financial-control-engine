import pytest
from datetime import datetime, timezone, timedelta
import threading
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from concurrent.futures import ThreadPoolExecutor
import uuid
import json

from src.storage.postgres_substrate import PostgresControlEventRepository, V2ControlEventRecord, ControlEventType
from src.storage.postgres.models import Base
from src.config.settings import FCESettings

TEST_DB_URL = FCESettings.load().database.url.get_secret_value()

@pytest.fixture
def db_session_maker():
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    yield sm
    
    # Cleanup after test
    with sm() as session:
        session.query(V2ControlEventRecord).delete()
        session.commit()
    engine.dispose()

def test_recover_stale_events_idempotency_and_concurrency(db_session_maker):
    repo = PostgresControlEventRepository(db_session_maker)
    
    # Create 50 stale events and 50 fresh IN_PROGRESS events
    stale_threshold = 300
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=stale_threshold + 10)
    fresh_time = datetime.now(timezone.utc) - timedelta(seconds=stale_threshold - 100)
    
    with db_session_maker() as session:
        for i in range(50):
            # Stale
            session.add(V2ControlEventRecord(
                event_id=str(uuid.uuid4()),
                event_type=ControlEventType.OBSERVATION_INGESTED,
                payload={"test": "stale"},
                status="IN_PROGRESS",
                created_at=stale_time,
                leased_at=stale_time
            ))
            # Fresh
            session.add(V2ControlEventRecord(
                event_id=str(uuid.uuid4()),
                event_type=ControlEventType.OBSERVATION_INGESTED,
                payload={"test": "fresh"},
                status="IN_PROGRESS",
                created_at=fresh_time,
                leased_at=fresh_time
            ))
        session.commit()
        
    # We will simulate 10 workers trying to recover stale events concurrently
    num_workers = 10
    results = []
    
    def worker_recovery():
        # A separate repo instance for each thread to simulate different workers
        thread_repo = PostgresControlEventRepository(db_session_maker)
        return thread_repo.recover_stale_events(stale_threshold)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker_recovery) for _ in range(num_workers)]
        for f in futures:
            results.append(f.result())
            
    # The total number of recovered events across all workers should be EXACTLY 50
    # Because Postgres UPDATE with row-level locking ensures only one transaction updates the row
    total_recovered = sum(results)
    assert total_recovered == 50, f"Expected exactly 50 recovered events, got {total_recovered}"
    
    # Idempotency check: run it again, should recover 0
    assert repo.recover_stale_events(stale_threshold) == 0
    
    # Verify DB state
    with db_session_maker() as session:
        pending_count = session.query(V2ControlEventRecord).filter_by(status="PENDING").count()
        in_progress_count = session.query(V2ControlEventRecord).filter_by(status="IN_PROGRESS").count()
        
        assert pending_count == 50, "Only the 50 stale events should be PENDING"
        assert in_progress_count == 50, "The 50 fresh events should remain IN_PROGRESS"
        
        # Verify leased_at is None for recovered events
        pending_events = session.query(V2ControlEventRecord).filter_by(status="PENDING").all()
        for ev in pending_events:
            assert ev.leased_at is None
