from datetime import datetime, timezone, timedelta
import uuid
from typing import List, Optional

from sqlalchemy import Column, String, Integer, DateTime, JSON, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.domain.core.models import (
    Expectation, 
    Observation, 
    Evidence, 
    ReconciliationResult, 
    BusinessStatus, 
    ReconciliationOutcome,
    CorrelationKeys
)
from src.storage.postgres.models import Base
from src.storage.substrate_repo import ObservationRepository

class SubstrateExpectationRecord(Base):
    __tablename__ = 'v2_expectations'

    expectation_id = Column(String, primary_key=True)
    domain = Column(String, nullable=False)
    expected_state = Column(String, nullable=False)
    expected_amount = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    business_status = Column(SQLEnum(BusinessStatus), nullable=False)
    correlation_keys = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False)

    def to_domain(self) -> Expectation:
        # Enforce UTC timezone for SQLite compatibility
        dt = self.created_at
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
            
        return Expectation( # type: ignore
            expectation_id=self.expectation_id, # type: ignore
            domain=self.domain, # type: ignore
            expected_state=self.expected_state, # type: ignore
            expected_amount=self.expected_amount, # type: ignore
            currency=self.currency, # type: ignore
            source_system=self.source_system, # type: ignore
            business_status=self.business_status, # type: ignore
            correlation_keys=CorrelationKeys(**(self.correlation_keys or {})), # type: ignore
            created_at=dt # type: ignore
        )

    @classmethod
    def from_domain(cls, exp: Expectation) -> "SubstrateExpectationRecord":
        from dataclasses import asdict
        c_keys = asdict(exp.correlation_keys) if exp.correlation_keys else {}
        return cls(
            expectation_id=exp.expectation_id,
            domain=exp.domain,
            expected_state=exp.expected_state,
            expected_amount=exp.expected_amount,
            currency=exp.currency,
            source_system=exp.source_system,
            business_status=exp.business_status,
            correlation_keys=c_keys,
            created_at=exp.created_at
        )


class SubstrateEvidenceRecord(Base):
    __tablename__ = 'v2_evidence'

    evidence_id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    source_reference = Column(String, nullable=False)
    payload_hash = Column(String, nullable=False)
    raw_payload_ref = Column(String, nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    def to_domain(self) -> Evidence:
        return Evidence( # type: ignore
            evidence_id=self.evidence_id, # type: ignore
            source=self.source, # type: ignore
            source_reference=self.source_reference, # type: ignore
            payload_hash=self.payload_hash, # type: ignore
            raw_payload_ref=self.raw_payload_ref, # type: ignore
            observed_at=self.observed_at, # type: ignore
            ingested_at=self.ingested_at # type: ignore
        )

    @classmethod
    def from_domain(cls, ev: Evidence) -> "SubstrateEvidenceRecord":
        return cls(
            evidence_id=ev.evidence_id,
            source=ev.source,
            source_reference=ev.source_reference,
            payload_hash=ev.payload_hash,
            raw_payload_ref=ev.raw_payload_ref,
            observed_at=ev.observed_at,
            ingested_at=ev.ingested_at
        )


class SubstrateObservationRecord(Base):
    __tablename__ = 'v2_observations'

    observation_id = Column(String, primary_key=True)
    provider = Column(String, nullable=False)
    provider_reference = Column(String, nullable=False)
    observation_type = Column(String, nullable=False)
    observed_state = Column(String, nullable=False)
    observed_amount = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    
    evidence_ids = Column(JSON, nullable=False, default=list)
    correlation_keys = Column(JSON, nullable=False, default=dict)
    
    provider_event_id = Column(String, nullable=True)
    provider_version = Column(String, nullable=True)
    
    observed_at = Column(DateTime(timezone=True), nullable=False)
    ingestion_event_id = Column(String, nullable=True, unique=True)

    __table_args__ = (
        UniqueConstraint('provider', 'provider_reference', 'observation_type', 'provider_event_id', name='uq_obs_instance_event'),
        UniqueConstraint('provider', 'provider_reference', 'observation_type', 'provider_version', name='uq_obs_instance_version'),
    )

    def to_domain(self) -> Observation:
        return Observation( # type: ignore
            observation_id=self.observation_id, # type: ignore
            provider=self.provider, # type: ignore
            provider_reference=self.provider_reference, # type: ignore
            observation_type=self.observation_type, # type: ignore
            observed_state=self.observed_state, # type: ignore
            observed_amount=self.observed_amount, # type: ignore
            currency=self.currency, # type: ignore
            evidence_ids=self.evidence_ids, # type: ignore
            correlation_keys=CorrelationKeys(**(self.correlation_keys or {})), # type: ignore
            provider_event_id=self.provider_event_id, # type: ignore
            provider_version=self.provider_version, # type: ignore
            observed_at=self.observed_at, # type: ignore
            ingestion_event_id=self.ingestion_event_id # type: ignore
        )

    @classmethod
    def from_domain(cls, obs: Observation) -> "SubstrateObservationRecord":
        from dataclasses import asdict
        c_keys = asdict(obs.correlation_keys) if obs.correlation_keys else {}
        return cls(
            observation_id=obs.observation_id,
            provider=obs.provider,
            provider_reference=obs.provider_reference,
            observation_type=obs.observation_type,
            observed_state=obs.observed_state,
            observed_amount=obs.observed_amount,
            currency=obs.currency,
            evidence_ids=obs.evidence_ids,
            correlation_keys=c_keys,
            provider_event_id=obs.provider_event_id,
            provider_version=obs.provider_version,
            observed_at=obs.observed_at,
            ingestion_event_id=obs.ingestion_event_id
        )


class SubstrateReconciliationResultRecord(Base):
    __tablename__ = 'v2_reconciliation_results'
    
    reconciliation_id = Column(String, primary_key=True)
    expectation_id = Column(String, nullable=True)
    observation_ids = Column(JSON, nullable=False, default=list)
    outcome = Column(SQLEnum(ReconciliationOutcome), nullable=False)
    reconciliation_reason = Column(String, nullable=False)
    from src.domain.core.models import DiscrepancyReason
    discrepancy_reason = Column(SQLEnum(DiscrepancyReason), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    def to_domain(self) -> ReconciliationResult:
        return ReconciliationResult( # type: ignore
            reconciliation_id=self.reconciliation_id, # type: ignore
            expectation_id=self.expectation_id, # type: ignore
            observation_ids=self.observation_ids, # type: ignore
            outcome=self.outcome, # type: ignore
            reconciliation_reason=self.reconciliation_reason, # type: ignore
            discrepancy_reason=self.discrepancy_reason, # type: ignore
            created_at=self.created_at # type: ignore
        )

    @classmethod
    def from_domain(cls, rr: ReconciliationResult) -> "SubstrateReconciliationResultRecord":
        return cls(
            reconciliation_id=rr.reconciliation_id,
            expectation_id=rr.expectation_id,
            observation_ids=rr.observation_ids,
            outcome=rr.outcome,
            reconciliation_reason=rr.reconciliation_reason,
            discrepancy_reason=rr.discrepancy_reason,
            created_at=rr.created_at
        )


from src.domain.investigation.models import CausalHypothesis
from enum import Enum as PyEnum

class InvestigationState(str, PyEnum):
    ACTIVE = "ACTIVE"
    INVESTIGATING = "INVESTIGATING"
    VERIFYING = "VERIFYING"
    RETRY_PENDING = "RETRY_PENDING"
    ESCALATED = "ESCALATED"
    COMPLETED = "COMPLETED"

class ControlEventType(str, PyEnum):
    OBSERVATION_INGESTED = "OBSERVATION_INGESTED"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"
    VERIFICATION_SUCCEEDED = "VERIFICATION_SUCCEEDED"

class V2ControlEventRecord(Base):
    __tablename__ = 'v2_control_events'
    
    event_id = Column(String, primary_key=True)
    event_type = Column(SQLEnum(ControlEventType), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default="PENDING") # PENDING, IN_PROGRESS, PROCESSED, FAILED
    created_at = Column(DateTime(timezone=True), nullable=False)
    leased_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)

class ActiveIncidentIdempotencyRecord(Base):
    __tablename__ = 'v2_active_incidents'
    
    # The active_subject is expectation_id for expectation-centric controls,
    # or observation_id for observation-centric controls (UNEXPECTED_EXECUTION)
    active_subject = Column(String, primary_key=True)
    discrepancy_reason = Column(String, primary_key=True)
    incident_id = Column(String, nullable=False, unique=True)
    
    state = Column(SQLEnum(InvestigationState), nullable=False, default=InvestigationState.ACTIVE)
    lease_owner = Column(String, nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    hypothesis_payload = Column(JSON, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False)


class PostgresExpectationRepository:
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def save(self, expectation: Expectation) -> None:
        with self.session_maker() as session:
            record = session.query(SubstrateExpectationRecord).filter_by(expectation_id=expectation.expectation_id).first()
            if record:
                # Expectation is mutable for business status
                record.business_status = expectation.business_status
            else:
                record = SubstrateExpectationRecord.from_domain(expectation)
                session.add(record)
            session.commit()

    def get(self, expectation_id: str) -> Optional[Expectation]:
        with self.session_maker() as session:
            record = session.query(SubstrateExpectationRecord).filter_by(expectation_id=expectation_id).first()
            return record.to_domain() if record else None

    def find_open(self) -> List[Expectation]:
        with self.session_maker() as session:
            records = session.query(SubstrateExpectationRecord).filter_by(business_status=BusinessStatus.OPEN).all()
            return [r.to_domain() for r in records]

    def find_by_correlation_keys(self, keys: "CorrelationKeys") -> List[Expectation]:
        from sqlalchemy import or_, func, cast, String
        with self.session_maker() as session:
            query = session.query(SubstrateExpectationRecord)
            filters = []
            is_sqlite = session.bind.dialect.name == 'sqlite'
            if keys.internal_ref:
                if is_sqlite:
                    filters.append(func.json_extract(SubstrateExpectationRecord.correlation_keys, '$.internal_ref') == keys.internal_ref)
                else:
                    filters.append(SubstrateExpectationRecord.correlation_keys['internal_ref'].as_string() == keys.internal_ref)
            if keys.provider_ref:
                if is_sqlite:
                    filters.append(func.json_extract(SubstrateExpectationRecord.correlation_keys, '$.provider_ref') == keys.provider_ref)
                else:
                    filters.append(SubstrateExpectationRecord.correlation_keys['provider_ref'].as_string() == keys.provider_ref)
            if not filters:
                return []
            records = query.filter(or_(*filters)).all()
            return [r.to_domain() for r in records]


class PostgresObservationRepository(ObservationRepository):
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def save(self, observation: Observation) -> None:
        """
        Persist an observation using upsert semantics.

        Two conflict scenarios are handled:
          1. uq_obs_instance_version  (provider, provider_reference, observation_type,
             provider_version)  — a second API poll for the same refund arrives;
             update the mutable fields so the canonical row reflects current state.
          2. uq_obs_instance_event    (provider, provider_reference, observation_type,
             provider_event_id) — a webhook is re-delivered; no-op (state is same).

        This ensures idempotent writes: retries after a crash never produce
        duplicate rows and never raise IntegrityError to callers.
        """
        from dataclasses import asdict
        c_keys = asdict(observation.correlation_keys) if observation.correlation_keys else {}
        values = dict(
            observation_id=observation.observation_id,
            provider=observation.provider,
            provider_reference=observation.provider_reference,
            observation_type=observation.observation_type,
            observed_state=observation.observed_state,
            observed_amount=observation.observed_amount,
            currency=observation.currency,
            evidence_ids=observation.evidence_ids,
            correlation_keys=c_keys,
            provider_event_id=observation.provider_event_id,
            provider_version=observation.provider_version,
            observed_at=observation.observed_at,
            ingestion_event_id=observation.ingestion_event_id,
        )
        stmt = (
            pg_insert(SubstrateObservationRecord)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_obs_instance_version",
                set_={
                    "observed_state": observation.observed_state,
                    "evidence_ids": observation.evidence_ids,
                    "observed_at": observation.observed_at,
                    "ingestion_event_id": observation.ingestion_event_id,
                },
                where=(
                    # Only advance the canonical row if incoming data is newer.
                    # Stale provider responses (older timestamps) are silently ignored.
                    SubstrateObservationRecord.observed_at < observation.observed_at
                ),
            )
        )
        with self.session_maker() as session:
            session.execute(stmt)
            session.commit()

    def get(self, observation_id: str) -> Optional[Observation]:
        with self.session_maker() as session:
            record = session.query(SubstrateObservationRecord).filter_by(observation_id=observation_id).first()
            return record.to_domain() if record else None

    def find_by_business_identity(self, provider: str, provider_reference: str, observation_type: str) -> List[Observation]:
        with self.session_maker() as session:
            records = session.query(SubstrateObservationRecord).filter_by(
                provider=provider,
                provider_reference=provider_reference,
                observation_type=observation_type
            ).all()
            return [r.to_domain() for r in records]

    def find_by_correlation_keys(self, keys: "CorrelationKeys") -> List[Observation]:
        from sqlalchemy import or_, func
        with self.session_maker() as session:
            query = session.query(SubstrateObservationRecord)
            filters = []
            is_sqlite = session.bind.dialect.name == 'sqlite'
            if keys.internal_ref:
                if is_sqlite:
                    filters.append(func.json_extract(SubstrateObservationRecord.correlation_keys, '$.internal_ref') == keys.internal_ref)
                else:
                    from sqlalchemy import cast, String
                    filters.append(cast(SubstrateObservationRecord.correlation_keys['internal_ref'], String) == f'"{keys.internal_ref}"')
            if keys.provider_ref:
                if is_sqlite:
                    filters.append(func.json_extract(SubstrateObservationRecord.correlation_keys, '$.provider_ref') == keys.provider_ref)
                else:
                    from sqlalchemy import cast, String
                    filters.append(cast(SubstrateObservationRecord.correlation_keys['provider_ref'], String) == f'"{keys.provider_ref}"')
                # Fallback to provider_reference column
                filters.append(SubstrateObservationRecord.provider_reference == keys.provider_ref)
            if not filters:
                return []
            records = query.filter(or_(*filters)).all()
            return [r.to_domain() for r in records]

    def get_all(self) -> List[Observation]:
        with self.session_maker() as session:
            records = session.query(SubstrateObservationRecord).all()
            return [r.to_domain() for r in records]


class PostgresEvidenceRepository:
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def save(self, evidence: Evidence) -> None:
        with self.session_maker() as session:
            try:
                record = SubstrateEvidenceRecord.from_domain(evidence)
                session.add(record)
                session.commit()
            except IntegrityError:
                session.rollback()
                pass

    def get(self, evidence_id: str) -> Optional[Evidence]:
        with self.session_maker() as session:
            record = session.query(SubstrateEvidenceRecord).filter_by(evidence_id=evidence_id).first()
            return record.to_domain() if record else None

    def get_by_ids(self, evidence_ids: List[str]) -> List[Evidence]:
        if not evidence_ids:
            return []
        with self.session_maker() as session:
            records = session.query(SubstrateEvidenceRecord).filter(
                SubstrateEvidenceRecord.evidence_id.in_(evidence_ids)
            ).all()
            return [r.to_domain() for r in records]


class PostgresActiveIncidentRepository:
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def count_active(self) -> int:
        with self.session_maker() as session:
            return session.query(ActiveIncidentIdempotencyRecord).filter(
                ActiveIncidentIdempotencyRecord.state != InvestigationState.COMPLETED,
                ActiveIncidentIdempotencyRecord.state != InvestigationState.ESCALATED
            ).count()
            
    def get_active_incident(self, active_subject: str, discrepancy_reason: str) -> Optional[ActiveIncidentIdempotencyRecord]:
        with self.session_maker() as session:
            return session.query(ActiveIncidentIdempotencyRecord).filter_by(
                active_subject=active_subject,
                discrepancy_reason=discrepancy_reason
            ).first()

    def try_claim_incident(self, active_subject: str, discrepancy_reason: str, incident_id: str) -> bool:
        """
        Attempts to create a new active incident tracking record.
        Returns True if successful (no active incident existed), False if one already exists.
        """
        with self.session_maker() as session:
            try:
                record = ActiveIncidentIdempotencyRecord(
                    active_subject=active_subject,
                    discrepancy_reason=discrepancy_reason,
                    incident_id=incident_id,
                    state=InvestigationState.ACTIVE,
                    created_at=datetime.now(timezone.utc)
                )
                session.add(record)
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False

    def acquire_lease(self, active_subject: str, discrepancy_reason: str, worker_id: str, ttl_seconds: int) -> Optional[ActiveIncidentIdempotencyRecord]:
        """
        Attempts to acquire a lease on an active or retry-pending incident.
        Returns the record if successful, None otherwise.
        """
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        expires_at = now + timedelta(seconds=ttl_seconds)
        
        with self.session_maker() as session:
            session.expire_on_commit = False
            from sqlalchemy import or_
            record = session.query(ActiveIncidentIdempotencyRecord).filter_by(
                active_subject=active_subject,
                discrepancy_reason=discrepancy_reason
            ).with_for_update().first()
            
            if not record:
                return None
                
            if record.state in [InvestigationState.ESCALATED, InvestigationState.COMPLETED]:
                return None
                
            # Can acquire if no lease, lease expired, or owner matches
            if record.lease_expires_at is None or record.lease_expires_at < now or record.lease_owner == worker_id:
                record.lease_owner = worker_id
                record.lease_expires_at = expires_at
                
                # Advance state if picking up fresh or from retry
                if record.state in [InvestigationState.ACTIVE, InvestigationState.RETRY_PENDING]:
                    # If we already have a hypothesis, go straight to VERIFYING
                    if record.hypothesis_payload:
                        record.state = InvestigationState.VERIFYING
                    else:
                        record.state = InvestigationState.INVESTIGATING
                        
                session.commit()
                session.expunge(record)
                return record
            return None

    def update_hypothesis(self, active_subject: str, discrepancy_reason: str, worker_id: str, hypothesis: CausalHypothesis) -> bool:
        """Saves the generated hypothesis and transitions state to VERIFYING."""
        with self.session_maker() as session:
            record = session.query(ActiveIncidentIdempotencyRecord).filter_by(
                active_subject=active_subject,
                discrepancy_reason=discrepancy_reason,
                lease_owner=worker_id
            ).first()
            
            if record:
                record.hypothesis_payload = hypothesis.model_dump(mode="json")
                record.state = InvestigationState.VERIFYING
                session.commit()
                return True
            return False

    def schedule_retry(self, active_subject: str, discrepancy_reason: str, worker_id: str, retry_delay_seconds: int) -> bool:
        """Transitions state to RETRY_PENDING and clears the current lease."""
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        
        with self.session_maker() as session:
            record = session.query(ActiveIncidentIdempotencyRecord).filter_by(
                active_subject=active_subject,
                discrepancy_reason=discrepancy_reason,
                lease_owner=worker_id
            ).first()
            
            if record:
                record.state = InvestigationState.RETRY_PENDING
                record.retry_count += 1
                record.next_retry_at = now + timedelta(seconds=retry_delay_seconds)
                record.lease_owner = None
                record.lease_expires_at = None
                session.commit()
                return True
            return False

    def release_incident(self, active_subject: str, discrepancy_reason: str, escalate: bool = False) -> None:
        """Removes or escalates the active incident record when resolved or permanently failed."""
        with self.session_maker() as session:
            if escalate:
                record = session.query(ActiveIncidentIdempotencyRecord).filter_by(
                    active_subject=active_subject,
                    discrepancy_reason=discrepancy_reason
                ).first()
                if record:
                    record.state = InvestigationState.ESCALATED
                    record.lease_owner = None
                    record.lease_expires_at = None
                    session.commit()
            else:
                session.query(ActiveIncidentIdempotencyRecord).filter_by(
                    active_subject=active_subject,
                    discrepancy_reason=discrepancy_reason
                ).delete()
                session.commit()

    def commit_verification_success(self, active_subject: str, discrepancy_reason: str, new_evidence: List["Evidence"], new_observations: List["Observation"], escalate: bool = False) -> None:
        """
        Atomically persists new evidence, upserts new observations, releases the incident,
        and publishes the OBSERVATION_INGESTED event to trigger re-reconciliation.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from dataclasses import asdict
        import uuid
        
        with self.session_maker() as session:
            # 1. Save Evidence (ON CONFLICT DO NOTHING)
            for ev in new_evidence:
                ev_stmt = pg_insert(SubstrateEvidenceRecord).values(
                    evidence_id=ev.evidence_id,
                    source=ev.source,
                    source_reference=ev.source_reference,
                    payload_hash=ev.payload_hash,
                    raw_payload_ref=ev.raw_payload_ref,
                    observed_at=ev.observed_at,
                    ingested_at=ev.ingested_at
                ).on_conflict_do_nothing(index_elements=['evidence_id'])
                session.execute(ev_stmt)

            # 2. Upsert Observations
            for obs in new_observations:
                c_keys = asdict(obs.correlation_keys) if obs.correlation_keys else {}
                obs_values = dict(
                    observation_id=obs.observation_id,
                    provider=obs.provider,
                    provider_reference=obs.provider_reference,
                    observation_type=obs.observation_type,
                    observed_state=obs.observed_state,
                    observed_amount=obs.observed_amount,
                    currency=obs.currency,
                    evidence_ids=obs.evidence_ids,
                    correlation_keys=c_keys,
                    provider_event_id=obs.provider_event_id,
                    provider_version=obs.provider_version,
                    observed_at=obs.observed_at,
                    ingestion_event_id=obs.ingestion_event_id,
                )
                obs_stmt = (
                    pg_insert(SubstrateObservationRecord)
                    .values(**obs_values)
                    .on_conflict_do_update(
                        constraint="uq_obs_instance_version",
                        set_={
                            "observed_state": obs.observed_state,
                            "evidence_ids": obs.evidence_ids,
                            "observed_at": obs.observed_at,
                            "ingestion_event_id": obs.ingestion_event_id,
                        },
                        where=(
                            SubstrateObservationRecord.observed_at < obs.observed_at
                        ),
                    )
                )
                session.execute(obs_stmt)
                
            # 3. Release or Escalate Incident
            if escalate:
                record = session.query(ActiveIncidentIdempotencyRecord).filter_by(
                    active_subject=active_subject,
                    discrepancy_reason=discrepancy_reason
                ).first()
                if record:
                    record.state = InvestigationState.ESCALATED
                    record.lease_owner = None
                    record.lease_expires_at = None
            else:
                session.query(ActiveIncidentIdempotencyRecord).filter_by(
                    active_subject=active_subject,
                    discrepancy_reason=discrepancy_reason
                ).delete()
            
            # 4. Publish Event
            if new_observations:
                event_id = str(uuid.uuid4())
                event_record = V2ControlEventRecord(
                    event_id=event_id,
                    event_type=ControlEventType.OBSERVATION_INGESTED,
                    payload={},
                    status="PENDING",
                    created_at=datetime.now(timezone.utc)
                )
                session.add(event_record)
                
            session.commit()


class PostgresReconciliationResultRepository:
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def save(self, result: ReconciliationResult) -> None:
        with self.session_maker() as session:
            record = SubstrateReconciliationResultRecord.from_domain(result)
            session.add(record)
            session.commit()

    def get(self, reconciliation_id: str) -> Optional[ReconciliationResult]:
        with self.session_maker() as session:
            record = session.query(SubstrateReconciliationResultRecord).filter_by(reconciliation_id=reconciliation_id).first()
            return record.to_domain() if record else None

class PostgresControlEventRepository:
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def count_pending(self) -> int:
        with self.session_maker() as session:
            return session.query(V2ControlEventRecord).filter_by(status="PENDING").count()

    def publish(self, event_type: ControlEventType, payload: dict) -> str:
        event_id = str(uuid.uuid4())
        with self.session_maker() as session:
            record = V2ControlEventRecord(
                event_id=event_id,
                event_type=event_type,
                payload=payload,
                status="PENDING",
                created_at=datetime.now(timezone.utc)
            )
            session.add(record)
            session.commit()
        return event_id

    def poll_pending_events(self, limit: int = 10) -> List[V2ControlEventRecord]:
        """
        Atomically claim up to `limit` PENDING events for this worker.

        Uses SELECT ... FOR UPDATE SKIP LOCKED so that two workers running
        concurrently never pick up the same event. Events are immediately
        transitioned to IN_PROGRESS inside the same transaction, preventing
        a second worker from seeing them on its next poll.
        """
        with self.session_maker() as session:
            session.expire_on_commit = False
            records = (
                session.query(V2ControlEventRecord)
                .filter(V2ControlEventRecord.status == "PENDING")
                .order_by(V2ControlEventRecord.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
                .all()
            )
            for record in records:
                record.status = "IN_PROGRESS"
                record.leased_at = datetime.now(timezone.utc)
            session.commit()
            session.expunge_all()
            return records

    def recover_stale_events(self, stale_threshold_seconds: int) -> int:
        """
        Atomically recover any IN_PROGRESS events that were leased longer than
        `stale_threshold_seconds` ago, returning them to PENDING state.
        """
        with self.session_maker() as session:
            stale_cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_threshold_seconds)
            updated_count = session.query(V2ControlEventRecord).filter(
                V2ControlEventRecord.status == "IN_PROGRESS",
                V2ControlEventRecord.leased_at < stale_cutoff
            ).update(
                {"status": "PENDING", "leased_at": None},
                synchronize_session=False
            )
            session.commit()
            return updated_count

    def mark_processed(self, event_id: str) -> None:
        with self.session_maker() as session:
            record = session.query(V2ControlEventRecord).filter_by(event_id=event_id).first()
            if record:
                record.status = "PROCESSED"
                record.processed_at = datetime.now(timezone.utc)
                session.commit()
                
    def mark_failed(self, event_id: str) -> None:
        with self.session_maker() as session:
            record = session.query(V2ControlEventRecord).filter_by(event_id=event_id).first()
            if record:
                record.status = "FAILED"
                record.processed_at = datetime.now(timezone.utc)
                session.commit()

