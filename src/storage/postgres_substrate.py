from datetime import datetime, timezone
import uuid
from typing import List, Optional

from sqlalchemy import Column, String, Integer, DateTime, JSON, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.domain.core.models import (
    Expectation, 
    Observation, 
    Evidence, 
    ReconciliationResult, 
    BusinessStatus, 
    ReconciliationOutcome
)
from src.storage.postgres.models import Base

class SubstrateExpectationRecord(Base):
    __tablename__ = 'v2_expectations'

    expectation_id = Column(String, primary_key=True)
    domain = Column(String, nullable=False)
    expected_state = Column(String, nullable=False)
    expected_amount = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    business_status = Column(SQLEnum(BusinessStatus), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    def to_domain(self) -> Expectation:
        return Expectation(
            expectation_id=self.expectation_id,
            domain=self.domain,
            expected_state=self.expected_state,
            expected_amount=self.expected_amount,
            currency=self.currency,
            source_system=self.source_system,
            business_status=self.business_status,
            created_at=self.created_at
        )

    @classmethod
    def from_domain(cls, exp: Expectation) -> "SubstrateExpectationRecord":
        return cls(
            expectation_id=exp.expectation_id,
            domain=exp.domain,
            expected_state=exp.expected_state,
            expected_amount=exp.expected_amount,
            currency=exp.currency,
            source_system=exp.source_system,
            business_status=exp.business_status,
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
        return Evidence(
            evidence_id=self.evidence_id,
            source=self.source,
            source_reference=self.source_reference,
            payload_hash=self.payload_hash,
            raw_payload_ref=self.raw_payload_ref,
            observed_at=self.observed_at,
            ingested_at=self.ingested_at
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
    
    provider_event_id = Column(String, nullable=True)
    provider_version = Column(String, nullable=True)
    
    observed_at = Column(DateTime(timezone=True), nullable=False)
    ingestion_event_id = Column(String, nullable=False, unique=True)

    __table_args__ = (
        UniqueConstraint('provider', 'provider_reference', 'observation_type', 'provider_event_id', name='uq_obs_instance_event'),
        UniqueConstraint('provider', 'provider_reference', 'observation_type', 'provider_version', name='uq_obs_instance_version'),
    )

    def to_domain(self) -> Observation:
        return Observation(
            observation_id=self.observation_id,
            provider=self.provider,
            provider_reference=self.provider_reference,
            observation_type=self.observation_type,
            observed_state=self.observed_state,
            observed_amount=self.observed_amount,
            currency=self.currency,
            evidence_ids=self.evidence_ids,
            provider_event_id=self.provider_event_id,
            provider_version=self.provider_version,
            observed_at=self.observed_at,
            ingestion_event_id=self.ingestion_event_id
        )

    @classmethod
    def from_domain(cls, obs: Observation) -> "SubstrateObservationRecord":
        return cls(
            observation_id=obs.observation_id,
            provider=obs.provider,
            provider_reference=obs.provider_reference,
            observation_type=obs.observation_type,
            observed_state=obs.observed_state,
            observed_amount=obs.observed_amount,
            currency=obs.currency,
            evidence_ids=obs.evidence_ids,
            provider_event_id=obs.provider_event_id,
            provider_version=obs.provider_version,
            observed_at=obs.observed_at,
            ingestion_event_id=obs.ingestion_event_id
        )


class SubstrateReconciliationResultRecord(Base):
    __tablename__ = 'v2_reconciliation_results'
    
    reconciliation_id = Column(String, primary_key=True)
    expectation_id = Column(String, nullable=False)
    observation_ids = Column(JSON, nullable=False, default=list)
    outcome = Column(SQLEnum(ReconciliationOutcome), nullable=False)
    reconciliation_reason = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    def to_domain(self) -> ReconciliationResult:
        return ReconciliationResult(
            reconciliation_id=self.reconciliation_id,
            expectation_id=self.expectation_id,
            observation_ids=self.observation_ids,
            outcome=self.outcome,
            reconciliation_reason=self.reconciliation_reason,
            created_at=self.created_at
        )

    @classmethod
    def from_domain(cls, rr: ReconciliationResult) -> "SubstrateReconciliationResultRecord":
        return cls(
            reconciliation_id=rr.reconciliation_id,
            expectation_id=rr.expectation_id,
            observation_ids=rr.observation_ids,
            outcome=rr.outcome,
            reconciliation_reason=rr.reconciliation_reason,
            created_at=rr.created_at
        )


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


class PostgresObservationRepository:
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def save(self, observation: Observation) -> None:
        with self.session_maker() as session:
            try:
                record = SubstrateObservationRecord.from_domain(observation)
                session.add(record)
                session.commit()
            except IntegrityError:
                session.rollback()
                # Ignore duplicate ingestion events or instances
                pass

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
