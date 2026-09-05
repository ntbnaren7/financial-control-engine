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

## Act 3 — Single-case demo & autonomous recovery (45 seconds)

Run:
```bash
uv run python scripts/test_7_cases.py
```

**Narrate while it runs:**

> "Here we demonstrate the complete autonomous loop across three distinct scenarios:
> Scenario A is the hero path: a state mismatch discrepancy is detected (expected SETTLED,
> observed PENDING/UNPAID). The A3 investigator forms a hypothesis, the validator approves it,
> the deterministic verifier queries the provider, policy derives the repair, governance claims budget,
> the actuation engine executes idempotently, and independent re-observation verifies convergence.
> The incident reaches RESOLVED."

> "Scenario B is the safe missing evidence path: the provider returns a 404 for a missing payment.
> The verifier reports missing evidence. The system safely escalates to ESCALATED_MISSING_EVIDENCE
> without attempting any financial mutation."

> "Scenario C is the adversarial containment path: the untrusted LLM hallucinated a fabricated
> evidence ID. The D4 OutputValidator catches the containment breach before any provider query runs,
> blocking verification and safely escalating to ESCALATED_UNKNOWN."

---

## Act 4 — Batch evaluation & UI Control Console (45 seconds)

Run terminal verification or open the UI console at `http://localhost:5173`:
```bash
uv run python scripts/batch_reconciliation.py --provider mock --count 60
```

**Pitch Narrating Guidance:**

> "This is not an accuracy claim. These are the observed outcomes of our 60-record control run:
> • 66.7% direct match rate = 40/60 records matched during deterministic reconciliation.
> • 18.3% autonomous remediation = 11/60 required and received the demonstrated refund workflow.
> • 15.0% escalation rate = 9/60 were not safely resolvable.
> • 85.0% total resolution = 51/60 reached a resolved outcome (40 direct matches + 11 remediated).
> • 0 unsupported resolutions = none of the 60 were declared resolved without the required control/evidence path."

> "Notice we don't hide the 9 escalations. When provider evidence is missing or amounts mismatch,
> the system halts actuation and generates an honest escalation."

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
