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
            payload_id=self.payload_id,
            provider=self.provider,
            event_type=self.event_type,
            raw_payload=self.raw_payload,
            payload_hash=self.payload_hash,
            idempotency_key=self.idempotency_key,
            status=self.status,
            lease_owner=self.lease_owner,
            lease_expires_at=self.lease_expires_at,
            created_at=self.created_at,
            processed_at=self.processed_at,
            error_message=self.error_message,
        )


class PostgresIngestionRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save_payload(self, payload: IngestionPayload) -> Tuple[IngestionPayload, bool]:
        with self.session_factory() as session:
            existing = (
                session.query(SubstrateIngestionPayloadRecord)
                .filter_by(provider=payload.provider, idempotency_key=payload.idempotency_key)
                .first()
            )
            if existing:
                return existing.to_domain(), False

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
