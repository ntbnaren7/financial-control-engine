from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import uuid
from datetime import datetime, timezone

from src.domain.correlation.models import CorrelationContext
from src.reconciliation.models import ExpectedRefund, ReconciliationResult
from src.state.models import ReconstructedState
from src.evidence.models import ProviderObservation

@dataclass
class ReconciliationCase:
    """
    The bounded entity generated for the V1 kernel.
    Distinctly separates input from derived artifacts.
    """
    correlation_context: CorrelationContext
    expectation: Optional[ExpectedRefund]
    provider_observations: List[ProviderObservation]
    
    case_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: Dict[str, Any] = field(default_factory=dict)
    
    # Derived Artifacts (Immutable once set)
    reconstructed_state: Optional[ReconstructedState] = None
    reconciliation_result: Optional[ReconciliationResult] = None
    
    def attach_derivatives(self, state: ReconstructedState, result: ReconciliationResult) -> "ReconciliationCase":
        """
        Creates a new case instance with derived artifacts attached, preserving immutability of the computation phase.
        """
        import copy
        new_case = copy.copy(self)
        new_case.reconstructed_state = state
        new_case.reconciliation_result = result
        return new_case
