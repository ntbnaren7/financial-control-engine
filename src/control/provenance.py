from pydantic import BaseModel, ConfigDict
from typing import Dict, Optional

class AuthorizationProvenance(BaseModel):
    """
    An immutable record capturing exactly *why* a financial mutation was authorized.
    This is generated from deterministic control facts, not LLM rationale.
    """
    model_config = ConfigDict(frozen=True)

    incident_id: str
    m3_discrepancy: str
    m4_hypothesis: Optional[str]
    semantic_validation: str
    verified_facts: Dict[str, bool]
    control_rule: str
    fresh_merchant_state: str
    atomic_precondition: str
    authorized: bool
    reason: str
