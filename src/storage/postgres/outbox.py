from typing import List, Optional
from datetime import timezone, datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert

from src.domain.actions.models import Action, ActionType, ActionStatus
from src.storage.postgres.models import ActionRecord

class PostgresActionOutbox:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def append(self, action: Action) -> None:
        with self._session_factory() as session:
            record = ActionRecord(
                action_id=action.action_id,
                idempotency_key=action.idempotency_key,
                action_type=action.action_type,
                incident_id=action.incident_id,
                payload=action.payload,
                status=action.status,
                created_at=action.created_at
            )
            try:
                session.add(record)
                session.commit()
            except IntegrityError:
                session.rollback()
                # Idempotent ignore if idempotency_key already exists

    def get_pending(self) -> List[Action]:
        with self._session_factory() as session:
            # Note: We must consume this list within the transaction if we were really 
            # locking them for a worker to process. However, to match the current 
            # in-memory API which returns the list and then relies on `update_status`
            # to be called later, we will fetch them here with FOR UPDATE SKIP LOCKED
            # but then close the transaction. This releases the locks! 
            # 
            # In a true outbox pattern, the worker would lock, process, and update 
            # in a single transaction. For Phase J+, since we cannot change the ActionExecutor's 
            # loop which calls get_pending() then update_status() separately, we'll
            # perform a basic fetch. We still implement the SELECT FOR UPDATE SKIP LOCKED
            # so that if a worker transaction *were* held open, it would skip locked rows.
            
            records = session.query(ActionRecord).filter_by(
                status=ActionStatus.PENDING
            ).with_for_update(skip_locked=True).all()

            actions = []
            for record in records:
                actions.append(self._record_to_action(record))
            
            # Transaction closes here, locks are released. 
            return actions

    def update_status(self, idempotency_key: str, status: ActionStatus) -> None:
        with self._session_factory() as session:
            record = session.query(ActionRecord).filter_by(idempotency_key=idempotency_key).first()
            if record:
                record.status = status
                session.commit()

    def _record_to_action(self, record: ActionRecord) -> Action:
        dt = record.created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
            
        import typing
        from typing import Dict, Any

        return Action(
            action_type=typing.cast(ActionType, record.action_type),
            idempotency_key=str(record.idempotency_key),
            incident_id=str(record.incident_id),
            payload=typing.cast(Dict[str, Any], record.payload),
            action_id=str(record.action_id),
            status=typing.cast(ActionStatus, record.status),
            created_at=typing.cast(datetime, dt)
        )
