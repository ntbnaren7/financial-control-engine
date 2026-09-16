# Contributing to Invariant

## 1. What Invariant Is

**Invariant is a financial control plane that sits between financial state and financial action.**

It reconciles heterogeneous financial state, uses AI only for bounded investigation, establishes facts deterministically, authorizes actions through explicit policy, executes with concurrency and idempotency guarantees, and independently verifies external convergence.

**The repository is not an autonomous AI agent.**
The LLM is an untrusted reasoning component inside a deterministic control system.

---

## 2. Contribution Philosophy

**Every contribution must make the system more correct, safer, more observable, or more useful without weakening its control boundary.**

### Never allow:
- LLM output to directly authorize financial mutation.
- `UNKNOWN` to silently become `FAILED`, `NOT_EXECUTED`, or `EXECUTED`.
- provider responses to be treated as financial truth without authority validation.
- retries to generate new financial intent identities.
- duplicate workers to create duplicate financial effects.
- a successful mutation response to automatically imply verified external state.
- contradictory evidence to be silently resolved by the model.
- test/demo behavior to masquerade as production guarantees.

---

## 3. Architecture Before Code

Understand these boundaries before modifying anything:

```text
Financial Observations
        ↓
Reconciliation / State Reconstruction
        ↓
Bounded Investigation
        ↓
Deterministic Verification
        ↓
Policy + Governance
        ↓
Authorized Action
        ↓
External Re-observation
        ↓
Verified Convergence / Escalation
```

### The Authority Hierarchy
**Provider observations → deterministic state/control logic → policy → action**

while:

**LLM → hypothesis/investigation only**

---

## 4. Current System / What Exists Today

| Area | Current capability |
|---|---|
| Reconciliation | Deterministic cross-system discrepancy detection |
| Investigation | Bounded LLM investigation |
| AI containment | D4 referential/evidence containment |
| Provider truth | Typed provider query/mutation boundary |
| State | Explicit epistemic + financial execution semantics |
| Authorization | Deterministic policy/control gate |
| Concurrency | OCC/CAS protection |
| Financial retries | Stable intent + idempotency |
| Execution | Transactional outbox / dispatcher |
| Verification | Post-action provider re-observation |
| Escalation | Explicit unresolved/unknown outcomes |
| Evaluation | 60-record controlled evaluation corpus |
| Live path | FastAPI + PostgreSQL + Ollama + Razorpay Test Mode |

*The current repository demonstrates the control architecture and its modeled failure behavior; production deployment would require the hardening described below.*

---

## 5. How to Contribute

### Before changing anything
1. Read the relevant architecture/specification docs.
2. Understand the invariant(s) affected.
3. Identify existing tests covering the behavior.
4. Define the failure modes introduced by the change.
5. Add/update evaluation coverage.
6. Only then implement.

**Do not silently introduce architectural changes through implementation. If a change contradicts an existing architectural decision, document the contradiction before coding.**

---

## 6. High-Value Areas for Improvement

### Expand Financial Control Coverage
The next product iteration should handle more financial exception classes. Expand the state space before expanding autonomous authority.

**Payment lifecycle:**
- authorized but not captured
- captured but merchant state stale
- failed payment with inconsistent merchant state
- duplicate payment
- partial capture / partial refund
- refund pending
- refund completed externally but missing internally
- chargeback/dispute state divergence

**Recurring revenue:**
- failed subscription payment
- mandate retry
- recurring payment recovery
- grace-period enforcement

**Finance operations:**
- settlement reconciliation
- payout reconciliation
- ledger vs gateway mismatch
- receivable reconciliation
- fee discrepancies
- currency/amount mismatches

---

## 7. Provider-Agnostic Control Plane

**Provider adapter → normalized financial observations → common FCE control plane**

The core engine shouldn't care which provider generated the observation. Potential adapters include Stripe, Adyen, PayPal, bank/payment processors, and internal payment systems.

---

## 8. Merchant Integration Layer

Normalize heterogeneous financial observations into one canonical control model through:
- payment-provider APIs
- webhooks
- order databases
- ERP/accounting systems
- internal ledgers
- event streams
- reconciliation files
- settlement reports

---

## 9. Policy Engine

Move beyond hardcoded demo policies. Merchants should define rules (e.g., maximum autonomous refund amount, allowed currencies, provider-specific constraints).

**Policy configuration must constrain authority, never expand authority beyond what deterministic verification establishes.**

---

## 10. Evidence & Provenance

Every decision should answer: **Why did we believe this?**

Maintain a complete provenance chain:
**Observation → Evidence → Hypothesis → Verification → Policy → Action → Provider Result → Re-observation**

---

## 11. Production Reliability

Every external financial mutation must have a defined behavior for crashes before request, during request, after provider acceptance, after response loss, and during retry.

Improve toward:
- PostgreSQL-backed transactional guarantees
- proper transaction isolation testing
- durable queues and worker leasing
- dead-letter handling
- provider timeout recovery and API rate limits
- idempotency retention handling
- network partitions and regional failures

---

## 12. Observability

The interesting product metric isn't merely "AI accuracy". It's:
- **How many exceptions were safely resolved?**
- **How many required escalation?**
- **How many financial mutations were prevented?**
- **How many duplicate-effect attempts were contained?**

---

## 13. Evaluation & Adversarial Testing

Treat this as a **first-class product subsystem**, not just tests. Expand the corpus continuously across clean cases, reconciliation failures, epistemic failures, distributed failures, and AI adversarial cases.

---

## 14. Product Surface

The UI should be a **representation of the control model**, not a second source of truth.
- **Control Console**: open exceptions, financial state, evidence, action history.
- **Policy Console**: limits, approval requirements, escalation rules.
- **Audit Console**: "Show me every autonomous financial action and why it was allowed."
- **Integration Console**: "Connect Razorpay / Stripe / ERP / ledger."

---

## 15. AI Evolution

Don't optimize primarily for autonomy. Optimize for:
- better hypothesis generation
- better evidence selection
- better causal correlation
- lower unnecessary provider queries

**AI can improve understanding; deterministic systems retain authority.**

---

## 16. Roadmap

### Phase 1 — Control Kernel (Current)
Deterministic reconciliation + bounded investigation + verification + policy + safe actuation + convergence.

### Phase 2 — Provider & Data Expansion
Multi-provider adapters + merchant ledger integrations + richer financial state models.

### Phase 3 — Production Hardening
Durability, isolation, queues, observability, failure recovery, security, operational tooling.

### Phase 4 — Financial Operations Platform
Settlement, refunds, disputes, subscriptions, payouts, receivables and other financial workflows.

### Phase 5 — Intelligent Control Plane
AI-assisted investigation, anomaly clustering, root-cause learning and policy recommendations — while retaining deterministic authority boundaries.

---

## 17. Definition of a Good Contribution

A good contribution to Invariant does not merely add functionality.

It makes a financial state easier to establish, a consequential action safer to authorize, a failure easier to recover from, or an outcome easier to prove.

**If a change makes the system more autonomous but less deterministic, auditable, or safe, it is not an improvement.**

---

**Invariant exists to make financial automation trustworthy under uncertainty. Contributions should strengthen that property, not trade it for autonomy.**
