from src.domain.investigation.lifecycle import IncidentState
"""
Unit tests for IncidentStateMachine.

Validates:
1. Every entry in VALID_TRANSITIONS is exercised.
2. ACTUATION_PENDING cannot directly reach RESOLVED.
3. REOBSERVING is the only predecessor to RESOLVED in the autonomous path.
4. Every ESCALATED_* state reachable from a live state is defined in IncidentState.
5. Invalid transitions raise InvalidStateTransitionError.
6. Self-transitions are idempotent (allowed, no error).
"""
import pytest
from src.domain.investigation.lifecycle import IncidentStateMachine, InvalidStateTransitionError


# ── 1. All valid transitions pass ─────────────────────────────────────────────

@pytest.mark.parametrize("source,target", [
    (source, target)
    for source, targets in IncidentStateMachine.VALID_TRANSITIONS.items()
    for target in targets
])
def test_valid_transitions_pass(source, target):
    IncidentStateMachine.assert_valid_transition(source, target)


# ── 2. Invalid transitions raise ──────────────────────────────────────────────

def test_invalid_transition_detected_to_resolved():
    with pytest.raises(InvalidStateTransitionError):
        IncidentStateMachine.assert_valid_transition(IncidentState.DETECTED, IncidentState.RESOLVED)

def test_invalid_transition_investigating_to_actuation_pending():
    with pytest.raises(InvalidStateTransitionError):
        IncidentStateMachine.assert_valid_transition(IncidentState.INVESTIGATING, IncidentState.ACTUATION_PENDING)

def test_invalid_transition_verifying_to_resolved():
    with pytest.raises(InvalidStateTransitionError):
        IncidentStateMachine.assert_valid_transition(IncidentState.VERIFYING, IncidentState.RESOLVED)

def test_resolved_is_strictly_terminal():
    """RESOLVED is a strict terminal state — no autonomous transitions out."""
    for state in IncidentState:
        if state == IncidentState.RESOLVED:
            continue
        with pytest.raises(InvalidStateTransitionError):
            IncidentStateMachine.assert_valid_transition(IncidentState.RESOLVED, state)


# ── 3. ACTUATION_PENDING / ACTUATING cannot skip REOBSERVING ──────────────────

def test_actuation_pending_cannot_reach_resolved_directly():
    """Financial safety: the system cannot skip REOBSERVING."""
    with pytest.raises(InvalidStateTransitionError):
        IncidentStateMachine.assert_valid_transition(IncidentState.ACTUATION_PENDING, IncidentState.RESOLVED)

def test_actuating_cannot_reach_resolved_directly():
    """Financial safety: must pass through REOBSERVING."""
    with pytest.raises(InvalidStateTransitionError):
        IncidentStateMachine.assert_valid_transition(IncidentState.ACTUATING, IncidentState.RESOLVED)


# ── 4. REOBSERVING invariant ──────────────────────────────────────────────────

def test_reobserving_is_valid_predecessor_of_resolved():
    IncidentStateMachine.assert_valid_transition(IncidentState.REOBSERVING, IncidentState.RESOLVED)

def test_reobserving_can_escalate_on_convergence_failure():
    IncidentStateMachine.assert_valid_transition(IncidentState.REOBSERVING, IncidentState.ESCALATED_CONVERGENCE_FAILED)

def test_reobserving_autonomous_predecessor_is_actuating():
    """Only ACTUATING should reach REOBSERVING in the autonomous path."""
    predecessors = {
        src
        for src, targets in IncidentStateMachine.VALID_TRANSITIONS.items()
        if IncidentState.REOBSERVING in targets
    }
    assert IncidentState.ACTUATING in predecessors
    assert IncidentState.RESOLVED not in predecessors
    assert IncidentState.INVESTIGATING not in predecessors
    assert IncidentState.VERIFYING not in predecessors


# ── 5. Full autonomous happy path ─────────────────────────────────────────────

def test_full_autonomous_happy_path():
    """
    Complete autonomous path must be a valid transition chain:
    DETECTED → INVESTIGATING → VERIFYING → ACTIONABLE →
    ACTUATION_PENDING → ACTUATING → REOBSERVING → RESOLVED
    """
    path = [
        IncidentState.DETECTED,
        IncidentState.INVESTIGATING,
        IncidentState.VERIFYING,
        IncidentState.ACTIONABLE,
        IncidentState.ACTUATION_PENDING,
        IncidentState.ACTUATING,
        IncidentState.REOBSERVING,
        IncidentState.RESOLVED,
    ]
    for i in range(len(path) - 1):
        IncidentStateMachine.assert_valid_transition(path[i], path[i + 1])


# ── 6. All ESCALATED_* states are reachable ───────────────────────────────────

def test_all_escalation_states_are_reachable():
    all_reachable = {
        target
        for targets in IncidentStateMachine.VALID_TRANSITIONS.values()
        for target in targets
    }
    escalation_states = [s for s in IncidentState if s.value.startswith("ESCALATED_")]
    for state in escalation_states:
        assert state in all_reachable, f"{state.value} is defined but never reachable"


# ── 7. Self-transitions are idempotent ────────────────────────────────────────

def test_self_transitions_are_allowed():
    for state in IncidentState:
        IncidentStateMachine.assert_valid_transition(state, state)  # must not raise


# ── 8. Terminal states ────────────────────────────────────────────────────────

def test_resolved_has_no_outbound_transitions():
    allowed = IncidentStateMachine.VALID_TRANSITIONS.get(IncidentState.RESOLVED, set())
    assert allowed == set()

def test_completed_has_no_outbound_transitions():
    allowed = IncidentStateMachine.VALID_TRANSITIONS.get(IncidentState.COMPLETED, set())
    assert allowed == set()


# ── 9. Error message is informative ──────────────────────────────────────────

def test_invalid_transition_error_message():
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        IncidentStateMachine.assert_valid_transition(IncidentState.DETECTED, IncidentState.RESOLVED)
    msg = str(exc_info.value)
    assert "DETECTED" in msg
    assert "RESOLVED" in msg
