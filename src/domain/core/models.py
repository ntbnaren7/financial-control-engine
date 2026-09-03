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

class DiscrepancyReason(str, Enum):
    ABSENT_EXECUTION = "ABSENT_EXECUTION"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    STATE_MISMATCH = "STATE_MISMATCH"
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"
    UNEXPECTED_EXECUTION = "UNEXPECTED_EXECUTION"
    SLA_BREACH = "SLA_BREACH"

@dataclass(frozen=True)
class CorrelationKeys:
    """Flexible correlation keys supporting partial knowledge."""
    internal_ref: Optional[str] = None
    provider_ref: Optional[str] = None
    provider: Optional[str] = None
    domain: Optional[str] = None
    observation_type: Optional[str] = None

@dataclass
class Expectation:
    """Internal financial intent or expected state."""
    domain: str  # e.g., "Refund", "Payout"
    expected_state: str
    expected_amount: int
    currency: str
    source_system: str
    correlation_keys: CorrelationKeys = field(default_factory=CorrelationKeys)
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
    correlation_keys: CorrelationKeys = field(default_factory=CorrelationKeys)
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
    expectation_id: Optional[str]
    observation_ids: List[str]
    outcome: ReconciliationOutcome
    reconciliation_reason: str
    discrepancy_reason: Optional[DiscrepancyReason] = None
    reconciliation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class RecoveryAction(str, Enum):
    REPAIR_MERCHANT_STATE = "REPAIR_MERCHANT_STATE"
    REFUND_PAYMENT = "REFUND_PAYMENT"
    ESCALATE = "ESCALATE"

class ActuationOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT_UNKNOWN = "TIMEOUT_UNKNOWN"
    REJECTED = "REJECTED"

@dataclass(frozen=True)
class RecoveryIntent:
    """Authorized intent derived from verified facts by deterministic policy."""
    action: RecoveryAction
    target_id: str
    amount: Optional[int] = None
    currency: Optional[str] = None
    reason: Optional[str] = None
    expected_provider_state: Optional[str] = None
    intent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
