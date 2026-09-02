"""
Provider integration semantic boundary.

This module defines the typed semantic contracts that the provider adapter
exposes to the FCE Control Plane. The Control Plane NEVER reasons over raw
HTTP status codes (400, 409, 500, 504). Instead, the adapter translates
transport/API responses into these two strictly-separated outcome types:

  ProviderMutationOutcome  — result of a dispatch (create/execute) operation
  ProviderQueryConfidence  — result of a status-query operation

Keeping these separate is critical because:
  - A mutation outcome describes what happened to the request transport + execution.
  - A query confidence describes the epistemic authority of a status lookup.
  They are not interchangeable.
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Optional


# ── Mutation outcomes ─────────────────────────────────────────────────────────

class ProviderMutationOutcome(str, Enum):
    """
    Typed result of a provider mutation request (dispatch / create refund).

    The adapter produces exactly one of these from whatever HTTP/API response
    the provider returned. The Control Plane branches on this, never on status
    codes.
    """
    ACCEPTED_EXECUTED = "ACCEPTED_EXECUTED"
    """Provider confirmed financial execution synchronously."""

    ACCEPTED_PENDING = "ACCEPTED_PENDING"
    """Provider accepted the request; outcome delivered asynchronously via webhook."""

    EXPLICITLY_REJECTED = "EXPLICITLY_REJECTED"
    """Provider explicitly refused the intent (e.g. insufficient balance, invalid refund).
    No execution occurred. Terminal if provider semantics say terminal."""

    AMBIGUOUS_OUTCOME = "AMBIGUOUS_OUTCOME"
    """Provider response was lost, timed out, or was a 5xx. FCE cannot determine
    whether execution occurred. KnowledgeState must remain UNKNOWN."""

    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    """Provider rejected the request because the idempotency key was previously used
    with a different payload. This is a semantic integrity failure."""

    TRANSIENT_CONFLICT = "TRANSIENT_CONFLICT"
    """Provider rejected with a concurrent-request conflict that is NOT an idempotency
    mismatch (e.g. in-flight deduplication). May be retried per provider contract."""


# ── Query authority outcomes ───────────────────────────────────────────────────

class ProviderQueryConfidence(str, Enum):
    """
    Typed result of a provider status-query operation.

    Captures both what was found AND the epistemic authority of the lookup.
    A query can return a financially-accurate answer with LOW authority
    (e.g. stale replica), or a false "not found" with HIGH authority
    (e.g. definitively not recorded anywhere in the provider's system).
    """
    AUTHORITATIVE_EXECUTED = "AUTHORITATIVE_EXECUTED"
    """Provider's authoritative lookup confirmed the refund intent executed."""

    AUTHORITATIVE_NOT_EXECUTED = "AUTHORITATIVE_NOT_EXECUTED"
    """Provider's authoritative, fresh, complete lookup confirmed the refund intent
    has NOT executed. Sufficient to establish VERIFIED + NOT_EXECUTED proposition.
    Must NOT be emitted from stale replicas or incomplete lookups."""

    NON_AUTHORITATIVE_QUERY = "NON_AUTHORITATIVE_QUERY"
    """Query result is insufficient to establish an authoritative proposition.
    May be stale (replica lag), partial (incomplete lookup), or cached.
    FCE KnowledgeState must NOT be changed from UNKNOWN based on this."""

    QUERY_FAILED = "QUERY_FAILED"
    """Query transport or service failed. No proposition can be established."""


# ── Raw provider response descriptor ──────────────────────────────────────────

@dataclass
class ProviderResponse:
    """
    Descriptor for the raw adapter-layer response before semantic translation.

    The adapter reads these fields to produce a ProviderMutationOutcome or
    ProviderQueryConfidence. Nothing above the adapter layer should ever
    inspect raw_status or http_status_code.
    """
    raw_status: str
    is_cached_response: bool
    is_partial_lookup: bool
    network_timeout: bool
    refund_exists: bool
    is_idempotency_mismatch: bool = False
    is_transient_conflict: bool = False
    is_explicit_rejection: bool = False


# ── Mock adapter ───────────────────────────────────────────────────────────────

class MockProviderAdapter:
    """
    Simulates a provider adapter for unit and integration tests.

    Translates ProviderResponse descriptors into typed semantic outcomes.
    The adapter is strictly responsible for the transport-to-semantics
    translation without leaking business rules upward.
    """

    def execute_refund(
        self,
        idempotency_key: str,
        scenario_override: Optional[ProviderResponse] = None,
    ) -> ProviderMutationOutcome:
        """
        Translate a provider response into a typed mutation outcome.

        Returns AMBIGUOUS_OUTCOME when no override is provided (fail-safe default).
        """
        if scenario_override is None:
            return ProviderMutationOutcome.AMBIGUOUS_OUTCOME

        if scenario_override.network_timeout:
            return ProviderMutationOutcome.AMBIGUOUS_OUTCOME

        if scenario_override.is_idempotency_mismatch:
            return ProviderMutationOutcome.IDEMPOTENCY_MISMATCH

        if scenario_override.is_transient_conflict:
            return ProviderMutationOutcome.TRANSIENT_CONFLICT

        if scenario_override.is_explicit_rejection:
            return ProviderMutationOutcome.EXPLICITLY_REJECTED

        if scenario_override.refund_exists:
            return ProviderMutationOutcome.ACCEPTED_EXECUTED

        # Provider acknowledged but no synchronous confirmation
        return ProviderMutationOutcome.ACCEPTED_PENDING

    def query_refund_status(
        self,
        idempotency_key: str,
        scenario_override: Optional[ProviderResponse] = None,
    ) -> ProviderQueryConfidence:
        """
        Translate a provider query response into a typed authority outcome.

        Returns QUERY_FAILED when no override is provided (fail-safe default).
        AUTHORITATIVE_NOT_EXECUTED is only emitted when the lookup is confirmed
        to be non-stale, non-partial, and non-cached.
        """
        if scenario_override is None:
            return ProviderQueryConfidence.QUERY_FAILED

        if scenario_override.network_timeout:
            return ProviderQueryConfidence.QUERY_FAILED

        if scenario_override.is_cached_response or scenario_override.is_partial_lookup:
            return ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY

        if scenario_override.refund_exists:
            return ProviderQueryConfidence.AUTHORITATIVE_EXECUTED

        # Real-time, comprehensive, non-cached lookup: not found is authoritative
        return ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED
