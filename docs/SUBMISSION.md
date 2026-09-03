# Track 4 Submission — AI Finance Controller

## One-sentence thesis

> A two-layer financial control engine where a deterministic kernel establishes
> financial truth and a bounded LLM investigates uncertainty — without receiving
> financial authority.

---

## Track 4 criteria mapping

### "One finance-ops loop across a 50+ record batch"

**What we built:** `scripts/run_batch_control.py` processes a 50-record synthetic
batch end-to-end: ingest → state reconstruction → V1 classification → LLM
investigation (where needed) → provider query → reclassification → report.

**Evidence:** The batch runner exits 0. Output includes match rate, resolution rate,
investigation activity breakdown, and the unresolved exception list. The run is fully
reproducible.

### "Reporting its match rate"

**What we report:**
- **78% initial match rate** — 39/50 cases resolved by V1 before investigation
- **96% resolution rate** — 48/50 ultimately resolved
- **50/50 correctness** — all final classifications match the independently defined
  ground truth

### "The exceptions it could not resolve"

**What we report:** Two named, explained unresolved exceptions:
- `REC-049` — provider outage (503) during investigation; stalemate preserved
- `REC-050` — D4 boundary rejection; LLM hypothesis contained invalid reference

The system does not hide unresolved cases. It maintains EPISTEMIC_STALEMATE rather
than manufacturing a resolution.

---

## Architectural differentiator

Most LLM-in-finance approaches give the model read access to financial records and
ask it to classify or summarise. The failure mode is model error becoming financial
error.

This engine inverts the trust structure:

1. **V1 classifies deterministically** from structured evidence. The LLM never
   receives a classification question.
2. **The LLM proposes what to investigate** — a narrow, schema-constrained output.
3. **D4 validates the proposal** against the bounded case before anything runs.
4. **D5 executes a deterministic provider query** using only parameters from the
   trusted case expectation — the LLM's text cannot influence what is queried.
5. **V1 reclassifies** on the new evidence.

The LLM is inside the loop, but outside the authority chain.

---

## Evaluation honesty

| Claim | Basis | Scope |
|---|---|---|
| 50/50 correctness | Spec-driven synthetic evaluation | Synthetic only |
| 96% resolution rate | Batch runner output | Synthetic only |
| D4 rejects invalid references | Unit tests + controlled C5 case | Verified |
| LLM has no classification authority | Architecture (V1 is called after D5, not after D3) | Structural |
| Stalemate preserved on provider error | C4 case (503) in batch run | Verified |

The C5 adversarial case is a **controlled injection**, not an organic LLM failure.
The claim it supports: "D4 correctly rejects hypotheses referencing fabricated
evidence IDs." That claim is also covered by `OutputValidator` unit tests
independently.

---

## What is not included and why

| Item | Decision |
|---|---|
| Persistence layer | Not required to demonstrate the control loop |
| Operator UI | Terminal output is sufficient for evaluation credibility |
| Multi-provider support | Razorpay client is the reference implementation |
| Real-data validation | Would strengthen the claim; honest gap |
| Distributed concurrency / TOCTOU | Out of scope for Track 4 |

---

## Running the submission

```bash
uv sync

# Single-case demo (Phase E)
PYTHONPATH=. uv run python scripts/demo_runner.py

# 50-record batch evaluation (Phase F)
PYTHONPATH=. uv run python scripts/run_batch_control.py

# Test suite
uv run pytest
```

Expected outputs:
- Demo: visible EPISTEMIC_STALEMATE → investigation → MATCH resolution
- Batch: 50/50 correctness, 96% resolution, 2 named unresolved exceptions
- Tests: 186 passed, 4 skipped
