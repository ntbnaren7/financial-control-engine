import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import (
    Column,
    String,
    DateTime,
    JSON,
    Enum as SQLEnum,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.domain.ingestion.models import IngestionPayload, PayloadProcessingStatus
from src.storage.postgres.models import Base


class SubstrateIngestionPayloadRecord(Base):
    __tablename__ = "substrate_ingestion_payloads"

    payload_id = Column(String, primary_key=True)
    provider = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    raw_payload = Column(JSON, nullable=False)
    payload_hash = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    status = Column(SQLEnum(PayloadProcessingStatus), nullable=False, default=PayloadProcessingStatus.PENDING)
    lease_owner = Column(String, nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "idempotency_key", name="uq_ingestion_provider_idempotency"),
    )

    def to_domain(self) -> IngestionPayload:
        return IngestionPayload(
            payload_id=self.payload_id,  # type: ignore
            provider=self.provider,  # type: ignore
            event_type=self.event_type,  # type: ignore
            raw_payload=self.raw_payload,  # type: ignore
            payload_hash=self.payload_hash,  # type: ignore
            idempotency_key=self.idempotency_key,  # type: ignore
            status=self.status,  # type: ignore
            lease_owner=self.lease_owner,  # type: ignore
            lease_expires_at=self.lease_expires_at,  # type: ignore
            created_at=self.created_at,  # type: ignore
            processed_at=self.processed_at,  # type: ignore
            error_message=self.error_message,  # type: ignore
        )


class PostgresIngestionRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save_payload(self, payload: IngestionPayload) -> Tuple[IngestionPayload, bool]:
        import sqlalchemy.exc
        with self.session_factory() as session:
            try:
                record = SubstrateIngestionPayloadRecord(
                    payload_id=payload.payload_id,
                    provider=payload.provider,
                    event_type=payload.event_type,
                    raw_payload=payload.raw_payload,
                    payload_hash=payload.payload_hash,
                    idempotency_key=payload.idempotency_key,
                    status=payload.status,
                    lease_owner=payload.lease_owner,
                    lease_expires_at=payload.lease_expires_at,
                    created_at=payload.created_at,
                    processed_at=payload.processed_at,
                    error_message=payload.error_message,
                )
                session.add(record)
                session.commit()
                return record.to_domain(), True
            except sqlalchemy.exc.IntegrityError:
                session.rollback()
                existing = (
                    session.query(SubstrateIngestionPayloadRecord)
                    .filter_by(provider=payload.provider, idempotency_key=payload.idempotency_key)
                    .first()
                )
                if existing:
                    return existing.to_domain(), False
                raise

    def claim_pending_payloads(
        self, worker_id: str, limit: int = 10, lease_seconds: int = 30
    ) -> List[IngestionPayload]:
        now = datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=lease_seconds)

        with self.session_factory() as session:
            # FOR UPDATE SKIP LOCKED
            records = (
                session.query(SubstrateIngestionPayloadRecord)
                .filter(
                    (SubstrateIngestionPayloadRecord.status == PayloadProcessingStatus.PENDING)
                    | (
                        (SubstrateIngestionPayloadRecord.status == PayloadProcessingStatus.PROCESSING)
                        & (SubstrateIngestionPayloadRecord.lease_expires_at < now)
                    )
                )
                .with_for_update(skip_locked=True)
                .limit(limit)
                .all()
            )

            claimed = []
            for r in records:
                r.status = PayloadProcessingStatus.PROCESSING
                r.lease_owner = worker_id
                r.lease_expires_at = lease_until
                claimed.append(r.to_domain())

            session.commit()
            return claimed

    def mark_processed(self, payload_id: str, error: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            record = (
                session.query(SubstrateIngestionPayloadRecord)
                .filter_by(payload_id=payload_id)
                .first()
            )
            if record:
                record.status = (
                    PayloadProcessingStatus.FAILED if error else PayloadProcessingStatus.PROCESSED
                )
                record.processed_at = now
                record.error_message = error
                record.lease_owner = None
                record.lease_expires_at = None
                session.commit()

    def save_normalized_payload(self, payload_id: str, evidence: Any, observation: Any) -> None:
        """Atomically saves evidence, observation, and marks ingestion as processed."""
        from src.storage.postgres_substrate import SubstrateEvidenceRecord, SubstrateObservationRecord
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from dataclasses import asdict

        with self.session_factory() as session:
            # 1. Evidence
            ev_record = SubstrateEvidenceRecord.from_domain(evidence)
            ev_stmt = pg_insert(SubstrateEvidenceRecord).values(
                evidence_id=ev_record.evidence_id,
                source=ev_record.source,
                source_reference=ev_record.source_reference,
                payload_hash=ev_record.payload_hash,
                raw_payload_ref=ev_record.raw_payload_ref,
                observed_at=ev_record.observed_at,
                ingested_at=ev_record.ingested_at,
            ).on_conflict_do_nothing(index_elements=['evidence_id'])
            session.execute(ev_stmt)

            # 2. Observation
            c_keys = asdict(observation.correlation_keys) if observation.correlation_keys else {}
            status_str = observation.canonical_status.value if hasattr(observation.canonical_status, "value") else str(observation.canonical_status)
            obs_values = dict(
                observation_id=observation.observation_id,
                provider=observation.provider,
                provider_reference=observation.provider_reference,
                observation_type=observation.observation_type,
                observed_state=status_str,
                observed_amount=observation.observed_amount,
                currency=observation.currency,
                evidence_ids=observation.evidence_ids,
                correlation_keys=c_keys,
                provider_event_id=observation.provider_event_id,
                provider_version=observation.provider_version,
                observed_at=observation.observed_at,
                ingestion_event_id=observation.ingestion_event_id,
            )
            obs_stmt = (
                pg_insert(SubstrateObservationRecord)
                .values(**obs_values)
                .on_conflict_do_update(
                    constraint="uq_obs_instance_version",
                    set_={
                        "observed_state": status_str,
                        "evidence_ids": observation.evidence_ids,
                        "observed_at": observation.observed_at,
                        "ingestion_event_id": observation.ingestion_event_id,
                    },
                    where=(
                        SubstrateObservationRecord.observed_at < observation.observed_at
                    ),
                )
            )
            session.execute(obs_stmt)

            # 3. Mark processed
            payload_record = session.query(SubstrateIngestionPayloadRecord).filter_by(payload_id=payload_id).first()
            if payload_record:
                payload_record.status = PayloadProcessingStatus.PROCESSED
                payload_record.processed_at = datetime.now(timezone.utc)
            
            session.commit()


class MemoryIngestionRepository:
    """In-memory thread-safe implementation of IngestionRepository for unit tests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._store: Dict[str, IngestionPayload] = {}
        self._idempotency_map: Dict[Tuple[str, str], str] = {}

    def save_payload(self, payload: IngestionPayload) -> Tuple[IngestionPayload, bool]:
        with self._lock:
            key = (payload.provider, payload.idempotency_key)
            if key in self._idempotency_map:
                existing_id = self._idempotency_map[key]
                return self._store[existing_id], False

            self._store[payload.payload_id] = payload
            self._idempotency_map[key] = payload.payload_id
            return payload, True

    def claim_pending_payloads(
        self, worker_id: str, limit: int = 10, lease_seconds: int = 30
    ) -> List[IngestionPayload]:
        now = datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=lease_seconds)

        with self._lock:
            claimed: List[IngestionPayload] = []
            for payload in self._store.values():
                is_pending = payload.status == PayloadProcessingStatus.PENDING
                is_expired_lease = (
                    payload.status == PayloadProcessingStatus.PROCESSING
                    and payload.lease_expires_at is not None
                    and payload.lease_expires_at < now
                )
                if is_pending or is_expired_lease:
                    payload.status = PayloadProcessingStatus.PROCESSING
                    payload.lease_owner = worker_id
                    payload.lease_expires_at = lease_until
                    claimed.append(payload)
                    if len(claimed) >= limit:
                        break
            return claimed

    def mark_processed(self, payload_id: str, error: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            if payload_id in self._store:
                payload = self._store[payload_id]
                payload.status = (
                    PayloadProcessingStatus.FAILED if error else PayloadProcessingStatus.PROCESSED
                )
                payload.processed_at = now
                payload.error_message = error
                payload.lease_owner = None
                payload.lease_expires_at = None
