"""
Independent Provider Double — Financial Truth Oracle.

This module provides a strict provider-truth model that is completely
decoupled from FCE's internal domain objects. It independently tracks
provider-side state: requests, idempotency keys, actual financial effects,
replica lag, webhook emissions, and idempotency expiry.

It NEVER reads from FCE KnowledgeState, ReconstructedState, or ControlDecision.
Its effect count is the authoritative financial oracle for the test matrix.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from src.domain.actions.models import Action
from src.integrations.provider import ProviderQueryConfidence
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProviderRefundStatus(str, Enum):
    """Provider-side financial status for a refund request."""
    PENDING = "PENDING"       # Accepted, processing
    PROCESSED = "PROCESSED"   # Financial effect occurred
    REJECTED = "REJECTED"     # Explicitly refused by provider
    NOT_FOUND = "NOT_FOUND"   # No record of this key at this provider


class ProviderTransportResult(str, Enum):
    """What the provider transport layer returned for a mutation request."""
    ACCEPTED_EXECUTED = "ACCEPTED_EXECUTED"         # 200 + financial effect confirmed
    ACCEPTED_PENDING = "ACCEPTED_PENDING"           # 200 + processing async
    EXPLICITLY_REJECTED = "EXPLICITLY_REJECTED"     # 400 terminal, provider refused
    AMBIGUOUS_OUTCOME = "AMBIGUOUS_OUTCOME"         # Timeout, 5xx, network drop
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"  # 409 + payload differs for same key
    TRANSIENT_CONFLICT = "TRANSIENT_CONFLICT"       # 409 + concurrent request collision


class ProviderQueryResult(str, Enum):
    """What a provider status query returned."""
    AUTHORITATIVE_EXECUTED = "AUTHORITATIVE_EXECUTED"
    AUTHORITATIVE_NOT_EXECUTED = "AUTHORITATIVE_NOT_EXECUTED"
    NON_AUTHORITATIVE_QUERY = "NON_AUTHORITATIVE_QUERY"    # Stale replica, partial lookup
    QUERY_FAILED = "QUERY_FAILED"                           # Network / service failure


@dataclass
class ProviderRequest:
    """A recorded dispatch attempt from FCE to the provider."""
    request_id: str
    idempotency_key: str
    intent_id: str
    payload: dict       # amount, currency, payment_id
    submitted_at: datetime


@dataclass
class ProviderEffect:
    """A confirmed financial effect at the provider."""
    effect_id: str
    idempotency_key: str
    intent_id: str
    executed_at: datetime


@dataclass
class EmittedWebhook:
    """A webhook the provider would emit for a terminal event."""
    event_id: str
    intent_id: str
    idempotency_key: str
    status: ProviderRefundStatus
    provider_timestamp: datetime
    delivered: bool = False


@dataclass
class ProviderDouble:
    """
    The independent financial-truth oracle.

    Tracks provider-side state for refund intents. Its `financial_effects`
    dict is the ground truth for all invariant assertions in the test matrix.

    Configure scenarios via the public `configure_*` methods BEFORE dispatching.
    """

    # ── Idempotency ──────────────────────────────────────────────────────────
    # Maps idempotency_key → (payload_fingerprint, recorded_at)
    _idempotency_registry: Dict[str, Tuple[str, datetime]] = field(default_factory=dict)

    # Provider idempotency guarantee window (default: simulate "infinite" for simplicity;
    # set to a timedelta to test expiry scenarios)
    idempotency_retention: Optional[timedelta] = None

    # ── Financial Truth ───────────────────────────────────────────────────────
    # Maps intent_id → list of ProviderEffect (should always be len 0 or 1)
    _effects: Dict[str, List[ProviderEffect]] = field(default_factory=dict)

    # ── Request log ──────────────────────────────────────────────────────────
    _requests: Dict[str, ProviderRequest] = field(default_factory=dict)

    # ── Webhook queue ─────────────────────────────────────────────────────────
    _webhooks: Dict[str, List[EmittedWebhook]] = field(default_factory=dict)

    # ── Scenario overrides ────────────────────────────────────────────────────
    # Keys set here will always return AMBIGUOUS_OUTCOME (simulates timeout/5xx)
    _force_ambiguous_keys: set = field(default_factory=set)

    # Keys that will be silently dropped (provider receives but drops; no response)
    _force_drop_keys: set = field(default_factory=set)

    # Keys that produce explicit rejection
    _force_reject_keys: set = field(default_factory=set)

    # Keys that return ACCEPTED_PENDING (async; webhook fires later)
    _force_pending_keys: set = field(default_factory=set)

    # Controls whether query hits a stale/lagging replica
    _force_stale_query_keys: set = field(default_factory=set)

    # Controls whether queries always fail
    _force_query_failure_keys: set = field(default_factory=set)

    # ── Replica state ─────────────────────────────────────────────────────────
    # When True, the replicated query store lags behind the primary
    replica_lag_enabled: bool = False

    # ── Clock injection ───────────────────────────────────────────────────────
    _clock: datetime = field(default_factory=utcnow)

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _tick(self, seconds: float = 0) -> datetime:
        if seconds:
            self._clock = self._clock + timedelta(seconds=seconds)
        return self._clock

    def _payload_fingerprint(self, payload: dict) -> str:
        import hashlib, json
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _idempotency_valid(self, key: str) -> bool:
        """Returns True if the key is still within the provider's retention window."""
        if self.idempotency_retention is None:
            return True  # Infinite retention by default
        entry = self._idempotency_registry.get(key)
        if entry is None:
            return True  # Key never seen; trivially OK
        _, recorded_at = entry
        return (utcnow() - recorded_at) < self.idempotency_retention

    # ── Configuration API ─────────────────────────────────────────────────────
    def configure_ambiguous(self, idempotency_key: str) -> None:
        """Force AMBIGUOUS_OUTCOME for this key (simulates timeout / 5xx)."""
        self._force_ambiguous_keys.add(idempotency_key)

    def configure_drop(self, idempotency_key: str) -> None:
        """Provider silently processes and executes but drops the response connection."""
        self._force_drop_keys.add(idempotency_key)

    def configure_reject(self, idempotency_key: str) -> None:
        """Force EXPLICITLY_REJECTED for this key."""
        self._force_reject_keys.add(idempotency_key)

    def configure_pending(self, idempotency_key: str) -> None:
        """Force ACCEPTED_PENDING; provider queues and fires webhook separately."""
        self._force_pending_keys.add(idempotency_key)

    def configure_stale_query(self, idempotency_key: str) -> None:
        """Query for this key hits stale replica → NON_AUTHORITATIVE_QUERY."""
        self._force_stale_query_keys.add(idempotency_key)

    def configure_query_failure(self, idempotency_key: str) -> None:
        """Query for this key always fails → QUERY_FAILED."""
        self._force_query_failure_keys.add(idempotency_key)

    # ── Mutation API ──────────────────────────────────────────────────────────
    def dispatch_refund(
        self,
        intent_id: str,
        idempotency_key: str,
        payload: dict,
    ) -> ProviderTransportResult:
        """
        Simulate a provider refund dispatch. Records a ProviderRequest,
        checks idempotency, and applies scenario overrides.

        Returns the transport-level result (never an HTTP status code).
        """
        fingerprint = self._payload_fingerprint(payload)
        now = self._tick()

        # ── Idempotency check ──────────────────────────────────────────────
        existing = self._idempotency_registry.get(idempotency_key)
        if existing is not None:
            prior_fingerprint, recorded_at = existing
            if not self._idempotency_valid(idempotency_key):
                # Guarantee expired — provider no longer tracks this key
                # Remove from registry so it's treated as a fresh request
                del self._idempotency_registry[idempotency_key]
                # Fall through to normal processing below
            elif prior_fingerprint != fingerprint:
                # Same key, different payload — semantic integrity violation
                return ProviderTransportResult.IDEMPOTENCY_MISMATCH
            else:
                # Valid idempotent replay: return original outcome without new effect
                if intent_id in self._effects and self._effects[intent_id]:
                    return ProviderTransportResult.ACCEPTED_EXECUTED
                # Key was registered but no effect (e.g. was pending/rejected previously)
                return ProviderTransportResult.ACCEPTED_PENDING

        # ── Scenario overrides (first dispatch) ───────────────────────────
        request_id = str(uuid.uuid4())
        self._requests[request_id] = ProviderRequest(
            request_id=request_id,
            idempotency_key=idempotency_key,
            intent_id=intent_id,
            payload=payload,
            submitted_at=now,
        )

        if idempotency_key in self._force_reject_keys:
            self._idempotency_registry[idempotency_key] = (fingerprint, now)
            return ProviderTransportResult.EXPLICITLY_REJECTED

        if idempotency_key in self._force_ambiguous_keys:
            # Provider doesn't execute; no effect, no registry entry
            return ProviderTransportResult.AMBIGUOUS_OUTCOME

        if idempotency_key in self._force_drop_keys:
            # Provider DOES execute but drops the response
            self._idempotency_registry[idempotency_key] = (fingerprint, now)
            self._record_effect(intent_id, idempotency_key, now)
            self._queue_webhook(intent_id, idempotency_key, ProviderRefundStatus.PROCESSED, now)
            return ProviderTransportResult.AMBIGUOUS_OUTCOME   # FCE sees ambiguity

        if idempotency_key in self._force_pending_keys:
            self._idempotency_registry[idempotency_key] = (fingerprint, now)
            self._queue_webhook(intent_id, idempotency_key, ProviderRefundStatus.PROCESSED, now)
            return ProviderTransportResult.ACCEPTED_PENDING

        # ── Normal execution ──────────────────────────────────────────────
        self._idempotency_registry[idempotency_key] = (fingerprint, now)
        self._record_effect(intent_id, idempotency_key, now)
        self._queue_webhook(intent_id, idempotency_key, ProviderRefundStatus.PROCESSED, now)
        return ProviderTransportResult.ACCEPTED_EXECUTED

    def _record_effect(self, intent_id: str, idempotency_key: str, at: datetime) -> None:
        effect = ProviderEffect(
            effect_id=str(uuid.uuid4()),
            idempotency_key=idempotency_key,
            intent_id=intent_id,
            executed_at=at,
        )
        self._effects.setdefault(intent_id, []).append(effect)

    def _queue_webhook(
        self,
        intent_id: str,
        idempotency_key: str,
        status: ProviderRefundStatus,
        at: datetime,
    ) -> None:
        webhook = EmittedWebhook(
            event_id=str(uuid.uuid4()),
            intent_id=intent_id,
            idempotency_key=idempotency_key,
            status=status,
            provider_timestamp=at,
        )
        self._webhooks.setdefault(intent_id, []).append(webhook)

    # ── Query API ─────────────────────────────────────────────────────────────
    def query_refund_status(self, idempotency_key: str) -> ProviderQueryResult:
        """
        Simulate a provider status query for a given idempotency key.

        Returns a typed query result. Never exposes HTTP status codes.
        Respects stale-replica and query-failure overrides.
        """
        if idempotency_key in self._force_query_failure_keys:
            return ProviderQueryResult.QUERY_FAILED

        if idempotency_key in self._force_stale_query_keys:
            return ProviderQueryResult.NON_AUTHORITATIVE_QUERY

        if self.replica_lag_enabled:
            return ProviderQueryResult.NON_AUTHORITATIVE_QUERY

        # Find the intent_id for this key
        intent_id = self._key_to_intent(idempotency_key)

        if intent_id is None:
            # Key was never registered; authoritatively not executed
            return ProviderQueryResult.AUTHORITATIVE_NOT_EXECUTED

        if intent_id in self._effects and self._effects[intent_id]:
            return ProviderQueryResult.AUTHORITATIVE_EXECUTED

        return ProviderQueryResult.AUTHORITATIVE_NOT_EXECUTED

    def _key_to_intent(self, idempotency_key: str) -> Optional[str]:
        """Reverse-lookup from idempotency key to intent_id via request log."""
        for req in self._requests.values():
            if req.idempotency_key == idempotency_key:
                return req.intent_id
        return None

    # ── Webhook API ───────────────────────────────────────────────────────────
    def deliver_webhooks(self, intent_id: str) -> List[EmittedWebhook]:
        """Return pending webhooks for an intent and mark them delivered."""
        pending = [w for w in self._webhooks.get(intent_id, []) if not w.delivered]
        for w in pending:
            w.delivered = True
        return pending

    def deliver_webhook_at_offset(
        self, intent_id: str, offset_seconds: float
    ) -> List[EmittedWebhook]:
        """Simulate a late webhook delivery at a specific time offset."""
        self._tick(offset_seconds)
        return self.deliver_webhooks(intent_id)

    # ── Oracle API ────────────────────────────────────────────────────────────
    def get_financial_effect_count(self, intent_id: str) -> int:
        """
        The authoritative financial oracle.

        Returns the number of actual financial effects recorded for this intent.
        Valid values under provider idempotency guarantees: 0 or 1.
        If this returns > 1, the implementation has a double-spend bug.
        """
        return len(self._effects.get(intent_id, []))

    def assert_at_most_one_effect(self, intent_id: str) -> None:
        """
        Convenience assertion: raise AssertionError if effects > 1.
        Use this as the primary safety invariant in every test.
        """
        count = self.get_financial_effect_count(intent_id)
        if count > 1:
            raise AssertionError(
                f"INVARIANT VIOLATED: refund_intent_id={intent_id!r} "
                f"produced {count} financial effects. Expected at most 1."
            )

    def provider_knows_intent(self, idempotency_key: str) -> bool:
        """True if the provider has any record of this key."""
        return idempotency_key in self._idempotency_registry

    def get_emitted_webhooks(self, intent_id: str) -> List[EmittedWebhook]:
        return self._webhooks.get(intent_id, [])

    def advance_clock(self, seconds: float) -> datetime:
        """Advance the provider's internal clock by `seconds`."""
        return self._tick(seconds)

    def expire_idempotency_for(self, idempotency_key: str) -> None:
        """
        Force-expire the idempotency entry for a key.
        Used in Scenario P to simulate guarantee window expiry.
        """
        if idempotency_key in self._idempotency_registry:
            fingerprint, _ = self._idempotency_registry[idempotency_key]
            # Set recorded_at far in the past so any finite retention window is exceeded
            expired_at = utcnow() - timedelta(days=365)
            self._idempotency_registry[idempotency_key] = (fingerprint, expired_at)


class E2EProviderAdapter:
    """
    Bridges the FCE Control/Outbox boundaries with the independent ProviderDouble.
    Translates transport semantics into the exact behaviors expected by FCE.
    """
    def __init__(self, double: ProviderDouble):
        self.double = double
        self.observations = []  # Simulates persistent observation store

    def dispatch_action(self, action: Action) -> bool:
        """Called by OutboxDispatcher."""
        # Use payload if present, else fallback to incident_id
        payload = getattr(action, 'payload', {}) or {}
        intent_id = payload.get("intent_id", action.incident_id)
        key = action.idempotency_key

        result = self.double.dispatch_refund(
            intent_id=intent_id,
            idempotency_key=key,
            payload={"amount": 100},  # Dummy payload
        )

        if result == ProviderTransportResult.AMBIGUOUS_OUTCOME:
            # Simulate a 5xx or transport timeout that outbox interprets as ambiguous
            raise ConnectionError("Transport dropped")
        
        if result in (ProviderTransportResult.ACCEPTED_EXECUTED, ProviderTransportResult.ACCEPTED_PENDING):
            return True
        
        return False

    def query_refund_status(self, idempotency_key: str) -> ProviderQueryConfidence:
        """Called by the Uncertainty Workflow (RefundQueryAdapter protocol)."""
        result = self.double.query_refund_status(idempotency_key)
        
        # Map ProviderDouble's exact enum to FCE's expected confidence enum
        if result == ProviderQueryResult.AUTHORITATIVE_EXECUTED:
            conf = ProviderQueryConfidence.AUTHORITATIVE_EXECUTED
        elif result == ProviderQueryResult.AUTHORITATIVE_NOT_EXECUTED:
            conf = ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED
        elif result == ProviderQueryResult.NON_AUTHORITATIVE_QUERY:
            conf = ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY
        else:
            conf = ProviderQueryConfidence.QUERY_FAILED
            
        return conf
