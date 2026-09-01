from src.integrations.provider import MockProviderAdapter, ProviderResponse, ProviderQueryConfidence

def test_provider_confidence_classification():
    """
    Proves that the adapter correctly distinguishes authoritative non-execution 
    from merely missing data or partial lookups.
    """
    adapter = MockProviderAdapter()
    
    # 1. Authoritative lookup -> refund absent
    auth_not_found = ProviderResponse(
        raw_status="not_found", 
        is_cached_response=False, 
        is_partial_lookup=False, 
        network_timeout=False, 
        refund_exists=False
    )
    assert adapter.query_refund_status("key_123", auth_not_found) == ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED

    # 2. Stale lookup -> refund absent
    stale_not_found = ProviderResponse(
        raw_status="not_found", 
        is_cached_response=True, 
        is_partial_lookup=False, 
        network_timeout=False, 
        refund_exists=False
    )
    assert adapter.query_refund_status("key_123", stale_not_found) == ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY

    # 3. Partial lookup -> refund absent
    partial_not_found = ProviderResponse(
        raw_status="not_found", 
        is_cached_response=False, 
        is_partial_lookup=True, 
        network_timeout=False, 
        refund_exists=False
    )
    assert adapter.query_refund_status("key_123", partial_not_found) == ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY

    # 4. Lookup timeout
    timeout_resp = ProviderResponse(
        raw_status="timeout", 
        is_cached_response=False, 
        is_partial_lookup=False, 
        network_timeout=True, 
        refund_exists=False
    )
    assert adapter.query_refund_status("key_123", timeout_resp) == ProviderQueryConfidence.QUERY_FAILED

    # 5. Refund actually exists
    auth_found = ProviderResponse(
        raw_status="processed", 
        is_cached_response=False, 
        is_partial_lookup=False, 
        network_timeout=False, 
        refund_exists=True
    )
    assert adapter.query_refund_status("key_123", auth_found) == ProviderQueryConfidence.AUTHORITATIVE_EXECUTED
