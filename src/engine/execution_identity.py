import uuid
from typing import List, Dict, Optional

class ExecutionIdentity:
    @staticmethod
    def generate(idempotency_seed: Optional[str] = None) -> str:
        """
        Generates a deterministic execution identity if an idempotency_seed is provided,
        ensuring trace continuity across orchestrator crashes.
        """
        if idempotency_seed:
            return str(uuid.uuid5(uuid.NAMESPACE_OID, idempotency_seed))
        return str(uuid.uuid4())

from src.domain.core.models import Observation

class ExecutionGroup:
    def __init__(self, execution_identity: str):
        self.execution_identity = execution_identity
        self.observations: List[Observation] = []

    def get_latest_observation(self) -> Observation:
        """Returns the most recent observation in this execution group."""
        return sorted(self.observations, key=lambda o: o.observed_at)[-1]

def group_by_execution(observations: List[Observation]) -> List[ExecutionGroup]:
    """
    Groups a list of observations into unique executions.
    The primary execution identity is the business correlation ID (internal_ref).
    If missing, it falls back to the provider reference or observation id.
    All observations belonging to one business execution must resolve to the same execution identity.
    """
    groups: Dict[str, ExecutionGroup] = {}
    
    for obs in observations:
        exec_id = None
        
        if obs.correlation_keys and obs.correlation_keys.internal_ref:
            exec_id = obs.correlation_keys.internal_ref
        elif obs.correlation_keys and obs.correlation_keys.provider_ref:
            exec_id = obs.correlation_keys.provider_ref
        elif obs.provider_reference:
            exec_id = obs.provider_reference
        else:
            exec_id = obs.observation_id
            
        if exec_id not in groups:
            groups[exec_id] = ExecutionGroup(exec_id)
        
        groups[exec_id].observations.append(obs)
        
    return list(groups.values())
