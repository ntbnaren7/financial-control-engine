"""
P2.1 Observability: Centralized Metrics Registry for FCE.

This module defines all Prometheus metrics for the Financial Control Engine.
All instrumentation MUST be strictly observational and fail-open.
Errors in metric collection must never break the control loop.
"""

from src.observability.logging import get_logger
from typing import Callable, Any
from functools import wraps

from prometheus_client import Counter, Histogram, Gauge

logger = get_logger(__name__)


def fail_open(func: Callable) -> Callable:
    """
    Decorator to ensure metric emission never throws an exception
    into the business logic flow.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # We log at debug to avoid spamming the operational logs 
            # if Prometheus goes down or a label is wrong.
            logger.debug(f"Telemetry error ignored: {e}")
            return None
    return wrapper


# ---------------------------------------------------------------------------
# 1. Control-Loop & Reconciliation Outcomes
# ---------------------------------------------------------------------------
FCE_CONTROL_LOOP_OUTCOMES = Counter(
    "fce_control_loop_outcomes_total",
    "Macro outcomes of the FCE control loop.",
    ["outcome"] # 'resolved', 'retry_pending', 'escalated', 'unresolved'
)

FCE_RECONCILIATION_OUTCOMES = Counter(
    "fce_reconciliation_outcomes_total",
    "Outcomes of deterministic reconciliation.",
    ["outcome"] # 'MATCH', 'DISCREPANCY', 'UNEXPECTED_EXECUTION'
)

# ---------------------------------------------------------------------------
# 2. Latency Definitions
# ---------------------------------------------------------------------------
FCE_INVESTIGATION_LATENCY = Histogram(
    "fce_investigation_latency_seconds",
    "Time from starting A2 assembly to finishing A4 verification.",
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, float('inf'))
)

FCE_CYCLE_RESOLUTION_LATENCY = Histogram(
    "fce_cycle_resolution_latency_seconds",
    "Time from discrepancy detection to resulting MATCH.",
    buckets=(1.0, 5.0, 15.0, 60.0, 300.0, 1800.0, 3600.0, 86400.0, float('inf'))
)

FCE_INCIDENT_LIFETIME = Histogram(
    "fce_incident_lifetime_seconds",
    "Time from incident creation to terminal resolution/escalation.",
    buckets=(1.0, 5.0, 15.0, 60.0, 300.0, 1800.0, 3600.0, 86400.0, float('inf'))
)

# ---------------------------------------------------------------------------
# 3. Worker & Queue Health
# ---------------------------------------------------------------------------
FCE_EVENTS_PROCESSED = Counter(
    "fce_events_processed_total",
    "Total events processed by the worker.",
    ["event_type"]
)

FCE_EVENT_PROCESSING_LATENCY = Histogram(
    "fce_event_processing_latency_seconds",
    "Time taken to process a single event end-to-end.",
    ["event_type"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float('inf'))
)

FCE_PENDING_EVENTS = Gauge(
    "fce_pending_events",
    "Current number of events in PENDING state."
)

FCE_ACTIVE_INCIDENTS = Gauge(
    "fce_active_incidents",
    "Current number of incidents holding active leases or pending retries."
)

# ---------------------------------------------------------------------------
# 4. A3 & A4 Telemetry
# ---------------------------------------------------------------------------
FCE_A3_FAILURES = Counter(
    "fce_a3_failures_total",
    "Failures during A3 Investigation.",
    ["error_type"] # 'connection', 'timeout', 'structured_output', 'unknown'
)

FCE_A4_VERIFICATIONS = Counter(
    "fce_a4_verifications_total",
    "Outcomes of A4 Verifications.",
    ["provider", "status"] # status: 'SUCCEEDED', 'FAILED', 'REJECTED'
)

FCE_PROVIDER_LATENCY = Histogram(
    "fce_provider_latency_seconds",
    "Latency of read-only provider queries.",
    ["provider"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf'))
)

# ---------------------------------------------------------------------------
# 5. System Health
# ---------------------------------------------------------------------------
FCE_LEASE_CONTENTION = Counter(
    "fce_lease_contention_total",
    "Count of failed lease acquisitions (worker contention or lock).",
)

FCE_STALE_EVENTS_DROPPED = Counter(
    "fce_stale_events_dropped_total",
    "Count of lagging/duplicate events dropped because current state is MATCH.",
)

# ---------------------------------------------------------------------------
# Fail-Open Interface Methods
# ---------------------------------------------------------------------------
# We export safe wrapper functions to guarantee business logic never crashes
# if Prometheus metrics throw an error.

@fail_open
def inc_control_loop_outcome(outcome: str) -> None:
    FCE_CONTROL_LOOP_OUTCOMES.labels(outcome=outcome).inc()

@fail_open
def inc_reconciliation_outcome(outcome: str) -> None:
    FCE_RECONCILIATION_OUTCOMES.labels(outcome=outcome).inc()

@fail_open
def observe_investigation_latency(seconds: float) -> None:
    FCE_INVESTIGATION_LATENCY.observe(seconds)

@fail_open
def observe_cycle_resolution_latency(seconds: float) -> None:
    FCE_CYCLE_RESOLUTION_LATENCY.observe(seconds)

@fail_open
def observe_incident_lifetime(seconds: float) -> None:
    FCE_INCIDENT_LIFETIME.observe(seconds)

@fail_open
def inc_event_processed(event_type: str) -> None:
    FCE_EVENTS_PROCESSED.labels(event_type=event_type).inc()

@fail_open
def observe_event_processing_latency(event_type: str, seconds: float) -> None:
    FCE_EVENT_PROCESSING_LATENCY.labels(event_type=event_type).observe(seconds)

@fail_open
def set_pending_events(count: int) -> None:
    FCE_PENDING_EVENTS.set(count)

@fail_open
def set_active_incidents(count: int) -> None:
    FCE_ACTIVE_INCIDENTS.set(count)

@fail_open
def inc_a3_failure(error_type: str) -> None:
    FCE_A3_FAILURES.labels(error_type=error_type).inc()

@fail_open
def inc_a4_verification(provider: str, status: str) -> None:
    FCE_A4_VERIFICATIONS.labels(provider=provider, status=status).inc()

@fail_open
def observe_provider_latency(provider: str, seconds: float) -> None:
    FCE_PROVIDER_LATENCY.labels(provider=provider).observe(seconds)

@fail_open
def inc_lease_contention() -> None:
    FCE_LEASE_CONTENTION.inc()

@fail_open
def inc_stale_event_dropped() -> None:
    FCE_STALE_EVENTS_DROPPED.inc()
