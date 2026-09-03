"""
Tests for the FCE metrics registry to ensure fail-open logic and metric definitions work.
"""

from src.observability.metrics import (
    inc_control_loop_outcome,
    inc_reconciliation_outcome,
    observe_investigation_latency,
    observe_cycle_resolution_latency,
    observe_incident_lifetime,
    inc_event_processed,
    observe_event_processing_latency,
    set_pending_events,
    set_active_incidents,
    inc_a3_failure,
    inc_a4_verification,
    observe_provider_latency,
    inc_lease_contention,
    inc_stale_event_dropped,
    FCE_CONTROL_LOOP_OUTCOMES
)

def test_metrics_fail_open():
    """
    Verify that calling metrics with invalid labels or types
    does not throw an exception, thanks to the @fail_open decorator.
    """
    # This would normally raise ValueError because the label is wrong or missing.
    # We simulate this by passing the wrong number of labels if it were direct,
    # but since our helper functions hardcode the label names, we just pass bad types
    # or rely on the decorator catching internal prometheus_client errors.
    
    # We can manually trigger an error by trying to access a label that doesn't exist
    # on the underlying prometheus object by calling the metric directly, but we want 
    # to test our wrappers. Let's just ensure the wrappers don't crash on normal input.
    inc_control_loop_outcome("resolved")
    inc_reconciliation_outcome("MATCH")
    observe_investigation_latency(1.5)
    observe_cycle_resolution_latency(2.0)
    observe_incident_lifetime(10.0)
    inc_event_processed("TEST_EVENT")
    observe_event_processing_latency("TEST_EVENT", 0.5)
    set_pending_events(5)
    set_active_incidents(2)
    inc_a3_failure("timeout")
    inc_a4_verification("razorpay", "SUCCEEDED")
    observe_provider_latency("razorpay", 0.2)
    inc_lease_contention()
    inc_stale_event_dropped()

    # Verify that the value was recorded for control loop outcome
    assert FCE_CONTROL_LOOP_OUTCOMES.labels(outcome="resolved")._value.get() >= 1

    # To truly test fail-open, we can monkeypatch the underlying prometheus metric
    # to raise an Exception and ensure our wrapper catches it.
    original_inc = FCE_CONTROL_LOOP_OUTCOMES.labels
    
    class MockLabels:
        def inc(self):
            raise RuntimeError("Simulated Prometheus Error")
            
    try:
        FCE_CONTROL_LOOP_OUTCOMES.labels = lambda **kwargs: MockLabels()
        # This should NOT raise an exception
        inc_control_loop_outcome("resolved")
    finally:
        FCE_CONTROL_LOOP_OUTCOMES.labels = original_inc
