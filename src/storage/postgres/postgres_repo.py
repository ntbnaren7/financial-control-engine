from typing import List, Optional, Tuple, Iterable, Dict
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from src.reconciliation.models import FinancialExpectation, ExpectedRefund
from src.evidence.models import ProviderObservation
from src.storage.postgres.models import ExpectationRecord, ObservationRecord

class PostgresRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def store_expectation(self, expectation: FinancialExpectation) -> None:
        with self._session_factory() as session:
            # Upsert or ignore on conflict? The user specified UNIQUE(intent_id).
            # We want idempotency, so if intent_id already exists, we can ignore or update.
            # Using basic try/except for IntegrityError to implement idempotent append.
            record = ExpectationRecord(
                expectation_id=expectation.expectation_id,
                refund_intent_id=expectation.intent_id,
                provider_payment_id=expectation.provider_payment_id if hasattr(expectation, 'provider_payment_id') else "unknown",
                amount=str(expectation.expected_amount),
                currency=expectation.currency,
                created_at=expectation.created_at,
                sla_seconds=expectation.sla_seconds,
                source_system=expectation.source_system,
                business_reason=expectation.business_reason,
                originating_trace_id=getattr(expectation, 'originating_trace_id', '')
            )
            try:
                session.add(record)
                session.commit()
            except IntegrityError:
                session.rollback()
                # Idempotent ignore if it already exists

    def store_observation(self, observation: ProviderObservation) -> None:
        with self._session_factory() as session:
            record = ObservationRecord(
                id=str(observation.id),
                provider=observation.provider,
                event_id=observation.event_id,
                entity_type=observation.entity_type,
                entity_id=observation.entity_id,
                event_type=observation.event_type,
                payload=observation.payload,
                created_at=observation.created_at
            )
            try:
                session.add(record)
                session.commit()
            except IntegrityError:
                session.rollback()
                # Idempotent ignore if event_id already exists

    @property
    def _expectations(self) -> Dict[str, ExpectedRefund]:
        with self._session_factory() as session:
            expectations = session.query(ExpectationRecord).all()
            exp_dict: Dict[str, ExpectedRefund] = {}
            for e in expectations:
                dt = e.created_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                
                exp_dict[e.refund_intent_id] = ExpectedRefund(
                    refund_intent_id=e.refund_intent_id,
                    provider_payment_id=e.provider_payment_id,
                    amount=Decimal(e.amount),
                    currency=e.currency,
                    created_at=dt,
                    sla_seconds=e.sla_seconds,
                    source_system=e.source_system,
                    business_reason=e.business_reason,
                    originating_trace_id=e.originating_trace_id,
                    expectation_id=e.expectation_id
                )
            return exp_dict

    @property
    def _observations(self) -> Dict[str, List[ProviderObservation]]:
        with self._session_factory() as session:
            observations = session.query(ObservationRecord).order_by(ObservationRecord.created_at.asc()).all()
            obs_dict: Dict[str, List[ProviderObservation]] = {}
            for o in observations:
                dt = o.created_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                
                obs = ProviderObservation(
                    provider=o.provider,
                    event_id=o.event_id,
                    entity_type=o.entity_type,
                    entity_id=o.entity_id,
                    event_type=o.event_type,
                    payload=o.payload,
                    created_at=dt
                )
                import uuid
                obs.id = uuid.UUID(o.id)

                if obs.entity_id not in obs_dict:
                    obs_dict[obs.entity_id] = []
                obs_dict[obs.entity_id].append(obs)
            return obs_dict

    def get_reconciliation_batch(self) -> Iterable[Tuple[Optional[FinancialExpectation], List[ProviderObservation]]]:
        """
        Returns all correlated groups of (Expectation, Observations)
        """
        exp_dict = self._expectations
        obs_dict = self._observations

        all_intent_ids = set(exp_dict.keys()) | set(obs_dict.keys())
        for intent_id in all_intent_ids:
            exp = exp_dict.get(intent_id)
            obs_list = obs_dict.get(intent_id, [])
            yield (exp, obs_list)
