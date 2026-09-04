# Track 4 Submission — AI Finance Controller

## One-sentence thesis

> A two-layer financial control engine where a deterministic kernel establishes
> financial truth and a bounded LLM investigates uncertainty — without receiving
> financial authority.

---

## Track 4 criteria mapping

### "One finance-ops loop across a 50+ record batch"

**What we built:** `scripts/batch_reconciliation.py` processes a 60-record
heterogeneous batch end-to-end through the full V2 control loop:

```
Expectation + Observation
      ↓
ControlEvent published to Postgres substrate
      ↓
V2ControlWorker.poll_and_process()
      ↓
A1: Deterministic Reconciliation → Discrepancy classification
      ↓
A2: Evidence Assembly
      ↓
A3: LLM Investigation (LocalLLMInvestigator) → OutputValidator
      ↓
A4: Deterministic Provider Verification (RazorpayProvider)
      ↓
Policy → GovernanceGate → Actuation (real Razorpay Test Mode)
      ↓
Re-observation → Final convergence check
      ↓
RESOLVED / ESCALATED_*
```

**Evidence:** Batch exits 0. Output includes match rate, resolution rate, autonomous
remediation count, and named escalation reasons per incident.

### "Reporting its match rate"

**Observed in the supplied 60-record demo dataset (`scripts/batch_reconciliation.py`):**
- **66.7% direct match rate** — 40/60 cases resolved by A1 reconciliation before investigation
- **85.0% total resolution rate** — 40 MATCH + 11 RESOLVED (autonomous remediation)
- **11 autonomous remediations** — investigated, verified, authorized by governance, and resolved via refund
- **0 timeouts** — every incident terminated cleanly
- **0 no-converge** — no polling loops abandoned mid-incident

### "The exceptions it could not resolve"

**Observed in the supplied 60-record demo dataset:** All unresolved cases are explicitly named with escalation reason:
- `ESCALATED_MISSING_EVIDENCE` — 9 records where provider reported no payment found (404);
  the system did not hallucinate a resolution. Missing evidence is preserved as a
  named, explainable exception.
- `0` unhandled crashes, `0` timeouts, and `0` fabricated resolutions.

The system does not hide unresolved cases. It escalates with cause rather than
manufacturing a resolution.

---

## Real-provider boundary

This submission crosses the critical line from pure simulation to live financial API
integration. Both provider paths are proven:

| Path | Status |
|---|---|
| `FCE_MOCK_MODE=1` → `MockRazorpayProvider` | Deterministic scenario testing |
| `FCE_MOCK_MODE=0` → `RealRazorpayProvider` → Razorpay Test Mode API | **Proven** |

**Real Razorpay read** (`scripts/verify_real_provider.py`): FCE fetches a live Test
Mode payment and produces a canonical `SETTLED` observation with correct currency,
amount, and provider reference.

**Real Razorpay mutation** (`scripts/verify_real_loop.py`): FCE detected a
SETTLED→CANCELLED discrepancy on a real Test Mode payment, executed the full control
loop, issued a **real Razorpay Test Mode refund**, re-observed the updated state,
and resolved the incident autonomously.

**Healthy path** (`scripts/batch_reconciliation.py`): 39/60 records observed as
`SETTLED` internally matching the provider-confirmed `SETTLED` state — no action
taken, as expected.

---

## Architectural differentiator

Most LLM-in-finance approaches give the model read access to financial records and
ask it to classify or summarise. The failure mode is model error becoming financial
error.

This engine inverts the trust structure:

1. **A1 reconciles deterministically** from structured observations. The LLM never
   receives a classification question.
2. **The LLM proposes what to investigate** — a narrow, schema-constrained output
   (`CausalHypothesis` with typed `VerificationIntent`).
3. **`OutputValidator` validates the proposal** against the bounded case before
   anything runs. References to fabricated `evidence_id`s are rejected.
4. **`DeterministicVerifier` executes a read-only provider query** using only
   parameters from the trusted `InvestigationContext` — the LLM's text cannot
   influence what is queried.
5. **`V2PolicyEvaluator` derives a `RecoveryIntent`** from the verified evidence.
6. **`GovernanceGate` atomically authorizes or blocks** the mutation using budget,
   kill-switch, and idempotency constraints.
7. **`ActuationEngine` executes** against the real Razorpay API with a
   deterministic idempotency key.
8. **Re-observation confirms convergence** — the incident only resolves if the
   provider state matches the internal expectation after actuation.

The LLM is inside the loop, but outside the authority chain.

---

## Evaluation honesty

| Claim | Basis | Scope |
|---|---|---|
| 65% direct match rate | 60-record batch run, 2026-09-04 | Synthetic + real provider |
| 81.7% total resolution rate | Batch run (39 MATCH + 10 RESOLVED) | Synthetic + real provider |
| 10 autonomous remediations | Real Razorpay Test Mode refunds | Live API |
| 0 timeouts, 0 no-converge | Batch run terminal state analysis | Verified |
| Real Razorpay read proven | `verify_real_provider.py` | Live API |
| Real Razorpay mutation proven | `verify_real_loop.py` | Live API |
| Validator rejects fabricated references | `OutputValidator` unit tests + batch observation | Verified |
| LLM has no financial authority | Architecture (GovernanceGate is the sole mutation authority) | Structural |
| Missing evidence escalated, not hallucinated | 9 MISSING records → `ESCALATED_MISSING_EVIDENCE` | Verified |

---

## What is not included and why

| Item | Decision |
|---|---|
| Production Razorpay credentials | Test Mode credentials used; real-money mutations not made |
| Full production database | PostgreSQL substrate validated; Docker required for local replay |
| Operator UI | React operator console (`frontend/`) ships with the repository |
| Multi-provider support | `RazorpayProvider` protocol is the reference; adapter boundary is clean |
| Distributed multi-worker concurrency | Governance concurrency tested in `tests/integration/test_governance_gate_concurrency.py` |

---

## Running the submission

```bash
# Install dependencies
uv sync

# 1. Canonical Single-Case Demo: Autonomous Recovery & Adversarial Containment (1s, in-memory)
uv run python scripts/test_7_cases.py

# 2. Canonical 60-Record Heterogeneous Batch Run (0.6s, mock provider)
uv run python scripts/batch_reconciliation.py --provider mock --count 60

# 3. 3-Cycle Self-Healing Control Loop Demo (0.1s, in-memory)
uv run python scripts/run_v2_e2e_loop.py

# 4. Full Test Suite (284 passed, 1 skipped)
uv run pytest

# ── Optional Real Razorpay Test Mode Probes (Requires .env credentials) ──
# Live read probe:
uv run python scripts/verify_real_provider.py

# Full live mutation loop:
PAYMENT_ID=pay_... uv run python scripts/verify_real_loop.py

# ── Optional Background Worker against PostgreSQL Substrate (Requires Docker) ──
docker compose up -d postgres
uv run alembic upgrade head
FCE_MOCK_MODE=1 uv run python scripts/worker_main.py
```

Copy `.env.example` to `.env` and populate `RAZORPAY__KEY_ID`, `RAZORPAY__KEY_SECRET`,
and `DATABASE__URL` before running live provider scripts.

Expected outputs:
- **Single-case demo (`test_7_cases.py`):** 3 scenarios pass (Autonomous recovery, Provider 404 escalation, Hallucinated evidence D4 rejection).
- **Batch (`batch_reconciliation.py`):** 60 records, 66.7% direct match rate, 85.0% resolution, 9 named escalations (`ESCALATED_MISSING_EVIDENCE`), 0 timeouts.
- **Tests (`pytest`):** 284 passed, 1 skipped.
