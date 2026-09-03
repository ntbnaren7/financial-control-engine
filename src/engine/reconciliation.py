from typing import List, Iterable, Optional
from datetime import datetime, timezone
from decimal import Decimal

from src.storage.memory_repo import MemoryRepository
from src.reconciliation.models import FinancialExpectation, ReconciliationResult
from src.evidence.models import ProviderObservation, EntityType
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.reconciliation.engine import reconcile

def utcnow():
    return datetime.now(timezone.utc)

class ReconciliationEngine:
    def __init__(self):
        self._state_engine = StateEngine()
        self._ordering_policy = TemporalOrderingPolicy()

    def _observed_amount(self, observations: List[ProviderObservation]) -> Optional[Decimal]:
        for obs in reversed(self._ordering_policy.sort_observations(observations)):
            a = obs.payload.get("amount")
            if a is not None:
                return Decimal(str(a))
        return None

    def _observed_currency(self, observations: List[ProviderObservation]) -> Optional[str]:
        for obs in reversed(self._ordering_policy.sort_observations(observations)):
            c = obs.payload.get("currency")
            if c:
                return c
        return None

    def _count_executions(self, observations: List[ProviderObservation]) -> int:
        return sum(
            1 for obs in observations
            if obs.payload.get("execution_state") == "EXECUTED"
        )

    def reconcile_batch(
        self,
        expectations: Iterable[FinancialExpectation],
        observations: Iterable[ProviderObservation],
        reconciliation_timestamp: Optional[datetime] = None
    ) -> List[ReconciliationResult]:
        if reconciliation_timestamp is None:
            reconciliation_timestamp = utcnow()
            
        repo = MemoryRepository()
        for exp in expectations:
            repo.store_expectation(exp)
        for obs in observations:
            repo.store_observation(obs)

        results = []
        for exp, obs_list in repo.get_reconciliation_batch():
            entity_id = exp.intent_id if exp else (obs_list[0].entity_id if obs_list else "unknown")
            # For now, default to REFUND_INTENT as the primary entity type.
            entity_type = EntityType.REFUND_INTENT if exp else (EntityType(obs_list[0].entity_type) if obs_list else EntityType.REFUND_INTENT)
            
            # Use StateEngine to reconstruct state
            reconstructed_state = self._state_engine.reconstruct_state(
                entity_type=entity_type,
                entity_id=entity_id,
                observations=obs_list,
                reconstructed_at=reconciliation_timestamp,
                ordering_policy=self._ordering_policy
            )
            
            exec_count = self._count_executions(obs_list)
            
            # Invoke V1 completely untouched
            result = reconcile(
                expectation=exp,
                reconstructed_state=reconstructed_state,
                reconciliation_timestamp=reconciliation_timestamp,
                observed_amount=self._observed_amount(obs_list),
                observed_currency=self._observed_currency(obs_list),
                matching_executions_count=max(exec_count, 1),
            )
            results.append(result)

        return results
