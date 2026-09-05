# Financial Control Engine (FCE)
*Autonomous Financial Exception Control with Deterministic Safety Boundaries*  
**Razorpay Buildathon — Track 4 (Control & Governance) × Track 3 (Autonomous Recovery)**

---

## 1. Executive Summary & Demo Surfaces

FCE is a two-layer control system for financial reconciliation and autonomous exception recovery. It pairs an untrusted local language model with a deterministic verification kernel to investigate payment mismatches, verify external ground truth, and safely execute idempotent financial mutations without delegating financial authority to AI.

| Surface | Link / Target | Runtime & Requirements | Scope & Purpose |
| :--- | :--- | :--- | :--- |
| 🌐 **Hosted Web Demo** | [Launch Simulator](https://financial-control-engine-fce.vercel.app/) | Browser only (Zero setup) | **Hosted deterministic simulation surface only**. Test actual outputs, D4 boundaries, and forensic audit trails instantly on any device without installing Python, Docker, or Ollama. *(Live execution path runs locally via FastAPI + Ollama).* |
| 🎥 **Video Walkthrough** | [Watch on YouTube](https://youtu.be/jk6LZ36RM3s?si=XS3nxXRAp9UroumY) | Video player | End-to-end architecture breakdown, live backend demonstration, and scenario walkthrough. |

---

## 2. Core Thesis

> **AI investigates uncertainty. Deterministic controls establish truth and authorize mutation.**

| Layer | Component | Authority | Responsibility |
| :--- | :--- | :--- | :--- |
| **Probabilistic Layer** | Local LLM (`qwen3:8b`) | **Zero** (No API keys, no write access) | Reason over bounded case files; propose causal hypotheses |
| **Control Boundary** | D4 Output Validator | **Gatekeeper** | Syntactic validation & strict referential citation checks |
| **Deterministic Layer** | Verifier, Governance, Actuator | **Sole Authority** | Gateway queries, budget enforcement, OCC mutations, re-observation |

---

## 3. The 7-Stage Control Architecture

```
01 DETECT ➔ 02 INVESTIGATE ➔ [ D4 BOUNDARY ] ➔ 03 VERIFY ➔ 04 DECIDE ➔ 05 ACT ➔ 06 RE-OBSERVE ➔ 07 OUTCOME
```

| Stage | Name | Worker | Core Operation | Deterministic Invariant |
| :---: | :--- | :--- | :--- | :--- |
| **01** | `DETECT` | Deterministic Kernel | Pure state comparison: Ledger vs Provider | Flags `STATE_MISMATCH` with 0% AI invocation |
| **02** | `INVESTIGATE` | Local LLM (`qwen3:8b`) | Analyzes 4 SHA-256 hashed evidence records | Proposes structured `CausalHypothesis` |
| **03** | `VERIFY` | Deterministic Verifier | Validates citations + queries Razorpay API | Halts on ungrounded IDs; proves external fact |
| **04** | `DECIDE` | Governance Gate | Evaluates policy + checks budget & kill-switch | Blocks action if budget exceeded or switch flipped |
| **05** | `ACT` | Idempotent Actuator | Claims OCC CAS lease (`v1 → v2`) + dispatches refund | Deterministic idempotency key prevents double spend |
| **06** | `RE-OBSERVE` | Provider Gateway | Re-polls Razorpay API post-mutation | Verifies external status actually flipped to `refunded` |
| **07** | `OUTCOME` | State Substrate | Re-runs kernel on fresh facts; commits audit trail | Transitions to `RESOLVED`; seals cryptographic record |

---

## 4. Safety Guarantees & Control Mechanisms

| Operational Risk | Control Mechanism | Technical Enforcement |
| :--- | :--- | :--- |
| **LLM Hallucination** | D4 Referential Validator | Rejects any hypothesis citing evidence IDs outside the bounded case |
| **Prompt Injection** | Isolated Verifier | Target parameters derived strictly from verified case records, never model text |
| **Runaway Spend** | Governance Gate | Action budget enforcement and emergency kill-switch |
| **Race Conditions** | Optimistic Concurrency (OCC) | Atomic CAS version increments (`v1 → v2`) prevent concurrent multi-worker execution |
| **Network Duplication** | Deterministic Idempotency | SHA-256 idempotency key (`idem_refund_{id}_v{version}`) persisted prior to call |
| **Silent Provider Failure** | Post-Action Re-Observation | Return codes (HTTP 200) not trusted; external ledger re-polled for proof |
| **Missing / Ambiguous Data** | Honest Escalation | Refuses to guess on 404s or amount mismatches; escalates to human review |

---

## 5. Concrete Evidence & Test Results

### A. 60-Record Heterogeneous Batch Benchmark (`scripts/batch_reconciliation.py`)

```bash
uv run python scripts/batch_reconciliation.py --provider mock --count 60
```

| Evaluation Metric | Benchmark Result | Technical Note |
| :--- | :--- | :--- |
| **Total Processed** | **60 records** (0.6s) | Authoritative test exceeding 50+ record benchmark |
| **Direct Matches** | **40 / 60 (66.7%)** | Resolved deterministically in Stage 1 with 0% AI invocation |
| **Autonomous Remediations** | **11 / 60 (18.3%)** | Investigated, verified, authorized, and refunded |
| **Total Automated Resolution** | **85.0% (51/60)** | Combined autonomous resolution rate |
| **Honest Safety Escalations** | **9 / 60 (15.0%)** | 6 provider 404s + 3 amount mismatches (Zero guessing) |
| **Timeouts / Crashes / Leaks** | **0 / 60 (0.0%)** | 100% clean termination across all records |

### B. Core Scenarios & Adversarial Containment (`scripts/test_7_cases.py`)

| Scenario | Injected Condition | Engine Action | Final Disposition | Invariant Proven |
| :--- | :--- | :--- | :--- | :--- |
| **A: Happy Path** | Ledger discrepancy | Full 7-stage control loop | `RESOLVED` | Closed-loop convergence confirmed |
| **B: Missing Data** | Provider returned HTTP 404 | Mutation halted | `ESCALATED_MISSING_EVIDENCE` | Refuses to guess without ground truth |
| **C: Adversarial** | LLM hallucinated evidence ID | Caught by D4 Validator | `ESCALATED_UNKNOWN` | Boundary halt; 0 gateway access, 0 spend |

### C. Test Suite & Invariants

| Suite | Command | Coverage & Invariants | Result |
| :--- | :--- | :--- | :--- |
| **Unit & Kernel** | `uv run pytest tests/unit tests/reconciliation tests/recovery tests/domain tests/api tests/control tests/state` | Kernel logic, D4 validator, recovery policy, OCC, retry | **175 passed** (0.30s) |
| **Full Architecture** | `uv run pytest` | Above + PostgreSQL Testcontainers concurrency & outbox | **284 passed** (19.6s) |
| **Live Read Probe** | `uv run python scripts/verify_real_provider.py` | Live Razorpay Test Mode API payment observation | **Verified** |
| **Live Loop Probe** | `uv run python scripts/verify_real_loop.py` | Live Razorpay Test Mode refund control loop | **Verified** |

---

## 6. How to Run Locally

```bash
# 1. Install Python dependencies
uv sync

# 2. Run the 60-record batch benchmark (0.6s)
uv run python scripts/batch_reconciliation.py --provider mock --count 60

# 3. Run the 3 core safety scenarios (Scenario A, B, and Adversarial C)
uv run python scripts/test_7_cases.py

# 4. Run fast test suite (175 tests in 0.3s)
uv run pytest tests/unit tests/reconciliation tests/recovery tests/domain tests/api tests/control tests/state

# 5. Launch the Forensic Operator Console
cd frontend && npm install && npm run dev
```

---

## 7. Current Scope & Boundaries

| Aspect | Implemented & Verified | Boundary / Requirement |
| :--- | :--- | :--- |
| **Dataset** | 60-record heterogeneous production batch | Seeded distribution for deterministic reproduction |
| **Provider** | Razorpay Payments & Refunds API adapter | Other gateways require `ProviderAdapter` implementation |
| **LLM Inference** | Local Ollama (`qwen3:8b`) with replay fallback | Replay fixtures preserve identical verification boundaries |
| **Actuation** | Razorpay Test Mode sandbox | Live accounts require production credentials & approvals |
