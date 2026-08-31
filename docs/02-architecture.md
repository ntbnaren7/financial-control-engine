# Architecture

## 1. Architectural Principle

The system separates:

```text
OBSERVATION
→ STATE
→ INVESTIGATION
→ VERIFICATION
→ CONTROL
→ ACTION
→ OUTCOME
```

AI operates inside the investigation boundary.

It does not own financial authority.

---

## 2. High-Level Architecture

```text
                    RAZORPAY
                       │
              ┌────────┴────────┐
              │                 │
           Webhooks            API
              │                 │
              └────────┬────────┘
                       ↓
                Integration Layer
                       ↓
                 Evidence Layer
                       ↓
                  State Engine
                       ↓
                  Incident Engine
                       ↓
              ┌────────┴────────┐
              │                 │
        Investigation       Verification
              │                 │
              └────────┬────────┘
                       ↓
                  Control Plane
                       ↓
                  Action Engine
                       ↓
                    Razorpay
                       ↓
               Outcome Verification
```

---

## 3. Deployment Model

V0 is a modular monolith.

Initial deployable components:

```text
API
Web
Worker
PostgreSQL
```

The components share one codebase where practical.

No microservice decomposition is required for V0.

---

## 4. Backend

### Language

Python 3.12+

### Framework

FastAPI

### Validation

Pydantic v2

### Database

PostgreSQL

### Persistence

SQLAlchemy 2

### Migrations

Alembic

---

## 5. Frontend

Next.js + TypeScript.

Backend API contracts are generated from FastAPI's OpenAPI specification.

```text
Pydantic
   ↓
FastAPI
   ↓
OpenAPI
   ↓
TypeScript generated types
   ↓
Next.js
```

Frontend types must not be manually duplicated from backend models.

---

## 6. Persistence Model

PostgreSQL is the V0 system of record.

Primary concepts include:

- orders
- payments
- refunds
- provider events
- evidence
- incidents
- actions
- action outcomes
- jobs/audit records as required

Raw provider evidence must remain immutable.

Derived state may be recalculated or versioned.

---

## 7. Provider Boundary

Razorpay-specific API and webhook behavior remains inside:

```text
integrations/razorpay/
```

The domain must not depend directly on raw Razorpay payload structures.

The integration layer converts provider responses into internal representations while preserving the original provider payload as evidence.

---

## 8. Event Handling

Provider webhooks are treated as asynchronous, at-least-once observations.

The system must handle:

- duplicate events
- out-of-order events
- delayed events
- invalid events
- invalid signatures

Raw evidence is persisted before successful acknowledgement where required by the processing path.

Background processing must not depend on the webhook HTTP request remaining alive.

---

## 9. Asynchronous Processing

Use a PostgreSQL-backed job/outbox mechanism.

Do not introduce a separate message broker unless implementation evidence requires one.

The transactional principle is:

```text
state/evidence change
+
processing intent
=
single database transaction
```

A worker processes durable jobs afterward.

---

## 10. State Model

Provider state and merchant state are observations.

Canonical financial state is derived from validated evidence.

Do not use:

```text
last received event = truth
```

or:

```text
provider status = entire system state
```

State transitions must be deterministic.

---

## 11. Investigation

Investigation follows a constrained workflow:

```text
Incident
   ↓
Evidence Context
   ↓
Investigation Planner
   ↓
LLM
   ↓
Structured Hypotheses / Claims
   ↓
Evidence Retrieval
   ↓
Deterministic Verification
```

The LLM does not control the overall execution loop.

---

## 12. Control Plane

Financial action requires:

```text
Recommendation
→ Verification
→ Policy Check
→ Authorization
→ State Freshness Check
→ Concurrency Check
→ Idempotent Execution
→ Outcome Verification
```

No step may be bypassed by an LLM.

---

## 13. Financial Actions

V0 prioritizes:

- state repair
- event reprocessing where applicable
- controlled refund execution
- escalation

Generic payment retry is not an autonomous V0 primitive.

Recovery must prefer the smallest safe action that restores consistency.

---

## 14. Concurrency

Actions affecting financial entities must prevent conflicting concurrent execution.

Authorization must be associated with the verified state against which the decision was made.

If the relevant state changes before execution, the action must be revalidated.

---

## 15. AI Failure Containment

The system must remain financially safe if the LLM:

- hallucinates
- produces malformed output
- produces incorrect hypotheses
- becomes unavailable
- receives adversarial input
- recommends an unsafe action
- expresses unjustified confidence

LLM confidence is never a financial authorization primitive.

---

## 16. Architecture Revisit Rule

Do not introduce a new service, database, framework, broker, abstraction, or infrastructure component unless:

1. a concrete requirement exists,
2. the current architecture cannot satisfy it adequately, and
3. the additional complexity is justified by the resulting capability or safety improvement.

---

## 17. Governing Constraint

The architecture must optimize for:

> **Minimum complexity required to achieve production-grade financial correctness and safety.**