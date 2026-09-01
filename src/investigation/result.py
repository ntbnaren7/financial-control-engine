from enum import Enum
from typing import Optional
from pydantic import BaseModel
from src.investigation.models import InvestigationProposal

class InvestigationStatus(str, Enum):
    ACCEPTED = "ACCEPTED"  
    # ACCEPTED: The proposal passed all Pydantic schema validation, structural invariants, 
    # and deterministic negative constraint admissibility checks.
    # CRITICAL: This designates epistemic admissibility for operator/downstream consumption; 
    # it does NOT assert that the proposed root cause is established ground-truth financial fact.
    
    API_ERROR = "API_ERROR"
    EMPTY_OUTPUT = "EMPTY_OUTPUT"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    INVARIANT_INVALID = "INVARIANT_INVALID"
    PROPOSAL_SEMANTIC_CONFLICT = "PROPOSAL_SEMANTIC_CONFLICT"  # Proposal contradicted authoritative evidence facts

class InvestigationResult(BaseModel):
    status: InvestigationStatus
    proposal: Optional[InvestigationProposal] = None
    validation_errors: list[str] = []
    failure_reason: Optional[str] = None
    latency_seconds: Optional[float] = None
    raw_output: Optional[str] = None
