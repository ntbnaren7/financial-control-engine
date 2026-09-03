from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict

@dataclass(frozen=True)
class Evidence:
    """
    The primitive representation of a financial record before truth is established.
    Invariant: Evidence is not truth; it is merely an input claim.
    """
    evidence_id: str
    source: str          # e.g., 'internal_oms', 'razorpay_webhook', 'razorpay_api'
    entity_id: str       # The raw ID in the source system
    timestamp: datetime  # Event occurrence time
    evidence_type: str   # e.g., 'REFUND_CREATED', 'REFUND_FAILED', 'REFUND_INTENT'
    payload: Dict[str, Any] = field(default_factory=dict)  # Raw preserved payload
    provenance: Dict[str, Any] = field(default_factory=dict) # How the FCE received it
