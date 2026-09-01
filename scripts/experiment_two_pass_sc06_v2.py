"""
EXPERIMENT: Two-pass SC-06 v2 — Reasoning Artifact + Mechanical Projection
===========================================================================
PURPOSE:
    Improve on v1 by making Pass 1 produce a COMPLETE semantic decision for
    all five hypotheses, so Pass 2 has zero inference to do. Pass 2's only
    job is mechanical projection of Stage-1's artifact into the proposal schema.

CHANGES FROM v1:
    - Pass 1 now produces a structured reasoning artifact covering ALL FIVE
      hypotheses (rank, confidence, supporting IDs, contradicting IDs, note).
    - Pass 2 is explicitly prohibited from determining eligibility, creating
      new evidence relationships, or reasoning about lower-ranked hypotheses.
    - Pass 2 instruction: "If Stage 1 did not establish a relationship, leave
      the evidence list empty."

CONSTRAINTS:
    - No production code modified.
    - No validator (semantic.py) modified.
    - No retries.
    - No second model (qwen3:8b for both passes).
    - Same SC-06 evidence packet as production.

SUCCESS CRITERIA:
    ✓ Pass 1 → H5
    ✓ Pass 2 → H5 (preserved, not re-derived)
    ✓ JSON valid
    ✓ Pydantic valid
    ✓ No hallucinated evidence IDs
    ✓ No evidence overlap invariant violation
    ✓ eligibility from Stage 1 (not independently decided by Stage 2)
    ✓ Lower-ranked evidence attribution from Stage 1 (not inferred by Stage 2)
    ✓ Zero new semantic claims introduced by Stage 2
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
from src.reconciliation.engine import M3Engine
from src.reconciliation.models import (
    MerchantOrderState,
    ProviderPayment,
    VerifiedDiscrepancy,
)
from scripts.validate_scenarios import seed_scenario_db

MODEL = "qwen3:8b"
OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1")

HYPOTHESIS_IDS = [h.value for h in V0HypothesisType]
HYPOTHESIS_NAMES_BLOCK = "\n".join(f"- {h}" for h in HYPOTHESIS_IDS)


# ---------------------------------------------------------------------------
# Pass 1: Reasoning → Structured Reasoning Artifact
# ---------------------------------------------------------------------------
PASS1_SYSTEM = (
    "You are a payment reconciliation analyst. "
    "Your job is to reason about payment discrepancies and produce a structured "
    "reasoning artifact covering all five hypotheses. "
    "Your output will be used by a downstream serializer — be explicit and precise."
)


def build_pass1_user(evidence_lines: str, valid_evidence_ids: list[str]) -> str:
    id_list = ", ".join(valid_evidence_ids)
    return f"""Payment discrepancy evidence (only these evidence IDs exist: {id_list}):
{evidence_lines}

CRITICAL EPISTEMIC RULE: For this case, state_transition_coverage = UNKNOWN.
Therefore, the absence of a state-transition observation cannot establish that
no state transition occurred. You must not conclude
WEBHOOK_PROCESSED_STATE_NOT_UPDATED or PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH
solely from the missing transition observation. If this uncertainty prevents
distinguishing the competing hypotheses, select EVIDENCE_INSUFFICIENT.

Five hypotheses (use these exact names):
{HYPOTHESIS_NAMES_BLOCK}

Reason step-by-step. Then produce a structured reasoning artifact in EXACTLY this format
(fill in every field; do not skip any hypothesis; use only IDs from the list above):

REASONING ARTIFACT
==================
ELIGIBILITY: <ELIGIBLE or INELIGIBLE — is this discrepancy worth investigating?>
SELECTED: <the single most likely hypothesis, exact name>
CONFIDENCE: <HIGH, MEDIUM, or LOW>
REASONING: <one-paragraph explanation of why SELECTED fits and why epistemic constraints apply>
UNCERTAINTIES: <bullet list of unresolved uncertainties that affected this decision>

HYPOTHESIS DECISIONS:
H1 WEBHOOK_NOT_OBSERVED: RANK=<2-5>, CONFIDENCE=<HIGH|MEDIUM|LOW>, SUPPORTING=[<comma-separated IDs or empty>], CONTRADICTING=[<comma-separated IDs or empty>], NOTE=<one sentence>
H2 WEBHOOK_OBSERVED_NOT_PROCESSED: RANK=<2-5>, CONFIDENCE=<HIGH|MEDIUM|LOW>, SUPPORTING=[<comma-separated IDs or empty>], CONTRADICTING=[<comma-separated IDs or empty>], NOTE=<one sentence>
H3 WEBHOOK_PROCESSED_STATE_NOT_UPDATED: RANK=<2-5>, CONFIDENCE=<HIGH|MEDIUM|LOW>, SUPPORTING=[<comma-separated IDs or empty>], CONTRADICTING=[<comma-separated IDs or empty>], NOTE=<one sentence>
H4 PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH: RANK=<2-5>, CONFIDENCE=<HIGH|MEDIUM|LOW>, SUPPORTING=[<comma-separated IDs or empty>], CONTRADICTING=[<comma-separated IDs or empty>], NOTE=<one sentence>
H5 EVIDENCE_INSUFFICIENT: RANK=<1-5>, CONFIDENCE=<HIGH|MEDIUM|LOW>, SUPPORTING=[<comma-separated IDs or empty>], CONTRADICTING=[<comma-separated IDs or empty>], NOTE=<one sentence>

Rules:
- SELECTED hypothesis must have RANK=1 in the HYPOTHESIS DECISIONS block.
- Ranks must be unique integers 1 through 5.
- Use ONLY evidence IDs from the list above.
- SUPPORTING and CONTRADICTING for the same hypothesis must NOT share any IDs.
- If you have no evidence to support or contradict a hypothesis, write [] (empty).
"""


# ---------------------------------------------------------------------------
# Pass 1 artifact parser — extracts structured decisions for Pass 2 report
# ---------------------------------------------------------------------------
def strip_think_tags(text: str) -> str:
    return re.sub(r"(?s)<think>.*?</think>", "", text).strip()


def parse_artifact(text: str) -> dict:
    """
    Parse the structured reasoning artifact from Pass 1.
    Returns a dict with eligibility, selected, confidence, and per-hypothesis decisions.
    Best-effort: missing fields left as None.
    """
    result: dict = {
        "eligibility": None,
        "selected": None,
        "confidence": None,
        "hypothesis_decisions": {},
    }

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ELIGIBILITY:"):
            result["eligibility"] = line.split(":", 1)[1].strip()
        elif line.startswith("SELECTED:"):
            result["selected"] = line.split(":", 1)[1].strip()
        elif line.startswith("CONFIDENCE:"):
            result["confidence"] = line.split(":", 1)[1].strip()
        else:
            # Match hypothesis decision lines:
            # H1 WEBHOOK_NOT_OBSERVED: RANK=2, CONFIDENCE=HIGH, SUPPORTING=[...], ...
            m = re.match(
                r"H\d\s+(\w+):\s+RANK=(\d+),\s*CONFIDENCE=(\w+),\s*SUPPORTING=\[([^\]]*)\],\s*CONTRADICTING=\[([^\]]*)\]",
                line,
            )
            if m:
                hyp_name = m.group(1)
                rank = int(m.group(2))
                conf = m.group(3)
                sup_raw = m.group(4).strip()
                con_raw = m.group(5).strip()
                sup = [s.strip() for s in sup_raw.split(",") if s.strip()] if sup_raw else []
                con = [c.strip() for c in con_raw.split(",") if c.strip()] if con_raw else []
                result["hypothesis_decisions"][hyp_name] = {
                    "rank": rank,
                    "confidence": conf,
                    "supporting": sup,
                    "contradicting": con,
                }
    return result


# ---------------------------------------------------------------------------
# Pass 2: Mechanical projection only — NO new reasoning
# ---------------------------------------------------------------------------
PASS2_SYSTEM = (
    "You are a serialization layer, not a reasoning layer. "
    "You will receive a pre-completed reasoning artifact. "
    "Your ONLY job is to project it into the required JSON schema. "
    "You are PROHIBITED from:\n"
    "  - Re-evaluating any evidence\n"
    "  - Changing the selected hypothesis\n"
    "  - Changing any rank or confidence level\n"
    "  - Creating new evidence relationships\n"
    "  - Determining eligibility independently\n"
    "  - Adding any claim not present in the reasoning artifact\n"
    "  - Filling empty evidence lists by inference\n"
    "If Stage 1 left an evidence list empty, emit an empty array. "
    "Transcribe, do not reason."
)


def build_pass2_user(
    artifact_text: str,
    valid_evidence_ids: list[str],
) -> str:
    id_list = ", ".join(f'"{eid}"' for eid in valid_evidence_ids)
    hyp_enum = ", ".join(f'"{h}"' for h in HYPOTHESIS_IDS)
    conf_enum = '"HIGH", "MEDIUM", "LOW"'

    schema = f"""{{
  "eligibility": <copy from artifact: "ELIGIBLE" or "INELIGIBLE">,
  "overall_confidence": <copy from artifact CONFIDENCE field: {conf_enum}>,
  "selections": [
    {{
      "hypothesis_id": <one of: {hyp_enum}>,
      "rank": <integer, copy from artifact>,
      "rationale": <copy NOTE from artifact for this hypothesis>,
      "confidence_band": <copy CONFIDENCE from artifact for this hypothesis: {conf_enum}>,
      "supporting_evidence_ids": [<copy from artifact SUPPORTING; use only IDs from: {id_list}>],
      "contradicting_evidence_ids": [<copy from artifact CONTRADICTING; use only IDs from: {id_list}>]
    }}
    // exactly 5 entries — one per hypothesis in the artifact, ranks 1 through 5
  ]
}}"""

    return (
        f"Valid evidence IDs (only these are allowed): {id_list}\n\n"
        f"Reasoning artifact to project:\n{artifact_text}\n\n"
        "PROJECTION RULES:\n"
        "- eligibility: copy EXACTLY from ELIGIBILITY field in artifact.\n"
        "- overall_confidence: copy EXACTLY from CONFIDENCE field in artifact.\n"
        "- For each hypothesis in HYPOTHESIS DECISIONS: copy rank, confidence, "
        "supporting IDs, and contradicting IDs exactly as given.\n"
        "- If artifact shows SUPPORTING=[] for a hypothesis, emit an empty array. Do NOT fill it.\n"
        "- If artifact shows CONTRADICTING=[] for a hypothesis, emit an empty array. Do NOT fill it.\n"
        "- Do NOT add any evidence ID not listed in the artifact for that hypothesis.\n"
        "- Do NOT change any rank.\n"
        "- rationale: copy the NOTE value from the artifact for that hypothesis.\n"
        "- Output ONLY the raw JSON object. No explanation. No commentary.\n\n"
        f"Required JSON schema:\n{schema}"
    )


# ---------------------------------------------------------------------------
# Validation helpers
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


def extract_json(text: str) -> str:
    clean = strip_think_tags(text)
    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1:
        return clean[start : end + 1]
    return clean


def check_invariants(proposal: InvestigationProposal, valid_ids: set[str]) -> list[str]:
    violations = []
    for sel in proposal.selections:
        overlap = set(sel.supporting_evidence_ids) & set(sel.contradicting_evidence_ids)
        if overlap:
            violations.append(f"rank={sel.rank} {sel.hypothesis_id}: ID overlap {overlap}")
        for eid in sel.supporting_evidence_ids + sel.contradicting_evidence_ids:
            if eid not in valid_ids:
                violations.append(f"rank={sel.rank} {sel.hypothesis_id}: hallucinated ID '{eid}'")
    return violations


def check_stage2_drift(
    artifact: dict,
    proposal: InvestigationProposal,
) -> list[str]:
    """
    Detect cases where Pass 2 introduced reasoning not present in the artifact.
    Returns list of drift observations (empty = clean transcription).
    """
    drifts = []
    decisions = artifact.get("hypothesis_decisions", {})

    for sel in proposal.selections:
        hyp_name = sel.hypothesis_id.value
        if hyp_name not in decisions:
            drifts.append(f"rank={sel.rank} {hyp_name}: not found in artifact")
            continue

        art_dec = decisions[hyp_name]

        # Rank drift
        if sel.rank != art_dec.get("rank"):
            drifts.append(
                f"{hyp_name}: rank changed {art_dec.get('rank')} → {sel.rank}"
            )

        # Supporting ID drift
        art_sup = set(art_dec.get("supporting", []))
        p2_sup = set(sel.supporting_evidence_ids)
        added_sup = p2_sup - art_sup
        dropped_sup = art_sup - p2_sup
        if added_sup:
            drifts.append(f"{hyp_name}: Stage 2 ADDED supporting IDs {added_sup} (not in artifact)")
        if dropped_sup:
            drifts.append(f"{hyp_name}: Stage 2 DROPPED supporting IDs {dropped_sup} (were in artifact)")

        # Contradicting ID drift
        art_con = set(art_dec.get("contradicting", []))
        p2_con = set(sel.contradicting_evidence_ids)
        added_con = p2_con - art_con
        dropped_con = art_con - p2_con
        if added_con:
            drifts.append(f"{hyp_name}: Stage 2 ADDED contradicting IDs {added_con} (not in artifact)")
        if dropped_con:
            drifts.append(f"{hyp_name}: Stage 2 DROPPED contradicting IDs {dropped_con} (were in artifact)")

    # Eligibility drift
    art_eligibility = artifact.get("eligibility", "").upper()
    p2_eligibility = proposal.eligibility.value.upper()
    if art_eligibility and art_eligibility != p2_eligibility:
        drifts.append(f"eligibility: Stage 2 changed '{art_eligibility}' → '{p2_eligibility}'")

    return drifts


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------
async def run_experiment() -> None:
    # ── 1. Seed and gather SC-06 evidence ────────────────────────────────────
    order_id = f"ord_sc06_v2_{uuid.uuid4().hex[:6]}"
    payment_id = f"pay_sc06_v2_{uuid.uuid4().hex[:6]}"

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
            description="SC-06 two-pass v2 experiment",
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
    sorted_ids = sorted(valid_ids)
    evidence_lines = format_evidence_summary(evidence_packet.items)

    print(f"\n{'='*70}")
    print(f"EXPERIMENT: Two-pass SC-06 v2  |  Model: {MODEL}  |  {len(valid_ids)} evidence items")
    print(f"Valid evidence IDs: {sorted_ids}")
    print(f"{'='*70}")

    client = AsyncOpenAI(base_url=OLLAMA_BASE, api_key="ollama")
    cfg = LLMConfig(model_name=MODEL)

    # ── PASS 1: Free reasoning → structured artifact ──────────────────────────
    print("\n[ PASS 1 — Free reasoning → structured reasoning artifact ]")
    print("Running... ", end="", flush=True)

    t1_start = time.time()
    p1_response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PASS1_SYSTEM},
            {"role": "user", "content": build_pass1_user(evidence_lines, sorted_ids)},
        ],
        temperature=0.0,
        # No response_format — intentionally unconstrained
    )
    t1 = time.time() - t1_start
    pass1_raw = p1_response.choices[0].message.content or ""
    pass1_clean = strip_think_tags(pass1_raw)

    print(f"Done ({t1:.1f}s)")
    print(f"\nPASS 1 RAW OUTPUT:\n{'-'*60}")
    print(pass1_clean if pass1_clean else "<EMPTY>")
    print("-" * 60)

    # Parse the artifact
    artifact = parse_artifact(pass1_clean)
    pass1_selected = artifact.get("selected", "")
    pass1_correct = pass1_selected == V0HypothesisType.EVIDENCE_INSUFFICIENT.value

    # ── PASS 2: Mechanical projection ────────────────────────────────────────
    print("\n[ PASS 2 — Mechanical projection → InvestigationProposal ]")
    print("Running... ", end="", flush=True)

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
    print(f"\nPASS 2 RAW OUTPUT:\n{'-'*60}")
    print(pass2_raw.strip() if pass2_raw.strip() else "<EMPTY>")
    print("-" * 60)

    # ── Parse and validate ────────────────────────────────────────────────────
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
    except json.JSONDecodeError as e:
        print(f"\n  [!] JSON parse error: {e}")
    except ValidationError as e:
        print(f"\n  [!] Pydantic validation error:\n{e}")

    # ── Final report ──────────────────────────────────────────────────────────
    total = t1 + t2
    print(f"\n{'='*70}")
    print("REPORT")
    print(f"{'='*70}")

    print(f"\nPASS 1")
    print(f"  Hypothesis : {pass1_selected or '<not parsed>'}")
    print(f"  Correct    : {'YES (H5)' if pass1_correct else 'NO'}")
    print(f"  Latency    : {t1:.1f}s")

    print(f"\nPASS 2")
    print(f"  JSON valid       : {'YES' if json_valid else 'NO'}")
    print(f"  Pydantic valid   : {'YES' if pydantic_valid else 'NO'}")
    print(f"  Hypothesis (r=1) : {pass2_hypothesis or '<not extracted>'}")
    print(f"  Correct          : {'YES (H5)' if pass2_hypothesis == V0HypothesisType.EVIDENCE_INSUFFICIENT.value else 'NO'}")

    has_hallucinations = any("hallucinated" in v for v in invariant_violations)
    print(f"  Evidence IDs     : {'ALL VALID' if json_valid and not has_hallucinations else 'VIOLATIONS: ' + str([v for v in invariant_violations if 'hallucinated' in v])}")
    print(f"  Invariant        : {'CLEAN' if not invariant_violations else 'VIOLATIONS: ' + str(invariant_violations)}")
    print(f"  Stage-2 drift    : {'CLEAN (zero new claims)' if not stage2_drifts else 'DRIFT DETECTED: ' + str(stage2_drifts)}")
    print(f"  Latency          : {t2:.1f}s")

    print(f"\nTOTAL LATENCY : {total:.1f}s")
    print(f"\n{'='*70}")
    print("EXPERIMENT COMPLETE — do not modify production code based on this output.")
    print(f"{'='*70}\n")

    await client.close()


if __name__ == "__main__":
    asyncio.run(run_experiment())
