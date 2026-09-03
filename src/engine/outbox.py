from typing import Dict, List, Optional
from src.domain.actions.models import Action, ActionStatus

class ActionOutbox:
    def __init__(self):
        self._actions: Dict[str, Action] = {}

    def append(self, action: Action) -> None:
        if action.idempotency_key not in self._actions:
            self._actions[action.idempotency_key] = action
            
    def get_pending(self) -> List[Action]:
        return [a for a in self._actions.values() if a.status == ActionStatus.PENDING]
        
    def update_status(self, idempotency_key: str, status: ActionStatus) -> None:
        if idempotency_key in self._actions:
            self._actions[idempotency_key].status = status
