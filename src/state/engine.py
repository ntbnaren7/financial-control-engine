from src.evidence.models import EntityType
from typing import List, Optional
from datetime import datetime, timezone
from src.state.models import ReconstructedState, ObservedFinancialState, KnowledgeState, ExecutionState
from src.evidence.models import ProviderObservation, EntityType
from src.integrations.provider import ProviderQueryConfidence
from typing import cast, Any, Dict

def utcnow():
    return datetime.now(timezone.utc)

class TemporalOrderingPolicy:
    """
    Defines how observations should be ordered to resolve the latest financial truth.
    The exact hierarchy depends on the provider contract.
    """
    def sort_observations(self, observations: List[ProviderObservation]) -> List[ProviderObservation]:
        def sort_key(obs: ProviderObservation):
            payload = obs.payload if obs.payload else {}
            # Primary: provider event sequence/version (if available)
            provider_sequence = payload.get("provider_sequence", 0)
            
            # Secondary: provider explicit timestamp
            provider_ts_str = payload.get("provider_timestamp")
            if provider_ts_str:
                try:
                    # Try to parse ISO format if it's a string, or treat it as a unix timestamp if float/int
                    if isinstance(provider_ts_str, (int, float)):
                        provider_ts = float(provider_ts_str)
                    else:
                        provider_ts = datetime.fromisoformat(provider_ts_str.replace("Z", "+00:00")).timestamp()
                except (ValueError, TypeError):
                    provider_ts = 0.0
            else:
                provider_ts = 0.0

            # Tertiary: FCE ingestion timestamp
            ingestion_time = obs.created_at.timestamp() if obs.created_at else 0.0
            
            # Tie-breaker: Deterministic string sorting of observation ID
            return (provider_sequence, provider_ts, ingestion_time, str(obs.id))
            
        return sorted(observations, key=sort_key)

class StateEngine:
    """
    Pure deterministic function over immutable ProviderObservation records.
    """
    def reconstruct_state(
        self,
        entity_type: EntityType,
        entity_id: str,
        observations: List[ProviderObservation],
        reconstructed_at: datetime,
        ordering_policy: TemporalOrderingPolicy
    ) -> ReconstructedState:
        
        # Ensure all observations match the scoped entity
        for obs in observations:
            if obs.entity_type != entity_type.value or obs.entity_id != entity_id:
                raise ValueError(f"StateEngine received observation for mismatched entity scope: {obs.entity_type}:{obs.entity_id}")

        if not observations:
            return ReconstructedState(
                entity_type=entity_type,
                entity_id=entity_id,
                observed_financial_state=None,
                knowledge_state=KnowledgeState.UNKNOWN,
                execution=None,
                observation_ids=(),
                reconstructed_at=reconstructed_at
            )

        # Sort observations using the explicit temporal ordering policy
        sorted_obs = ordering_policy.sort_observations(observations)
        
        financial_state: Optional[ObservedFinancialState] = None
        knowledge_state: KnowledgeState = KnowledgeState.UNKNOWN
        execution: Optional[ExecutionState] = None
        obs_ids = []
        
        seen_concrete = False
        latest_is_not_executed = False
        latest_is_executed = False

        for obs in sorted_obs:
            obs_ids.append(str(obs.id))
            payload = obs.payload if obs.payload else {}
            
            status = payload.get("status")
            confidence = payload.get("query_confidence")

            if confidence == ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED.value:
                latest_is_not_executed = True
                financial_state = None
                knowledge_state = KnowledgeState.VERIFIED
                execution = ExecutionState.NOT_EXECUTED
                if seen_concrete or latest_is_executed:
                    # Provider says it never happened, but we previously saw it happen
                    knowledge_state = KnowledgeState.CONTRADICTED
                    execution = None
            elif confidence == ProviderQueryConfidence.AUTHORITATIVE_EXECUTED.value:
                latest_is_executed = True
                financial_state = None
                knowledge_state = KnowledgeState.VERIFIED
                execution = ExecutionState.EXECUTED
                if latest_is_not_executed:
                    knowledge_state = KnowledgeState.CONTRADICTED
                    execution = None
            elif status:
                try:
                    new_state = ObservedFinancialState(status.upper())
                    financial_state = new_state
                    seen_concrete = True
                    latest_is_not_executed = False
                    latest_is_executed = True  # A concrete status implies execution
                    knowledge_state = KnowledgeState.VERIFIED
                    execution = ExecutionState.EXECUTED
                except ValueError:
                    pass

        terminal_states = {ObservedFinancialState.CAPTURED.value, ObservedFinancialState.REFUNDED.value, ObservedFinancialState.FAILED.value, ObservedFinancialState.VOIDED.value}
        seen_terminals = set()
        for obs in sorted_obs:
            payload = obs.payload if obs.payload else {}
            st = payload.get("status")
            if st and st.upper() in terminal_states:
                seen_terminals.add(st.upper())
                
        if len(seen_terminals) > 1:
            knowledge_state = KnowledgeState.CONTRADICTED
            execution = None
            
        # Ensure observation IDs are deterministically ordered (alphabetical sort is fine for just the IDs)
        # However, it's better to preserve the semantic sorted order from the TemporalOrderingPolicy
        
        return ReconstructedState(
            entity_type=entity_type,
            entity_id=entity_id,
            observed_financial_state=financial_state,
            knowledge_state=knowledge_state,
            execution=execution,
            observation_ids=tuple(obs_ids),
            reconstructed_at=reconstructed_at
        )
