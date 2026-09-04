from enum import Enum

class IncidentState(str, Enum):
    # Core Flow
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    VERIFYING = "VERIFYING"
    ACTIONABLE = "ACTIONABLE"
    
    # Actuation Flow
    ACTUATION_PENDING = "ACTUATION_PENDING"
    ACTUATING = "ACTUATING"
    REOBSERVING = "REOBSERVING"

    # Terminal (Autonomous Escalations) - not permanently terminal, operator can retry
    ESCALATED_PAUSED_BY_KILL_SWITCH = "ESCALATED_PAUSED_BY_KILL_SWITCH"
    ESCALATED_BUDGET_EXHAUSTED = "ESCALATED_BUDGET_EXHAUSTED"
    ESCALATED_POLICY_BLOCKED = "ESCALATED_POLICY_BLOCKED"
    ESCALATED_MISSING_EVIDENCE = "ESCALATED_MISSING_EVIDENCE"
    ESCALATED_MUTATION_FAILED = "ESCALATED_MUTATION_FAILED"
    ESCALATED_CONVERGENCE_FAILED = "ESCALATED_CONVERGENCE_FAILED"
    ESCALATED_UNKNOWN = "ESCALATED_UNKNOWN"

    # Terminal (Resolved)
    RESOLVED = "RESOLVED"

    # Legacy / Unused (for migration compatibility)
    ACTIVE = "ACTIVE"
    RETRY_PENDING = "RETRY_PENDING"
    ESCALATED = "ESCALATED"
    COMPLETED = "COMPLETED"


class InvalidStateTransitionError(Exception):
    def __init__(self, current: IncidentState, target: IncidentState):
        super().__init__(f"Illegal incident transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


class IncidentStateMachine:
    VALID_TRANSITIONS = {
        # Entry points
        IncidentState.ACTIVE: {IncidentState.DETECTED, IncidentState.INVESTIGATING},
        IncidentState.RETRY_PENDING: {IncidentState.INVESTIGATING},

        IncidentState.DETECTED: {IncidentState.INVESTIGATING, IncidentState.ESCALATED_UNKNOWN},
        
        IncidentState.INVESTIGATING: {
            IncidentState.VERIFYING, 
            IncidentState.ACTIONABLE, 
            IncidentState.ESCALATED_MISSING_EVIDENCE,
            IncidentState.ESCALATED_UNKNOWN
        },
        
        IncidentState.VERIFYING: {
            IncidentState.ACTIONABLE,
            IncidentState.INVESTIGATING, # Retry scenario
            IncidentState.ESCALATED_MISSING_EVIDENCE,
            IncidentState.ESCALATED_UNKNOWN
        },
        
        IncidentState.ACTIONABLE: {
            IncidentState.ACTUATION_PENDING,
            IncidentState.RESOLVED, # Policy says no action
            IncidentState.ESCALATED_PAUSED_BY_KILL_SWITCH,
            IncidentState.ESCALATED_BUDGET_EXHAUSTED,
            IncidentState.ESCALATED_POLICY_BLOCKED,
            IncidentState.ESCALATED_UNKNOWN
        },
        
        IncidentState.ACTUATION_PENDING: {
            IncidentState.ACTUATING,
            IncidentState.ESCALATED_MUTATION_FAILED,
            IncidentState.ESCALATED_UNKNOWN
        },
        
        IncidentState.ACTUATING: {
            IncidentState.REOBSERVING,
            IncidentState.ESCALATED_MUTATION_FAILED,
            IncidentState.ESCALATED_UNKNOWN
        },
        
        IncidentState.REOBSERVING: {
            IncidentState.RESOLVED,
            IncidentState.ESCALATED_CONVERGENCE_FAILED,
            IncidentState.ESCALATED_UNKNOWN
        },
        
        # Escalations can be transitioned back to ACTIONABLE or INVESTIGATING by an operator (Step 4)
        IncidentState.ESCALATED_PAUSED_BY_KILL_SWITCH: {IncidentState.ACTIONABLE, IncidentState.RESOLVED},
        IncidentState.ESCALATED_BUDGET_EXHAUSTED: {IncidentState.ACTIONABLE, IncidentState.RESOLVED},
        IncidentState.ESCALATED_POLICY_BLOCKED: {IncidentState.ACTIONABLE, IncidentState.INVESTIGATING, IncidentState.RESOLVED},
        IncidentState.ESCALATED_MISSING_EVIDENCE: {IncidentState.INVESTIGATING, IncidentState.RESOLVED},
        IncidentState.ESCALATED_MUTATION_FAILED: {IncidentState.ACTUATION_PENDING, IncidentState.RESOLVED},
        IncidentState.ESCALATED_CONVERGENCE_FAILED: {IncidentState.REOBSERVING, IncidentState.RESOLVED},
        IncidentState.ESCALATED_UNKNOWN: {IncidentState.INVESTIGATING, IncidentState.ACTIONABLE, IncidentState.RESOLVED},
        
        # Legacy escalations for backwards compatibility
        IncidentState.ESCALATED: {IncidentState.INVESTIGATING, IncidentState.ACTIONABLE, IncidentState.RESOLVED},
        
        # Resolved is strictly terminal for autonomous execution, but could theoretically be re-opened manually? No, strict terminal.
        IncidentState.RESOLVED: set(),
        IncidentState.COMPLETED: set(),
    }

    @classmethod
    def assert_valid_transition(cls, current: IncidentState, target: IncidentState) -> None:
        if current == target:
            return # Self-transitions are usually fine, or maybe we want to reject them? Let's allow self-transitions for idempotency (e.g., retries or crash recovery).
            
        allowed_targets = cls.VALID_TRANSITIONS.get(current, set())
        if target not in allowed_targets:
            raise InvalidStateTransitionError(current, target)
