# Razorpay Buildathon Submission — Financial Control Engine (FCE)
**Track 4 (AI Finance Controller — Control & Governance) × Track 3 (Autonomous Recovery)**

---

## 1. Executive Summary & Verification Surfaces

The **Financial Control Engine (FCE)** is an autonomous financial control system that detects ledger discrepancies, uses an untrusted local language model to investigate root causes, establishes external ground truth via deterministic gateway queries, and safely executes autonomous financial recovery without granting AI financial authority.

| Surface | Link / Target | Runtime & Requirements | Scope & Purpose |
| :--- | :--- | :--- | :--- |
| 🌐 **Hosted Web Demo** | [Launch Simulator](https://financial-control-engine-fce.vercel.app/) | Browser only (Zero setup) | **Hosted deterministic simulation surface only**. Deployed for judges and evaluators to test real engine outputs, D4 boundaries, and forensic audit trails instantly on any device without installing Python, Docker, or Ollama. |
| 🎥 **Video Walkthrough** | [Watch on YouTube](https://youtu.be/jk6LZ36RM3s?si=XS3nxXRAp9UroumY) | Video player | End-to-end architecture breakdown, live local engine proof, and scenario execution. |
| 💻 **Local Live Engine** | `http://localhost:8000` | FastAPI + Ollama (`qwen3:8b`) + PostgreSQL | **Live execution path**. Dispatches live model inference and real-time Razorpay sandbox API mutations. *(Not hosted on Vercel).* |

---

## 2. Why Tracks 4 + 3: The Interlock

| Track | Problem in Isolation | FCE Architectural Role |
| :--- | :--- | :--- |
| **Track 4: Control & Governance** | Detection without recovery creates an unsustainable human operational backlog. | **The Foundation**: Establishes mathematical ground truth, enforces D4 referential containment, and bounds financial risk. |
| **Track 3: Autonomous Recovery** | Recovery without control boundaries risks catastrophic financial leakage via AI hallucinations. | **The Payoff**: Safely executes idempotent refunds and ledger syncs once ground truth is proven by deterministic controls. |
| **FCE Synthesis** | Traditional systems separate these tracks. | **FCE proves that deterministic control boundaries are what make autonomous financial recovery safe to deploy.** |

---

## 3. Core Technical Thesis

> **AI can hypothesize, but it cannot establish truth, authorize action, or mutate financial state.**

| Control Layer | Component | Authority | Guarantees Enforced |
| :--- | :--- | :--- | :--- |
| **Untrusted Reasoning** | Local LLM (`qwen3:8b`) | **Zero** | Receives immutable context of 4 SHA-256 hashed records; outputs hypothesis only. |
| **Trust Boundary** | D4 Output Validator | **Hard Stop** | Rejects any hypothesis referencing ungrounded evidence IDs outside the bounded case. |
| **Deterministic Truth** | Gateway Verifier | **Ground Truth** | Queries Razorpay API directly using verified case parameters (never LLM text). |
| **Deterministic Action** | Governance Gate & Actuator | **Sole Authority** | Enforces kill-switches, action budgets, OCC CAS version leases (`v1 → v2`), and idempotency. |
| **Closed-Loop Proof** | Re-Observation Engine | **Verification** | Re-polls Razorpay ledger post-mutation to confirm convergence before closing incident. |

---

## 4. The 7-Stage Control Architecture

```
01 DETECT ➔ 02 INVESTIGATE ➔ [ D4 BOUNDARY ] ➔ 03 VERIFY ➔ 04 DECIDE ➔ 05 ACT ➔ 06 RE-OBSERVE ➔ 07 OUTCOME
```

| Stage | Name | Worker | Core Operation | Deterministic Invariant |
| :---: | :--- | :--- | :--- | :--- |
| **01** | `DETECT` | Deterministic Kernel | Pure state comparison: Ledger vs Provider | Flags `STATE_MISMATCH` with 0% AI invocation |
| **02** | `INVESTIGATE` | Local LLM (`qwen3:8b`) | Analyzes 4 SHA-256 hashed evidence records | Proposes structured `CausalHypothesis` (0% authority) |
| **03** | `VERIFY` | Deterministic Verifier | D4 citation validation + Razorpay API query | Rejects ungrounded IDs; proves external ground truth |
| **04** | `DECIDE` | Governance Gate | Policy matching + budget & kill-switch checks | Derives `REFUND_PAYMENT`; enforces daily spend quotas |
| **05** | `ACT` | Idempotent Actuator | OCC CAS version lease (`v1 → v2`) + refund call | Unique idempotency key prevents duplicate execution |
| **06** | `RE-OBSERVE` | Provider Gateway | Re-polls Razorpay API post-mutation | Verifies external status flipped to `refunded` |
| **07** | `OUTCOME` | State Substrate | Re-evaluates kernel on fresh state; persists audit | Transitions to `RESOLVED`; seals Merkle evidence log |

---

## 5. Safety & Control Guarantees

| Risk in Naive AI Automation | How FCE Solves It | Technical Enforcement |
| :--- | :--- | :--- |
| **Model Hallucination** | Output strictly bounded to case context | **D4 Referential Validator** rejects any ungrounded evidence ID |
| **Prompt Injection / Jailbreak** | Model output cannot influence API parameters | **Gateway Verifier** derives parameters solely from trusted case file |
| **Runaway Financial Loss** | LLM cannot authorize financial spend | **Governance Gate** enforces kill-switches and daily spend limits |
| **Duplicate Webhooks / Races** | Concurrent workers cannot process same payment twice | **Atomic OCC CAS Leases** (`v1 → v2`) reject out-of-order execution |
| **Network Retries / Duplicates** | Provider retries cannot cause double refunds | **Deterministic Idempotency Keys** persisted before dispatch |
| **Silent Mutation Failure** | HTTP 200 return code not trusted as truth | **Post-Action Re-Observation Loop** verifies provider ledger convergence |
| **Unprovable Cases** | Engine refuses to guess when data is missing | **Honest Escalation** (`ESCALATED_MISSING_EVIDENCE`) preserves safety |

---

## 6. Concrete Evidence & Evaluation Results

### A. Track 4 Benchmark: 60-Record Heterogeneous Batch

```bash
uv run python scripts/batch_reconciliation.py --provider mock --count 60
```

| Evaluation Metric | Observed Result | Engineering Interpretation |
| :--- | :--- | :--- |
| **Total Processed** | **60 records** (0.6s) | Exceeds Track 4 requirement of 50+ records |
| **Direct Matches** | **40 / 60 (66.7%)** | Resolved deterministically in Stage 1 with 0% AI invocation |
| **Autonomous Remediations** | **11 / 60 (18.3%)** | Discrepancy investigated, verified, authorized, and refunded |
| **Total Automated Resolution** | **85.0% (51/60)** | Combined autonomous resolution rate |
| **Honest Safety Escalations** | **9 / 60 (15.0%)** | 6 provider 404s + 3 amount mismatches (Zero guessing) |
| **Timeouts / Crashes** | **0 / 60 (0.0%)** | 100% clean termination across all incidents |
| **Unauthorized Mutations** | **0 / 60 (0.0%)** | Zero false refunds; zero ungrounded mutations |

### B. Core Scenarios & Adversarial Containment (`scripts/test_7_cases.py`)

| Scenario | Condition Tested | Engine Action | Final Disposition | Invariant Proven |
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

## 7. Forensic Operator Console Capabilities

| Capability | Hosted Simulation ([Web Demo](https://financial-control-engine-fce.vercel.app/)) | Local Environment (`frontend/`) |
| :--- | :--- | :--- |
| **7-Stage Control Step-Through** | Yes — deterministic interactive progression | Yes — identical stepping logic |
| **Scenario A, B & C Selection** | Yes — test happy path, 404s, and adversarial halt | Yes — full scenario selector |
| **Inline Audit Accordions** | Yes — inspect SHA-256 evidence hashes and context | Yes — full forensic inspector |
| **Razorpay cURL Terminal** | Yes — dark terminal inspecting HTTP requests | Yes — dark terminal view |
| **60-Record Batch Modal** | Yes — filter by Match, Remediation, and Escalation | Yes — interactive batch inspector |
| **Live Engine Triggering** | No (Hosted simulation surface only; no local backend) | **Yes** — connects to `localhost:8000` + Ollama (`qwen3:8b`) |

---

## 8. Verification Commands

```bash
# 1. Reproduce 60-record batch benchmark (0.6s)
uv run python scripts/batch_reconciliation.py --provider mock --count 60

# 2. Run the 3 core safety scenarios (Scenario A, B, and Adversarial C)
uv run python scripts/test_7_cases.py

# 3. Run the deterministic test suite (175 tests, 0.3s)
uv run pytest tests/unit tests/reconciliation tests/recovery tests/domain tests/api tests/control tests/state

# 4. Launch the Interactive Operator Console
cd frontend && npm run dev
```
