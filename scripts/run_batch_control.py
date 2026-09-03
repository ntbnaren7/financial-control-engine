"""
Phase F — Finance Control Batch Runner

Ingests `data/synthetic_batch.json` (50 synthetic records with per-record
ground-truth classifications), runs the full deterministic finance-control
loop, and prints a Finance Control Report.

Architecture: strictly a batch orchestrator.  Does NOT modify V1, D1–D6,
or Phase B semantics.

Control loop per record:
  1. Reconstruct state from ProviderObservations via StateEngine
  2. V1 reconcile() → initial classification
  3. MATCH / deterministic exception → record final result
  4. EPISTEMIC_STALEMATE → route to D2–D3–D4–D5 investigation pipeline
  5. V1 reconcile() again with new evidence → final classification
  6. Compare final classification against ground truth

Run:
  uv run python scripts/run_batch_control.py [--data path/to/batch.json]

The match rate, resolution rate, and unresolved exception list are derived
EXCLUSIVELY from V1 Kernel outputs.  The LLM's confidence score and hypothesis
text have zero weight in the report.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Project imports — nothing is modified; these are orchestration-only calls
# ---------------------------------------------------------------------------

import httpx

from src.evidence.models import EntityType, ProviderObservation
from src.reconciliation.engine import reconcile
from src.reconciliation.models import DiscrepancyType, ExpectedRefund, ReconciliationResult
from src.state.engine import StateEngine
from src.state.models import (
    ExecutionState,
    KnowledgeState,
    ObservedFinancialState,
    ReconstructedState,
)

# Phase D investigation substrate (read-only)
from src.investigation.input_formatter import format_case_for_investigation
from src.investigation.agent import (
    LocalLLMInvestigator,
    OllamaConnectionError,
    OllamaModelNotFound,
    StructuredOutputError,
)
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier

# Domain models
from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationIntent,
    ValidationRejection,
    VerificationRejection,
)
from src.domain.cases.models import ReconciliationCase
from src.domain.correlation.models import CorrelationContext

# Batch mock transport
from tests.doubles.batch_mock_transport import BatchMockTransport
from src.integrations.razorpay.client import RazorpayClient

# ---------------------------------------------------------------------------
# Per-record result
# ---------------------------------------------------------------------------


@dataclass
class RecordResult:
    record_id: str
    scenario: str
    ground_truth: str
    initial_v1: str
    investigation_attempted: bool = False
    investigation_outcome: str = ""   # "d4_rejected" | "verified" | "provider_error" | ""
    final_v1: str = ""
    correct: bool = False
    notes: str = ""

    def __post_init__(self):
        if not self.final_v1:
            self.final_v1 = self.initial_v1
        self.correct = self.final_v1 == self.ground_truth


# ---------------------------------------------------------------------------
# Helpers: deserialise synthetic records into live domain objects
# ---------------------------------------------------------------------------


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_expectation(raw: Optional[dict]) -> Optional[ExpectedRefund]:
    if raw is None:
        return None
    return ExpectedRefund(
        expectation_id=raw["expectation_id"],
        refund_intent_id=raw["refund_intent_id"],
        provider_payment_id=raw["provider_payment_id"],
        amount=Decimal(raw["amount"]),
        currency=raw["currency"],
        created_at=_parse_dt(raw["created_at"]),
        sla_seconds=raw["sla_seconds"],
        source_system=raw["source_system"],
        business_reason=raw["business_reason"],
    )


def _load_observations(raw_list: list[dict]) -> list[ProviderObservation]:
    obs = []
    for raw in raw_list:
        obs.append(
            ProviderObservation(
                id=uuid.UUID(raw["id"]),
                provider=raw["provider"],
                event_id=raw["event_id"],
                entity_type=raw["entity_type"],
                entity_id=raw["entity_id"],
                event_type=raw["event_type"],
                payload=raw["payload"],
                created_at=_parse_dt(raw["created_at"]),
            )
        )
    return obs


# ---------------------------------------------------------------------------
# State reconstruction from ProviderObservations
# ---------------------------------------------------------------------------


def _reconstruct(
    entity_id: str,
    observations: list[ProviderObservation],
    now: datetime,
) -> Optional[ReconstructedState]:
    """
    Build a ReconstructedState from the payload fields embedded in each
    ProviderObservation.  This mirrors what StateEngine.reconstruct_state()
    does with its domain models.
    """
    if not observations:
        return None

    knowledge_raw = None
    financial_raw = None
    execution_raw = None
    obs_ids: list[str] = []

    for obs in observations:
        p = obs.payload
        if p.get("knowledge_state"):
            knowledge_raw = p["knowledge_state"]
        if p.get("financial_state"):
            financial_raw = p["financial_state"]
        if p.get("execution_state"):
            execution_raw = p["execution_state"]
        obs_ids.append(obs.event_id)

    knowledge = KnowledgeState(knowledge_raw) if knowledge_raw else KnowledgeState.UNKNOWN
    financial = ObservedFinancialState(financial_raw) if financial_raw else None
    execution = ExecutionState(execution_raw) if execution_raw else None

    return ReconstructedState(
        entity_type=EntityType.REFUND_INTENT,
        entity_id=entity_id,
        observed_financial_state=financial,
        knowledge_state=knowledge,
        execution=execution,
        observation_ids=tuple(obs_ids),
        reconstructed_at=now,
    )


# ---------------------------------------------------------------------------
# Observed amounts helper
# ---------------------------------------------------------------------------


def _observed_amount(observations: list[ProviderObservation]) -> Optional[Decimal]:
    for obs in reversed(observations):
        a = obs.payload.get("amount")
        if a is not None:
            return Decimal(str(a))
    return None


def _observed_currency(observations: list[ProviderObservation]) -> Optional[str]:
    for obs in reversed(observations):
        c = obs.payload.get("currency")
        if c:
            return c
    return None


# ---------------------------------------------------------------------------
# EXCESS_EFFECT detector
# ---------------------------------------------------------------------------


def _count_executions(observations: list[ProviderObservation]) -> int:
    return sum(
        1 for obs in observations
        if obs.payload.get("execution_state") == "EXECUTED"
    )


# ---------------------------------------------------------------------------
# Investigation pipeline (D2 → D3 → D4 → D5 → V1)
# ---------------------------------------------------------------------------


async def _investigate(
    record: dict,
    case: ReconciliationCase,
    now: datetime,
    investigator,
    validator: OutputValidator,
    verifier: DeterministicVerifier,
) -> tuple[str, str, list[ProviderObservation]]:
    """
    Run the investigation pipeline for a single EPISTEMIC_STALEMATE record.

    Returns:
      (investigation_outcome, notes, new_observations)

    investigation_outcome: "verified" | "d4_rejected" | "provider_error"
    new_observations: additional ProviderObservations from D5 (may be empty)
    """
    sub_case = record.get("investigation_sub_case", "")

    # D2 — Format bounded input for the LLM
    agent_input = format_case_for_investigation(case)

    # D3 — LLM investigation (LIVE or REPLAY fallback)
    hypothesis: Optional[CausalHypothesis] = None
    if investigator is None:
        # Ollama unavailable — use deterministic REPLAY hypothesis
        hypothesis = CausalHypothesis(
            hypothesis="Provider status unknown; issuing query to establish execution state.",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            missing_evidence_description="Provider refund record",
            confidence="LOW",
            disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
            verification_intent=VerificationIntent.QUERY_PROVIDER_REFUND,
        )
    else:
        try:
            hypothesis = await asyncio.to_thread(investigator.investigate, agent_input)
        except (OllamaConnectionError, OllamaModelNotFound, StructuredOutputError):
            hypothesis = CausalHypothesis(
                hypothesis="Provider status unknown; issuing query to establish execution state.",
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[],
                missing_evidence_description="Provider refund record",
                confidence="LOW",
                disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
                verification_intent=VerificationIntent.QUERY_PROVIDER_REFUND,
            )

    # Special case: C5 — produce a deliberately invalid hypothesis to exercise
    # the D4 boundary rejection path.
    if sub_case == "C5_BOUNDARY_REJECT":
        hypothesis = CausalHypothesis(
            hypothesis="Hypothesis referencing a fabricated evidence ID.",
            supporting_evidence_ids=["hallucinated_evidence_ref_999"],  # Invalid
            contradicting_evidence_ids=[],
            missing_evidence_description="None",
            confidence="LOW",
            disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
            verification_intent=VerificationIntent.QUERY_PROVIDER_REFUND,
        )

    # D4 — Output validation (validator expects the raw dict and the agent_input)
    validation = validator.validate(hypothesis.model_dump(), agent_input)
    if isinstance(validation, ValidationRejection):
        return "d4_rejected", f"D4 rejected: {validation.reason} — {validation.detail}", []

    # D5 — Deterministic provider query
    try:
        new_evidences = await verifier.verify(hypothesis, case)
    except Exception as e:
        return "provider_error", f"Provider error during verification: {e}", []

    # D5 may return either List[Evidence] or VerificationRejection.
    # VerificationRejection covers: provider errors (503), exhausted, unsupported intent.
    if isinstance(new_evidences, VerificationRejection):
        return "provider_error", f"D5 rejected: {new_evidences.reason} — {new_evidences.detail}", []

    # Normalise List[Evidence] → List[ProviderObservation] for V1 ingestion.
    # RazorpayApiNormalizer stores raw Razorpay fields in payload; we must
    # infer the V1 state fields (knowledge_state / financial_state /
    # execution_state) from the Razorpay `status` field here.
    evidence_list: list = new_evidences  # now guaranteed List[Evidence]
    new_observations: list[ProviderObservation] = []
    for ev in evidence_list:
        raw_status = (ev.payload.get("status") or "").lower()

        # Map Razorpay status → V1 knowledge / financial / execution state
        if raw_status == "processed":
            knowledge_state = "VERIFIED"
            financial_state = "REFUNDED"
            execution_state = "EXECUTED"
        elif raw_status in ("failed", "cancelled"):
            knowledge_state = "VERIFIED"
            financial_state = "FAILED"
            execution_state = "NOT_EXECUTED"
        elif raw_status in ("not_found", ""):
            knowledge_state = "VERIFIED"
            financial_state = None
            execution_state = "NOT_EXECUTED"
        else:
            # Carry through any pre-annotated fields, defaulting to UNKNOWN
            knowledge_state = ev.payload.get("knowledge_state", "UNKNOWN")
            financial_state = ev.payload.get("financial_state")
            execution_state = ev.payload.get("execution_state")

        new_observations.append(
            ProviderObservation(
                provider="razorpay",
                event_id=ev.evidence_id,
                entity_type=EntityType.REFUND_INTENT.value,
                entity_id=case.expectation.refund_intent_id if case.expectation else ev.entity_id,
                event_type=ev.evidence_type,
                payload={
                    "status": ev.payload.get("status"),
                    "amount": ev.payload.get("amount"),
                    "currency": ev.payload.get("currency"),
                    "knowledge_state": knowledge_state,
                    "financial_state": financial_state,
                    "execution_state": execution_state,
                },
                created_at=ev.timestamp,
                id=uuid.uuid4(),
            )
        )

    return "verified", "", new_observations


# ---------------------------------------------------------------------------
# Single-record processing
# ---------------------------------------------------------------------------


async def _process_record(
    record: dict,
    now: datetime,
    investigator,
    validator: OutputValidator,
    verifier: DeterministicVerifier,
) -> RecordResult:
    record_id = record["record_id"]
    scenario = record["scenario"]
    ground_truth = record["ground_truth"]

    expectation = _load_expectation(record.get("expectation"))
    observations = _load_observations(record.get("provider_observations", []))

    # Reconstruct state
    entity_id = (
        expectation.refund_intent_id if expectation
        else observations[0].entity_id if observations
        else record_id
    )
    state = _reconstruct(entity_id, observations, now)

    # V1 initial reconciliation
    exec_count = _count_executions(observations)
    result: ReconciliationResult = reconcile(
        expectation=expectation,
        reconstructed_state=state,
        reconciliation_timestamp=now,
        observed_amount=_observed_amount(observations),
        observed_currency=_observed_currency(observations),
        matching_executions_count=max(exec_count, 1),
    )
    initial_v1 = result.discrepancy_type.value

    # Non-stalemate: record directly
    if result.discrepancy_type != DiscrepancyType.EPISTEMIC_STALEMATE:
        return RecordResult(
            record_id=record_id,
            scenario=scenario,
            ground_truth=ground_truth,
            initial_v1=initial_v1,
            final_v1=initial_v1,
        )

    # EPISTEMIC_STALEMATE → investigation
    case = ReconciliationCase(
        correlation_context=CorrelationContext(),
        case_id=str(uuid.uuid4()),
        expectation=expectation,
        provider_observations=list(observations),
        created_at=now,
    )

    outcome, notes, new_obs = await _investigate(
        record, case, now, investigator, validator, verifier
    )

    if outcome == "d4_rejected":
        return RecordResult(
            record_id=record_id,
            scenario=scenario,
            ground_truth=ground_truth,
            initial_v1=initial_v1,
            investigation_attempted=True,
            investigation_outcome="d4_rejected",
            final_v1=DiscrepancyType.EPISTEMIC_STALEMATE.value,
            notes=notes,
        )

    if outcome == "provider_error":
        return RecordResult(
            record_id=record_id,
            scenario=scenario,
            ground_truth=ground_truth,
            initial_v1=initial_v1,
            investigation_attempted=True,
            investigation_outcome="provider_error",
            final_v1=DiscrepancyType.EPISTEMIC_STALEMATE.value,
            notes=notes,
        )

    # When the verifier successfully queried the provider but got back an empty
    # list, that is an authoritative negative: the provider confirmed no refund
    # exists.  Inject a VERIFIED / NOT_EXECUTED synthetic observation so V1 can
    # classify this as ABSENT_EXECUTION rather than staying EPISTEMIC_STALEMATE.
    if outcome == "verified" and not new_obs:
        new_obs = [
            ProviderObservation(
                provider="razorpay",
                event_id=str(uuid.uuid4()),
                entity_type=EntityType.REFUND_INTENT.value,
                entity_id=entity_id,
                event_type="RAZORPAY_API_REFUND_NOT_FOUND",
                payload={
                    "status": "not_found",
                    "knowledge_state": "VERIFIED",
                    "financial_state": None,
                    "execution_state": "NOT_EXECUTED",
                },
                created_at=now,
                id=uuid.uuid4(),
            )
        ]

    # Merge new observations and re-run V1
    all_obs = list(observations) + new_obs
    final_state = _reconstruct(entity_id, all_obs, now)
    final_result = reconcile(
        expectation=expectation,
        reconstructed_state=final_state,
        reconciliation_timestamp=now,
        observed_amount=_observed_amount(all_obs),
        observed_currency=_observed_currency(all_obs),
        matching_executions_count=max(_count_executions(all_obs), 1),
    )

    return RecordResult(
        record_id=record_id,
        scenario=scenario,
        ground_truth=ground_truth,
        initial_v1=initial_v1,
        investigation_attempted=True,
        investigation_outcome="verified",
        final_v1=final_result.discrepancy_type.value,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Batch mock transport builder
# ---------------------------------------------------------------------------


def _build_mock_transport(records: list[dict]) -> BatchMockTransport:
    routes: dict[str, dict] = {}
    for rec in records:
        if "investigation_sub_case" not in rec:
            continue
        exp = rec.get("expectation")
        if not exp:
            continue
        routes[exp["provider_payment_id"]] = {
            "sub_case": rec["investigation_sub_case"],
            "expected_amount": int(exp["amount"]),
            "intent_id": exp["refund_intent_id"],  # receipt for verifier filter
        }
    return BatchMockTransport(payment_routes=routes)


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------


def _print_report(results: list[RecordResult], elapsed: float, investigator_mode: str) -> None:
    total = len(results)
    matches = sum(1 for r in results if r.final_v1 == "MATCH")
    unresolved = [r for r in results if r.final_v1 == "EPISTEMIC_STALEMATE"]
    resolved = total - len(unresolved)
    resolution_rate = resolved / total * 100

    investigated = [r for r in results if r.investigation_attempted]
    d4_rejected = sum(1 for r in investigated if r.investigation_outcome == "d4_rejected")
    provider_error = sum(1 for r in investigated if r.investigation_outcome == "provider_error")
    inv_verified = sum(1 for r in investigated if r.investigation_outcome == "verified")
    # Of verified, how many ended up resolved (not stalemate)?
    inv_resolved = sum(
        1 for r in investigated
        if r.investigation_outcome == "verified" and r.final_v1 != "EPISTEMIC_STALEMATE"
    )

    correct = sum(1 for r in results if r.correct)
    throughput = total / elapsed if elapsed > 0 else 0

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║           FINANCIAL CONTROL BATCH REPORT                ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"  Investigator mode     {investigator_mode}")
    print(f"  Provider              REPLAY (BatchMockTransport)")
    print()
    print(f"  Records processed     {total}")
    print(f"  Matched               {matches}")
    print(f"  Resolved exceptions   {resolved - matches}")
    print(f"  Unresolved            {len(unresolved)}")
    print()
    print(f"  Match rate            {matches/total*100:.0f}%  ({matches}/{total})")
    print(f"  Resolution rate       {resolution_rate:.0f}%  ({resolved}/{total})")
    print(f"  Throughput            {throughput:.1f} records/sec")
    print()
    print("  ── Investigation Activity ──────────────────────────────")
    print()
    print(f"  Stalemates routed     {len(investigated)}")
    print(f"    D4 boundary rejected  {d4_rejected}")
    print(f"    Provider verified     {inv_verified}")
    print(f"      of which resolved   {inv_resolved}")
    print(f"      of which stalemate  {inv_verified - inv_resolved}  (provider outage / no evidence)")
    print()
    print("  ── Correctness vs Ground Truth ─────────────────────────")
    print()
    print(f"  Correct classifications  {correct} / {total}")
    if correct < total:
        wrong = [r for r in results if not r.correct]
        for r in wrong:
            print(f"    ✗ {r.record_id}  expected={r.ground_truth}  got={r.final_v1}")
    else:
        print("  All classifications match ground truth.")
    print()
    print("  ── Unresolved Exceptions ───────────────────────────────")
    print()
    if unresolved:
        for r in unresolved:
            reason = r.notes or r.investigation_outcome or "—"
            print(f"  {r.record_id}  {r.scenario:<40}  {reason}")
    else:
        print("  None.")
    print()
    print("═" * 62)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> int:
    data_path = Path(__file__).parent.parent / "data" / "synthetic_batch.json"
    if "--data" in sys.argv:
        idx = sys.argv.index("--data")
        data_path = Path(sys.argv[idx + 1])

    if not data_path.exists():
        print(f"ERROR: batch data not found at {data_path}")
        print("Run: uv run python scripts/generate_batch_data.py")
        return 1

    print(f"Loading batch data from {data_path} …")
    records: list[dict] = json.loads(data_path.read_text())
    print(f"  {len(records)} records loaded.")

    # Use the dataset's seed timestamp as the evaluation reference point.
    # All record created_at values and SLA deadlines in synthetic_batch.json
    # are relative to _SEED_BASE_TIME = 2024-01-15T10:00:00Z (from
    # generate_batch_data.py).  Using that same anchor ensures:
    #   • Category A/B past-SLA records are always past their deadline
    #   • IN_FLIGHT_PENDING records (created 30 min before seed, SLA=24h)
    #     are always within their SLA window
    # This makes the evaluation fully deterministic and reproducible at any
    # future wall-clock time.
    now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    # Build batch mock transport (keyed by payment_id → sub_case)
    mock_transport = _build_mock_transport(records)
    # Use the same base_url as RazorpayClient.BASE_URL so path segments align
    http_client = httpx.AsyncClient(transport=mock_transport, base_url="https://api.razorpay.com/v1")
    razorpay_client = RazorpayClient(client=http_client)
    verifier = DeterministicVerifier(razorpay_client=razorpay_client)
    validator = OutputValidator()

    # Investigator: LIVE if Ollama is available, else REPLAY
    investigator_mode = "LIVE (qwen3:8b)"
    try:
        investigator = LocalLLMInvestigator(model="qwen3:8b")
    except Exception:
        investigator_mode = "REPLAY (deterministic fallback — Ollama unavailable)"
        investigator = None  # Handled in _investigate via exception path

    print(f"  Investigator: {investigator_mode}")
    print(f"  Running {len(records)} records …\n")

    t0 = time.monotonic()
    results: list[RecordResult] = []
    for record in records:
        result = await _process_record(record, now, investigator, validator, verifier)
        results.append(result)

    elapsed = time.monotonic() - t0
    _print_report(results, elapsed, investigator_mode)

    # Exit 0 only if all records are classified correctly
    all_correct = all(r.correct for r in results)
    if not all_correct:
        print("WARNING: Some records did not match their ground truth.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
