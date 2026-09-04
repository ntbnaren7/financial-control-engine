#!/usr/bin/env python
import os
import time
import subprocess
import psycopg
import sys
import uuid
import datetime

# Database connection to the docker-compose postgres port
DB_URL = "postgresql://postgres:postgres@localhost:5432/fce"
DB_URL_SA = "postgresql+psycopg://postgres:postgres@localhost:5432/fce"

def run_cmd(cmd: list[str], check: bool = True) -> str:
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed with code {result.returncode}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        sys.exit(1)
    return result.stdout

def wait_for_db(timeout_sec=30):
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            with psycopg.connect(DB_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    return
        except psycopg.OperationalError:
            time.sleep(1)
    print("Database did not become available!")
    sys.exit(1)

def inject_events(count=10) -> list[str]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.storage.postgres.models import Base
    from src.domain.core.models import Expectation, Observation, ReconciliationResult, ReconciliationOutcome, DiscrepancyReason, CanonicalStatus
    from src.storage.postgres_substrate import PostgresExpectationRepository, PostgresObservationRepository, PostgresReconciliationResultRepository, PostgresControlEventRepository, ControlEventType
    
    engine = create_engine(DB_URL_SA)
    SessionMaker = sessionmaker(bind=engine)
    
    exp_repo = PostgresExpectationRepository(SessionMaker)
    obs_repo = PostgresObservationRepository(SessionMaker)
    recon_repo = PostgresReconciliationResultRepository(SessionMaker)
    evt_repo = PostgresControlEventRepository(SessionMaker)

    event_ids = []
    for _ in range(count):
        evt_id = uuid.uuid4().hex
        exp_id = f"exp_{evt_id}"
        obs_id = f"obs_{evt_id}"
        recon_id = f"rec_{evt_id}"
        
        exp_repo.save(Expectation(expectation_id=exp_id, domain="Refund", expected_canonical_status=CanonicalStatus.SETTLED, expected_amount=100, currency="INR", source_system="ledger"))
        obs_repo.save(Observation(observation_id=obs_id, provider="razorpay", provider_reference="ref1", observation_type="refund", canonical_status=CanonicalStatus.FAILED, observed_amount=100, currency="INR", evidence_ids=[]))
        recon_repo.save(ReconciliationResult(
            reconciliation_id=recon_id,
            expectation_id=exp_id,
            observation_ids=[obs_id],
            outcome=ReconciliationOutcome.DISCREPANCY,
            discrepancy_reason=DiscrepancyReason.AMOUNT_MISMATCH,
            reconciliation_reason="Test setup"
        ))
        
        published_evt_id = evt_repo.publish(ControlEventType.DISCREPANCY_DETECTED, {"reconciliation_id": recon_id})
        event_ids.append(published_evt_id) 
    return event_ids

def check_all_events_completed(timeout_sec=30):
    start = time.time()
    while time.time() - start < timeout_sec:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM v2_control_events WHERE status != 'PROCESSED'")
                row = cur.fetchone()
                count = row[0] if row else 0
                if count == 0:
                    return True
        time.sleep(1)
    return False

def count_worker_logs(worker_name: str, keyword: str) -> int:
    logs = run_cmd(["docker-compose", "logs", worker_name])
    return logs.count(keyword)

def get_in_progress_event():
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT event_id FROM v2_control_events WHERE status = 'IN_PROGRESS' LIMIT 1")
            row = cur.fetchone()
            return row[0] if row else None

def main():
    print("=== 1. Starting Docker Containers ===")
    run_cmd(["docker-compose", "down", "-v"])
    run_cmd(["docker-compose", "up", "-d", "--build"])
    
    print("=== 2. Waiting for DB and Migrations ===")
    wait_for_db()
    time.sleep(10)  # Give workers time to run alembic upgrade head and start
    
    print("=== 3. Validating Multi-Worker Processing ===")
    inject_events(10)
    if not check_all_events_completed(timeout_sec=30):
        print("Events were not completed in time!")
        print("Worker A Logs:")
        print(run_cmd(["docker-compose", "logs", "worker-a"]))
        print("Worker B Logs:")
        print(run_cmd(["docker-compose", "logs", "worker-b"]))
        sys.exit(1)
        
    print("Events completed. Checking worker logs for distribution...")
    # Give logs a moment to flush
    time.sleep(2)
    worker_a_processed = count_worker_logs("worker-a", "Verification SUCCEEDED for")
    worker_b_processed = count_worker_logs("worker-b", "Verification SUCCEEDED for")
    print(f"Worker-a processed: {worker_a_processed} events")
    print(f"Worker-b processed: {worker_b_processed} events")
    
    if worker_a_processed == 0 and worker_b_processed == 0:
        print("Workers did not log successful processing.")
        sys.exit(1)
    if worker_a_processed == 0 or worker_b_processed == 0:
        print("WARNING: One worker processed all events. Not a strict failure but indicates poor distribution in this run.")

    print("=== 4. Validating Crash Recovery ===")
    # Clear DB to make it easy
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM v2_active_incidents")
            cur.execute("DELETE FROM v2_control_events")
            conn.commit()

    print("Stopping worker-b to isolate worker-a...")
    run_cmd(["docker-compose", "stop", "worker-b"])
    
    print("Injecting test event...")
    [evt_id] = inject_events(1)
    
    print("Waiting for event to become IN_PROGRESS...")
    start_wait = time.time()
    in_progress = False
    while time.time() - start_wait < 10:
        in_prog_evt = get_in_progress_event()
        if in_prog_evt and in_prog_evt == evt_id:
            in_progress = True
            break
        time.sleep(0.1)
    
    if not in_progress:
        print("Event did not become IN_PROGRESS. worker-a logs:")
        print(run_cmd(["docker-compose", "logs", "worker-a"], check=False))
        sys.exit(1)
        
    print("Event is IN_PROGRESS. SIGKILLing worker-a!")
    run_cmd(["docker-compose", "kill", "-s", "SIGKILL", "worker-a"])
    
    print("Starting worker-b to recover the event...")
    run_cmd(["docker-compose", "start", "worker-b"])
    
    print("Waiting for event to be completed by worker-b...")
    if not check_all_events_completed(timeout_sec=15):
        print("worker-b failed to recover and complete the event.")
        run_cmd(["docker-compose", "logs", "worker-b"])
        sys.exit(1)
        
    recovery_logs = count_worker_logs("worker-b", "Recovered 1 stale events")
    if recovery_logs == 0:
        print("worker-b completed the event but did not log recovery!")
        sys.exit(1)
        
    print("Crash recovery successful!")
    
    print("=== 5. Shutdown Validation ===")
    run_cmd(["docker-compose", "stop"])
    
    print("✅ All Docker runtime validations passed successfully!")

if __name__ == "__main__":
    main()
