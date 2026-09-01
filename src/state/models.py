from src.evidence.models import EntityType
from enum import Enum
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

class ObservedFinancialState(str, Enum):
    """
    What the provider's financial system has done. Concrete only.
    Absence is represented as Optional[ObservedFinancialState] = None.
    """
    CAPTURED = "CAPTURED"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"
    PROCESSING = "PROCESSING"
    VOIDED = "VOIDED"


class KnowledgeState(str, Enum):
    """
    What the system can currently establish about a financial entity's state.
    """
    VERIFIED = "VERIFIED"          # Deterministic evidence established this
    UNKNOWN = "UNKNOWN"            # Cannot currently establish — epistemic gap
    CONTRADICTED = "CONTRADICTED"  # Two trusted observations are mutually incompatible


@dataclass(frozen=True)
class ReconstructedState:
    """
    Output of the pure StateEngine function. A view over immutable observations.
    """
    entity_type: EntityType
    entity_id: str
    observed_financial_state: Optional[ObservedFinancialState]
    knowledge_state: KnowledgeState
    observation_ids: Tuple[str, ...]  # Which ProviderObservation records produced this
    reconstructed_at: datetime
