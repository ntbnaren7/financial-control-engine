from dataclasses import dataclass
from typing import Any, Optional
from enum import Enum

class IngestionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"
    SCHEMA_ERROR = "SCHEMA_ERROR"

@dataclass
class IngestionResult:
    status: IngestionStatus
    domain_object: Optional[Any] = None
    error_message: Optional[str] = None
