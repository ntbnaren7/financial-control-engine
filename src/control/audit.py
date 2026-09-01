import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict

# Create a dedicated logger for audit events
audit_logger = logging.getLogger("fce.audit")
audit_logger.setLevel(logging.INFO)

class Actor(str, Enum):
    SYSTEM = "SYSTEM"
    M3 = "M3"
    M4 = "M4"
    CONTROL = "CONTROL"
    RECOVERY = "RECOVERY"
    VERIFIER = "VERIFIER"

def emit_audit_event(
    incident_id: str,
    state: str,
    actor: Actor,
    reason: str,
    extra_context: Dict[str, Any] | None = None
) -> None:
    """
    Emits a structured JSON audit log for critical system transitions.
    """
    import uuid
    
    event = {
        "event_id": f"evt_audit_{uuid.uuid4().hex[:8]}",
        "incident_id": incident_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "actor": actor.value,
        "reason": reason
    }
    
    if extra_context:
        safe_context = {}
        for k, v in extra_context.items():
            if hasattr(v, "model_dump_json"):
                safe_context[k] = json.loads(v.model_dump_json(exclude_none=True))
            elif hasattr(v, "__dict__"):
                safe_context[k] = str(vars(v))
            else:
                safe_context[k] = str(v)
        event["context"] = safe_context

    audit_logger.info(json.dumps(event))
