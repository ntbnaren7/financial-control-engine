# Demo Narrative — Financial Control Engine

**Track 4: AI Finance Controller**  
Target duration: 2–3 minutes

---

## Setup

Two terminal windows:

```bash
# Window 1: single-case demo
cd financial-control-engine

# Window 2: batch evaluation
cd financial-control-engine
```

Both commands run offline. No live provider credentials required.

---

## Act 1 — The problem (30 seconds)

> "Payment providers deliver refund confirmations through webhooks that can be lost
> or delayed. When a webhook never arrives, a finance team has an open case: the
> internal system expected a refund, but nothing was confirmed. Someone has to
> manually query the provider, interpret the response, and decide what happened.
> At scale — hundreds of transactions per day — that manual loop is expensive."

> "This engine closes that loop automatically."

---

## Act 2 — The architecture (30 seconds)

> "There are two layers. A deterministic kernel — V1 — classifies every case from
> the evidence available. When the evidence is sufficient, it produces a terminal
> classification: match, mismatch, absent, or duplicate. When the evidence is
> insufficient — when the provider is silent past the SLA — V1 declares
> EPISTEMIC_STALEMATE and routes the case for investigation."

> "The investigation layer uses a local LLM to form a hypothesis about what happened.
> A boundary validator checks the hypothesis before anything runs. A deterministic
> verifier queries the provider using only parameters from the trusted case — the
> LLM cannot influence what is queried. V1 then reclassifies on the new evidence."

> "The LLM's only job is to decide what to look at. It never classifies a financial
> outcome."

---

## Act 3 — Single-case demo (45 seconds)

Run:
```bash
PYTHONPATH=. uv run python scripts/demo_runner.py
```

**Narrate while it runs:**

> "This is a real EPISTEMIC_STALEMATE case — a refund was expected, the SLA has
> expired, and the provider gave no confirmation. V1 declares stalemate."

> "The investigator proposes querying the provider for the refund record. The
> boundary validator approves the hypothesis — the evidence IDs and intent are
> all valid. The verifier queries the provider. A refund record comes back."

> "V1 re-runs on the new evidence. VERIFIED, EXECUTED, matching amount: MATCH.
> The case is resolved."

**If running in REPLAY mode** (Ollama not available):
> "We're running in replay mode — the investigator uses a deterministic fallback
> hypothesis rather than the live LLM. The evaluation result is identical."

---

## Act 4 — Batch evaluation (45 seconds)

Run:
```bash
PYTHONPATH=. uv run python scripts/run_batch_control.py
```

**Narrate while it runs:**

> "50 predefined financial scenarios. 8 classification types. 5 that require
> investigation."

**After output:**

> "40 were direct matches — V1 resolved them without investigation. 8 more were
> resolved after investigation — the verifier queried the provider and V1
> reclassified on new evidence. 2 remain explicitly unresolved."

> "This one — REC-049 — the provider returned a 503 during investigation. We
> don't know the answer, and we say so. The system preserves EPISTEMIC_STALEMATE
> rather than manufacturing a resolution."

> "This one — REC-050 — the LLM's hypothesis referenced an evidence ID that
> doesn't exist in the bounded case. D4 rejected it. No provider query ran."

> "50 cases, 50 correct final classifications against independently defined
> ground truth. 96% resolution rate. 2 honest stalemates."

---

## Likely judge questions and answers

**Q: What happens when the LLM is wrong?**
> "Two failure modes. If the hypothesis references a fabricated evidence ID or an
> unsupported intent, D4 rejects it — no provider query runs, case stays stalemate.
> If the hypothesis is valid but the provider confirms nothing, V1 stays stalemate.
> The LLM cannot cause a wrong classification."

**Q: What would connecting to real Razorpay look like?**
> "The `RazorpayClient` is already implemented. The demo runner has a LIVE mode
> flag. You'd set the API credentials in the environment and remove the mock
> transport. No architectural change."

**Q: What's missing for production?**
> "An operator interface to review unresolved exceptions. Multi-provider support beyond
> Razorpay. Real-world validation on live transaction data. The engine includes a
> PostgreSQL-backed durable state and outbox (Phase J+), validated against 15 adversarial
> invariants. That persistence layer is the integration test path — the demonstration
> runs against an in-memory repository for Docker-free execution."

**Q: Why not just let the LLM classify directly?**
> "The same reason you don't let an analyst approve their own journal entries.
> Financial classification needs to be auditable and reproducible. An LLM output
> is probabilistic and not deterministic — you can't sign off on it. V1's
> output is a pure function of the evidence. That's what makes it auditable."

---

## What NOT to say

- Do not claim the 96% resolution rate applies to real financial data.
- Do not say "the LLM was caught hallucinating" — the C5 rejection was a
  controlled adversarial injection, not an organic model failure.
- Do not claim the system is production-ready.
- Do not compare to the old 40% metric from a different evaluation run.
