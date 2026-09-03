from typing import Dict, List, Optional
from src.domain.incidents.models import Incident

class IncidentRepository:
    """Thin in-memory repository for Incident lifecycle tracking."""
    def __init__(self):
        # Keyed by intent_id to easily map from expectations
        self._incidents_by_intent: Dict[str, Incident] = {}
        self._incidents_by_id: Dict[str, Incident] = {}

    def save(self, incident: Incident) -> None:
        self._incidents_by_id[incident.incident_id] = incident
        if incident.refund_intent_id:
            self._incidents_by_intent[incident.refund_intent_id] = incident

    def get_by_intent_id(self, intent_id: str) -> Optional[Incident]:
        return self._incidents_by_intent.get(intent_id)

    def get_all(self) -> List[Incident]:
        return list(self._incidents_by_id.values())
