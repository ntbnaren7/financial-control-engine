"""
Phase F — Synthetic Batch Data Generator

Generates a deterministic 50-record evaluation dataset for the Finance Control
Batch Runner.  Every record carries its own independent ground-truth
classification so the batch runner can measure correctness without relying on
the mock provider to determine what the "right answer" should be.

Distribution (locked):
  Category A — Direct matches                 38 records  MATCH
  Category B — Deterministic exceptions        7 records  Various
  Category C — Epistemic stalemates            5 records  Investigated

Category B breakdown:
  VALUE_MISMATCH          2
  IN_FLIGHT_PENDING       2
  ORPHANED_EXECUTION      1
  EXCESS_EFFECT           1
  ABSENT_EXECUTION        1

Category C breakdown (all start as EPISTEMIC_STALEMATE):
  C1 — Missing webhook    → MATCH after investigation
  C2 — Provider dropped   → ABSENT_EXECUTION after investigation
  C3 — Amount mismatch    → VALUE_MISMATCH after investigation
  C4 — Provider outage    → EPISTEMIC_STALEMATE (unresolved)
  C5 — Boundary reject    → EPISTEMIC_STALEMATE (unresolved, D4 rejection)

Run:
  uv run python scripts/generate_batch_data.py

Output:
  data/synthetic_batch.json
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixed seeds — never change these; reproducibility depends on them
# ---------------------------------------------------------------------------

_SEED_BASE_TIME = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
_PAST_SLA_DELTA = timedelta(hours=3)   # 3 hours — well past any SLA
_IN_FLIGHT_DELTA = timedelta(minutes=5)  # 5 minutes — within any reasonable SLA

# SLA = 1 hour = 3600 seconds for all records
_SLA_SECONDS = 3600

# Deterministic UUID namespace for reproducibility
_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _intent_id(record_id: str) -> str:
    return str(uuid.uuid5(_NS, f"intent:{record_id}"))


def _payment_id(record_id: str) -> str:
    return f"pay_{uuid.uuid5(_NS, f'payment:{record_id}').hex[:12]}"


def _expectation_id(record_id: str) -> str:
    return str(uuid.uuid5(_NS, f"expectation:{record_id}"))


def _obs_id(record_id: str, suffix: str = "") -> str:
    return str(uuid.uuid5(_NS, f"obs:{record_id}:{suffix}"))


def _ts(delta: timedelta = timedelta()) -> str:
    return (_SEED_BASE_TIME + delta).isoformat()


def _make_expectation(
    record_id: str,
    amount_inr: int,
    created_delta: timedelta,
) -> dict:
    return {
        "expectation_id": _expectation_id(record_id),
        "refund_intent_id": _intent_id(record_id),
        "provider_payment_id": _payment_id(record_id),
        "amount": str(amount_inr),
        "currency": "INR",
        "created_at": _ts(created_delta),
        "sla_seconds": _SLA_SECONDS,
        "source_system": "OMS",
        "business_reason": f"Refund for order associated with {record_id}",
    }


def _make_obs(
    record_id: str,
    event_type: str,
    payload: dict,
    suffix: str = "a",
    delta: timedelta = timedelta(),
) -> dict:
    return {
        "id": _obs_id(record_id, suffix),
        "provider": "razorpay",
        "event_id": str(uuid.uuid5(_NS, f"event:{record_id}:{suffix}")),
        "entity_type": "REFUND_INTENT",
        "entity_id": _intent_id(record_id),
        "event_type": event_type,
        "payload": payload,
        "created_at": _ts(delta),
    }


# ---------------------------------------------------------------------------
# Record builders per category
# ---------------------------------------------------------------------------

def _cat_a(record_id: str, index: int) -> dict:
    """Category A: Direct match. Expectation + VERIFIED/REFUNDED observation."""
    created = _PAST_SLA_DELTA * -1 - timedelta(hours=1)  # Well before SLA
    obs_delta = _PAST_SLA_DELTA * -1 + timedelta(minutes=10)
    amount = 100 + (index * 50) % 5000  # Vary amounts

    return {
        "record_id": record_id,
        "scenario": "direct_match",
        "ground_truth": "MATCH",
        "expectation": _make_expectation(record_id, amount, created),
        "provider_observations": [
            _make_obs(
                record_id,
                event_type="refund.processed",
                payload={
                    "status": "processed",
                    "amount": amount,
                    "currency": "INR",
                    "knowledge_state": "VERIFIED",
                    "financial_state": "REFUNDED",
                    "execution_state": "EXECUTED",
                },
                delta=obs_delta,
            )
        ],
    }


def _cat_b_value_mismatch(record_id: str, index: int) -> dict:
    """Category B-1: Provider refunded wrong amount."""
    expected_amount = 500
    observed_amount = 400 if index == 0 else 600
    created = _PAST_SLA_DELTA * -1 - timedelta(hours=1)
    return {
        "record_id": record_id,
        "scenario": "value_mismatch",
        "ground_truth": "VALUE_MISMATCH",
        "expectation": _make_expectation(record_id, expected_amount, created),
        "provider_observations": [
            _make_obs(
                record_id,
                event_type="refund.processed",
                payload={
                    "status": "processed",
                    "amount": observed_amount,
                    "currency": "INR",
                    "knowledge_state": "VERIFIED",
                    "financial_state": "REFUNDED",
                    "execution_state": "EXECUTED",
                },
                delta=_PAST_SLA_DELTA * -1 + timedelta(minutes=5),
            )
        ],
    }


def _cat_b_in_flight(record_id: str) -> dict:
    """Category B-2: Within SLA; no provider event yet — normal."""
    # Must be created relative to *actual* current time so the SLA hasn't expired.
    # Using a fixed past timestamp would make the SLA appear expired.
    now_iso = datetime.now(timezone.utc).isoformat()
    sla_seconds = 3600  # 1 hour SLA
    return {
        "record_id": record_id,
        "scenario": "in_flight_pending",
        "ground_truth": "IN_FLIGHT_PENDING",
        "expectation": {
            "expectation_id": _expectation_id(record_id),
            "refund_intent_id": _intent_id(record_id),
            "provider_payment_id": _payment_id(record_id),
            "amount": "300",
            "currency": "INR",
            "created_at": now_iso,  # Just created — SLA not expired
            "sla_seconds": sla_seconds,
            "source_system": "OMS",
            "business_reason": f"Refund for order associated with {record_id}",
        },
        "provider_observations": [],  # No provider event yet
    }


def _cat_b_orphaned(record_id: str) -> dict:
    """Category B-3: Provider webhook with NO matching internal expectation."""
    return {
        "record_id": record_id,
        "scenario": "orphaned_execution",
        "ground_truth": "ORPHANED_EXECUTION",
        "expectation": None,  # No OMS intent
        "provider_observations": [
            _make_obs(
                record_id,
                event_type="refund.processed",
                payload={
                    "status": "processed",
                    "amount": 750,
                    "currency": "INR",
                    "knowledge_state": "VERIFIED",
                    "financial_state": "REFUNDED",
                    "execution_state": "EXECUTED",
                },
            )
        ],
    }


def _cat_b_excess(record_id: str) -> dict:
    """Category B-4: Two provider webhooks for one intent = duplicate refund."""
    created = _PAST_SLA_DELTA * -1 - timedelta(hours=1)
    return {
        "record_id": record_id,
        "scenario": "excess_effect",
        "ground_truth": "EXCESS_EFFECT",
        "expectation": _make_expectation(record_id, 200, created),
        "provider_observations": [
            _make_obs(
                record_id,
                event_type="refund.processed",
                payload={
                    "status": "processed",
                    "amount": 200,
                    "currency": "INR",
                    "knowledge_state": "VERIFIED",
                    "financial_state": "REFUNDED",
                    "execution_state": "EXECUTED",
                },
                suffix="a",
                delta=_PAST_SLA_DELTA * -1 + timedelta(minutes=5),
            ),
            _make_obs(
                record_id,
                event_type="refund.processed",
                payload={
                    "status": "processed",
                    "amount": 200,
                    "currency": "INR",
                    "knowledge_state": "VERIFIED",
                    "financial_state": "REFUNDED",
                    "execution_state": "EXECUTED",
                },
                suffix="b",
                delta=_PAST_SLA_DELTA * -1 + timedelta(minutes=7),
            ),
        ],
    }


def _cat_b_absent(record_id: str) -> dict:
    """Category B-5: Past SLA + VERIFIED + NOT_EXECUTED = ABSENT_EXECUTION directly."""
    created = _PAST_SLA_DELTA * -1 - timedelta(hours=1)
    return {
        "record_id": record_id,
        "scenario": "absent_execution_direct",
        "ground_truth": "ABSENT_EXECUTION",
        "expectation": _make_expectation(record_id, 150, created),
        "provider_observations": [
            _make_obs(
                record_id,
                event_type="refund.query_response",
                payload={
                    "status": "not_found",
                    "knowledge_state": "VERIFIED",
                    "financial_state": None,
                    "execution_state": "NOT_EXECUTED",
                },
            )
        ],
    }


def _cat_c(record_id: str, sub_case: str) -> dict:
    """
    Category C: Epistemic stalemate — requires investigation.

    All C records have: past-SLA expectation + UNKNOWN provider state.
    The sub_case label drives the batch mock transport and determines
    the final V1 outcome after investigation.

    Ground truth is the expected FINAL V1 classification, not the
    initial EPISTEMIC_STALEMATE.  This is what the batch runner
    compares against.
    """
    created = _PAST_SLA_DELTA * -1 - timedelta(hours=1)

    ground_truth_map = {
        "C1_MISSING_WEBHOOK": "MATCH",
        "C2_PROVIDER_DROPPED": "ABSENT_EXECUTION",
        "C3_AMOUNT_MISMATCH": "VALUE_MISMATCH",
        "C4_PROVIDER_OUTAGE": "EPISTEMIC_STALEMATE",
        "C5_BOUNDARY_REJECT": "EPISTEMIC_STALEMATE",
    }

    amounts = {
        "C1_MISSING_WEBHOOK": 200,
        "C2_PROVIDER_DROPPED": 350,
        "C3_AMOUNT_MISMATCH": 500,
        "C4_PROVIDER_OUTAGE": 125,
        "C5_BOUNDARY_REJECT": 275,
    }

    return {
        "record_id": record_id,
        "scenario": f"epistemic_stalemate:{sub_case}",
        "ground_truth": ground_truth_map[sub_case],
        # The batch mock transport uses sub_case to select its response.
        "investigation_sub_case": sub_case,
        "expectation": _make_expectation(record_id, amounts[sub_case], created),
        # UNKNOWN knowledge — SLA expired but no authoritative provider evidence.
        "provider_observations": [
            _make_obs(
                record_id,
                event_type="refund.status_unknown",
                payload={
                    "status": "unknown",
                    "knowledge_state": "UNKNOWN",
                    "financial_state": None,
                    "execution_state": None,
                },
            )
        ],
    }


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def generate() -> list[dict]:
    records: list[dict] = []
    idx = 1

    def rid(n: int) -> str:
        return f"REC-{n:03d}"

    # --- Category A: 38 direct matches ---
    for i in range(38):
        records.append(_cat_a(rid(idx), i))
        idx += 1

    # --- Category B: 7 deterministic exceptions ---
    records.append(_cat_b_value_mismatch(rid(idx), 0)); idx += 1
    records.append(_cat_b_value_mismatch(rid(idx), 1)); idx += 1
    records.append(_cat_b_in_flight(rid(idx))); idx += 1
    records.append(_cat_b_in_flight(rid(idx))); idx += 1
    records.append(_cat_b_orphaned(rid(idx))); idx += 1
    records.append(_cat_b_excess(rid(idx))); idx += 1
    records.append(_cat_b_absent(rid(idx))); idx += 1

    # --- Category C: 5 epistemic stalemates ---
    records.append(_cat_c(rid(idx), "C1_MISSING_WEBHOOK")); idx += 1
    records.append(_cat_c(rid(idx), "C2_PROVIDER_DROPPED")); idx += 1
    records.append(_cat_c(rid(idx), "C3_AMOUNT_MISMATCH")); idx += 1
    records.append(_cat_c(rid(idx), "C4_PROVIDER_OUTAGE")); idx += 1
    records.append(_cat_c(rid(idx), "C5_BOUNDARY_REJECT")); idx += 1

    assert len(records) == 50, f"Expected 50 records, got {len(records)}"
    return records


def main() -> None:
    out_path = Path(__file__).parent.parent / "data" / "synthetic_batch.json"
    out_path.parent.mkdir(exist_ok=True)

    records = generate()
    out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    # Summary
    from collections import Counter
    dist = Counter(r["ground_truth"] for r in records)
    cat_c = [r for r in records if "epistemic_stalemate:" in r.get("scenario", "")]

    print(f"Generated {len(records)} records → {out_path}")
    print("\nGround-truth distribution:")
    for k, v in sorted(dist.items()):
        print(f"  {k:<30} {v}")
    print(f"\nCategory C ({len(cat_c)} stalemates to investigate):")
    for r in cat_c:
        print(f"  {r['record_id']}  {r['investigation_sub_case']:<25}  → {r['ground_truth']}")


if __name__ == "__main__":
    main()
