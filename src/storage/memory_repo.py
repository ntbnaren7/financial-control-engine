from typing import Dict, List, Optional, Tuple, Iterable

from src.reconciliation.models import FinancialExpectation
from src.evidence.models import ProviderObservation

class MemoryRepository:
    def __init__(self):
        self._expectations: Dict[str, FinancialExpectation] = {}
        self._observations: Dict[str, List[ProviderObservation]] = {}

    def store_expectation(self, expectation: FinancialExpectation) -> None:
        # Keyed by intent_id as per correlation requirement
        self._expectations[expectation.intent_id] = expectation

    def store_observation(self, observation: ProviderObservation) -> None:
        intent_id = observation.entity_id
        if intent_id not in self._observations:
            self._observations[intent_id] = []
        self._observations[intent_id].append(observation)

    def get_reconciliation_batch(self) -> Iterable[Tuple[Optional[FinancialExpectation], List[ProviderObservation]]]:
        """
        Returns all correlated groups of (Expectation, Observations)
        """
        all_intent_ids = set(self._expectations.keys()) | set(self._observations.keys())
        for intent_id in all_intent_ids:
            exp = self._expectations.get(intent_id)
            obs = self._observations.get(intent_id, [])
            yield (exp, obs)
