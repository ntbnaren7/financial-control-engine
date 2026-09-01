"""
EXPERIMENT: Two-pass SC-03 v2 — Reasoning Artifact + Mechanical Projection
===========================================================================
PURPOSE:
    Verify that the two-pass v2 architecture correctly solves SC-03 (where H3
    is the correct answer) and does not regress on the "happy path" case.
"""
import asyncio
import json
import os
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
    InvestigationProposal,
    V0HypothesisType,
)
from src.reconciliation.engine import M3Engine
from src.reconciliation.models import (
    MerchantOrderState,
    ProviderPayment,
    VerifiedDiscrepancy,
)
from scripts.validate_scenarios import seed_scenario_db

# Import prompts and helpers directly from v2
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


async def run_experiment() -> None:
    order_id = f"ord_sc03_v2_{uuid.uuid4().hex[:6]}"
    payment_id = f"pay_sc03_v2_{uuid.uuid4().hex[:6]}"

    await seed_scenario_db("SC-03", order_id, payment_id)

    payment = ProviderPayment(
        payment_id=payment_id,
        order_id=order_id,
        amount=5000,
        currency="INR",
        status="captured",
        captured=True,
        observed_at=datetime.now(timezone.utc),
    )
    order_state = MerchantOrderState(
        merchant_order_id=f"mo_{order_id}",
        razorpay_order_id=order_id,
        expected_amount=5000,
        currency="INR",
        status="UNPAID",
    )
    m3 = M3Engine()
    try:
        discrepancy = m3.evaluate_reconciliation(payment, order_state)
    except ValueError:
        discrepancy = None

    if not discrepancy:
        discrepancy = VerifiedDiscrepancy(
            discrepancy_id=f"disc_{order_id}",
            payment_id=payment_id,
            order_id=order_id,
            description="SC-03 two-pass v2 experiment",
            provider_status="captured",
            merchant_status="UNPAID",
            amount_match=True,
            currency_match=True,
            identity_verified=True,
        )

    gatherer = DatabaseEvidenceGatherer(session_maker)
    evidence_packet = await gatherer.gather(discrepancy)

    # Note: Unlike SC-06, we do NOT apply the epistemic override (UNKNOWN state-transition coverage).
    # SC-03 has COMPLETE state-transition coverage with count 0.

    valid_ids: set[str] = {ev.id for ev in evidence_packet.items}
    sorted_ids = sorted(valid_ids)
    evidence_lines = format_evidence_summary(evidence_packet.items)

    print(f"\n{'='*70}")
    print(f"EXPERIMENT: Two-pass SC-03 v2  |  Model: {MODEL}  |  {len(valid_ids)} evidence items")
    print(f"Valid evidence IDs: {sorted_ids}")
    print(f"{'='*70}")

    client = AsyncOpenAI(base_url=OLLAMA_BASE, api_key="ollama")
    cfg = LLMConfig(model_name=MODEL)

    # ── PASS 1 ────────────────────────────────────────────────────────────────
    print("\n[ PASS 1 — Free reasoning → structured reasoning artifact ]")
    t1_start = time.time()
    p1_response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PASS1_SYSTEM},
            {"role": "user", "content": build_pass1_user(evidence_lines, sorted_ids)},
        ],
        temperature=0.0,
    )
    t1 = time.time() - t1_start
    pass1_raw = p1_response.choices[0].message.content or ""
    pass1_clean = strip_think_tags(pass1_raw)

    print(f"Done ({t1:.1f}s)")
    print(f"\nPASS 1 RAW OUTPUT:\n{'-'*60}")
    print(pass1_clean if pass1_clean else "<EMPTY>")
    print("-" * 60)

    artifact = parse_artifact(pass1_clean)
    pass1_selected = artifact.get("selected", "")
    pass1_correct = pass1_selected == V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED.value

    # ── PASS 2 ────────────────────────────────────────────────────────────────
    print("\n[ PASS 2 — Mechanical projection → InvestigationProposal ]")
    t2_start = time.time()
    p2_response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PASS2_SYSTEM},
            {
                "role": "user",
                "content": build_pass2_user(pass1_clean, sorted_ids),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=cfg.max_tokens,
        extra_body={"num_ctx": cfg.num_ctx},
    )
    t2 = time.time() - t2_start
    pass2_raw = p2_response.choices[0].message.content or ""
    pass2_json_str = extract_json(pass2_raw)

    print(f"Done ({t2:.1f}s)")
    
    json_valid = False
    pydantic_valid = False
    pass2_hypothesis: str | None = None
    invariant_violations: list[str] = []
    stage2_drifts: list[str] = []
    proposal: InvestigationProposal | None = None

    try:
        parsed_dict = json.loads(pass2_json_str)
        json_valid = True
        proposal = InvestigationProposal.model_validate(parsed_dict)
        pydantic_valid = True
        top = min(proposal.selections, key=lambda s: s.rank)
        pass2_hypothesis = top.hypothesis_id.value
        invariant_violations = check_invariants(proposal, valid_ids)
        stage2_drifts = check_stage2_drift(artifact, proposal)
    except Exception as e:
        pass

    total = t1 + t2
    print(f"\n{'='*70}")
    print("REPORT")
    print(f"{'='*70}")

    print(f"\nPASS 1")
    print(f"  Hypothesis : {pass1_selected or '<not parsed>'}")
    print(f"  Correct    : {'YES (H3)' if pass1_correct else 'NO'}")
    
    print(f"\nPASS 2")
    print(f"  JSON valid       : {'YES' if json_valid else 'NO'}")
    print(f"  Pydantic valid   : {'YES' if pydantic_valid else 'NO'}")
    print(f"  Hypothesis (r=1) : {pass2_hypothesis or '<not extracted>'}")
    print(f"  Correct          : {'YES (H3)' if pass2_hypothesis == V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED.value else 'NO'}")
    print(f"  Invariant        : {'CLEAN' if not invariant_violations else 'VIOLATIONS: ' + str(invariant_violations)}")
    print(f"  Stage-2 drift    : {'CLEAN (zero new claims)' if not stage2_drifts else 'DRIFT DETECTED: ' + str(stage2_drifts)}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(run_experiment())
