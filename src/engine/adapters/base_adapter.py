from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
from src.domain.core.models import Observation, Evidence


class DomainAdapter(ABC):
    """
    Abstract boundary for translating raw external provider/source data into
    canonical Domain Observation and Evidence representations.
    
    Invariants:
    1. Provider-specific statuses, vocabulary, and IDs are normalized here.
    2. The resulting Observation must use CanonicalStatus exclusively.
    3. The resulting Evidence contains the immutable raw audit trail and payload hash.
    4. Kernel layers downstream of DomainAdapter never receive raw provider strings.
    """

    @abstractmethod
    def normalize_payload(
        self,
        raw_payload: Dict[str, Any],
        headers: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Observation, Evidence]:
        """Translate raw provider payload into canonical Observation and Evidence pair."""
        ...
