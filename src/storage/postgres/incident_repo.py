from typing import List, Optional
from datetime import timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert

from src.domain.incidents.models import Incident, IncidentState
from src.reconciliation.models import DiscrepancyType
from src.storage.postgres.models import IncidentRecord

class PostgresIncidentRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def save(self, incident: Incident) -> None:
        with self._session_factory() as session:
            stmt = insert(IncidentRecord).values(
                incident_id=incident.incident_id,
                refund_intent_id=incident.refund_intent_id,
                lifecycle_state=incident.lifecycle_state,
                expectation_id=incident.expectation_id,
                provider_payment_id=incident.provider_payment_id,
                discrepancy_type=incident.discrepancy_type,
                discrepancy_instance_id=incident.discrepancy_instance_id,
                discrepancy_history=incident.discrepancy_history,
                reconciliation_timestamp=incident.reconciliation_timestamp,
                reconstructed_state_ids=incident.reconstructed_state_ids,
                evidence_references=incident.evidence_references,
                severity=incident.severity,
                provenance=incident.provenance,
                next_evaluation_at=incident.next_evaluation_at,
                deadline_at=incident.deadline_at,
                monitoring_reason=incident.monitoring_reason,
                query_count=incident.query_count
            )

            # Perform an UPSERT using PostgreSQL's ON CONFLICT DO UPDATE
            update_dict = {c.name: c for c in stmt.excluded if c.name != 'incident_id'}
            
            stmt = stmt.on_conflict_do_update(
                index_elements=['incident_id'],
                set_=update_dict
            )
            
            session.execute(stmt)
            session.commit()

    def get_by_intent_id(self, intent_id: str) -> Optional[Incident]:
        with self._session_factory() as session:
            record = session.query(IncidentRecord).filter_by(refund_intent_id=intent_id).first()
            if not record:
                return None
            return self._record_to_incident(record)

    def get_all(self) -> List[Incident]:
        with self._session_factory() as session:
            records = session.query(IncidentRecord).all()
            return [self._record_to_incident(record) for record in records]

    def _record_to_incident(self, record: IncidentRecord) -> Incident:
        def enforce_tz(dt):
            if dt and dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        import typing
        from typing import Dict, Any, List, Optional

        return Incident(
            incident_id=str(record.incident_id),
            lifecycle_state=typing.cast(IncidentState, record.lifecycle_state),
            expectation_id=str(record.expectation_id) if record.expectation_id else None,
            refund_intent_id=str(record.refund_intent_id) if record.refund_intent_id else None,
            provider_payment_id=str(record.provider_payment_id) if record.provider_payment_id else None,
            discrepancy_type=typing.cast(Optional[DiscrepancyType], record.discrepancy_type),
            discrepancy_instance_id=str(record.discrepancy_instance_id) if record.discrepancy_instance_id else None,
            discrepancy_history=typing.cast(List[str], record.discrepancy_history),
            reconciliation_timestamp=enforce_tz(record.reconciliation_timestamp),
            reconstructed_state_ids=typing.cast(List[str], record.reconstructed_state_ids),
            evidence_references=typing.cast(List[str], record.evidence_references),
            severity=str(record.severity),
            provenance=typing.cast(Optional[Dict[str, Any]], record.provenance),
            next_evaluation_at=enforce_tz(record.next_evaluation_at),
            deadline_at=enforce_tz(record.deadline_at),
            monitoring_reason=str(record.monitoring_reason) if record.monitoring_reason else None,
            query_count=int(str(record.query_count))
        )
