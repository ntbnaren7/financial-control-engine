import threading
from typing import Dict, Optional
from src.domain.actions.models import Action, ActionStatus

class ActionConcurrencyError(Exception):
    pass

class ActionRegistry:
    """
    Simulates a database table with a unique constraint on idempotency_key.
    Uses a thread lock to simulate atomic inserts.
    """
    def __init__(self):
        self._actions: Dict[str, Action] = {}
        self._lock = threading.Lock()

    def record_action_attempt(self, action: Action) -> Action:
        """
        Attempts to record an action. If the idempotency key already exists,
        it raises ActionConcurrencyError (simulating a unique constraint violation).
        """
        with self._lock:
            # Simulate DB unique constraint on idempotency_key
            for existing_action in self._actions.values():
                if existing_action.idempotency_key == action.idempotency_key:
                    raise ActionConcurrencyError(f"Duplicate idempotency key: {action.idempotency_key}")
            
            self._actions[action.action_id] = action
            return action

    def get_action_by_idempotency_key(self, idempotency_key: str) -> Optional[Action]:
        with self._lock:
            for action in self._actions.values():
                if action.idempotency_key == idempotency_key:
                    return action
            return None
