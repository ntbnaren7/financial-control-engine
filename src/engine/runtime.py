import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.reconciliation.models import ExpectedRefund, ReconciliationResult
from src.evidence.models import ProviderObservation
from src.storage.memory_repo import MemoryRepository
from src.engine.reconciliation import ReconciliationEngine
from src.engine.incidents import IncidentEngine
from src.domain.incidents.models import Incident

class Event:
    pass

class ExpectationReceived(Event):
    def __init__(self, expectation: ExpectedRefund):
        self.expectation = expectation

class ObservationReceived(Event):
    def __init__(self, observation: ProviderObservation):
        self.observation = observation

class ControlRuntime:
    def __init__(
        self,
        repository: MemoryRepository,
        reconciliation_engine: ReconciliationEngine,
        incident_engine: IncidentEngine,
    ):
        self._repo = repository
        self._recon_engine = reconciliation_engine
        self._incident_engine = incident_engine
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._intents_to_reconcile = set()

    async def ingest_event(self, event: Event):
        await self._queue.put(event)

    async def run_until_drained(self, now: datetime) -> List[Incident]:
        """
        Runs the control loop until the queue is empty.
        Returns the final incidents from the IncidentEngine repo.
        """
        while not self._queue.empty():
            event = await self._queue.get()
            
            if isinstance(event, ExpectationReceived):
                self._repo.store_expectation(event.expectation)
                self._intents_to_reconcile.add(event.expectation.refund_intent_id)
            elif isinstance(event, ObservationReceived):
                self._repo.store_observation(event.observation)
                self._intents_to_reconcile.add(event.observation.entity_id)
                
            self._queue.task_done()

        # Batch reconciliation trigger
        if self._intents_to_reconcile:
            exps_to_reconcile = []
            obs_to_reconcile = []
            
            grouped_expectations = self._repo._expectations
            grouped_observations = self._repo._observations

            for intent_id in self._intents_to_reconcile:
                exp = grouped_expectations.get(intent_id)
                if exp:
                    exps_to_reconcile.append(exp)
                obs_to_reconcile.extend(grouped_observations.get(intent_id, []))

            # Reconcile
            recon_results = self._recon_engine.reconcile_batch(exps_to_reconcile, obs_to_reconcile, reconciliation_timestamp=now)
            
            import typing
            grouped_expectations_cast = typing.cast(Dict[str, ExpectedRefund], grouped_expectations)
            
            # Pass to IncidentEngine
            await self._incident_engine.process_results(
                recon_results,
                grouped_expectations_cast,
                grouped_observations,
                now
            )
            self._intents_to_reconcile.clear()

        return self._incident_engine._repo.get_all()
