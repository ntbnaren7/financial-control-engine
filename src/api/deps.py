"""
FastAPI dependency injection — shared app context.
All routers pull repositories from here rather than re-creating them.
"""
import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage.postgres_substrate import (
    PostgresActiveIncidentRepository,
    PostgresActuationRepository,
    PostgresObservationRepository,
    PostgresExpectationRepository,
    PostgresEvidenceRepository,
    PostgresReconciliationResultRepository,
)
from src.storage.postgres_governance import PostgresGovernanceRepository
from src.storage.postgres_ingestion import PostgresIngestionRepository


def _make_session_factory():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    engine = create_engine(db_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


_session_factory = None


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = _make_session_factory()
    return _session_factory


def get_incident_repo() -> PostgresActiveIncidentRepository:
    return PostgresActiveIncidentRepository(get_session_factory())


def get_actuation_repo() -> PostgresActuationRepository:
    return PostgresActuationRepository(get_session_factory())


def get_governance_repo() -> PostgresGovernanceRepository:
    return PostgresGovernanceRepository(get_session_factory())


def get_ingestion_repo() -> PostgresIngestionRepository:
    return PostgresIngestionRepository(get_session_factory())


def get_observation_repo() -> PostgresObservationRepository:
    return PostgresObservationRepository(get_session_factory())


def get_reconciliation_repo() -> PostgresReconciliationResultRepository:
    return PostgresReconciliationResultRepository(get_session_factory())


def get_evidence_repo() -> PostgresEvidenceRepository:
    return PostgresEvidenceRepository(get_session_factory())
