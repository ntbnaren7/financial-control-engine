"""
DIAGNOSTIC: Minimal free-text reasoning test — SC-03 + SC-06
=============================================================
PURPOSE:
    Determine whether Qwen3 8B can perform the core epistemic reasoning
    task when completely stripped of:
      - JSON output contract
      - evidence-ID arrays
      - formal hypothesis definitions
      - multi-field schema
      - production validator

    This answers: "Is the failure in reasoning, or in structured generation?"

TWO CASES:
    SC-03 — Processed State Stale (expected: H3 WEBHOOK_PROCESSED_STATE_NOT_UPDATED)
    SC-06 — Epistemic Indeterminacy (expected: H5 EVIDENCE_INSUFFICIENT)

OUTPUT:
    For each case: raw model text, selected hypothesis (parsed from text), latency.

DO NOT use this output to modify production code.
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openai import AsyncOpenAI

MODEL = "qwen3:8b"
OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1")

HYPOTHESIS_NAMES = [
    "WEBHOOK_NOT_OBSERVED",
    "WEBHOOK_OBSERVED_NOT_PROCESSED",
    "WEBHOOK_PROCESSED_STATE_NOT_UPDATED",
    "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH",
    "EVIDENCE_INSUFFICIENT",
]

# ---------------------------------------------------------------------------
# Evidence summaries — plain English, no IDs, no schema fields.
# These reproduce the exact epistemic content of SC-03 and SC-06.
# ---------------------------------------------------------------------------

SC03_EVIDENCE = """
Payment captured by Razorpay: YES
Webhook event received: YES
Merchant processing record: YES, status = PROCESSED
State transition (processing → settled) recorded: NO  
State-transition observation coverage: COMPLETE (the observation layer 
  has full coverage — if a transition had occurred, it would have been recorded)
Merchant order status: UNPAID
"""

SC06_EVIDENCE = """
Payment captured by Razorpay: YES
Webhook event received: YES
Merchant processing record: YES, status = PROCESSED
State transition (processing → settled) recorded: NO
State-transition observation coverage: UNKNOWN (we do not know whether the
  observation layer has full coverage — the absence of a transition record
  could mean the transition never happened, OR it could mean we simply
  didn't observe it)
Merchant order status: UNPAID
"""

SYSTEM_PROMPT = (
    "You are a payment reconciliation analyst. "
    "You will be shown the state of a payment discrepancy. "
    "Pick the single most likely root cause from the five options listed."
)

def build_user_prompt(evidence: str, epistemic_rule: str = "") -> str:
    hyp_list = "\n".join(f"- {h}" for h in HYPOTHESIS_NAMES)
    rule_block = f"\n\n{epistemic_rule}" if epistemic_rule else ""
    return (
        f"Payment discrepancy evidence:\n{evidence}{rule_block}\n\n"
        f"Five possible root causes:\n{hyp_list}\n\n"
        "Which single root cause best fits the evidence? "
        "State the hypothesis name, then explain in one sentence why."
    )


def parse_hypothesis(text: str) -> str | None:
    """Extract the first hypothesis name found in the model's response."""
    upper = text.upper()
    for h in HYPOTHESIS_NAMES:
        if h in upper:
            return h
    return None


async def run_case(
    client: AsyncOpenAI,
    label: str,
    evidence: str,
    expected: str,
    epistemic_rule: str = "",
) -> None:
    print(f"\n{'='*70}")
    print(f"CASE: {label}  (expected: {expected})")
    print(f"{'='*70}")
    print("Running inference... ", end="", flush=True)

    start = time.time()
    response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(evidence, epistemic_rule)},
        ],
        temperature=0.0,
        # No response_format — pure free text
    )
    latency = time.time() - start
    raw = response.choices[0].message.content or ""

    print(f"Done ({latency:.1f}s)\n")
    print("RAW OUTPUT:")
    print("-" * 60)
    print(raw.strip() if raw.strip() else "<EMPTY>")
    print("-" * 60)

    parsed = parse_hypothesis(raw)
    correct = parsed == expected

    print(f"\nPARSED HYPOTHESIS : {parsed or '<not found>'}")
    print(f"EXPECTED          : {expected}")
    print(f"CORRECT           : {'YES' if correct else 'NO'}")
    print(f"EMPTY OUTPUT      : {'YES' if not raw.strip() else 'NO'}")


SC06_EPISTEMIC_RULE = (
    "CRITICAL EPISTEMIC RULE: For this case, state_transition_coverage = UNKNOWN. "
    "Therefore, the absence of a state-transition observation cannot establish that "
    "no state transition occurred. You must not conclude "
    "WEBHOOK_PROCESSED_STATE_NOT_UPDATED or "
    "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH solely from the missing "
    "transition observation. If this uncertainty prevents distinguishing the "
    "competing hypotheses, select EVIDENCE_INSUFFICIENT."
)


async def main() -> None:
    client = AsyncOpenAI(base_url=OLLAMA_BASE, api_key="ollama")

    print(f"MODEL  : {MODEL}")
    print(f"OLLAMA : {OLLAMA_BASE}")
    print("\nOption 1 experiment — SC-06 only, with SC-06-scoped UNKNOWN coverage rule.")
    print("No production code, schema, or validator modified.")

    await run_case(
        client,
        label="SC-06 (Epistemic Indeterminacy) — with UNKNOWN coverage rule",
        evidence=SC06_EVIDENCE,
        expected="EVIDENCE_INSUFFICIENT",
        epistemic_rule=SC06_EPISTEMIC_RULE,
    )

    print(f"\n{'='*70}")
    print("OPTION 1 EXPERIMENT COMPLETE")
    print("Do not modify production code based on this output.")
    print(f"{'='*70}\n")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
