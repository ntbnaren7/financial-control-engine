from typing import List
from src.domain.core.models import Expectation, Observation
from src.storage.substrate_repo import ObservationRepository, ExpectationRepository

class CandidateSelector:
    def __init__(self, observation_repo: ObservationRepository, expectation_repo: ExpectationRepository):
        self.observation_repo = observation_repo
        self.expectation_repo = expectation_repo

    def select_observations_for_expectation(self, expectation: Expectation) -> List[Observation]:
        """
        Expectation-centric selection:
        Find candidate observations associated with the known keys of the expectation.
        """
        if not expectation.correlation_keys:
            return []
        return self.observation_repo.find_by_correlation_keys(expectation.correlation_keys)

    def select_expectations_for_observation(self, observation: Observation) -> List[Expectation]:
        """
        Observation-centric selection:
        Find candidate expectations that justify this observation.
        """
        if not observation.correlation_keys:
            # Fallback to provider_reference mapping if correlation_keys is missing
            from src.domain.core.models import CorrelationKeys
            fallback_keys = CorrelationKeys(provider_ref=observation.provider_reference)
            return self.expectation_repo.find_by_correlation_keys(fallback_keys)
        return self.expectation_repo.find_by_correlation_keys(observation.correlation_keys)
