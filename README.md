# Financial Control Engine (FCE)
*Autonomous Financial Exception Control with Deterministic Safety Boundaries*  
**Razorpay Buildathon — Track 4 (Control & Governance) × Track 3 (Autonomous Recovery)**

---

## 1. What FCE Is

The Financial Control Engine (FCE) is a two-layer control system for financial reconciliation and autonomous exception recovery. It couples a deterministic verification kernel with an untrusted, bounded local language model to investigate payment mismatches, verify external ground truth, and safely execute idempotent financial mutations without delegating financial authority to AI.

### Demo Video & Hosted Interactive Simulation
- 🎥 **Video Walkthrough**: [https://youtu.be/jk6LZ36RM3s?si=XS3nxXRAp9UroumY](https://youtu.be/jk6LZ36RM3s?si=XS3nxXRAp9UroumY)
- 🌐 **Interactive Web Demo**: [https://financial-control-engine-fce.vercel.app/](https://financial-control-engine-fce.vercel.app/)

> **Hosted Deployment Notice:**  
> This web deployment is the **hosted deterministic simulation surface only**. It is provided so evaluators can immediately test and inspect the actual outputs, decision trees, D4 validation boundaries, and cryptographic evidence trails of the FCE engine directly on their own devices in a frictionless demo environment without setting up Python, Docker, PostgreSQL, or local Ollama models.  
>  
> **The LIVE execution path is not hosted**: Real-time live execution requires local infrastructure (our FastAPI backend daemon, PostgreSQL state substrate, and local Ollama instance running `qwen3:8b` on `localhost:8000`). The hosted deployment does not connect to or simulate live backend/provider credentials.

---

## 2. Core Control Principle

> **AI investigates uncertainty. Deterministic controls establish truth and authorize mutation.**

Traditional reconciliation flags discrepancies but leaves investigation and manual repair to human ops. Naive automation gives probabilistic models API keys to move funds. FCE inverts that trust model: the LLM is treated as an untrusted reasoning worker with zero execution credentials, strictly bounded by cryptographic evidence containment, deterministic gateway queries, hard governance quotas, and post-action re-observation.

---

## 3. Architecture & Trust Boundary

```
[ Ingested Financial Events ] (Internal Ledger + Provider Webhooks)
             │
             ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ Stage 01: DETECT (Deterministic Kernel — 0% LLM)            │
   │ Pure state comparison: MATCH vs STATE_MISMATCH              │
   └─────────────────────────────┬───────────────────────────────┘
                                 │ Discrepancy Found
                                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ Stage 02: INVESTIGATE (Untrusted Local LLM Worker)          │
   │ Bounded Context (4 SHA-256 Hashed Records) → Hypothesis     │
   │ Authority: NONE (Zero API keys, zero mutation power)        │
   └─────────────────────────────┬───────────────────────────────┘
                                 │ CausalHypothesis + Target ID
═════════════════════════════════╪═════════════════════════════════  D4 TRUST BOUNDARY
                                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ Stage 03: VERIFY (Deterministic Verifier)                   │
   │ 1. D4 Output Validation: Reject fabricated evidence IDs     │
   │ 2. Deterministic Gateway Query: GET /v1/payments/{id}       │
   └─────────────────────────────┬───────────────────────────────┘
                                 │ Fact Proven (HTTP 200 captured)
                                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ Stage 04: DECIDE (Policy & Governance Gate)                 │
   │ Policy: REFUND_PAYMENT · Kill-Switch Check · Budget Quota   │
   └─────────────────────────────┬───────────────────────────────┘
                                 │ Authorized Recovery Intent
                                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ Stage 05: ACT (Idempotent Actuation Engine)                 │
   │ Atomic OCC CAS Lease (v1 → v2) · Unique Idempotency Key     │
   │ Gateway Mutation: POST /v1/payments/{id}/refund             │
   └─────────────────────────────┬───────────────────────────────┘
                                 │ Mutation Dispatched
                                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ Stage 06: RE-OBSERVE (External State Verification)          │
   │ Fresh Gateway Poll: status = 'refunded' · Kernel Re-eval    │
   └─────────────────────────────┬───────────────────────────────┘
                                 │ Convergence Verified (MATCH)
                                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ Stage 07: OUTCOME (Terminal Sealed Disposition)             │
   │ Final State: RESOLVED (Audit trail persisted to PostgreSQL) │
   └─────────────────────────────────────────────────────────────┘
```

---

## 4. How the System Works: 7-Stage Flow

1. **`DETECT` (Deterministic Kernel)**: Compares internal ledger expectations against provider observations using pure state comparison. Flags discrepancies (e.g. `STATE_MISMATCH`) with zero probabilistic inference.
2. **`INVESTIGATE` (Bounded Local LLM)**: Assembles four immutable evidence records under SHA-256 hashes. Local LLM (`qwen3:8b`) hypothesizes root cause and proposes a read-only `VerificationIntent`. The model has zero financial authority.
3. **`VERIFY` (D4 & Gateway Proof)**: 
   - **D4 Validator** enforces syntactic schema and referential containment: if the model cites any evidence ID outside the bounded context, the pipeline immediately halts.
   - **Deterministic Verifier** queries Razorpay’s API (`GET /v1/payments/{id}`) using trusted case parameters to establish external ground truth.
4. **`DECIDE` (Policy & Governance Gate)**: Evaluates deterministic business rules (e.g. `MERCHANT_CANCELLED_PROVIDER_CAPTURED` $\rightarrow$ `REFUND_PAYMENT`). The Governance Gate verifies the system kill-switch is active and checks remaining daily budget allowance.
5. **`ACT` (Idempotent Actuation)**: Acquires an atomic Optimistic Concurrency Control (OCC) CAS version lease (`v1 → v2`) and persists a deterministic idempotency key before dispatching the refund mutation to Razorpay.
6. **`RE-OBSERVE` (Convergence Confirmation)**: Re-polls Razorpay post-action to confirm the external payment state actually flipped to `refunded`. Re-runs the deterministic reconciliation kernel.
7. **`OUTCOME` (Terminal Sealed State)**: Once external convergence is mathematically proven, transitions incident state to `RESOLVED` and commits the cryptographic Merkle audit trail.

---

## 5. Safety & Control Guarantees

- **D4 Referential Containment Invariant**: An LLM cannot inject ungrounded evidence. Output referencing unverified IDs is rejected prior to gateway access.
- **Strict Separation of Reasoning and Execution**: LLM output is structured data (`CausalHypothesis`), never code, SQL, or executable API payloads.
- **OCC Concurrency Protection**: Multi-worker race conditions and duplicate webhook events are blocked via atomic CAS version increments.
- **Deterministic Idempotency**: All mutations carry an SHA-256 deterministic idempotency key (`idem_refund_{payment_id}_v{version}`).
- **Closed-Loop Convergence**: No action is marked resolved based on mutation return codes; success requires independent re-observation of external provider state.
- **Honest Escalation**: When evidence is missing (e.g. provider 404) or contradictory (amount mismatch), the engine safely halts and escalates (`ESCALATED_MISSING_EVIDENCE`).

---

## 6. Concrete Evidence & Test Results

### A. 60-Record Heterogeneous Production Batch (`scripts/batch_reconciliation.py`)
Run command: `uv run python scripts/batch_reconciliation.py --provider mock --count 60`
- **Total Processed**: 60 records (0.6s elapsed)
- **Direct Matches**: 40 / 60 (66.7%) — resolved in Stage 1 without invoking AI
- **Autonomous Remediations**: 11 / 60 (18.3%) — verified, authorized, and refunded
- **Total Resolution Rate**: **85.0%** (51/60 automated resolution)
- **Honest Safety Escalations**: 9 / 60 (15.0%) — 6 provider 404s + 3 amount mismatches
- **Timeouts & Crashes**: 0 timeouts, 0 unhandled exceptions, 0 false mutations

### B. Single-Case Invariant & Adversarial Validation (`scripts/test_7_cases.py`)
Run command: `uv run python scripts/test_7_cases.py`
- **Scenario A (Happy Path Refund)**: Closed-loop detection $\rightarrow$ investigation $\rightarrow$ D4 verification $\rightarrow$ OCC refund $\rightarrow$ convergence confirmed $\rightarrow$ `RESOLVED`.
- **Scenario B (Missing Evidence 404)**: Provider returned HTTP 404 $\rightarrow$ ground truth unestablished $\rightarrow$ mutation blocked $\rightarrow$ `ESCALATED_MISSING_EVIDENCE`.
- **Scenario C (Adversarial Hallucination Injection)**: Model injected fabricated evidence ID `ev_hallucinated_fabricated_id_99999` $\rightarrow$ caught by D4 validator $\rightarrow$ gateway query blocked $\rightarrow$ mutation blocked $\rightarrow$ `ESCALATED_UNKNOWN`.

### C. Test Suite
- **Fast Unit & Component Suite**: `uv run pytest tests/unit tests/reconciliation tests/recovery tests/domain tests/api tests/control tests/state`
  - **175 passed in 0.30s**
- **Full Architecture & Concurrency Suite**: 284 passed (includes PostgreSQL Testcontainers validating OCC race conditions, outbox durability, and distributed worker crashes).

### D. Live Provider Verification (Razorpay Test Mode)
- **Live Read Verification**: `scripts/verify_real_provider.py` connects to live Razorpay Test Mode API, validates key authentication, and ingests live canonical payment observations.
- **Live Mutation Loop**: `scripts/verify_real_loop.py` executes full live control loop against real Razorpay API, issuing verified test-mode refunds.

---

## 7. How to Run Locally

### Prerequisites
- Python 3.12+ with `uv`
- Node.js 18+ (for frontend console)
- *(Optional)* Docker (for PostgreSQL container tests) & Ollama (for live local LLM)

```bash
# 1. Clone repository
git clone https://github.com/ntbnaren7/financial-control-engine.git
cd financial-control-engine

# 2. Install Python dependencies
uv sync

# 3. Run the 60-record batch evaluation benchmark (0.6s)
uv run python scripts/batch_reconciliation.py --provider mock --count 60

# 4. Run the 3 core safety scenarios (Scenario A, B, and Adversarial C)
uv run python scripts/test_7_cases.py

# 5. Run the deterministic test suite (175 tests, 0.3s)
uv run pytest tests/unit tests/reconciliation tests/recovery tests/domain tests/api tests/control tests/state

# 6. Launch the Interactive Forensic Console (UI)
cd frontend
npm install
npm run dev
# Open http://localhost:5173 in browser
```

---

## 8. Current Scope & Limitations

1. **Synthetic & Seeded Evaluation**: The 60-record benchmark uses deterministic seeded distributions to guarantee 100% reproducible SLA and reconciliation metrics.
2. **Provider Scope**: The reference integration is built against the Razorpay Payments & Refunds API specification. Additional provider protocols require implementing the `ProviderAdapter` interface.
3. **Local LLM Execution**: Live inference requires a running Ollama daemon (`qwen3:8b`). In environments without Ollama, the engine falls back to deterministic replay fixtures while maintaining identical verification boundaries.
4. **Test Mode Actuation**: Live provider actuation is validated against Razorpay Test Mode; real-money production accounts are not connected.
