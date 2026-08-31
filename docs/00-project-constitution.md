# Project Constitution

## 1. Purpose

Build a production-grade financial control and recovery system that can determine what actually happened when payment-related systems disagree, verify that conclusion using financial evidence, and safely recover or escalate the incident.

The system is designed around one principle:

> **Never take a financial action unless the system has sufficient deterministic evidence that the action is safe.**

---

## 2. Core Product Loop

```text
OBSERVE
  ↓
UNDERSTAND
  ↓
VERIFY
  ↓
DECIDE
  ↓
ACT
  ↓
VERIFY AGAIN
```

The system must close the loop rather than stop at reconciliation or recommendation.

---

## 3. Core Product Thesis

Financial failures are often not clean failures.

Money may successfully move while surrounding systems remain stale, contradictory, incomplete, delayed, or uncertain.

The product therefore combines:

- financial state reconstruction
- evidence-based investigation
- deterministic verification
- controlled recovery
- post-action verification

---

## 4. V0 Scope

V0 focuses on Razorpay Test Mode and a deliberately narrow set of payment incidents.

Primary incident:

> **Payment captured by Razorpay while the merchant's local order state remains unpaid/stale.**

Secondary incident:

> **Refund execution becomes uncertain because the provider response is unavailable or ambiguous.**

V0 should demonstrate:

- Razorpay API integration
- webhook ingestion
- evidence preservation
- financial state reconstruction
- discrepancy detection
- investigation
- deterministic verification
- safe non-monetary recovery
- idempotent monetary recovery where applicable
- outcome verification
- escalation when evidence is insufficient

---

## 5. Non-Negotiable Principles

### Financial safety

AI must never directly control money movement.

### Evidence integrity

Raw provider observations are immutable.

### Determinism

Financial identity, amounts, state transitions, authorization, idempotency, and safety checks must be deterministic.

### Fail closed

Unknown, stale, contradictory, or insufficiently verified financial state must not trigger autonomous monetary action.

### Idempotency

Repeated delivery, retry, worker execution, or network uncertainty must not create duplicate financial effects.

### Re-verification

An action is not considered successful merely because an API request succeeded. The resulting financial state must be independently verified.

### Minimal complexity

Use the smallest architecture that satisfies the required correctness, reliability, security, and operational properties.

### No speculative infrastructure

Do not introduce infrastructure, services, frameworks, databases, or abstractions without a demonstrated requirement.

---

## 6. AI Boundary

AI is an investigation component.

AI may:

- generate hypotheses
- correlate evidence
- identify missing evidence
- propose investigation steps
- explain verified findings
- recommend possible actions

AI may not:

- define financial truth
- establish financial identity
- override deterministic state
- bypass invariants
- authorize itself
- directly execute monetary actions

---

## 7. Production-Grade Definition

Production-grade means:

- correct
- safe
- deterministic where required
- idempotent
- observable
- auditable
- testable
- secure
- maintainable
- recoverable

Production-grade does **not** mean:

- microservices
- Kubernetes
- Kafka
- multiple databases
- generic agent frameworks
- unnecessary abstraction
- premature horizontal scaling

---

## 8. Technology Direction

V0 uses:

- Python + FastAPI backend
- Pydantic
- PostgreSQL
- SQLAlchemy
- Alembic
- Next.js + TypeScript
- OpenAPI-generated frontend types
- direct LLM SDK integration
- pytest + Hypothesis
- Razorpay Test Mode

Technology choices may change only when implementation evidence demonstrates that the current choice is inadequate.

---

## 9. Scope Discipline

Build the smallest complete vertical slice first.

Do not generalize a component merely because it may be useful later.

Prefer:

> one real, correct implementation

over:

> a generalized framework with no proven use case.

---

## 10. Governing Question

Every significant architectural or implementation decision must answer:

> **Could this architecture survive being connected to real money?**

If the answer is no or uncertain, the design is not complete.