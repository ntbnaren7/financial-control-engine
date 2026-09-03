from enum import Enum
from typing import Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, field
import uuid

class BusinessStatus(str, Enum):
    CREATED = "CREATED"
    OPEN = "OPEN"
    SATISFIED = "SATISFIED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class ReconciliationOutcome(str, Enum):
    MATCH = "MATCH"
    DISCREPANCY = "DISCREPANCY"

@dataclass
class Expectation:
    """Internal financial intent or expected state."""
    domain: str  # e.g., "Refund", "Payout"
    expected_state: str
    expected_amount: int
    currency: str
    source_system: str
    expectation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    business_status: BusinessStatus = BusinessStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(frozen=True)
class Evidence:
    """Immutable provenance record justifying an observation."""
    source: str
    source_reference: str
    payload_hash: str
    raw_payload_ref: str
    observed_at: datetime
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass(frozen=True)
class Observation:
    """Immutable external financial report of state."""
    provider: str
    provider_reference: str
    observation_type: str
    observed_state: str
    observed_amount: int
    currency: str
    evidence_ids: List[str]
    # Instance Identity fields
    provider_event_id: Optional[str] = None
    provider_version: Optional[str] = None
    # Temporal metadata
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Delivery Identity
    ingestion_event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    observation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass(frozen=True)
class ReconciliationResult:
    """Deterministic, immutable result of comparing an expectation against candidate observations."""
    expectation_id: str
    observation_ids: List[str]
    outcome: ReconciliationOutcome
    reconciliation_reason: str
    reconciliation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
