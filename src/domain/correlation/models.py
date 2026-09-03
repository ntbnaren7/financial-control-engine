from enum import Enum
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from src.domain.evidence.models import Evidence

class CorrelationStatus(str, Enum):
    CORRELATED = "CORRELATED"
    UNMATCHED = "UNMATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    TEMPORAL_VIOLATION = "TEMPORAL_VIOLATION"

@dataclass(frozen=True)
class CorrelationResult:
    """
    Exposes *why* the records were correlated (or why they failed).
    """
    internal_evidence: Optional[Evidence]
    provider_evidence: Optional[Evidence]
    
    status: CorrelationStatus
    
    # Metadata on why
    matched_by: Optional[str] = None
    temporal_check: bool = False
    entity_scope: bool = False
    amount_check: bool = False
    currency_check: bool = False
    
    def is_correlated(self) -> bool:
        return self.status == CorrelationStatus.CORRELATED

@dataclass
class CorrelationContext:
    """
    A grouping of Evidence objects that mathematically relate to the same financial event lifecycle.
    For refunds: usually 1 internal intent + 0..N provider webhooks/API results.
    """
    intent: Optional[Evidence] = None
    provider_records: List[Evidence] = field(default_factory=list)
    results: List[CorrelationResult] = field(default_factory=list)
