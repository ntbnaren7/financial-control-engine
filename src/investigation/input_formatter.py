"""
D2 — Deterministic Input Formatter.

Responsibility: Translate a trusted ReconciliationCase into a bounded,
read-only dict that the LLM investigator is permitted to see.

Contract (strict):
  - Input:  trusted ReconciliationCase (produced by Phase C + V1)
  - Output: plain dict matching the Phase D agent-input schema
  - No LLM calls
  - No database access
  - No provider access
  - No financial inference
  - No fields or IDs invented outside the case
  - Raw provider payloads are NOT forwarded; only safe metadata is surfaced
  - permitted_verification_intents comes from the hardcoded Phase D
    capability allowlist (VerificationIntent), never from LLM output
  - The formatter does not decide what evidence is relevant enough to
    investigate — Phase C / V1 have already established the bounded case;
    D2 merely serialises that trusted boundary for the untrusted model
  - Formatting the same case twice must produce identical output
    (no random / time-dependent fields introduced here)
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.domain.cases.models import ReconciliationCase
from src.domain.correlation.models import CorrelationStatus
from src.domain.investigation.models import VerificationIntent

# The complete, hardcoded Phase D capability allowlist forwarded to the agent.
# This list is injected by the formatter; it never originates from LLM output.
_PERMITTED_INTENTS: List[str] = [v.value for v in VerificationIntent]


def format_case_for_investigation(case: ReconciliationCase) -> Dict[str, Any]:
    """
    Produce the bounded agent-input dict for *case*.

    The returned dict contains only the fields the LLM is permitted to see.
    Raw payloads, internal database IDs, provider credentials, and any field
    not explicitly listed below are excluded.

    Fields in the returned dict
    ---------------------------
    case_id                     str   — stable case identifier
    discrepancy_type            str   — V1 classification (e.g. EPISTEMIC_STALEMATE)
    knowledge_state             str   — V1 KnowledgeState (e.g. UNKNOWN)
    expected_refund             dict  — intent fields (no raw payload)
    correlated_observations     list  — provider records that passed correlation
    unmatched_observations      list  — provider records that did not correlate
    permitted_verification_intents list — hardcoded allowlist
    """
    # ── Expected refund (may be None for orphan cases) ───────────────────────
    expected_refund: Dict[str, Any] | None = None
    if case.expectation is not None:
        exp = case.expectation
        expected_refund = {
            "intent_id":          exp.refund_intent_id,
            "provider_payment_id": exp.provider_payment_id,
            "amount":             str(exp.amount),
            "currency":           exp.currency,
            "created_at":         exp.created_at.isoformat() if exp.created_at else None,
        }

    # ── Knowledge state ──────────────────────────────────────────────────────
    knowledge_state: str | None = None
    if case.reconstructed_state is not None:
        knowledge_state = case.reconstructed_state.knowledge_state.value

    # ── Discrepancy type ─────────────────────────────────────────────────────
    discrepancy_type: str | None = None
    if case.reconciliation_result is not None:
        discrepancy_type = case.reconciliation_result.discrepancy_type.value

    # ── Correlation results: partition into correlated vs unmatched ──────────
    correlated_observations: List[Dict[str, Any]] = []
    unmatched_observations: List[Dict[str, Any]] = []

    for result in case.correlation_context.results:
        ev = result.provider_evidence
        if ev is None:
            continue

        # Expose only safe metadata — deliberately NOT the raw payload.
        observation_entry: Dict[str, Any] = {
            "evidence_id":        ev.evidence_id,
            "source":             ev.source,
            "evidence_type":      ev.evidence_type,
            "timestamp":          ev.timestamp.isoformat(),
            "correlation_status": result.status.value,
            # Include the correlation diagnostics so the agent can reason about
            # *why* a record was or was not accepted.
            "correlation_checks": {
                "matched_by":     result.matched_by,
                "temporal_check": result.temporal_check,
                "entity_scope":   result.entity_scope,
                "amount_check":   result.amount_check,
                "currency_check": result.currency_check,
            },
        }

        if result.status == CorrelationStatus.CORRELATED:
            correlated_observations.append(observation_entry)
        elif result.status in (
            CorrelationStatus.UNMATCHED,
            CorrelationStatus.TEMPORAL_VIOLATION,
            CorrelationStatus.AMBIGUOUS,
            CorrelationStatus.OUT_OF_SCOPE,
        ):
            unmatched_observations.append(observation_entry)

    return {
        "case_id":                      case.case_id,
        "discrepancy_type":             discrepancy_type,
        "knowledge_state":              knowledge_state,
        "expected_refund":              expected_refund,
        "correlated_observations":      correlated_observations,
        "unmatched_observations":       unmatched_observations,
        "permitted_verification_intents": _PERMITTED_INTENTS,
    }
