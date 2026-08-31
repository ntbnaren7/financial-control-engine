# Engineering Rules

## 1. General Rule

Build the smallest system that satisfies the required production properties.

Do not optimize for architectural complexity, technology count, or perceived sophistication.

---

## 2. Financial Safety Rules

1. Never execute a monetary action directly from LLM output.
2. Never treat LLM confidence as authorization.
3. Never use semantic similarity as financial identity.
4. Never perform an action against stale authorization.
5. Never assume an unknown outcome is a failure.
6. Never assume an unknown outcome is a success.
7. Never retry a monetary action without preserving action identity and idempotency.
8. Never allow concurrent actions to create duplicate financial effects.
9. Never overwrite immutable provider evidence.
10. Never mark a financial operation successful solely because an HTTP request succeeded.

---

## 3. Evidence Rules

1. Preserve raw provider observations.
2. Record provenance for derived claims.
3. Separate evidence from inference.
4. Separate hypotheses from verified conclusions.
5. Do not modify historical evidence to match current conclusions.
6. Preserve enough information to reconstruct why a decision was made.

---

## 4. State Rules

1. State transitions must be deterministic.
2. Event arrival order must not automatically determine financial chronology.
3. Duplicate events must be safely deduplicated.
4. Provider and merchant state must remain distinguishable.
5. State must be versioned where authorization depends on its freshness.
6. Contradictory evidence must remain contradictory until resolved.
7. Unknown state must not be silently converted into a known state.

---

## 5. AI Rules

AI may:

- investigate
- hypothesize
- correlate
- explain
- recommend

AI may not:

- define financial truth
- establish financial identity
- authorize money movement
- bypass policy
- bypass invariants
- directly invoke uncontrolled mutation operations

All machine-consumed AI output must be structurally validated.

---

## 6. API Rules

1. Validate untrusted input at the boundary.
2. Do not expose raw provider structures throughout the domain.
3. Maintain explicit request/response contracts.
4. Keep frontend and backend contracts synchronized through OpenAPI-generated types.
5. Do not silently change API semantics.

---

## 7. Database Rules

1. Use transactions for atomic financial state changes.
2. Enforce important uniqueness constraints at the database level.
3. Do not rely solely on application-level duplicate checks.
4. Monetary values use integer minor units.
5. Migrations are required for schema changes.
6. Audit-critical records must not depend exclusively on application logs.

---

## 8. Concurrency Rules

For actions affecting financial state:

```text
read
→ verify
→ authorize
→ acquire execution protection
→ revalidate
→ execute
```

If relevant state changes before execution, invalidate the previous authorization.

---

## 9. Recovery Rules

Prefer:

```text
smallest safe corrective action
```

over:

```text
largest possible automation
```

Reprocessing an event is not the same as repeating a financial action.

State repair is a valid recovery operation.

---

## 10. Reliability Rules

Every externally triggered asynchronous operation must have explicit behavior for:

- duplicate delivery
- timeout
- retry
- worker crash
- provider unavailability
- partial completion
- unknown outcome

Do not introduce infrastructure unless it solves an actual reliability requirement.

---

## 11. Testing Rules

Critical financial invariants must have automated tests.

Tests must cover:

- happy paths
- boundary conditions
- duplicate events
- out-of-order events
- invalid evidence
- stale state
- concurrent actions
- timeout/unknown outcomes
- unsafe recommendations
- idempotent retries

If a failure can cause unsafe financial behavior, it must become a regression test.

---

## 12. Security Rules

1. Secrets never enter source control.
2. Test and live credentials must remain isolated.
3. Webhook authenticity must be verified before accepting provider evidence.
4. Authorization must be explicit.
5. External input must be treated as untrusted.
6. LLM output must be treated as untrusted.
7. Provider metadata must not be assumed safe merely because it originated from a payment flow.

---

## 13. Architecture Rules

Before adding any dependency, service, framework, database, abstraction, or infrastructure, answer:

1. What concrete requirement requires it?
2. What failure or limitation does it address?
3. Why is the simpler solution insufficient?

If these cannot be answered, do not add it.

---

## 14. Implementation Rule

Do not generalize prematurely.

Implement:

```text
specific correct behavior
```

before:

```text
generic framework for possible future behavior
```

Generalize only when repeated requirements demonstrate that the abstraction is warranted.

---

## 15. Review Question

For every material change:

> **Could this change create an unsafe financial state if the provider, network, worker, database, or AI behaves unexpectedly?**

If yes, the failure mode must be explicitly handled and tested.