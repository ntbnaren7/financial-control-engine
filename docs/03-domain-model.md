# Domain Model

## 1. Domain Principle

Financial entities and operational incidents are separate concepts.

An incident **references** financial entities.

An incident does not own or contain the financial entity itself.

---

## 2. Core Entities

### Order

Represents the merchant's payment order.

An Order may have multiple Payment attempts.

### Payment

Represents a payment attempt associated with an Order.

A Payment has:

- provider identity
- order relationship
- amount
- currency
- provider status
- timestamps
- captured/refunded information as applicable

### Refund

Represents a refund associated with a captured Payment.

A Refund has:

- provider identity
- payment relationship
- amount
- status
- idempotency identity
- timestamps

### Evidence

Represents an observed fact obtained from a trusted system or internal source.

Evidence must retain:

- source
- entity identity
- observation time
- ingestion time
- raw content or reference
- provenance
- integrity metadata where required

Evidence is immutable.

### Incident

Represents an investigation/work unit created when an inconsistency, uncertainty, or potentially actionable financial condition is detected.

An Incident references relevant:

- Order
- Payment
- Refund
- Evidence

It may contain:

- hypotheses
- claims
- verification results
- decisions
- actions
- outcomes

---

## 3. Entity Relationship

```text
Order
  │
  └── Payment
        │
        └── Refund


Incident
  ├── references Order
  ├── references Payment
  ├── references Refund
  ├── references Evidence
  ├── contains Investigation
  └── contains Actions
```

---

## 4. Identity

Financial identity is deterministic.

Provider identity must include sufficient provider-specific identifiers to distinguish entities.

Never establish financial identity using:

- embeddings
- semantic similarity
- LLM judgment
- amount alone
- timestamp alone
- customer text similarity

Two financially similar records may still represent different transactions.

---

## 5. Monetary Representation

Monetary values are represented using integer minor units.

Example:

```text
₹500.00 → 50000 paise
```

Floating-point arithmetic must not be used for monetary invariants.

Currency is stored explicitly.

---

## 6. State

The system distinguishes:

```text
Provider Observed State
Merchant Observed State
Canonical Financial State
Epistemic State
```

These must not be collapsed into one status field.

---

## 7. Evidence vs Inference

### Evidence

Something directly observed from a provider, merchant system, or trusted system.

Example:

```text
Razorpay reports payment P123 as captured.
```

### Claim

A statement derived from one or more observations.

Example:

```text
Payment P123 belongs to Order O123.
```

### Hypothesis

A proposed explanation that has not yet been established.

Example:

```text
Merchant webhook processing failed.
```

### Verified conclusion

A hypothesis or claim whose required evidence and deterministic checks have passed.

---

## 8. Incident Lifecycle

Conceptually:

```text
DETECTED
  ↓
INVESTIGATING
  ↓
VERIFIED / UNCERTAIN / CONTRADICTED
  ↓
RESOLUTION DECISION
  ↓
ACTION / ESCALATION
  ↓
OUTCOME VERIFICATION
  ↓
RESOLVED / RECOVERED / ESCALATED / BLOCKED
```

Exact implementation states may evolve as the system is built.

---

## 9. Action

An Action represents an intended or executed operational/financial side effect.

An action must identify:

- target entity
- action type
- amount where applicable
- state version used for authorization
- evidence supporting the decision
- policy decision
- action identity
- idempotency identity
- execution status
- outcome

---

## 10. Ownership Rule

Financial entities exist independently of incidents.

Therefore:

```text
Payment → may exist without Incident
Incident → may reference Payment
```

An incident must never become the canonical owner of a Payment, Order, or Refund.