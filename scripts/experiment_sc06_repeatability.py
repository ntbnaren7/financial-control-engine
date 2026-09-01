"""
VALIDATION: SC-06 repeatability — 4 consecutive runs, two-pass v2, no changes
==============================================================================
PURPOSE:
    Determine whether the two-pass architecture is *reliably* correct on SC-06,
    not just correct once. Runs the exact same v2 experiment 4 times back-to-back
    with zero prompt/architecture changes between runs.

RECORDS PER RUN:
    - Pass-1 top hypothesis
    - Pass-1 rank uniqueness (are all 5 ranks distinct in artifact?)
    - Pass-2 schema validity (JSON + Pydantic)
    - Pass-2 drift (zero new claims?)
    - Evidence-ID validity (hallucinations?)
    - Invariant status (overlap violations?)
    - Rank uniqueness in final proposal
    - Token counts for Pass 1 and Pass 2 (latency root-cause)
    - Latency for each pass

CONSTRAINTS:
    - No production code modified.
    - No validator modified.
    - No prompt changes between runs.
    - Same model for both passes (qwen3:8b).
"""
import asyncio
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openai import AsyncOpenAI
from pydantic import ValidationError

from src.evidence.db import AsyncSessionLocal as session_maker
from src.evidence.gatherer import DatabaseEvidenceGatherer
from src.investigation.config import LLMConfig
from src.investigation.models import (
    EvidenceCoverage,
    EvidenceType,
    InvestigationProposal,
    StateTransitionCoverageContent,
    V0HypothesisType,
)
from src.investigation.validator import validate_proposal_invariants
from src.reconciliation.engine import M3Engine
from src.reconciliation.models import (
    MerchantOrderState,
    ProviderPayment,
    VerifiedDiscrepancy,
)
from scripts.validate_scenarios import seed_scenario_db

# Import the prompts and helpers from v2 — identical, zero modifications
from scripts.experiment_two_pass_sc06_v2 import (
    PASS1_SYSTEM,
    PASS2_SYSTEM,
    build_pass1_user,
    build_pass2_user,
    check_invariants,
    check_stage2_drift,
    extract_json,
    format_evidence_summary,
    parse_artifact,
    strip_think_tags,
)

MODEL = "qwen3:8b"
OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1")
N_RUNS = 4


async def run_once(
    client: AsyncOpenAI,
    run_idx: int,
    evidence_lines: str,
    valid_ids: set[str],
    sorted_ids: list[str],
    cfg: LLMConfig,
) -> dict:
    """Single two-pass SC-06 run. Returns a results dict."""
    print(f"\n{'─'*70}")
    print(f"RUN {run_idx + 1}/{N_RUNS}")
    print(f"{'─'*70}")

    r: dict = {
        "run": run_idx + 1,
        "p1_hypothesis": None,
        "p1_rank_unique": None,
        "p1_latency": None,
        "p1_output_tokens": None,
        "p2_json_valid": False,
        "p2_pydantic_valid": False,
        "p2_hypothesis": None,
        "p2_invariant": None,
        "p2_drift": None,
        "p2_structural_validator": None,
        "p2_latency": None,
        "p2_output_tokens": None,
        "total_latency": None,
    }

    # ── Pass 1 ────────────────────────────────────────────────────────────────
    print(f"  Pass 1... ", end="", flush=True)
    t1 = time.time()
    p1 = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PASS1_SYSTEM},
            {"role": "user", "content": build_pass1_user(evidence_lines, sorted_ids)},
        ],
        temperature=0.0,
    )
    t1_elapsed = time.time() - t1

    pass1_raw = p1.choices[0].message.content or ""
    pass1_clean = strip_think_tags(pass1_raw)
    p1_tokens = p1.usage.completion_tokens if p1.usage else None

    artifact = parse_artifact(pass1_clean)
    r["p1_hypothesis"] = artifact.get("selected", "<not parsed>")
    r["p1_latency"] = round(t1_elapsed, 1)
    r["p1_output_tokens"] = p1_tokens

    # Check rank uniqueness in the artifact
    decisions = artifact.get("hypothesis_decisions", {})
    artifact_ranks = [d["rank"] for d in decisions.values() if "rank" in d]
    r["p1_rank_unique"] = len(artifact_ranks) == len(set(artifact_ranks)) and sorted(artifact_ranks) == list(range(1, 6))

    print(f"Done ({t1_elapsed:.1f}s, {p1_tokens or '?'} tokens)  hypothesis={r['p1_hypothesis']}")

    # ── Pass 2 ────────────────────────────────────────────────────────────────
    print(f"  Pass 2... ", end="", flush=True)
    t2 = time.time()
    p2 = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PASS2_SYSTEM},
            {"role": "user", "content": build_pass2_user(pass1_clean, sorted_ids)},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=cfg.max_tokens,
        extra_body={"num_ctx": cfg.num_ctx},
    )
    t2_elapsed = time.time() - t2

    pass2_raw = p2.choices[0].message.content or ""
    pass2_json_str = extract_json(pass2_raw)
    p2_tokens = p2.usage.completion_tokens if p2.usage else None

    r["p2_latency"] = round(t2_elapsed, 1)
    r["p2_output_tokens"] = p2_tokens

    try:
        parsed_dict = json.loads(pass2_json_str)
        r["p2_json_valid"] = True
        proposal = InvestigationProposal.model_validate(parsed_dict)
        r["p2_pydantic_valid"] = True
        top = min(proposal.selections, key=lambda s: s.rank)
        r["p2_hypothesis"] = top.hypothesis_id.value

        inv = check_invariants(proposal, valid_ids)
        r["p2_invariant"] = "CLEAN" if not inv else f"VIOLATIONS: {inv}"

        drift = check_stage2_drift(artifact, proposal)
        r["p2_drift"] = "CLEAN" if not drift else f"DRIFT: {drift}"

        struct = validate_proposal_invariants(proposal, sorted_ids)
        r["p2_structural_validator"] = "PASS" if struct.is_valid else f"FAIL: {struct.errors}"
    except json.JSONDecodeError as e:
        r["p2_json_valid"] = False
        r["p2_invariant"] = f"JSON ERROR: {e}"
    except ValidationError as e:
        r["p2_pydantic_valid"] = False
        r["p2_invariant"] = f"PYDANTIC ERROR: {e}"

    r["total_latency"] = round(t1_elapsed + t2_elapsed, 1)
    p1_correct = r["p1_hypothesis"] == V0HypothesisType.EVIDENCE_INSUFFICIENT.value
    p2_correct = r["p2_hypothesis"] == V0HypothesisType.EVIDENCE_INSUFFICIENT.value
    print(
        f"Done ({t2_elapsed:.1f}s, {p2_tokens or '?'} tokens)  "
        f"hypothesis={r['p2_hypothesis']}  "
        f"drift={r['p2_drift']}  "
        f"struct={r['p2_structural_validator']}"
    )

    return r


async def main() -> None:
    # ── Seed evidence once; reuse across all runs ─────────────────────────────
    order_id = f"ord_sc06_rep_{uuid.uuid4().hex[:6]}"
    payment_id = f"pay_sc06_rep_{uuid.uuid4().hex[:6]}"
    await seed_scenario_db("SC-06", order_id, payment_id)

    payment = ProviderPayment(
        payment_id=payment_id, order_id=order_id,
        amount=5000, currency="INR", status="captured", captured=True,
        observed_at=datetime.now(timezone.utc),
    )
    order_state = MerchantOrderState(
        merchant_order_id=f"mo_{order_id}", razorpay_order_id=order_id,
        expected_amount=5000, currency="INR", status="UNPAID",
    )
    m3 = M3Engine()
    try:
        discrepancy = m3.evaluate_reconciliation(payment, order_state)
    except ValueError:
        discrepancy = None
    if not discrepancy:
        discrepancy = VerifiedDiscrepancy(
            discrepancy_id=f"disc_{order_id}", payment_id=payment_id, order_id=order_id,
            description="SC-06 repeatability", provider_status="captured",
            merchant_status="UNPAID", amount_match=True, currency_match=True,
            identity_verified=True,
        )

    gatherer = DatabaseEvidenceGatherer(session_maker)
    evidence_packet = await gatherer.gather(discrepancy)
    for ev in evidence_packet.items:
        if ev.type == EvidenceType.E_STATE_TRANSITION_COVERAGE:
            ev.content = StateTransitionCoverageContent(
                coverage=EvidenceCoverage.UNKNOWN, transition_count=0
            )

    valid_ids: set[str] = {ev.id for ev in evidence_packet.items}
    sorted_ids = sorted(valid_ids)
    evidence_lines = format_evidence_summary(evidence_packet.items)

    print(f"\n{'='*70}")
    print(f"REPEATABILITY TEST: SC-06  |  {N_RUNS} runs  |  Model: {MODEL}")
    print(f"Evidence IDs: {sorted_ids}")
    print(f"{'='*70}")

    client = AsyncOpenAI(base_url=OLLAMA_BASE, api_key="ollama")
    cfg = LLMConfig(model_name=MODEL)

    results = []
    for i in range(N_RUNS):
        r = await run_once(client, i, evidence_lines, valid_ids, sorted_ids, cfg)
        results.append(r)

    await client.close()

    # ── Summary table ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("REPEATABILITY REPORT — SC-06  (4 runs)")
    print(f"{'='*70}")
    header = (
        f"{'Run':>3}  {'P1-Hyp':>26}  {'P1-Rnks':>7}  {'P2-Hyp':>26}  "
        f"{'Drift':>5}  {'Struct':>6}  {'P1-tok':>6}  {'P2-tok':>6}  {'Total':>7}"
    )
    print(header)
    print("─" * len(header))

    h5 = V0HypothesisType.EVIDENCE_INSUFFICIENT.value
    for r in results:
        p1ok = "✓" if r["p1_hypothesis"] == h5 else "✗"
        p2ok = "✓" if r["p2_hypothesis"] == h5 else "✗"
        rnk = "✓" if r["p1_rank_unique"] else "✗"
        drift = "✓" if r["p2_drift"] == "CLEAN" else "✗"
        struct = "✓" if r["p2_structural_validator"] == "PASS" else "✗"
        p1t = str(r["p1_output_tokens"]) if r["p1_output_tokens"] else "?"
        p2t = str(r["p2_output_tokens"]) if r["p2_output_tokens"] else "?"
        print(
            f"{r['run']:>3}  {p1ok} {r['p1_hypothesis'] or 'None':>24}  "
            f"{rnk:>7}  {p2ok} {r['p2_hypothesis'] or 'None':>24}  "
            f"{drift:>5}  {struct:>6}  {p1t:>6}  {p2t:>6}  {r['total_latency']:>6.1f}s"
        )

    print()
    p1_correct = sum(1 for r in results if r["p1_hypothesis"] == h5)
    p2_correct = sum(1 for r in results if r["p2_hypothesis"] == h5)
    p1_rank_ok = sum(1 for r in results if r["p1_rank_unique"])
    drift_ok = sum(1 for r in results if r["p2_drift"] == "CLEAN")
    struct_ok = sum(1 for r in results if r["p2_structural_validator"] == "PASS")
    avg_total = sum(r["total_latency"] for r in results) / len(results)
    avg_p1 = sum(r["p1_latency"] for r in results) / len(results)
    avg_p2 = sum(r["p2_latency"] for r in results) / len(results)
    avg_p1_tok = [r["p1_output_tokens"] for r in results if r["p1_output_tokens"]]
    avg_p2_tok = [r["p2_output_tokens"] for r in results if r["p2_output_tokens"]]

    print(f"Pass-1 H5 correct         : {p1_correct}/{N_RUNS}")
    print(f"Pass-1 rank uniqueness    : {p1_rank_ok}/{N_RUNS}")
    print(f"Pass-2 H5 correct         : {p2_correct}/{N_RUNS}")
    print(f"Pass-2 stage-2 drift clean: {drift_ok}/{N_RUNS}")
    print(f"Pass-2 structural PASS    : {struct_ok}/{N_RUNS}")
    print(f"Avg latency Pass 1        : {avg_p1:.1f}s")
    print(f"Avg latency Pass 2        : {avg_p2:.1f}s")
    print(f"Avg total latency         : {avg_total:.1f}s")
    if avg_p1_tok:
        print(f"Avg output tokens Pass 1  : {sum(avg_p1_tok)//len(avg_p1_tok)}")
    if avg_p2_tok:
        print(f"Avg output tokens Pass 2  : {sum(avg_p2_tok)//len(avg_p2_tok)}")

    print(f"\n{'='*70}")
    print("REPEATABILITY TEST COMPLETE — do not modify production code.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
