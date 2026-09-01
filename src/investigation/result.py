from enum import Enum
from typing import Optional
from pydantic import BaseModel
from src.investigation.models import InvestigationProposal

class InvestigationStatus(str, Enum):
    ACCEPTED = "ACCEPTED"  # Proposal is structurally and semantically admissible (not necessarily proven true)
    API_ERROR = "API_ERROR"
    EMPTY_OUTPUT = "EMPTY_OUTPUT"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    INVARIANT_INVALID = "INVARIANT_INVALID"
    PROPOSAL_SEMANTIC_CONFLICT = "PROPOSAL_SEMANTIC_CONFLICT"  # Proposal contradicts authoritative facts

class InvestigationResult(BaseModel):
    status: InvestigationStatus
    proposal: Optional[InvestigationProposal] = None
    validation_errors: list[str] = []
    failure_reason: Optional[str] = None
    latency_seconds: Optional[float] = None
    raw_output: Optional[str] = None
