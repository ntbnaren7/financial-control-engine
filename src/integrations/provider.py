from enum import Enum
from dataclasses import dataclass
from typing import Optional

class ProviderQueryConfidence(str, Enum):
    AUTHORITATIVE_NOT_EXECUTED = "AUTHORITATIVE_NOT_EXECUTED"
    AUTHORITATIVE_EXECUTED = "AUTHORITATIVE_EXECUTED"
    NON_AUTHORITATIVE_QUERY = "NON_AUTHORITATIVE_QUERY"
    QUERY_FAILED = "QUERY_FAILED"

@dataclass
class ProviderResponse:
    raw_status: str
    is_cached_response: bool
    is_partial_lookup: bool
    network_timeout: bool
    refund_exists: bool

class MockProviderAdapter:
    """
    Simulates a provider adapter. The adapter is strictly responsible for determining
    the ProviderQueryConfidence based on the provider semantics, without leaking business rules.
    """
    def query_refund_status(self, idempotency_key: str, scenario_override: Optional[ProviderResponse] = None) -> ProviderQueryConfidence:
        if scenario_override is None:
            return ProviderQueryConfidence.QUERY_FAILED
            
        if scenario_override.network_timeout:
            return ProviderQueryConfidence.QUERY_FAILED
            
        if scenario_override.is_cached_response or scenario_override.is_partial_lookup:
            return ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY
            
        if scenario_override.refund_exists:
            return ProviderQueryConfidence.AUTHORITATIVE_EXECUTED
            
        # If it's a real-time, comprehensive query and it's not found:
        return ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED
