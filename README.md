# Financial Control Engine (FCE)
*Autonomous Financial Exception Control with Deterministic Safety Boundaries*

**Razorpay Buildathon — Track 4 (Control & Governance) × Track 3 (Autonomous Recovery)**

---

## 1. Abstract

The Financial Control Engine (FCE) presents a novel dual-layer control architecture for autonomous financial reconciliation and exception recovery. The system explicitly untrusts artificial intelligence in financial execution. Instead of delegating financial authority to a Large Language Model (LLM), FCE isolates the probabilistic reasoning of an LLM within a strictly bounded deterministic verification kernel. 

Under this architecture, the AI investigates payment mismatches and formulates structured causal hypotheses. However, all external ground truth verification and state mutations (such as issuing refunds) are strictly executed by the deterministic control layer. This ensures that idempotent financial operations remain mathematically verifiable and completely isolated from model hallucinations.

**Core Thesis:** Probabilistic models investigate uncertainty; deterministic controls establish truth and authorize mutation.

---

## 2. Problem Formulation

Modern financial infrastructure operates at immense scale, yet exception handling (e.g., payment drops, gateway timeouts, mismatched ledgers) remains heavily reliant on manual forensic investigation. Introducing autonomous agents into this loop presents critical operational risks:
1. **Hallucination of Financial State**: AI models cannot be trusted to infer truth from probabilistic distributions.
2. **Unauthorized Mutation**: Delegating write-access to financial APIs (e.g., Stripe, Razorpay) directly to LLMs violates core governance and compliance principles.
3. **State Desynchronization**: Agentic retry loops without strict idempotency risk catastrophic failures like double-spending.

FCE solves this by introducing a firm boundary between *inference* and *actuation*.

---

## 3. System Architecture

The FCE pipeline is explicitly designed to isolate probabilistic reasoning from deterministic financial execution through a rigorous 7-stage pipeline.

```
01 DETECT ➔ 02 INVESTIGATE ➔ [ D4 BOUNDARY ] ➔ 03 VERIFY ➔ 04 DECIDE ➔ 05 ACT ➔ 06 RE-OBSERVE ➔ 07 OUTCOME
```

### The Probabilistic Layer (Stages 1-2)
- **01 DETECT**: The deterministic kernel performs a pure state comparison between the internal ledger and the provider gateway. It flags `STATE_MISMATCH` with zero AI invocation.
- **02 INVESTIGATE**: A local LLM (e.g., `qwen3:8b`) analyzes hashed evidence records to propose a structured `CausalHypothesis`. The model has no API keys and zero write access.

### The D4 Referential Boundary
Before a hypothesis can proceed, it must pass the D4 Referential Validator. This strict syntactic gatekeeper rejects any hypothesis that cites evidence IDs outside the bounded case, effectively neutering LLM hallucinations.

### The Deterministic Layer (Stages 3-7)
- **03 VERIFY**: The deterministic verifier validates citations and queries the Razorpay API. It halts on ungrounded IDs and proves external facts.
- **04 DECIDE**: The Governance Gate evaluates policy, enforces strict action budgets, and checks emergency kill-switches.
- **05 ACT**: The Idempotent Actuator claims an Optimistic Concurrency (OCC) CAS lease (`v1 → v2`) and dispatches the refund. A cryptographic idempotency key prevents double-spending.
- **06 RE-OBSERVE**: The Provider Gateway re-polls the Razorpay API post-mutation to verify the external status has physically transitioned to `refunded`.
- **07 OUTCOME**: The State Substrate re-runs the kernel on fresh facts, commits the audit trail, and transitions the case to `RESOLVED`, sealing the cryptographic record.

---

## 4. Security Guarantees & Control Mechanisms

The architecture enforces strict mathematical and computational boundaries to mitigate operational risks inherent to autonomous systems.

| Operational Risk | Control Mechanism | Technical Enforcement |
| :--- | :--- | :--- |
| **LLM Hallucination** | D4 Referential Validator | Rejects any hypothesis citing evidence IDs outside the bounded case |
| **Prompt Injection** | Isolated Verifier | Target parameters derived strictly from verified case records, never model text |
| **Runaway Spend** | Governance Gate | Strict action budget enforcement and hardware emergency kill-switch |
| **Race Conditions** | Optimistic Concurrency (OCC) | Atomic CAS version increments (`v1 → v2`) prevent concurrent execution |
| **Network Duplication** | Deterministic Idempotency | SHA-256 idempotency key (`idem_refund_{id}_v{version}`) persisted prior to API call |
| **Silent Provider Failure**| Post-Action Re-Observation | Return codes (HTTP 200) not trusted; external ledger strictly re-polled for proof |

---

## 5. Technical Documentation & Empirical Evidence

- **[Launch Web Simulator](https://financial-control-engine-fce.vercel.app/)**
  Execute deterministic simulations, observe boundary validations, and review forensic audit trails within a zero-setup browser environment.
  
- **[Architecture Walkthrough](https://youtu.be/jk6LZ36RM3s?si=XS3nxXRAp9UroumY)**
  Comprehensive video demonstration detailing the end-to-end architecture, backend execution flow, and adversarial scenario containment.

- **[Empirical Evidence & Test Results](docs/evidence_and_tests.md)**
  Detailed quantitative analysis of the 60-record batch benchmarks (85% autonomous resolution), adversarial boundary containment proofs, and the 284-test invariant suite.

---

## 6. Local Execution Environment

To initialize the backend execution engine and execute the deterministic test suites within a local environment, proceed with the following commands:
### Local LLM Requirements
FCE requires [Ollama](https://ollama.com/) to be running locally for the probabilistic investigation phase.
```bash
# Pull your preferred reasoning model (e.g., qwen2.5:14b, llama3, etc.)
ollama pull <model_name>
```

### Backend Initialization
```bash
# 1. Synchronize Python dependencies via uv
uv sync

# 2. Execute the 60-record batch benchmark
uv run python scripts/batch_reconciliation.py --provider mock --count 60

# 3. Execute the core safety invariants (Standard, Missing Data, Adversarial)
uv run python scripts/test_7_cases.py

# 4. Execute the comprehensive unit and integration test suite
uv run pytest tests/unit tests/reconciliation tests/recovery tests/domain tests/api tests/control tests/state
```

### Forensic Operator Console (Frontend)
```bash
cd frontend
npm install
npm run dev
```
