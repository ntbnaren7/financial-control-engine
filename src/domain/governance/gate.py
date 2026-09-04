from typing import Optional
from dataclasses import dataclass
from enum import Enum

from src.domain.core.models import RecoveryIntent
from src.domain.actuation.models import ActuationRecord

class GovernanceGateDecision(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED_BY_KILL_SWITCH = "BLOCKED_BY_KILL_SWITCH"
    BLOCKED_BY_BUDGET = "BLOCKED_BY_BUDGET"
    CLAIM_FAILED = "CLAIM_FAILED"

@dataclass
class GateDecision:
    status: GovernanceGateDecision
    reason: str
    actuation_record: Optional[ActuationRecord] = None
