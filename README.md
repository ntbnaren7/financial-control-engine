# Financial Control Engine

**Track 4 — AI Finance Controller**

> **AI investigates financial uncertainty. Deterministic controls decide financial truth.**

---

## The Problem

Payment providers deliver refund status through webhooks that can be lost, delayed, or
contradictory. When they are, finance teams face a queue of unresolved cases:

- Was the refund actually executed?
- Did the provider drop it?
- Was a different amount refunded?

Today, resolving each case requires a human to query the provider, read the response,
and make a judgement call. At scale, this is expensive and slow.

## What This Engine Does

The Financial Control Engine runs a closed reconciliation loop over financial records:

1. **Classify** every case deterministically — match, mismatch, or uncertain.
2. **Investigate** uncertain cases using a local LLM to form a hypothesis.
3. **Validate** the hypothesis at a hard boundary before any external action.
4. **Query** the provider deterministically — using only parameters from the trusted case.
5. **Reclassify** on the new evidence.
6. **Report** match rate, resolution rate, and an honest unresolved exception list.

The LLM's only role is to decide *what to look at*. It never classifies a financial
outcome and never receives financial authority.

---

## Architecture

```
Provider Events
      │
      ▼
┌─────────────────────────────────────────────────────┐
│                   State Engine                       │
│   ProviderObservation → ReconstructedState           │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              V1 Deterministic Kernel                 │
│   reconcile(expectation, state) → DiscrepancyType    │
│                                                      │
│   MATCH / VALUE_MISMATCH / ABSENT_EXECUTION /        │
│   ORPHANED_EXECUTION / EXCESS_EFFECT /               │
│   IN_FLIGHT_PENDING / EPISTEMIC_STALEMATE            │
└──────────┬──────────────────────┬───────────────────┘
           │                      │
     Resolved                EPISTEMIC_STALEMATE
     (record)                     │
                                  ▼
                    ┌─────────────────────────────┐
                    │  D2  Format bounded input    │
                    │  D3  LLM hypothesis          │◀── LLM boundary
                    │  D4  Validate references     │    (read-only)
                    │  D5  Provider query          │
                    └──────────────┬──────────────┘
                                   │ new Evidence
                                   ▼
                          V1 Kernel (re-runs)
                                   │
                          Final classification
```

### The trust boundary

**D4 is the hard boundary.** Any hypothesis that references a fabricated evidence ID,
an out-of-scope intent, or an unsupported verification type is rejected before D5 runs.
D5 derives all query parameters exclusively from the trusted `ReconciliationCase` —
the LLM's text cannot influence what is queried.

V1 (`src/reconciliation/engine.py`) is a pure function. It has no network access, no
side effects, and no awareness of the LLM's output. It classifies on state alone.

---

## Phase F Evaluation Results

```
╔══════════════════════════════════════════════════════════╗
║           FINANCIAL CONTROL BATCH REPORT                ║
╚══════════════════════════════════════════════════════════╝

  Records processed     50
  Matched               39
  Resolved exceptions   9
  Unresolved            2

  Match rate            78%  (39/50)
  Resolution rate       96%  (48/50)

  ── Investigation Activity ──────────────────────────────

  Stalemates routed     5
    D4 boundary rejected  1
    Provider verified     3
      of which resolved   3
      of which stalemate  0
    Provider error        1

  ── Correctness vs Ground Truth ─────────────────────────

  Correct classifications  50 / 50

  ── Unresolved Exceptions ───────────────────────────────

  REC-049  C4_PROVIDER_OUTAGE    Provider returned 503 — stalemate preserved
  REC-050  C5_BOUNDARY_REJECT    D4 rejected invalid evidence reference
```

### What these numbers mean

| Metric | Value | What it measures |
|---|---|---|
| **50/50 correctness** | 100% | Accuracy against independently defined ground truth |
| **96% resolution rate** | 48/50 | Operational resolution on the synthetic matrix |
| **78% initial match rate** | 39/50 | Cases resolved by V1 before investigation |
| **2 unresolved** | 4% | Deliberately retained uncertainty |

**The 96% figure is a result on a synthetic evaluation matrix, not a real-world rate.**

The 50/50 correctness result is a specification-driven accuracy claim: 50 financial
scenarios were defined by their expected final outcome first; V1's classifications
were compared against those predefined specifications independently.

### Evaluation reproducibility

The batch runner is anchored to the dataset's fixed seed timestamp
(`2024-01-15T10:00:00Z`). All SLA deadlines are deterministic relative to that anchor.
The 50/50 result reproduces at any future wall-clock time.

---

## Running the Evaluation

```bash
# Install dependencies
uv sync

# Generate the 50-record synthetic dataset
uv run python scripts/generate_batch_data.py

# Run the full batch evaluation
PYTHONPATH=. uv run python scripts/run_batch_control.py

# Run the single-case investigation demo (Phase E)
PYTHONPATH=. uv run python scripts/demo_runner.py

# Run the test suite
uv run pytest
```

---

## Key Source Files

| File | What it does |
|---|---|
| `src/reconciliation/engine.py` | V1 deterministic kernel — pure function, no I/O |
| `src/reconciliation/models.py` | `DiscrepancyType` enum and `ReconciliationResult` |
| `src/state/engine.py` | Reconstructs `ReconstructedState` from `ProviderObservation` |
| `src/investigation/agent.py` | Local LLM investigator (D3) |
| `src/investigation/validator.py` | D4 boundary validator |
| `src/investigation/verifier.py` | D5 deterministic provider query |
| `scripts/demo_runner.py` | Single-case EPISTEMIC_STALEMATE → resolution demo |
| `scripts/run_batch_control.py` | 50-record batch evaluation with correctness report |
| `scripts/generate_batch_data.py` | Synthetic dataset generator |
| `tests/doubles/batch_mock_transport.py` | Per-case Razorpay mock for batch evaluation |

---

## What Is and Is Not Claimed

### Claimed
- V1 correctly classifies every financial state it can determine from available evidence.
- The D4 boundary rejects hypotheses with fabricated evidence references.
- The system preserves EPISTEMIC_STALEMATE when evidence is insufficient rather than
  manufacturing a resolution.
- 50/50 correctness on a specification-driven synthetic evaluation.
- The LLM has no path to financial classification or provider mutation.

### Not claimed
- Real-world accuracy (not measured on real financial data).
- Production readiness (no persistence layer, operator UI, or multi-tenant support).
- The C5 adversarial case represents an organic LLM failure in live evaluation —
  it is a controlled injection to verify D4's boundary validation.

---

## Limitations

- **Synthetic evaluation only.** The 50-record matrix uses programmatically generated
  cases. Real refund pipelines will produce distributions and edge cases not represented.
- **Ollama dependency for live mode.** Without a running `qwen3:8b` instance, the
  demo and batch runner fall back to a deterministic REPLAY hypothesis. The evaluation
  result is identical in REPLAY mode.
- **No persistence.** The engine processes records in memory. A production deployment
  would require a durable case store and an outbox for provider queries.

---

## Test Suite

```
186 passed, 4 skipped
```

Covers: V1 kernel invariants, D4 boundary validation, D5 verifier, state engine,
evidence normalization, reconciliation model properties, and integration slices.
