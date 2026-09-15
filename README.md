# Financial Control Engine (FCE)
*Autonomous Financial Exception Control with Deterministic Safety Boundaries*  
**Razorpay Buildathon — Track 4 (Control & Governance) × Track 3 (Autonomous Recovery)**

---

## What is FCE?

The Financial Control Engine (FCE) is a two-layer control system built for autonomous financial reconciliation and exception recovery. 

It explicitly **untrusts** artificial intelligence. Instead of giving an LLM access to your financial APIs, FCE pairs an untrusted local language model with a **deterministic verification kernel**. The AI investigates payment mismatches and proposes hypotheses, but the deterministic kernel verifies external ground truth and safely executes idempotent financial mutations without ever delegating financial authority to the AI.

> **Core Thesis:** AI investigates uncertainty. Deterministic controls establish truth and authorize mutation.

---

## Quick Links

- 🌐 **[Launch Web Simulator](https://financial-control-engine-fce.vercel.app/)**: Test actual outputs, D4 boundaries, and forensic audit trails instantly in your browser (Zero setup).
- 🎥 **[Watch Video Walkthrough](https://youtu.be/jk6LZ36RM3s?si=XS3nxXRAp9UroumY)**: End-to-end architecture breakdown, live backend demonstration, and scenario walkthrough.
- 🏗️ **[Architecture & Security Guarantees](docs/architecture_and_security.md)**: Deep dive into the 7-Stage Control Architecture and the D4 Referential Validator.
- 📊 **[Evidence & Test Results](docs/evidence_and_tests.md)**: See the 60-record batch benchmarks, the adversarial containment proofs, and the 284-test Pytest suite.

---

## How to Run Locally

If you want to run the python backend engine and test suites locally:

```bash
# 1. Install Python dependencies using uv
uv sync

# 2. Run the 60-record batch benchmark (Completes in ~0.6s)
uv run python scripts/batch_reconciliation.py --provider mock --count 60

# 3. Run the 3 core safety scenarios (Happy path, Missing Data, and Adversarial LLM)
uv run python scripts/test_7_cases.py

# 4. Run the fast test suite (175 tests in 0.3s)
uv run pytest tests/unit tests/reconciliation tests/recovery tests/domain tests/api tests/control tests/state
```

To run the Forensic Operator Console (Frontend):
```bash
cd frontend
npm install
npm run dev
```
