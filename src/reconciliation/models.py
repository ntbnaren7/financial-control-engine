from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
import hashlib
from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable
import uuid

from src.evidence.models import EntityType
from src.state.models import ExecutionState, KnowledgeState, ObservedFinancialState, ReconstructedState
from src.domain.refunds.models import Refund


class DiscrepancyType(str, Enum):
    """
    Typed taxonomy of reconciliation outcomes as defined by the specification.
    """
    MATCH = "MATCH"
    """Expectation perfectly satisfied by provider execution within limits."""

    IN_FLIGHT_PENDING = "IN_FLIGHT_PENDING"
    """Within configured SLA grace period; provider execution not yet proven."""

    EPISTEMIC_STALEMATE = "EPISTEMIC_STALEMATE"
    """SLA expired OR in-flight mutation occurred, but provider reality is UNKNOWN,
    incomplete, contradicted, or non-authoritative. Demands status query probe."""

    ABSENT_EXECUTION = "ABSENT_EXECUTION"
    """SLA has expired AND provider reality is AUTHORITATIVELY PROVEN to be
    NOT_EXECUTED. Actionable for V1 Control Policy evaluation."""

    VALUE_MISMATCH = "VALUE_MISMATCH"
    """Provider executed refund, but amount differs from expected_amount."""

    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    """Provider executed refund, but currency differs from expected currency."""

    CONTRADICTORY_TERMINALITY = "CONTRADICTORY_TERMINALITY"
    """Provider executed a terminal failure (e.g. chargeback closed/failed),
    incompatible with fulfillment."""

    ORPHANED_EXECUTION = "ORPHANED_EXECUTION"
    """Provider executed a mutation on this payment with no matching internal
    intent. Potential fraud, rogue script, or manual dashboard action."""

    EXCESS_EFFECT = "EXCESS_EFFECT"
    """Multiple provider executions detected for a single intent.
    Direct financial loss / duplicate refund. Requires immediate containment."""


@runtime_checkable
class FinancialExpectation(Protocol):
    """
    Immutable specification of an expected financial event originating from business systems.
    """
    @property
    def expectation_id(self) -> str: ...

    @property
    def intent_id(self) -> str: ...

    @property
    def entity_type(self) -> EntityType: ...

    @property
    def expected_amount(self) -> Decimal: ...

    @property
    def currency(self) -> str: ...

    @property
    def created_at(self) -> datetime: ...

    @property
    def sla_seconds(self) -> int: ...

    @property
    def source_system(self) -> str: ...

    @property
    def business_reason(self) -> str: ...

    def reconciliation_deadline(self) -> datetime: ...


@dataclass(frozen=True)
class ExpectedRefund:
    """
    Concrete expectation of a customer or operational refund.
    """
    refund_intent_id: str
    provider_payment_id: str
    amount: Decimal
    currency: str
    created_at: datetime
    sla_seconds: int = 300
    source_system: str = "OMS"
    business_reason: str = ""
    originating_trace_id: str = ""
    expectation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        if not self.refund_intent_id:
            raise ValueError("refund_intent_id cannot be empty")
        if not self.provider_payment_id:
            raise ValueError("provider_payment_id cannot be empty")
        if self.amount <= Decimal("0"):
            raise ValueError(f"amount must be strictly positive, got {self.amount}")
        if not self.currency:
            raise ValueError("currency cannot be empty")
        if self.sla_seconds < 0:
            raise ValueError(f"sla_seconds cannot be negative, got {self.sla_seconds}")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC)")

    @property
    def intent_id(self) -> str:
        return self.refund_intent_id

    @property
    def expected_amount(self) -> Decimal:
        return self.amount

    @property
    def entity_type(self) -> EntityType:
        return EntityType.REFUND_INTENT

    def reconciliation_deadline(self) -> datetime:
        return self.created_at + timedelta(seconds=self.sla_seconds)

    def get_provider_idempotency_key(self) -> str:
        """
        Derives the deterministic provider idempotency key strictly from
        payment and intent, matching V1 Refund.get_provider_idempotency_key().
        """
        key_content = f"{self.provider_payment_id}_REFUND_{self.refund_intent_id}"
        return hashlib.sha256(key_content.encode("utf-8")).hexdigest()

    def to_refund(self) -> "Refund":
        """
        Creates a V1 Refund instance from this expectation, maintaining the same
        intent_id and provider_payment_id for correct idempotency derivation.
        """
        from src.domain.refunds.models import Refund
        return Refund(
            provider_payment_id=self.provider_payment_id,
            amount=self.amount,
            currency=self.currency,
            refund_intent_id=self.refund_intent_id,
            business_reason=self.business_reason
        )

    @classmethod
    def create_new(
        cls,
        provider_payment_id: str,
        amount: Decimal,
        currency: str,
        created_at: datetime,
        sla_seconds: int = 300,
        business_reason: str = "",
        source_system: str = "OMS",
        originating_trace_id: str = "",
    ) -> ExpectedRefund:
        return cls(
            expectation_id=str(uuid.uuid4()),
            refund_intent_id=str(uuid.uuid4()),
            provider_payment_id=provider_payment_id,
            amount=amount,
            currency=currency.strip().upper(),
            created_at=created_at,
            sla_seconds=sla_seconds,
            source_system=source_system,
            business_reason=business_reason,
            originating_trace_id=originating_trace_id or str(uuid.uuid4()),
        )


@dataclass(frozen=True)
class ReconciliationResult:
    """
    Deterministic output of reconcile(expectation, reconstructed_state).
    """
    expectation_id: Optional[str]
    intent_id: str
    discrepancy_type: DiscrepancyType
    is_actionable: bool
    reconciliation_timestamp: datetime
    expected_amount: Optional[Decimal]
    expected_currency: Optional[str]
    observed_amount: Optional[Decimal]
    observed_currency: Optional[str]
    observed_knowledge_state: KnowledgeState
    reconstructed_state_ids: Tuple[str, ...]
    details: Dict[str, Any] = field(default_factory=dict, hash=False)

    @property
    def is_clean_match(self) -> bool:
        return self.discrepancy_type == DiscrepancyType.MATCH

    @property
    def requires_investigation(self) -> bool:
        return self.discrepancy_type in (
            DiscrepancyType.EPISTEMIC_STALEMATE,
            DiscrepancyType.ABSENT_EXECUTION,
            DiscrepancyType.VALUE_MISMATCH,
            DiscrepancyType.EXCESS_EFFECT,
            DiscrepancyType.CONTRADICTORY_TERMINALITY,
            DiscrepancyType.ORPHANED_EXECUTION,
            DiscrepancyType.CURRENCY_MISMATCH,
        )
