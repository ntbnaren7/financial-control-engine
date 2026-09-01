# The Submission Thesis: Why FCE Matters

*“FCE does not give an AI agent permission to fix financial data. It uses AI to investigate a deterministically detected discrepancy, then requires an independent control plane to authorize a narrowly bounded repair.”*

## 1. The Financial Problem
At the core of digital payments, state machines drift. A webhook drops due to a fleeting network partition. An asynchronous processing queue stalls. Inevitably, the money moves (captured by the provider) but the internal state remains ignorant (`UNPAID`). 

The friction isn't just that the customer gets angry—it's that a human has to sit in the loop to fix it. Customer Support escalates to Operations, Operations hunts down logs, checks the Razorpay dashboard, manually reconciles the state, and forcefully overrides the database. 

## 2. Why It Is Difficult to Automate Safely
The reason humans remain in this loop is that autonomous mutation of financial state is terrifyingly dangerous. If an automated script misfires and marks orders paid that aren't, businesses bleed capital instantly. Hard-coded rules break down because the *evidence* surrounding a failure (webhooks, API logs, state transitions) is heterogeneous and constantly evolving.

## 3. Our Thesis
**Rules are excellent at enforcing known invariants but poor at explaining heterogeneous evidence when the failure mode isn't fully encoded. LLMs are good at synthesizing heterogeneous evidence but unsafe as financial authorities.**

Use AI where ambiguity and evidence synthesis exist. Use deterministic systems where financial authority exists.

## 4. What FCE Actually Does
The Financial Control Engine (FCE) automates the *investigation* of financial discrepancies using an AI, but forcefully strips that AI of the power to fix them. It translates the messy reality of heterogeneous evidence into a structured proposal, then hands that proposal to a strict, mathematical control plane to make the actual financial decision.

## 5. Why AI Alone is Insufficient
If we grant an LLM a SQL connection or a direct API execution tool, we invite catastrophe. LLMs are fundamentally non-deterministic and prone to hallucination. An LLM might authorize a refund because it misread a webhook timestamp. Financial systems cannot tolerate probabilistic data corruption. 

## 6. Why Deterministic Control Alone is Insufficient
If we rely purely on `if/else` logic, the system breaks on edge cases. What if the webhook payload shape changes? What if there's a partial network failure that leaves only partial evidence in the logs? Deterministic code is too brittle to handle the sheer entropy of microservice failure states at scale.

## 7. The Hybrid Architecture
FCE connects the two. 
- **Deterministic Detection (M3)** notices the discrepancy.
- **Untrusted Investigation (M4)** acts as an AI detective, piecing together the evidence.
- **Deterministic Control (Control Plane)** acts as the judge, re-reading the evidence and applying strict financial admissibility rules.
- **Atomic Execution** acts as the bailiff, attempting a conditional `UPDATE` that only succeeds if the data hasn't drifted.

## 8. The ₹5,000 Hero Incident
Our baseline incident: A customer pays ₹5,000. It is captured at Razorpay. The webhook fails. The internal order is stuck in `UNPAID`. FCE detects this, the AI connects the dots between the missing webhook and the captured payment API state, and proposes fixing the internal state. The Control Plane verifies the facts, and safely executes the repair. Zero human intervention.

## 9. Finance Controller Batch Evaluation (Track 4 Breadth Proof)
To prove the controller can process a finance-ops workload reliably, we ran a synthetic acceptance workload of 50 financial cases through the pipeline. The batch isolates controller measurement from LLM nondeterminism and proves 100% oracle conformance without a single unauthorized mutation.

```text
FINANCE CONTROLLER — BATCH ACCEPTANCE RUN
══════════════════════════════════════════════════════

INPUT
  Records processed:                50

RECONCILIATION
  Reconciliation match rate:        27/50 = 54.0%
  Consistent (no discrepancy):      27
  Discrepant:                       23
    Actionable (Authorized):         8
    Rejected before M4/action:      15

ORACLE CONFORMANCE (CLASSIFICATION)
  Expected classifications:         50
  Correct:                          50
  Incorrect:                        0
  Conformance:                      100.0%

ORACLE CONFORMANCE (CONTROLLER OUTCOME)
  Expected outcomes:                50
  Correct outcomes:                 50
  Incorrect outcomes:               0
  Conformance:                      100.0%

CONTROL OUTCOMES
  Automatically resolved:            8
  Safely refused / rejected:        15
  Conflicts (TOCTOU):                0
  Verification failures:             0

OPERATIONS
  M4 investigations:                 21
  Financial mutations:               8

SAFETY
  Unauthorized mutations:            0   ✓
  False autonomous actions:          0   ✓

UNRESOLVED EXCEPTION LIST
  PAYMENT_NOT_CAPTURED     × 6  — provider not yet settled, no repair path
  AMOUNT_MISMATCH          × 4  — amount delta detected, no repair path
  CURRENCY_MISMATCH        × 3  — currency mismatch, no repair path
  IDENTITY_UNKNOWN         × 2  — order identity cannot be verified

EVALUATION THROUGHPUT
  Processing time:        0.15 s
  Evaluation throughput:  340.2 records/sec
  Environment:            PostgreSQL (test isolated)
  LLM:                    deterministic mock (identical to run_golden_e2e.py)
══════════════════════════════════════════════════════
```

## 10. The 1 → 0 → 0 Empirical Result (Depth Proof)
We empirically validated our safety boundaries under tested adversarial scenarios, using mocked, deterministic boundaries to isolate the control plane:
1. **Initial Authorized Mutation = 1:** The system successfully detects, investigates, and executes exactly one repair.
2. **Replay Mutation = 0:** If the exact same webhook and incident are re-triggered, the system idempotently drops the request.
3. **TOCTOU Race Mutation = 0:** If another process pays the order milliseconds before FCE attempts to fix it, the atomic database predicate (`UPDATE ... WHERE status = 'UNPAID'`) catches the conflict, rolls back the transaction, and rejects the AI's proposal.

## 10. The Qwen3 Hallucination Incident
**The strongest demonstration isn't when the AI gets the answer right. It's when the AI gets the answer wrong and the financial system still refuses to trust it.**

During our live E2E testing with a local Qwen3 model, the LLM hallucinated an evidence ID that did not exist in the database in order to justify its decision. **FCE rejected it instantly.** The semantic validator blocked the payload, and the financial system refused to trust the AI. This is exactly the behavior a financial pipeline must exhibit: *The AI is allowed to be wrong; the system is not allowed to trust it.*

## 11. Failure Handling & Adversarial Evidence
Through our adversarial test suite, we threw malformed JSON, out-of-scope hypotheses, and missing critical evidence at the AI. In every instance, the Control Plane caught the missing preconditions and halted execution safely. 

## 12. Production-Minded Guarantees
FCE emits a structured, immutable `AuthorizationProvenance` log for every single execution. An auditor can look at any resolved order and see exactly what deterministic facts authorized the mutation, independently of what the AI said.

## 13. Current V0 Boundary
We do not claim V0 is a drop-in Razorpay production system. V0 operates locally with simple async loops and SQLite. It proves the **trust boundary pattern**, not the durability of the event queues. We explicitly outline these constraints in our Threat Model.

## 14. Why This Could Matter at Razorpay Scale
At Razorpay's volume, even a 0.01% discrepancy rate means thousands of manual operations tickets. By adopting FCE's architecture as a potential control-plane capability, Razorpay could begin resolving the long-tail of heterogeneous failure states automatically, reducing support overhead drastically, without risking the core integrity of the ledger.

## 15. What V1 Could Become
V1 would transition this architecture onto durable event queues (e.g., Kafka), swap the local SQLite database for highly concurrent transactional stores (Postgres/CockroachDB), and expand the Control Plane to support configurable multi-tenant rules. 
