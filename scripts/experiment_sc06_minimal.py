"""
EXPERIMENT: SC-06 Minimal Output Contract
==========================================
PURPOSE:
    Isolate whether Qwen3 8B's SC-06 failure is caused by output-contract
    complexity (5 ranked hypotheses + mutual-exclusive evidence IDs) or by
    genuine inability to reason about UNKNOWN coverage.

METHOD:
    - Exact same EvidencePacket and epistemic rules as production SC-06.
    - Exact same system prompt reasoning contract (no changes).
    - Simplified output schema: single hypothesis assessment only.
      { hypothesis_id, rationale, supporting_evidence_ids, contradicting_evidence_ids }
    - No 5-item ranking requirement.
    - No production validators, schemas, or code modified.

DO NOT:
    - Use this script's output to modify production code.
    - Make further prompt changes based on this result.
    - Merge this into the production pipeline.
"""
import asyncio
import json
import os
import sys
import uuid
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openai import AsyncOpenAI

from src.evidence.db import AsyncSessionLocal as session_maker
from src.evidence.gatherer import DatabaseEvidenceGatherer
from src.investigation.config import LLMConfig
from src.investigation.models import (
    DiscrepancyContext,
    HYPOTHESIS_DEFINITIONS,
    EvidenceType,
    EvidenceCoverage,
    StateTransitionCoverageContent,
    WebhookCoverageContent,
)


# Production imports for seeding only
from scripts.validate_scenarios import seed_scenario_db
from src.reconciliation.models import ProviderPayment, MerchantOrderState, VerifiedDiscrepancy
from src.reconciliation.engine import M3Engine

MODEL = "qwen3:8b"
SCENARIO_ID = "SC-06"

MINIMAL_OUTPUT_EXAMPLE = """{
  "hypothesis_id": "<ONE OF THE FIVE HYPOTHESIS IDs>",
  "rationale": "<explanation grounded in the evidence>",
  "supporting_evidence_ids": ["<EV-ID>"],
  "contradicting_evidence_ids": []
}"""

VALID_HYPOTHESIS_IDS = [
    "WEBHOOK_NOT_OBSERVED",
    "WEBHOOK_OBSERVED_NOT_PROCESSED",
    "WEBHOOK_PROCESSED_STATE_NOT_UPDATED",
    "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH",
    "EVIDENCE_INSUFFICIENT",
]


def build_system_prompt() -> str:
    hyp_block = []
    for defn in HYPOTHESIS_DEFINITIONS.values():
        hyp_block.append(f"### {defn.hypothesis_id.value}")
        hyp_block.append(f"**Meaning:** {defn.meaning}")
        hyp_block.append("**Supporting conditions:**")
        for c in defn.supporting_conditions:
            hyp_block.append(f"  - {c}")
        hyp_block.append("**Disqualifying conditions:**")
        for c in defn.disqualifying_conditions:
            hyp_block.append(f"  - {c}")
        hyp_block.append(f"**Uncertainty:** {defn.uncertainty_note}")
        hyp_block.append("")
    hypothesis_block = "\n".join(hyp_block)

    return (
        "You are an investigation assistant for a financial control engine.\n"
        "Analyze the provided discrepancy and evidence, then identify the single most "
        "likely causal hypothesis.\n\n"

        "## Reasoning Contract\n\n"
        "Reason over the observed event sequence. A hypothesis may be selected only when "
        "its supporting conditions are backed by authoritative evidence.\n\n"
        "**Critical epistemic rules:**\n"
        "- Step 1: Check coverage status.\n"
        "  * If any relevant coverage item (e.g. E_WEBHOOK_COVERAGE, E_PROCESSING_COVERAGE, "
        "E_STATE_TRANSITION_COVERAGE) has coverage='UNKNOWN' or is absent, "
        "you CANNOT conclude a specific event failure occurred (absence of record is inconclusive) "
        "-> You MUST select EVIDENCE_INSUFFICIENT.\n"
        "- Step 2: If coverage is COMPLETE, examine the observed event sequence:\n"
        "  * If no webhook observation is present and E_WEBHOOK_COVERAGE shows count 0 with COMPLETE "
        "coverage -> select WEBHOOK_NOT_OBSERVED.\n"
        "  * If webhook is present (E_WEBHOOK_CAPTURED) but E_PROCESSING_COVERAGE shows count 0 "
        "under COMPLETE coverage -> select WEBHOOK_OBSERVED_NOT_PROCESSED.\n"
        "  * If webhook is present, merchant processing succeeded (E_MERCHANT_PROCESSING status='PROCESSED'), "
        "but merchant order is UNPAID and transition count is 0 under COMPLETE coverage -> "
        "select WEBHOOK_PROCESSED_STATE_NOT_UPDATED.\n"
        "  * If all processing and transitions succeeded and states differ only in label -> "
        "select PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH.\n"
        "- Step 3: Consistency check:\n"
        "  * Do NOT select WEBHOOK_NOT_OBSERVED if a webhook observation (E_WEBHOOK_CAPTURED) "
        "is present (this is a fatal contradiction).\n"
        "  * Do NOT select a hypothesis whose disqualifying conditions are present.\n\n"

        "## Hypothesis Definitions\n\n"
        f"{hypothesis_block}"

        "## Required Output Format\n\n"
        "Output ONLY a raw JSON object. Do NOT output markdown code blocks.\n"
        "Select the single most appropriate hypothesis from this closed set:\n"
        f"{', '.join(VALID_HYPOTHESIS_IDS)}\n\n"
        "Use exactly this structure:\n"
        f"{MINIMAL_OUTPUT_EXAMPLE}\n\n"

        "## Output Rules\n"
        "- hypothesis_id: MUST be exactly one of the five IDs listed above. No other values.\n"
        "- rationale: Brief explanation grounded in the evidence.\n"
        "- supporting_evidence_ids: IDs from the supplied packet that support this hypothesis.\n"
        "- contradicting_evidence_ids: IDs that contradict this hypothesis. "
        "MUST NOT overlap with supporting_evidence_ids.\n"
        "- Raw JSON only."
    )


def build_user_prompt(context: DiscrepancyContext, evidence) -> str:
    prompt = (
        f"Case: {context.case_id}\n"
        f"Discrepancy: {context.description}\n"
        f"- Provider Status: {context.provider_status}\n"
        f"- Merchant Status: {context.merchant_status}\n"
        f"- Amount Match: {context.amount_match}\n"
        f"- Currency Match: {context.currency_match}\n"
        f"- Identity Verified: {context.identity_verified}\n\n"
        f"Supplied Evidence Packet ({len(evidence)} items):\n"
    )
    for ev in evidence:
        content_str = (
            ev.content.model_dump_json(exclude_none=True)
            if hasattr(ev.content, "model_dump_json")
            else json.dumps(ev.content)
        )
        prompt += f"- [{ev.id}] {ev.type.value}: {content_str}\n"
    return prompt


async def run_experiment():
    order_id = f"ord_sc06_exp_{uuid.uuid4().hex[:6]}"
    payment_id = f"pay_sc06_exp_{uuid.uuid4().hex[:6]}"

    # 1. Seed exact SC-06 database state
    await seed_scenario_db(SCENARIO_ID, order_id, payment_id)

    # 2. Build payment/order objects and gather evidence via production path
    payment = ProviderPayment(
        payment_id=payment_id,
        order_id=order_id,
        amount=5000,
        currency="INR",
        status="captured",
        captured=True,
        observed_at=datetime.now(timezone.utc),
    )
    order = MerchantOrderState(
        merchant_order_id=f"mo_{order_id}",
        razorpay_order_id=order_id,
        expected_amount=5000,
        currency="INR",
        status="UNPAID",
    )
    m3 = M3Engine()
    try:
        discrepancy = m3.evaluate_reconciliation(payment, order)
    except ValueError:
        discrepancy = None

    if not discrepancy:
        discrepancy = VerifiedDiscrepancy(
            discrepancy_id=f"disc_{order_id}",
            payment_id=payment_id,
            order_id=order_id,
            description="Reconciliation discrepancy for SC-06 experiment",
            provider_status="captured",
            merchant_status="UNPAID",
            amount_match=True,
            currency_match=True,
            identity_verified=True,
        )

    gatherer = DatabaseEvidenceGatherer(session_maker)
    evidence_packet = await gatherer.gather(discrepancy)

    # 3. Apply SC-06 epistemic override (exact same as production run_scenario)
    for ev in evidence_packet.items:
        if ev.type == EvidenceType.E_STATE_TRANSITION_COVERAGE:
            ev.content = StateTransitionCoverageContent(
                coverage=EvidenceCoverage.UNKNOWN, transition_count=0
            )

    context = DiscrepancyContext(
        case_id=discrepancy.discrepancy_id,
        description=discrepancy.description,
        provider_status=discrepancy.provider_status,
        merchant_status=discrepancy.merchant_status,
        amount_match=discrepancy.amount_match,
        currency_match=discrepancy.currency_match,
        identity_verified=discrepancy.identity_verified,
    )

    # 4. Call model with minimal output contract
    cfg = LLMConfig(
        model_name=MODEL,
        base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1"),
        api_key="ollama",
        temperature=0.0,
    )
    client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    print(f"\n{'='*70}")
    print(f"EXPERIMENT: SC-06 Minimal Contract — Model: {MODEL}")
    print(f"Evidence items: {len(evidence_packet.items)}")
    print(f"{'='*70}\n")
    print("Running inference... ", end="", flush=True)

    start = time.time()
    response = await client.chat.completions.create(
        model=cfg.model_name,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(context, evidence_packet.items)},
        ],
        response_format={"type": "json_object"},
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        extra_body={"num_ctx": cfg.num_ctx},
    )
    latency = time.time() - start
    raw_output = response.choices[0].message.content or ""

    print(f"Done ({latency:.2f}s)\n")

    # 5. Parse and report — no production validators invoked
    import re
    clean = re.sub(r"(?s)<think>.*?</think>", "", raw_output).strip()
    start_idx = clean.find("{")
    end_idx = clean.rfind("}")
    if start_idx != -1 and end_idx != -1:
        clean = clean[start_idx:end_idx + 1]

    print("RAW OUTPUT:")
    print("-" * 60)
    print(raw_output.strip())
    print("-" * 60)

    parsed = None
    parse_error = None
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        parse_error = str(e)

    print("\nPARSE RESULT:")
    if parse_error:
        print(f"  JSON parse failed: {parse_error}")
    else:
        data: dict = parsed  # type: ignore[assignment]  # narrowed: parse_error is None only when parsed succeeded
        hyp = data.get("hypothesis_id", "<MISSING>")
        valid = hyp in VALID_HYPOTHESIS_IDS
        correct = hyp == "EVIDENCE_INSUFFICIENT"
        print(f"  hypothesis_id    : {hyp}")
        print(f"  closed-set valid : {'YES' if valid else 'NO — HALLUCINATED'}")
        print(f"  correct (H5)     : {'YES' if correct else 'NO'}")
        print(f"  rationale        : {data.get('rationale', '')[:200]}")
        sup = data.get("supporting_evidence_ids", [])
        con = data.get("contradicting_evidence_ids", [])
        overlap = set(sup) & set(con)
        print(f"  supporting IDs   : {sup}")
        print(f"  contradicting IDs: {con}")
        print(f"  overlap violation: {'YES ' + str(overlap) if overlap else 'NO'}")

    print(f"\n{'='*70}")
    print("EXPERIMENT COMPLETE — do not use this output to modify production code.")
    print(f"{'='*70}\n")
    await client.close()


if __name__ == "__main__":
    asyncio.run(run_experiment())
