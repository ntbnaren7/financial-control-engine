from pydantic import BaseModel, ConfigDict
from typing import Dict, Any

class AuthorizationProvenance(BaseModel):
    """
    An immutable record capturing exactly *why* a financial mutation was authorized.
    This is generated from deterministic control facts.
    """
    model_config = ConfigDict(frozen=True)

    incident_id: str
    control_rule: str
    verified_facts: Dict[str, Any]
    atomic_precondition: str
    authorized: bool
    reason: str
