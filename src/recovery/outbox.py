from enum import Enum
from typing import List, Optional, Dict
from dataclasses import dataclass, field
import uuid
import threading
from datetime import datetime, timezone

from src.domain.actions.models import Action

class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DISPATCHED = "DISPATCHED"
    RETRYABLE = "RETRYABLE"
    AMBIGUOUS = "AMBIGUOUS"

class ConcurrencyError(Exception):
    """
    Simulates a database IntegrityError for duplicate transactional records.
    """
    pass

@dataclass
class OutboxMessage:
    action: Action
    status: OutboxStatus = OutboxStatus.PENDING
    retry_count: int = 0
    next_retry_at: Optional[datetime] = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class TransactionalOutbox:
    """
    Simulates a persistent outbox. In a real system, the Action and OutboxMessage
    would be written to the database in a single transaction.
    """
    def __init__(self):
        self._messages: Dict[str, OutboxMessage] = {}
        self._lock = threading.Lock()

    def publish_action(self, action: Action):
        with self._lock:
            # Simulates a UNIQUE(action_type, idempotency_key) database constraint.
            # In V1, this composite key acts as a surrogate for the true business invariant:
            # UNIQUE(action_type, financial_intent_id). It ensures that at most one
            # executable action can be committed per refund intent operation.
            # We enforce this for any action that is currently "executable" to allow retries.
            for existing_msg in self._messages.values():
                if (existing_msg.action.action_type == action.action_type and 
                    existing_msg.action.idempotency_key == action.idempotency_key):
                    
                    if existing_msg.status in (OutboxStatus.PENDING, OutboxStatus.PROCESSING, OutboxStatus.DISPATCHED):
                        raise ConcurrencyError(
                            f"Concurrent authorization prevented. Executable action {action.action_type} "
                            f"with idempotency key {action.idempotency_key} already exists."
                        )
            
            msg = OutboxMessage(action=action)
            self._messages[msg.message_id] = msg

    def get_pending_messages(self) -> List[OutboxMessage]:
        with self._lock:
            return [
                msg for msg in self._messages.values() 
                if msg.status == OutboxStatus.PENDING
            ]
            
    def update_status(self, message_id: str, status: OutboxStatus):
        with self._lock:
            if message_id in self._messages:
                self._messages[message_id].status = status

class OutboxDispatcher:
    """
    Reads from TransactionalOutbox and dispatches to Provider Adapter.
    Translates transport results into outbox delivery states.
    Does NOT mutate financial knowledge state directly.
    """
    def __init__(self, outbox: TransactionalOutbox, provider_adapter):
        self.outbox = outbox
        self.provider = provider_adapter
        
    def process_pending(self):
        messages = self.outbox.get_pending_messages()
        for msg in messages:
            self.outbox.update_status(msg.message_id, OutboxStatus.PROCESSING)
            try:
                # Dispatch to provider
                # Provider adapter must return explicit result or raise known exceptions
                success = self.provider.dispatch_action(msg.action)
                if success:
                    self.outbox.update_status(msg.message_id, OutboxStatus.DISPATCHED)
                else:
                    # Clear non-ambiguous failure (if the provider API guarantees it failed validation)
                    self.outbox.update_status(msg.message_id, OutboxStatus.RETRYABLE)
            except Exception as e:
                # 5xx or transport loss -> AMBIGUOUS
                # Financial outcome is UNKNOWN
                self.outbox.update_status(msg.message_id, OutboxStatus.AMBIGUOUS)
