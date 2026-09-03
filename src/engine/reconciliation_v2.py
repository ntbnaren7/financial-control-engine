from typing import List
from src.domain.core.models import ReconciliationResult
from src.storage.postgres_substrate import PostgresExpectationRepository, PostgresObservationRepository
from src.engine.reconciliation_controls import evaluate_expectation_centric

class V2ReconciliationEngine:
    def __init__(
        self,
        exp_repo: PostgresExpectationRepository,
        obs_repo: PostgresObservationRepository
    ):
        self.exp_repo = exp_repo
        self.obs_repo = obs_repo

    def reconcile_batch(self) -> List[ReconciliationResult]:
        from src.engine.reconciliation_controls import evaluate_observation_centric
        results = []
        open_expectations = self.exp_repo.find_open()
        
        mapped_obs_ids = set()
        
        for exp in open_expectations:
            candidate_observations = self.obs_repo.find_by_correlation_keys(exp.correlation_keys)
            for obs in candidate_observations:
                mapped_obs_ids.add(obs.observation_id)
            res = evaluate_expectation_centric(exp, candidate_observations)
            if res:
                results.append(res)
                from src.observability.metrics import inc_reconciliation_outcome
                inc_reconciliation_outcome(res.outcome.value)
            
        if hasattr(self.obs_repo, "get_all"):
            all_observations = self.obs_repo.get_all()
            for obs in all_observations:
                if obs.observation_id not in mapped_obs_ids:
                    obs_result = evaluate_observation_centric(obs, [])
                    if obs_result:
                        results.append(obs_result)
                        from src.observability.metrics import inc_reconciliation_outcome
                        inc_reconciliation_outcome(obs_result.outcome.value)
            
        return results
