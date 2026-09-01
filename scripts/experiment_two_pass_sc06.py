"""
EXPERIMENT: Two-pass SC-06 — Qwen3 8B (same model, two calls)
==============================================================
PURPOSE:
    Test whether separating reasoning (Pass 1, free text) from serialization
    (Pass 2, constrained JSON) produces a correct, valid InvestigationProposal
    for SC-06 without modifying any production code.

ARCHITECTURE UNDER TEST:
    EvidencePacket
         │
         ▼
    [Pass 1 — Free reasoning, no JSON, explicit epistemic rules]
         │ → Reasoning Artifact (free text)
         ▼
    [Pass 2 — JSON serialization only, no new reasoning]
         │ → InvestigationProposal (JSON)
         ▼
    [Checks — parse, Pydantic, invariant, hypothesis, evidence IDs]

CONSTRAINTS:
    - No production code modified.
    - No validator (semantic.py) modified.
    - No retries.
    - No second model (qwen3:8b for both passes).
    - Exact same SC-06 evidence as production.

REPORT FORMAT:
    PASS 1: hypothesis, reasoning, latency
    PASS 2: JSON valid, hypothesis, evidence IDs valid, invariant valid, latency
    TOTAL LATENCY
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
    ConfidenceBand,
    EvidenceType,
    InvestigationEligibility,
    InvestigationProposal,
    StateTransitionCoverageContent,
    EvidenceCoverage,
    V0HypothesisType,
)
from src.reconciliation.engine import M3Engine
from src.reconciliation.models import MerchantOrderState, ProviderPayment, VerifiedDiscrepancy
from scripts.validate_scenarios import seed_scenario_db

MODEL = "qwen3:8b"
OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1")

HYPOTHESIS_IDS = [h.value for h in V0HypothesisType]
HYPOTHESIS_NAMES_BLOCK = "\n".join(f"- {h}" for h in HYPOTHESIS_IDS)


# ---------------------------------------------------------------------------
# Pass 1: Reasoning prompt
# ---------------------------------------------------------------------------
PASS1_SYSTEM = (
    "You are a payment reconciliation analyst. "
    "Your job is to reason carefully about payment discrepancies and determine "
    "the single most likely root cause, taking epistemic uncertainty seriously."
)

def build_pass1_user(evidence_summary: str) -> str:
    return (
        f"Payment discrepancy evidence:\n{evidence_summary}\n\n"
        "CRITICAL EPISTEMIC RULE: For this case, state_transition_coverage = UNKNOWN. "
        "Therefore, the absence of a state-transition observation cannot establish that "
        "no state transition occurred. You must not conclude "
        "WEBHOOK_PROCESSED_STATE_NOT_UPDATED or "
        "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH solely from the missing "
        "transition observation. If this uncertainty prevents distinguishing the "
        "competing hypotheses, select EVIDENCE_INSUFFICIENT.\n\n"
        f"Five possible root causes:\n{HYPOTHESIS_NAMES_BLOCK}\n\n"
        "Reason through the evidence step by step. Then state:\n"
        "1. Your selected hypothesis (exact name from the list above)\n"
        "2. Why this hypothesis fits\n"
        "3. Why alternatives are weaker\n"
        "4. Any unresolved uncertainty that influenced your selection"
    )


# ---------------------------------------------------------------------------
# Pass 2: Serialization prompt
# ---------------------------------------------------------------------------
PASS2_SYSTEM = (
    "You are a JSON serializer for a financial control system. "
    "Your ONLY job is to convert a reasoning artifact into a structured proposal. "
    "Do NOT introduce new conclusions. Do NOT change the selected hypothesis. "
    "Do NOT reason further. Faithfully represent what the reasoning says."
)

def build_pass2_user(
    evidence_lines: str,
    pass1_reasoning: str,
    valid_evidence_ids: list[str],
) -> str:
    id_list = ", ".join(f'"{eid}"' for eid in valid_evidence_ids)
    hyp_enum = ", ".join(f'"{h}"' for h in HYPOTHESIS_IDS)
    conf_enum = '"HIGH", "MEDIUM", "LOW"'

    schema = f"""{{
  "eligibility": <"ELIGIBLE" or "INELIGIBLE">,
  "overall_confidence": <{conf_enum}>,
  "selections": [
    {{
      "hypothesis_id": <one of: {hyp_enum}>,
      "rank": <integer 1-5, must be unique>,
      "rationale": <brief string>,
      "confidence_band": <{conf_enum}>,
      "supporting_evidence_ids": [<zero or more from: {id_list}>],
      "contradicting_evidence_ids": [<zero or more from: {id_list}>]
    }}
    // ... exactly 5 entries, ranks 1 through 5, no duplicate ranks
  ]
}}"""

    return (
        f"Evidence items (use only these IDs):\n{evidence_lines}\n\n"
        f"Reasoning artifact from Pass 1:\n{pass1_reasoning}\n\n"
        "SERIALIZATION RULES:\n"
        "- hypothesis_id MUST be exactly one of the five values listed in the schema.\n"
        "- supporting_evidence_ids and contradicting_evidence_ids MUST contain only IDs from the evidence list above.\n"
        "- supporting_evidence_ids and contradicting_evidence_ids for the same hypothesis MUST NOT overlap.\n"
        "- selections MUST contain exactly 5 entries with unique ranks 1 through 5.\n"
        "- Rank 1 must reflect the hypothesis selected in the reasoning artifact.\n"
        "- Do NOT introduce a hypothesis or evidence ID not present in this prompt.\n\n"
        "Output ONLY the raw JSON object matching this schema:\n"
        f"{schema}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def format_evidence_summary(items) -> str:
    lines = []
    for ev in items:
        content_str = (
            ev.content.model_dump_json(exclude_none=True)
            if hasattr(ev.content, "model_dump_json")
            else json.dumps(ev.content)
        )
        lines.append(f"[{ev.id}] {ev.type.value}: {content_str}")
    return "\n".join(lines)


def extract_first_hypothesis(text: str) -> str | None:
    upper = text.upper()
    for h in HYPOTHESIS_IDS:
        if h in upper:
            return h
    return None


def strip_think_tags(text: str) -> str:
    return re.sub(r"(?s)<think>.*?</think>", "", text).strip()


def extract_json(text: str) -> str:
    clean = strip_think_tags(text)
    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1:
        return clean[start : end + 1]
    return clean


def check_evidence_id_invariant(proposal: InvestigationProposal, valid_ids: set[str]) -> list[str]:
    """Returns list of violations (empty = clean)."""
    violations = []
    for sel in proposal.selections:
        # Overlap check
        overlap = set(sel.supporting_evidence_ids) & set(sel.contradicting_evidence_ids)
        if overlap:
            violations.append(
                f"rank={sel.rank} {sel.hypothesis_id}: "
                f"evidence ID overlap {overlap}"
            )
        # Unknown ID check
        for eid in sel.supporting_evidence_ids + sel.contradicting_evidence_ids:
            if eid not in valid_ids:
                violations.append(
                    f"rank={sel.rank} {sel.hypothesis_id}: "
                    f"hallucinated evidence ID '{eid}'"
                )
    return violations


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------
async def run_experiment() -> None:
    # ── 1. Seed and gather SC-06 evidence (identical to production) ──────────
    order_id = f"ord_sc06_2p_{uuid.uuid4().hex[:6]}"
    payment_id = f"pay_sc06_2p_{uuid.uuid4().hex[:6]}"

    await seed_scenario_db("SC-06", order_id, payment_id)

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
            description="SC-06 two-pass experiment",
            provider_status="captured",
            merchant_status="UNPAID",
            amount_match=True,
            currency_match=True,
            identity_verified=True,
        )

    gatherer = DatabaseEvidenceGatherer(session_maker)
    evidence_packet = await gatherer.gather(discrepancy)

    # Apply SC-06 epistemic override (UNKNOWN state-transition coverage)
    for ev in evidence_packet.items:
        if ev.type == EvidenceType.E_STATE_TRANSITION_COVERAGE:
            ev.content = StateTransitionCoverageContent(
                coverage=EvidenceCoverage.UNKNOWN, transition_count=0
            )

    valid_ids: set[str] = {ev.id for ev in evidence_packet.items}
    evidence_summary = format_evidence_summary(evidence_packet.items)

    print(f"\n{'='*70}")
    print(f"EXPERIMENT: Two-pass SC-06  |  Model: {MODEL}  |  {len(valid_ids)} evidence items")
    print(f"Valid evidence IDs: {sorted(valid_ids)}")
    print(f"{'='*70}")

    client = AsyncOpenAI(base_url=OLLAMA_BASE, api_key="ollama")
    cfg = LLMConfig(model_name=MODEL)

    # ── PASS 1: Free reasoning ───────────────────────────────────────────────
    print("\n[ PASS 1 — Free reasoning, no JSON ]")
    print("Running... ", end="", flush=True)

    t1_start = time.time()
    p1_response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PASS1_SYSTEM},
            {"role": "user", "content": build_pass1_user(evidence_summary)},
        ],
        temperature=0.0,
        # No response_format — intentionally unconstrained
    )
    t1 = time.time() - t1_start
    pass1_raw = p1_response.choices[0].message.content or ""
    pass1_clean = strip_think_tags(pass1_raw)

    pass1_hypothesis = extract_first_hypothesis(pass1_clean)
    pass1_correct = pass1_hypothesis == V0HypothesisType.EVIDENCE_INSUFFICIENT.value

    print(f"Done ({t1:.1f}s)")
    print(f"\nPASS 1 RAW OUTPUT:\n{'-'*60}")
    print(pass1_clean if pass1_clean else "<EMPTY>")
    print("-" * 60)

    # ── PASS 2: Constrained serialization ───────────────────────────────────
    print("\n[ PASS 2 — Serialization to InvestigationProposal ]")
    print("Running... ", end="", flush=True)

    t2_start = time.time()
    p2_response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PASS2_SYSTEM},
            {
                "role": "user",
                "content": build_pass2_user(
                    evidence_summary, pass1_clean, sorted(valid_ids)
                ),
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
    print(f"\nPASS 2 RAW OUTPUT:\n{'-'*60}")
    print(pass2_raw.strip() if pass2_raw.strip() else "<EMPTY>")
    print("-" * 60)

    # ── Parse and validate Pass 2 ────────────────────────────────────────────
    json_valid = False
    pydantic_valid = False
    pass2_hypothesis: str | None = None
    invariant_violations: list[str] = []
    proposal: InvestigationProposal | None = None

    try:
        parsed_dict = json.loads(pass2_json_str)
        json_valid = True
        proposal = InvestigationProposal.model_validate(parsed_dict)
        pydantic_valid = True
        top = min(proposal.selections, key=lambda s: s.rank)
        pass2_hypothesis = top.hypothesis_id.value
        invariant_violations = check_evidence_id_invariant(proposal, valid_ids)
    except json.JSONDecodeError as e:
        print(f"\n  [!] JSON parse error: {e}")
    except ValidationError as e:
        print(f"\n  [!] Pydantic validation error:\n{e}")

    # ── Final report ─────────────────────────────────────────────────────────
    total = t1 + t2
    print(f"\n{'='*70}")
    print("REPORT")
    print(f"{'='*70}")
    print(f"\nPASS 1")
    print(f"  Hypothesis : {pass1_hypothesis or '<not found>'}")
    print(f"  Correct    : {'YES (H5)' if pass1_correct else 'NO'}")
    print(f"  Latency    : {t1:.1f}s")

    print(f"\nPASS 2")
    print(f"  JSON valid       : {'YES' if json_valid else 'NO'}")
    print(f"  Pydantic valid   : {'YES' if pydantic_valid else 'NO'}")
    print(f"  Hypothesis (r=1) : {pass2_hypothesis or '<not extracted>'}")
    print(f"  Correct    : {'YES (H5)' if pass2_hypothesis == V0HypothesisType.EVIDENCE_INSUFFICIENT.value else 'NO'}")
    print(f"  Evidence IDs     : {'ALL VALID' if json_valid and not any('hallucinated' in v for v in invariant_violations) else 'VIOLATIONS: ' + str([v for v in invariant_violations if 'hallucinated' in v])}")
    print(f"  Invariant        : {'CLEAN' if not invariant_violations else 'VIOLATIONS: ' + str(invariant_violations)}")
    print(f"  Latency          : {t2:.1f}s")

    print(f"\nTOTAL LATENCY : {total:.1f}s")
    print(f"\n{'='*70}")
    print("EXPERIMENT COMPLETE — do not modify production code based on this output.")
    print(f"{'='*70}\n")

    await client.close()


if __name__ == "__main__":
    asyncio.run(run_experiment())
