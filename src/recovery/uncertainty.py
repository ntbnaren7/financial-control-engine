"""
Refund Uncertainty Workflow — Minimal resolution pipeline.

This module implements ONLY the behaviour required by the locked
Refund-Uncertainty Failure Contract:

  UNKNOWN
    → deterministic investigation (provider query)
    → immutable ProviderObservation
    → StateEngine reconstruction
    → deterministic ControlPlane decision
    → ResolutionOutcome (verified / authorized-retry / escalate)

Design constraints:
  - UNKNOWN alone NEVER authorizes retry. All retry preconditions are
    evaluated explicitly by RetryPolicy.evaluate().
  - No new refund_intent_id is ever created here.
  - No KnowledgeState or ObservedFinancialState values are added.
  - No generic workflow engine. No async state machine.
  - StateEngine remains a pure function — no worker coordination.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Protocol

from src.domain.refunds.models import Refund
from src.evidence.models import EntityType, ProviderObservation
from src.integrations.provider import ProviderQueryConfidence
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.state.models import KnowledgeState, ReconstructedState


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Resolution outcome ────────────────────────────────────────────────────────

class ResolutionStatus(str, Enum):
    """What the uncertainty workflow concluded for the intent."""
    VERIFIED_EXECUTED = "VERIFIED_EXECUTED"
    """Provider confirmed execution. No further action needed."""

    VERIFIED_NOT_EXECUTED = "VERIFIED_NOT_EXECUTED"
    """Provider authoritatively confirmed non-execution AND retry policy
    does NOT permit retry. No consequential action taken."""

    AUTHORIZED_RETRY = "AUTHORIZED_RETRY"
    """Provider authoritatively confirmed non-execution AND all retry
    preconditions are met. Caller may dispatch the same intent again."""

    VERIFIED_REJECTED = "VERIFIED_REJECTED"
    """Provider explicitly rejected the intent. No financial effect established.
    Automatic retry prohibited for terminal rejections."""

    ESCALATE = "ESCALATE"
    """Evidence is insufficient, contradictory, or query failed. No
    consequential action may be taken. Human review required."""


@dataclass(frozen=True)
class ResolutionOutcome:
    intent_id: str
    status: ResolutionStatus
    reconstructed_state: ReconstructedState
    query_confidence: ProviderQueryConfidence
    reason: str
    resolved_at: datetime = field(default_factory=utcnow)


# ── Retry policy ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RetryPolicy:
    """
    Explicit precondition set that must ALL be satisfied before a retry
    is authorized. UNKNOWN knowledge alone is never sufficient.

    Attributes:
        max_attempts:           Maximum total dispatch attempts before escalation.
        provider_key_valid:     Whether the provider's idempotency guarantee is
                                still in force for this key. The caller must
                                establish this from external policy (e.g. clock
                                check against provider SLA).
    """
    max_attempts: int
    provider_key_valid: bool

    def evaluate(
        self,
        refund: Refund,
        reconstructed: ReconstructedState,
        query_confidence: ProviderQueryConfidence,
        attempts_so_far: int,
    ) -> tuple[bool, str]:
        """
        Evaluate whether a same-intent retry is authorized.

        Returns (authorized: bool, reason: str).

        All conditions must pass. First failure short-circuits with a reason.
        """
        # 1. Knowledge must be VERIFIED + no concrete financial state
        if reconstructed.knowledge_state != KnowledgeState.VERIFIED:
            return False, (
                f"KnowledgeState is {reconstructed.knowledge_state.value}; "
                "retry requires VERIFIED knowledge of non-execution."
            )

        # 2. Query must be authoritative non-execution
        if query_confidence != ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED:
            return False, (
                f"Query confidence is {query_confidence.value}; "
                "retry requires AUTHORITATIVE_NOT_EXECUTED."
            )

        # 3. No prior concrete financial effect on this intent
        if reconstructed.observed_financial_state is not None:
            return False, (
                f"A concrete financial state already exists: "
                f"{reconstructed.observed_financial_state.value}. Retry blocked."
            )

        # 4. Provider idempotency guarantee must still be valid
        if not self.provider_key_valid:
            return False, (
                "Provider idempotency guarantee has expired for this key. "
                "Authoritative verification required before any retry."
            )

        # 5. Retry count within policy limits
        if attempts_so_far >= self.max_attempts:
            return False, (
                f"Retry limit reached ({attempts_so_far}/{self.max_attempts}). Escalate."
            )

        # 6. Refund intent scope: verify the intent is self-consistent
        #    (refund_intent_id + idempotency key must be stable derivatives)
        if not refund.refund_intent_id or not refund.get_provider_idempotency_key():
            return False, "Refund intent is missing a stable identity. Cannot authorize retry."

        return True, (
            f"All preconditions met. Same-intent retry authorized for "
            f"intent={refund.refund_intent_id!r} "
            f"(attempt {attempts_so_far + 1}/{self.max_attempts})."
        )


# ── Provider query adapter protocol ──────────────────────────────────────────

class RefundQueryAdapter(Protocol):
    """
    Protocol the uncertainty workflow uses to query provider status.

    The adapter translates provider-specific identifiers (payment ID, provider
    refund ID, etc.) into a typed ProviderQueryConfidence result. The workflow
    never calls provider APIs directly or interprets HTTP status codes.
    """
    def query_refund_status(self, idempotency_key: str) -> ProviderQueryConfidence:
        """
        Query whether the refund intent executed at the provider.

        The adapter must:
        - Map FCE idempotency key to the provider's query mechanism.
        - Return AUTHORITATIVE_NOT_EXECUTED only if the lookup is fresh,
          comprehensive, and non-stale.
        - Return NON_AUTHORITATIVE_QUERY for stale replicas / partial lookups.
        - Return QUERY_FAILED on transport or service failures.
        """
        ...


# ── Observation factory ───────────────────────────────────────────────────────

def _build_observation(
    refund: Refund,
    query_confidence: ProviderQueryConfidence,
    provider_name: str,
    extra_payload: Optional[dict] = None,
) -> ProviderObservation:
    """
    Construct an immutable ProviderObservation from a query result.

    Encodes the ProviderQueryConfidence in the payload so the StateEngine
    can reconstruct propositions from this observation. Uses a stable
    event_id derived from the refund intent and confidence so duplicate
    observations from concurrent workers are absorbed idempotently by the
    DB uniqueness constraint.
    """
    now = utcnow()
    payload: dict = {
        "query_confidence": query_confidence.value,
        "provider_timestamp": now.isoformat(),
        **(extra_payload or {}),
    }
    # Stable event_id: same intent + same confidence from the same query run
    # will produce the same event_id, enabling DB-level idempotent absorption.
    stable_event_id = (
        f"uncertainty_query:{refund.refund_intent_id}:{query_confidence.value}"
    )
    return ProviderObservation(
        id=uuid.uuid4(),
        provider=provider_name,
        event_id=stable_event_id,
        entity_type=EntityType.REFUND_INTENT.value,
        entity_id=refund.refund_intent_id,
        event_type="UNCERTAINTY_RESOLUTION_QUERY",
        payload=payload,
        created_at=now,
    )


# ── Workflow ──────────────────────────────────────────────────────────────────

_ENGINE = StateEngine()
_ORDERING = TemporalOrderingPolicy()


def resolve_refund_uncertainty(
    refund: Refund,
    existing_observations: List[ProviderObservation],
    query_adapter: RefundQueryAdapter,
    retry_policy: RetryPolicy,
    provider_name: str = "provider",
    attempts_so_far: int = 0,
) -> tuple[ResolutionOutcome, Optional[ProviderObservation]]:
    """
    Minimal refund-uncertainty resolution workflow.

    Steps:
      1. Query the provider via the typed adapter.
      2. Build an immutable ProviderObservation for the query result.
      3. Pass observations to StateEngine for deterministic reconstruction.
      4. Evaluate the reconstructed state against the RetryPolicy.
      5. Return a ResolutionOutcome and the new observation (if any).

    The caller is responsible for persisting the returned observation
    before acting on the ResolutionOutcome. The workflow never persists
    state directly.

    Returns:
        (ResolutionOutcome, new_observation | None)
        new_observation is None only if the query produced no new evidence
        worth persisting (e.g. QUERY_FAILED with no change in knowledge).
    """
    now = utcnow()

    # ── Step 1: Query provider ────────────────────────────────────────────
    idempotency_key = refund.get_provider_idempotency_key()
    query_confidence = query_adapter.query_refund_status(idempotency_key)

    # ── Step 2: Build observation ─────────────────────────────────────────
    new_observation: Optional[ProviderObservation] = None

    if query_confidence in (
        ProviderQueryConfidence.AUTHORITATIVE_EXECUTED,
        ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED,
    ):
        # Authoritative evidence produces a new observation worth persisting.
        new_observation = _build_observation(refund, query_confidence, provider_name)
        all_observations = existing_observations + [new_observation]
    elif query_confidence == ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY:
        # Non-authoritative: persist as evidence (for audit) but it cannot
        # change the reconstructed proposition.
        new_observation = _build_observation(refund, query_confidence, provider_name)
        all_observations = existing_observations  # Do NOT include in reconstruction
    else:
        # QUERY_FAILED: no evidence; reconstruct from existing only
        all_observations = existing_observations

    # ── Step 3: StateEngine reconstruction ───────────────────────────────
    reconstructed = _ENGINE.reconstruct_state(
        entity_type=EntityType.REFUND_INTENT,
        entity_id=refund.refund_intent_id,
        observations=all_observations,
        reconstructed_at=now,
        ordering_policy=_ORDERING,
    )

    # ── Step 4 & 5: Evaluate and emit outcome ────────────────────────────

    # CONTRADICTED: block all actions
    if reconstructed.knowledge_state == KnowledgeState.CONTRADICTED:
        return ResolutionOutcome(
            intent_id=refund.refund_intent_id,
            status=ResolutionStatus.ESCALATE,
            reconstructed_state=reconstructed,
            query_confidence=query_confidence,
            reason="Authoritative observations are contradictory. Escalating for investigation.",
        ), new_observation

    # QUERY_FAILED or NON_AUTHORITATIVE: cannot advance knowledge
    if query_confidence in (
        ProviderQueryConfidence.QUERY_FAILED,
        ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY,
    ):
        return ResolutionOutcome(
            intent_id=refund.refund_intent_id,
            status=ResolutionStatus.ESCALATE,
            reconstructed_state=reconstructed,
            query_confidence=query_confidence,
            reason=(
                f"Query confidence is {query_confidence.value}. "
                "Insufficient authority to advance knowledge. Escalating."
            ),
        ), new_observation

    # AUTHORITATIVE_EXECUTED: the intent executed
    if query_confidence == ProviderQueryConfidence.AUTHORITATIVE_EXECUTED:
        return ResolutionOutcome(
            intent_id=refund.refund_intent_id,
            status=ResolutionStatus.VERIFIED_EXECUTED,
            reconstructed_state=reconstructed,
            query_confidence=query_confidence,
            reason="Provider authoritatively confirmed refund executed.",
        ), new_observation

    # AUTHORITATIVE_NOT_EXECUTED: evaluate retry policy
    # This is VERIFIED + NOT_EXECUTED proposition — not a financial failure
    retry_ok, retry_reason = retry_policy.evaluate(
        refund=refund,
        reconstructed=reconstructed,
        query_confidence=query_confidence,
        attempts_so_far=attempts_so_far,
    )
    if retry_ok:
        return ResolutionOutcome(
            intent_id=refund.refund_intent_id,
            status=ResolutionStatus.AUTHORIZED_RETRY,
            reconstructed_state=reconstructed,
            query_confidence=query_confidence,
            reason=retry_reason,
        ), new_observation
    else:
        return ResolutionOutcome(
            intent_id=refund.refund_intent_id,
            status=ResolutionStatus.VERIFIED_NOT_EXECUTED,
            reconstructed_state=reconstructed,
            query_confidence=query_confidence,
            reason=f"VERIFIED NOT_EXECUTED, retry not authorized: {retry_reason}",
        ), new_observation
