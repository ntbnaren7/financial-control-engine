Below is the **detailed V0 PRD**. It is deliberately product-focused: it tells Claude/Gemini **what we're building, what behavior is required, what constitutes correctness, and what is explicitly out of scope**—without prematurely dictating implementation.

# Financial Control & Recovery Engine
## Product Requirements Document — V0

**Status:** Active  
**Version:** 0.1  
**Product:** Financial Control & Recovery Engine  
**Provider:** Razorpay  
**Environment:** Razorpay Test Mode  
**Primary Objective:** Build a production-grade financial control loop that can detect, investigate, verify, safely resolve/recover, and re-verify uncertain financial states.

---

# 1. Executive Summary

Financial transactions rarely exist as a single source of truth.

A payment may be captured by a payment provider while a merchant's internal order remains unpaid. A webhook may be delayed, duplicated, lost, or processed incorrectly. A refund request may time out after the provider has already processed it. Different systems can therefore hold contradictory representations of the same financial event.

Existing payment infrastructure generally exposes transaction states and APIs, but the merchant is still responsible for determining what actually happened when those states disagree and deciding what action is safe.

The Financial Control & Recovery Engine addresses this gap.

The system continuously reasons over financial evidence from multiple sources, reconstructs the most defensible financial state, investigates discrepancies, verifies hypotheses deterministically, and—only when sufficient evidence and safety conditions exist—executes the smallest appropriate recovery action.

The central product loop is:

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

The system is explicitly designed around the principle:

> **Knowing when NOT to act is a core financial capability.**

---

# 2. Problem Definition

## 2.1 The Problem

Payment failures are often not binary.

The real world contains states such as:

```text
Provider: CAPTURED
Merchant: UNPAID

Provider: PROCESSING
Merchant: TIMEOUT

Provider: REFUNDED
Merchant: REFUND UNKNOWN

Webhook: RECEIVED
Merchant DB: EVENT MISSING

Webhook: DUPLICATE
Merchant: PROCESSED TWICE

Provider: SUCCESS
Internal operation: UNKNOWN
```

These contradictions create operational uncertainty.

The merchant must determine:

1. What actually happened?
2. Which system's observation is relevant?
3. Is the apparent failure a real financial failure or a state synchronization failure?
4. What evidence supports the explanation?
5. Is the proposed recovery safe?
6. Could recovery itself create another financial error?
7. Can the result be independently verified?

---

# 3. Core Product Thesis

> **When money enters an uncertain or contradictory state, determine what actually happened, verify the explanation using financial evidence, and—when it is safe—take the correct recovery action. Otherwise, escalate with the exact reason and evidence required.**

The product is therefore not simply:

```text
AI reconciliation
```

and not simply:

```textpayment retry automation
```

It is:

```text
Financial Control & Recovery
```

---

# 4. Product Goal

The goal of V0 is to demonstrate a trustworthy financial control loop capable of:

```text
Detect
  ↓
Reconstruct
  ↓
Investigate
  ↓
Verify
  ↓
Decide
  ↓
Recover / Resolve / Escalate
  ↓
Verify Outcome
```

The product must reduce unnecessary human investigation while ensuring that uncertainty never silently becomes an unsafe financial action.

---

# 5. Target User

## Primary User

A merchant/payment operations engineer or finance/operations operator responsible for investigating payment exceptions.

Typical responsibilities include:

- investigating failed or ambiguous payments
- reconciling provider and merchant state
- determining whether customers were charged
- resolving stale orders
- handling refunds
- identifying duplicate operations
- investigating webhook failures
- deciding whether to retry or wait
- providing evidence during financial audits

The system acts as a **financial investigation and control layer**, not as a replacement for the merchant's entire payment infrastructure.

---

# 6. Jobs To Be Done

When a payment-related incident occurs, the operator should be able to ask:

### What happened?

The system reconstructs the event using available evidence.

### Why did it happen?

The system identifies and evaluates plausible explanations.

### Can we prove that explanation?

The system verifies claims against deterministic evidence.

### What should we do?

The system determines the safest available resolution.

### Can we safely automate it?

The system evaluates authorization, state freshness, invariants, and idempotency.

### Did the action actually work?

The system independently verifies the resulting state.

### If automation is unsafe, what should a human do?

The system produces an escalation with the evidence, uncertainty, and required next step.

---

# 7. Product Principles

## 7.1 Evidence Before Action

No consequential action should be based solely on inference.

---

## 7.2 AI Assists; Deterministic Systems Control

AI is responsible for reasoning over evidence.

Deterministic systems are responsible for:

- financial identity
- amounts
- state
- invariants
- authorization
- policy
- idempotency
- action gating
- outcome verification

---

## 7.3 Unknown Is a Valid State

The system must explicitly represent uncertainty.

```text
UNKNOWN ≠ FAILED
UNKNOWN ≠ SUCCESS
```

Unknown states must not be silently converted into assumptions.

---

## 7.4 Minimum Safe Action

When multiple actions could resolve an incident, prefer the smallest action that restores consistency without creating unnecessary financial risk.

Example:

```text
Captured payment + stale merchant state
```

does not require another payment.

The correct recovery may be:

```text
repair merchant state
```

---

## 7.5 Abstention Is Success

If evidence is insufficient or contradictory, refusing to act is correct behavior.

The product must optimize for:

> **safe resolution, not maximum automation.**

---

## 7.6 Every Action Has an Outcome

An action is not complete because an API request returned successfully.

The resulting financial state must be independently observed and verified.

---

# 8. Core Product Loop

```text
┌─────────────────────┐
│       OBSERVE       │
│ Provider + Merchant │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│     RECONSTRUCT     │
│ Canonical financial │
│       state         │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│    INVESTIGATE      │
│ Hypotheses +        │
│ missing evidence    │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│       VERIFY        │
│ Deterministic       │
│ evidence checks     │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│       DECIDE        │
│ Resolve / Recover / │
│ Escalate / Block    │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│        ACT          │
│ Controlled action   │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│   VERIFY OUTCOME    │
│ Independent state   │
│ confirmation        │
└─────────────────────┘
```

---

# 9. V0 Scope

V0 is deliberately narrow.

## 9.1 Provider

Razorpay only.

## 9.2 Environment

Razorpay Test Mode only.

No real-money execution is permitted.

## 9.3 Merchant Model

Single merchant/demo environment.

Multi-tenant product infrastructure is not a V0 requirement.

## 9.4 Financial Objects

V0 primarily operates on:

- Orders
- Payments
- Refunds

## 9.5 Operational Objects

V0 includes:

- Evidence
- Incidents
- Investigation
- Verification
- Actions
- Action outcomes

---

# 10. Primary Hero Incident

## Captured Payment + Stale Merchant State

### Initial condition

```text
Razorpay:
Payment = CAPTURED

Merchant:
Order = UNPAID
```

### Potential underlying causes

Examples include:

- webhook delivery failure
- webhook processing failure
- stale merchant state
- event processing race
- delayed synchronization
- incorrect association between payment and order

The system must not assume the cause before investigating.

---

# 11. Hero Incident Requirements

The system must:

1. Observe the provider payment state.
2. Observe the merchant order state.
3. Identify the inconsistency.
4. Create an incident.
5. Gather relevant evidence.
6. Generate plausible explanations.
7. Identify evidence required to distinguish those explanations.
8. Verify claims deterministically.
9. Determine whether the payment was actually captured.
10. Determine whether another monetary action is required.
11. Prefer state repair when the money movement already succeeded.
12. Execute the safe corrective action when authorized.
13. Re-observe the relevant state.
14. Verify that the merchant state is now consistent.
15. Close the incident only after verification.

---

# 12. Expected Hero Incident Outcome

Example:

```text
Payment
₹5,000
CAPTURED

Merchant Order
₹5,000
UNPAID
```

Evidence:

```text
✓ payment exists
✓ payment belongs to order
✓ payment amount matches
✓ payment captured
✓ capture timestamp available
✓ relevant webhook exists
✗ merchant state updated
```

Verified conclusion:

```text
Payment succeeded.
Merchant state is stale.
```

Recovery:

```text
Repair merchant state.
```

Outcome:

```text
Merchant Order = PAID
Payment = CAPTURED
```

Incident:

```text
RESOLVED
```

---

# 13. Secondary Incident

## Refund With Uncertain Provider Outcome

### Scenario

A refund request is initiated.

The provider request times out or the response becomes unavailable.

The system cannot determine immediately whether the refund succeeded.

### Required behavior

The system must represent:

```text
Refund outcome = UNKNOWN
```

It must not interpret the timeout as:

```text
refund failed
```

or:

```text
refund succeeded
```

The system must independently query/observe provider state before deciding whether another action is required.

If retry is necessary, the retry must preserve action identity and provider idempotency.

---

# 14. Failure Classes V0 Must Understand

V0 should explicitly test and handle the following classes.

## Provider-state discrepancy

Provider and merchant disagree.

## Duplicate event

The same provider event is delivered more than once.

## Out-of-order event

Events arrive in an order different from their logical occurrence.

## Missing event

A state-changing event is not observed by the merchant.

## Delayed event

A valid event arrives significantly later than expected.

## Invalid webhook

Webhook authenticity fails verification.

## Identity mismatch

Evidence refers to a different financial entity.

## Amount mismatch

Amounts do not satisfy expected financial relationships.

## Unknown provider outcome

An external operation's final state cannot immediately be determined.

## Duplicate action risk

A retry could create a second monetary effect.

## Stale authorization

The state used to approve an action has changed before execution.

## Contradictory evidence

Two trusted observations cannot currently be reconciled.

---

# 15. Incident Lifecycle

Conceptually:

```text
DETECTED
   ↓
INVESTIGATING
   ↓
EVIDENCE GATHERED
   ↓
VERIFICATION
   ↓
┌────────────┬──────────────┬───────────────┐
│ VERIFIED   │  UNCERTAIN   │ CONTRADICTED │
└─────┬──────┴──────┬───────┴───────┬───────┘
      ↓             ↓               ↓
  RESOLUTION     ESCALATE       ESCALATE /
   DECISION                      BLOCK
      ↓
 ACTION / RESOLUTION
      ↓
OUTCOME VERIFICATION
      ↓
RESOLVED / RECOVERED / ESCALATED / BLOCKED
```

Exact implementation states may evolve without changing the product semantics.

---

# 16. Evidence Requirements

Every important conclusion must be traceable to evidence.

Evidence should identify:

- source
- source entity
- observation
- observation timestamp
- ingestion timestamp
- provenance
- raw provider information where applicable
- relationship to the incident

The product must distinguish:

```text
Evidence
Claim
Hypothesis
Verified conclusion
```

These are not interchangeable.

---

# 17. Investigation Requirements

Investigation begins with known evidence.

The system should:

1. Identify the discrepancy.
2. Enumerate plausible explanations.
3. Identify what evidence would support or reject each explanation.
4. Retrieve relevant evidence.
5. Evaluate the explanations.
6. produce a verified or unresolved conclusion.

The investigation must not become an uncontrolled autonomous agent.

The system owns the investigation workflow.

---

# 18. AI Requirements

AI should be used where reasoning over heterogeneous evidence is difficult.

AI may:

- generate hypotheses
- correlate evidence
- identify missing evidence
- propose investigation steps
- summarize verified findings
- explain why a hypothesis was accepted or rejected

AI must not:

- establish financial identity
- determine monetary amounts
- define canonical financial truth
- bypass verification
- bypass authorization
- bypass policy
- directly execute uncontrolled financial mutations
- convert uncertainty into certainty through confidence scores

---

# 19. Deterministic Verification

Critical financial conclusions must be verified using deterministic rules.

Examples:

```text
Payment identity matches expected Order
Payment amount matches expected amount
Payment status is actually captured
Refund amount does not exceed refundable amount
Action target matches verified entity
Authorization corresponds to current state
Action identity has not already been executed
```

AI-generated reasoning is therefore an input to verification, not a substitute for it.

---

# 20. Decision Outcomes

Every incident must result in an explicit decision.

## RESOLVE

Existing state can be safely corrected.

## RECOVER

A controlled action is required and can be safely executed.

## BLOCK

A proposed action violates a safety rule or invariant.

## ESCALATE

Evidence is insufficient, contradictory, stale, or outside autonomous authority.

The system must not force every incident into an automated resolution.

---

# 21. Recovery Requirements

Recovery must distinguish between:

### Operational recovery

Examples:

- repair merchant state
- replay processing
- surface missing evidence

and:

### Monetary recovery

Examples:

- refund
- other provider-supported financial correction

A monetary action requires a higher safety threshold than an operational state repair.

---

# 22. Monetary Action Safety

Before executing a consequential financial action, the system must establish:

```text
Target identity
      ↓
Current state
      ↓
Required evidence
      ↓
Invariant checks
      ↓
Policy eligibility
      ↓
Authorization
      ↓
State freshness
      ↓
Concurrency protection
      ↓
Idempotency
      ↓
Execution
      ↓
Outcome verification
```

Any failed condition must prevent autonomous execution.

---

# 23. Idempotency Requirement

A repeated operation must not create an unintended duplicate financial effect.

The system must account for:

- duplicate webhook delivery
- worker retry
- API retry
- network timeout
- provider response loss
- concurrent workers

For monetary actions, action identity and provider-supported idempotency mechanisms must be preserved where applicable.

---

# 24. Outcome Verification

After an action:

```text
ACTION REQUEST
      ↓
PROVIDER RESPONSE
      ↓
INDEPENDENT OBSERVATION
      ↓
STATE VERIFICATION
      ↓
FINAL OUTCOME
```

The provider's immediate response is evidence, not necessarily the final truth.

If the resulting state cannot be established:

```text
Outcome = UNKNOWN
```

The system must not falsely report success.

---

# 25. Human-in-the-Loop

Humans remain the authority for cases outside deterministic safety boundaries.

Escalation must contain:

- incident summary
- financial entities involved
- verified evidence
- unresolved evidence
- hypotheses considered
- hypotheses rejected
- reason automation was blocked
- recommended next investigation step
- required human action

The goal is not simply:

```text
"Needs human review."
```

It is:

> **Give the human the exact evidence required to make the remaining decision.**

---

# 26. Operator Experience

The primary interface should allow an operator to:

1. View active incidents.
2. Understand why an incident exists.
3. Inspect the financial entities involved.
4. Inspect the evidence timeline.
5. See provider vs merchant state.
6. See investigation hypotheses.
7. See verification results.
8. See the proposed resolution.
9. Understand why an action is allowed or blocked.
10. Inspect action execution and outcome.
11. Understand why an incident was escalated.

---

# 27. Incident Detail View

A useful incident should visually communicate:

```text
INCIDENT
   ↓
WHAT WE OBSERVED
   ↓
WHAT DISAGREES
   ↓
WHAT COULD EXPLAIN IT
   ↓
WHAT THE EVIDENCE PROVES
   ↓
WHAT WE DECIDED
   ↓
WHAT WE DID
   ↓
WHAT HAPPENED AFTERWARD
```

The UI should expose reasoning and evidence rather than merely display an "AI answer."

---

# 28. Auditability Requirements

A reviewer must be able to reconstruct:

```text
What happened?
What evidence existed?
What did the system believe?
Why did it believe that?
What did the deterministic verifier establish?
Why was an action allowed?
What action was executed?
What was the resulting state?
```

Critical decisions must not depend solely on transient application logs.

---

# 29. Observability Requirements

At minimum, the system should make it possible to correlate:

```text
Provider Event
      ↓
Evidence
      ↓
State Change
      ↓
Incident
      ↓
Investigation
      ↓
Decision
      ↓
Action
      ↓
Outcome
```

Each meaningful operation should have sufficient identifiers to trace this chain.

---

# 30. Security Requirements

V0 must:

- protect provider credentials
- isolate Test Mode credentials
- validate webhook authenticity
- validate external inputs
- treat LLM output as untrusted
- enforce explicit action authorization
- prevent unauthorized financial actions
- avoid exposing secrets through logs
- maintain clear boundaries between observation and mutation

---

# 31. Evaluation Philosophy

The product must be evaluated primarily on **financial correctness and safety**, not on how impressive the AI response sounds.

The most important evaluation question is:

> **Did the system make the correct decision given the available evidence?**

---

# 32. Primary Evaluation Metrics

V0 should measure:

### Unsafe monetary actions

Target:

```text
0
```

### Correct discrepancy detection

Did the system identify the actual inconsistency?

### Correct resolution

Did the system select the appropriate resolution?

### Correct abstention

Did the system refuse to act when evidence was insufficient?

### Duplicate financial actions

Target:

```text
0
```

### Evidence-backed decisions

Can each consequential decision be traced to evidence?

### Outcome verification

Did the system independently establish the resulting state?

---

# 33. Adversarial Evaluation

The system must be deliberately tested against cases including:

```text
duplicate webhook
out-of-order webhook
missing webhook
delayed webhook
invalid signature
wrong payment ID
wrong order ID
amount mismatch
stale merchant state
provider timeout
lost action response
duplicate action attempt
concurrent action attempt
contradictory evidence
LLM hallucinated hypothesis
LLM unsafe recommendation
LLM unavailable
```

The purpose is not to make the AI appear intelligent.

The purpose is to prove the control system remains safe when components behave incorrectly.

---

# 34. Real-World Applicability

Although V0 uses a controlled Razorpay environment, the underlying problem must correspond to real payment-system failure modes.

The system should therefore model realistic conditions rather than fabricate simplistic demo errors.

The following principles must hold:

```text
Provider observation ≠ merchant state
API success ≠ final financial truth
Timeout ≠ failure
Captured payment ≠ paid merchant order
Unknown ≠ permission to retry
AI explanation ≠ verified fact
```

---

# 35. Razorpay Integration Role

Razorpay is the external financial system against which V0 observes and acts.

The product should use Razorpay capabilities where they provide real evidence or controlled actions.

Relevant capabilities include:

- order creation
- payment retrieval
- payment status observation
- webhook ingestion
- webhook authenticity verification
- refund operations
- provider-side status verification
- provider-supported idempotency mechanisms where applicable

The product must not pretend to have capabilities that the provider does not expose.

Actual provider behavior discovered during implementation supersedes assumptions in this document.

---

# 36. V0 Non-Goals

V0 will not attempt to build:

- multi-provider support
- full accounting/ERP reconciliation
- generic banking infrastructure
- live-money autonomous recovery
- autonomous payment retry across arbitrary providers
- full multi-tenant SaaS infrastructure
- distributed microservice architecture
- Kafka/RabbitMQ infrastructure
- Kubernetes
- generic vector-search RAG
- autonomous multi-agent orchestration
- generalized workflow marketplace
- predictive fraud detection
- complete financial ledger replacement
- enterprise reporting suite

These may be future opportunities, not V0 requirements.

---

# 37. Future Direction

If V0 proves the core thesis, the product could expand toward:

```text
Multiple Providers
      ↓
Multiple Merchant Systems
      ↓
Broader Financial Events
      ↓
Cross-System Financial Control
      ↓
Automated Recovery
      ↓
Continuous Financial Operations
```

Potential future domains include:

- payouts
- refunds
- settlements
- disputes
- subscription payments
- marketplace flows
- bank transfer reconciliation

None of these should influence V0 architecture unless a concrete V0 requirement demands it.

---

# 38. Product Risks

## False positive investigation

The system may create incidents where no meaningful discrepancy exists.

## False confidence

AI may produce a convincing but incorrect explanation.

## Stale evidence

A previously valid observation may no longer represent current state.

## Duplicate action

A retry may create a second financial effect.

## Incorrect identity association

Evidence from one transaction may be incorrectly attributed to another.

## Provider ambiguity

Provider APIs may not expose sufficient information to establish final state.

## Automation overreach

The system may attempt to resolve cases that require human authority.

The architecture and evaluation strategy must prioritize preventing unsafe consequences over maximizing automation rate.

---

# 39. Definition of Done

V0 is considered complete only when the following end-to-end flow works against Razorpay Test Mode:

```text
REAL TEST PAYMENT
      ↓
PROVIDER OBSERVATION
      ↓
EVIDENCE
      ↓
MERCHANT STATE
      ↓
DISCREPANCY DETECTION
      ↓
INCIDENT
      ↓
INVESTIGATION
      ↓
DETERMINISTIC VERIFICATION
      ↓
SAFE DECISION
      ↓
RECOVERY / RESOLUTION
      ↓
INDEPENDENT OUTCOME VERIFICATION
```

And the system can demonstrate at least one case where:

```text
AI recommends / hypothesizes incorrectly
                ↓
deterministic control rejects unsafe action
                ↓
financial system remains safe
```

It must also demonstrate a case where:

```text
external action becomes uncertain
                ↓
system does NOT blindly retry
                ↓
provider state is independently checked
                ↓
duplicate financial effect is prevented
```

---

# 40. Final Product Standard

The product should not be judged by:

- number of technologies used
- number of agents
- number of endpoints
- amount of generated code
- UI complexity
- AI verbosity

It should be judged by:

```text
Can it correctly determine what happened?

Can it prove why?

Can it safely decide what to do?

Can it refuse when it cannot prove enough?

Can it recover without creating another financial error?

Can it verify the result?

Can a human audit the entire chain?
```

The governing product question is:

> **Could this system be trusted to control a financial operation if it were connected to real money?**

V0 does not execute against real money.

It must nevertheless be engineered as though its control decisions matter.