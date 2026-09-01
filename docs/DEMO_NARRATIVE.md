# FCE Demo Narrative Script

This script is designed for a video presentation or live demo. It traces exactly one hero incident to prove the boundaries of the Financial Control Engine.

## The Setup
**Speaker:** "Welcome to the Financial Control Engine demo. We are going to show you how we solve one of the most frustrating problems in payments: the silent failure."

*(Show the database state or terminal.)*

**Speaker:** "Here we have a simulated incident. A customer paid ₹5,000 via Razorpay. The money was captured. But the webhook failed. The internal merchant order is stuck in the `UNPAID` state. We are going to trigger the FCE pipeline to fix it."

## Controller Breadth (Track 4 Batch Acceptance)
**Action:** *Run the batch evaluation via CLI (`uv run scripts/run_batch_evaluation.py`).*

**Speaker:** "But before we dive into how that single incident is fixed, let's look at the system's operational breadth. We just fed a synthetic finance-ops workload of 50 financial cases into the controller."

*(Point to the terminal output showing 50 records processed, 100% synthetic oracle conformance, and 0 unauthorized mutations under tested scenarios.)*

**Speaker:** "The system successfully resolved the actionable discrepancies and cleanly rejected the ones with no safe repair path, like currency mismatches and orphaned payments. It achieved 100% synthetic classification and outcome conformance without a single unauthorized mutation under our tested scenarios. Now, let's zoom in on exactly how it resolved one of those actionable cases."

## Detection & AI Investigation
**Action:** *Run the pipeline via CLI (canonical V1 demo runner — to be finalized in the V1 demo phase).*

**Speaker:** "First, the M3 deterministic engine spots the discrepancy between the provider and the merchant state. It flags a `CAPTURED_PAYMENT_STALE_ORDER`."

**Speaker:** "Instead of alerting a human operator, it passes the evidence to the M4 AI Investigation Engine. The AI acts as our detective. It synthesizes the missing webhook and the captured state, and generates a structured JSON proposal suggesting we repair the state."

## The Crucial Boundary
**Action:** *Highlight the logs where Semantic Validation and Control Plane execute.*

**Speaker:** "But here is the core thesis of FCE: **The AI is allowed to be wrong; the system is not allowed to trust it.** We do not give the AI a SQL connection."

**Speaker:** "Instead, the AI's proposal is passed to our Control Plane. The Control Plane completely ignores the AI's rationale. It reads the raw evidence independently, checks strict financial admissibility rules, and verifies the preconditions. Only then does it authorize the repair."

## The Safe Execution (Good LLM Output)
**Action:** *Show the output for a valid proposal:*
`H3 → admissible → ALLOW → 1 mutation → VERIFIED`

**Speaker:** "The authorization triggers an atomic database mutation. Our verifier does a fresh read of the database to ensure the state actually changed. We successfully repaired the order with zero human intervention, generating an immutable provenance log to prove exactly why we did it."

## The Hallucination Defense (Bad LLM Output)
**Action:** *Trigger the local Qwen3 model or a mocked adversarial payload:*
`hallucinated evidence ID → INVARIANT_INVALID → NO_ACTION → 0 mutations`

**Speaker:** "But here is why this architecture is necessary. If we run a local LLM and it hallucinates an evidence ID, or if we feed it adversarial JSON, the semantic validator and deterministic control plane instantly reject it. The system fails safely. We remove the human bottleneck, but we keep the financial authority locked down."

## The Replay & Race Defense (Concurrency)
**Action:** *Show the TOCTOU race condition execution:*
`ALLOW → concurrent state change → atomic UPDATE affects 0 rows → CONFLICT → 0 mutations`

**Speaker:** "Finally, what if the system goes haywire? What if another process pays the order at the exact millisecond we try to fix it? Because our mutation is strictly bounded by atomic preconditions (`UPDATE ... WHERE status = 'UNPAID'`), hitting it with a race condition results in a safe `CONFLICT` rollback. The financial invariants hold."
