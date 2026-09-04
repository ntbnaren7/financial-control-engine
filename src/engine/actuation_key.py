import hashlib
import json
from typing import Any, Dict

def generate_canonical_payload(mutation_parameters: Dict[str, Any]) -> str:
    """
    Sorts dictionary keys and serializes to a canonical JSON string.
    This ensures that logically identical dictionaries produce identical strings.
    """
    return json.dumps(mutation_parameters, sort_keys=True, separators=(',', ':'))

def generate_idempotency_key(execution_identity: str, intent_action: str, target_id: str, canonical_payload: str) -> str:
    """
    Generates a deterministic idempotency key safe for provider APIs (e.g. Razorpay).
    Requires keys to be at least 10 chars, alphanumeric/hyphens/underscores.
    We use the SHA-256 hex digest of the concatenated identity fields.
    """
    raw_string = f"{execution_identity}:{intent_action}:{target_id}:{canonical_payload}"
    digest = hashlib.sha256(raw_string.encode('utf-8')).hexdigest()
    # hex digest is alphanumeric and safe for headers
    return digest
