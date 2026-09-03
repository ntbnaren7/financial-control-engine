from typing import List, Dict

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
    For refunds/payments, the provider_reference uniquely identifies one execution.
    Multiple observations with the same provider_reference (e.g. PROCESSING -> PROCESSED)
    belong to the same execution.
    """
    groups: Dict[str, ExecutionGroup] = {}
    
    for obs in observations:
        # Execution identity is derived from the provider reference (or fallback to observation id)
        exec_id = obs.correlation_keys.provider_ref or obs.provider_reference or obs.observation_id
        
        if exec_id not in groups:
            groups[exec_id] = ExecutionGroup(exec_id)
        
        groups[exec_id].observations.append(obs)
        
    return list(groups.values())
