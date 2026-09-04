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

**What we report (60-record batch run, 2026-09-04):**
- **65.0% direct match rate** — 39/60 cases resolved by A1 before investigation
- **81.7% resolution rate** — 39 MATCH + 10 RESOLVED (autonomous remediation)
- **10 autonomous remediations** — real Razorpay Test Mode refunds executed and confirmed
- **0 timeouts** — every incident terminated cleanly
- **0 no-converge** — no polling loops abandoned mid-incident

### "The exceptions it could not resolve"

**What we report:** All unresolved cases are explicitly named with escalation reason:
- `ESCALATED_MISSING_EVIDENCE` — 9 records with no provider payment found (404);
  the system did not hallucinate a resolution. Missing evidence is preserved as a
  named, explainable exception.
- `ESCALATED_UNKNOWN` — 2 records where LLM output validation rejected an
  unsupported evidence reference; the system escalated rather than bypassing validation.

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

# Start the API and worker (requires Postgres via Docker)
docker-compose up -d postgres
uv run alembic upgrade head

# Worker (real provider, requires .env with RAZORPAY__KEY_ID and RAZORPAY__KEY_SECRET)
uv run python scripts/worker_main.py

# Worker (mock mode, no credentials needed)
FCE_MOCK_MODE=1 uv run python scripts/worker_main.py

# 60-record batch run (mock provider, no credentials needed)
uv run python scripts/batch_reconciliation.py

# Real provider read probe (requires Test Mode credentials in .env)
uv run python scripts/verify_real_provider.py

# Full real control loop (requires Test Mode credentials + real payment ID)
PAYMENT_ID=pay_... uv run python scripts/verify_real_loop.py

# Demo runner (100-record synthetic, mock provider)
uv run python scripts/run_demo.py

# Test suite (no Docker required for core suite)
uv run pytest
```

Copy `.env.example` to `.env` and populate `RAZORPAY__KEY_ID`, `RAZORPAY__KEY_SECRET`,
and `DATABASE__URL` before running live provider scripts.

Expected outputs:
- Batch: 60 records, ~65% match rate, ~81.7% resolution, 0 timeouts
- Real provider read: canonical `SETTLED` observation from live Razorpay Test API
- Tests: deterministic unit + integration suite (postgres tests require Docker)
