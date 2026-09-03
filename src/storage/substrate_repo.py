from typing import Protocol, List, Optional
from src.domain.core.models import Expectation, Observation, Evidence, ReconciliationResult
from src.domain.core.models import Expectation, Observation, Evidence, ReconciliationResult, CorrelationKeys
from abc import ABC, abstractmethod

class ExpectationRepository(Protocol):
    def save(self, expectation: Expectation) -> None:
        ...
    def get(self, expectation_id: str) -> Optional[Expectation]:
        ...
    def find_open(self) -> List[Expectation]:
        ...
    def find_by_correlation_keys(self, keys: CorrelationKeys) -> List[Expectation]:
        ...

class ObservationRepository(ABC):
    @abstractmethod
    def save(self, observation: Observation) -> None:
        ...
    @abstractmethod
    def get(self, observation_id: str) -> Optional[Observation]:
        ...
    @abstractmethod
    def find_by_business_identity(self, provider: str, provider_reference: str, observation_type: str) -> List[Observation]:
        ...
    @abstractmethod
    def find_by_correlation_keys(self, keys: CorrelationKeys) -> List[Observation]:
        ...

class EvidenceRepository(Protocol):
    def save(self, evidence: Evidence) -> None:
        ...
    def get(self, evidence_id: str) -> Optional[Evidence]:
        ...
    def get_by_ids(self, evidence_ids: List[str]) -> List[Evidence]:
        ...

class ReconciliationResultRepository(Protocol):
    def save(self, result: ReconciliationResult) -> None:
        ...
    def get(self, reconciliation_id: str) -> Optional[ReconciliationResult]:
        ...


class MemoryExpectationRepository:
    def __init__(self):
        self._store = {}
        
    def save(self, expectation: Expectation) -> None:
        self._store[expectation.expectation_id] = expectation
        
    def get(self, expectation_id: str) -> Optional[Expectation]:
        return self._store.get(expectation_id)
        
    def find_open(self) -> List[Expectation]:
        from src.domain.core.models import BusinessStatus
        return [e for e in self._store.values() if e.business_status == BusinessStatus.OPEN]

    def find_by_correlation_keys(self, keys: CorrelationKeys) -> List[Expectation]:
        results = []
        for exp in self._store.values():
            if keys.internal_ref and exp.correlation_keys.internal_ref == keys.internal_ref:
                results.append(exp)
            elif keys.provider_ref and exp.correlation_keys.provider_ref == keys.provider_ref:
                results.append(exp)
        return results

class MemoryObservationRepository(ObservationRepository):
    def __init__(self):
        self._store = {}
        
    def save(self, observation: Observation) -> None:
        self._store[observation.observation_id] = observation
        
    def get(self, observation_id: str) -> Optional[Observation]:
        return self._store.get(observation_id)
        
    def find_by_business_identity(self, provider: str, provider_reference: str, observation_type: str) -> List[Observation]:
        return [
            o for o in self._store.values()
            if o.provider == provider 
            and o.provider_reference == provider_reference 
            and o.observation_type == observation_type
        ]

    def find_by_correlation_keys(self, keys: CorrelationKeys) -> List[Observation]:
        results = []
        for obs in self._store.values():
            if keys.internal_ref and obs.correlation_keys.internal_ref == keys.internal_ref:
                results.append(obs)
            elif keys.provider_ref and obs.correlation_keys.provider_ref == keys.provider_ref:
                results.append(obs)
            elif keys.provider_ref and obs.provider_reference == keys.provider_ref: # Fallback
                results.append(obs)
        return results

class MemoryEvidenceRepository:
    def __init__(self):
        self._store = {}
        
    def save(self, evidence: Evidence) -> None:
        self._store[evidence.evidence_id] = evidence
        
    def get(self, evidence_id: str) -> Optional[Evidence]:
        return self._store.get(evidence_id)
        
    def get_by_ids(self, evidence_ids: List[str]) -> List[Evidence]:
        return [self._store[eid] for eid in evidence_ids if eid in self._store]

class MemoryReconciliationResultRepository:
    def __init__(self):
        self._store = {}
        
    def save(self, result: ReconciliationResult) -> None:
        self._store[result.reconciliation_id] = result
        
    def get(self, reconciliation_id: str) -> Optional[ReconciliationResult]:
        return self._store.get(reconciliation_id)
