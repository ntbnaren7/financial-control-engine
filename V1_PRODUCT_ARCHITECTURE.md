# V1 Product Architecture

**Role:** Skeptical principal engineer + product architect  
**Date:** 2026-09-01  
**Read-only design document. No code changes.**  
**Governing constraint:** Every component must answer YES to:  
> *"Could this architecture survive being connected to real money?"*

---

## Preamble — What This Document Is

This document specifies the **architectural contract** for transitioning the frozen V0 control kernel into the complete Financial Control & Recovery product originally specified in the PRD.

It is not an implementation plan. It is not a backlog. It is the domain model, safety invariants, and component boundaries that must be agreed on before any V1 code is written.

---

## 1. Canonical Financial Domain Model

### Classification

| Component | Classification |
|---|---|
| Payment, Refund, Order, ProviderObservation | REQUIRED BY ORIGINAL PRODUCT |
| FinancialEvent, EvidenceRecord | REQUIRED BY ORIGINAL PRODUCT |
| Subscription, Payout | OPTIONAL FUTURE (§37 "Future Direction" only — not in V0 PRD requirements) |
| Checkout | NOT JUSTIFIED (not in original PRD domain model at all) |

### Core entities and relationships

```
Order
  ├── merchant_order_id   (internal PK)
  ├── provider_order_id   (Razorpay ID — deterministic identity)
  ├── amount              (integer, minor units)
  ├── currency            (explicit)
  ├── lifecycle_state     (see §2)
  └── ── Payment (1..N)
              ├── payment_id          (internal PK)
              ├── provider_payment_id (Razorpay ID — deterministic identity)
              ├── order_id            (FK → Order)
              ├── amount              (integer, minor units)
              ├── currency            (explicit)
              ├── provider_state      (from provider observation)
              ├── processing_state    (UNKNOWN / PROCESSING / SUCCESS / FAILED)
              ├── captured            (bool, from provider)
              └── ── Refund (0..N)
                          ├── refund_id           (internal PK)
                          ├── provider_refund_id  (nullable — may be unknown pre-confirmation)
                          ├── payment_id          (FK → Payment)
                          ├── amount              (integer, minor units)
                          ├── idempotency_key     (deterministic, stable)
                          ├── provider_state      (UNKNOWN / PROCESSING / REFUNDED / FAILED)
                          └── outcome_verified    (bool)
```

**Identity rule (must not change from V0):** Financial identity is established exclusively through provider-issued IDs (`provider_payment_id`, `provider_order_id`). Never through amount, timestamp, customer text, embeddings, or AI judgment.

---

## 2. Financial State Model

The V0 system conflates multiple distinct state concepts into `MerchantOrder.status`. V1 must separate them.

### State taxonomy

```
ProviderState       — What the provider API reports
MerchantState       — What the merchant's internal system records
ProcessingState     — Whether a financial event was processed
OutcomeState        — The verified result of an action
EpistemicState      — What the system knows vs. what it doesn't know
```

### UNKNOWN is a first-class state

This is the most important addition from the audit. `UNKNOWN` must not collapse into `FAILED` or `SUCCESS`.

```
OutcomeState:
  SUCCESS       — Provider confirmed, independently verified
  FAILED        — Provider confirmed failure, independently verified
  PROCESSING    — In-flight, provider not yet final
  UNKNOWN       — Cannot determine. System has not yet queried provider.
  TIMED_OUT     — Query window exceeded. Still not FAILED.
```

### V0 → V1 state mapping

| V0 MerchantOrder.status | V1 equivalent |
|---|---|
| `UNPAID` | `MerchantState.UNPAID` |
| `PAID` | `MerchantState.PAID` |
| (no UNKNOWN) | `OutcomeState.UNKNOWN` — NEW |
| (no PROCESSING) | `OutcomeState.PROCESSING` — NEW |

### State transition rule

All state transitions must be deterministic. The system must never:
- silently convert `UNKNOWN` to `FAILED`
- infer `SUCCESS` from timeout expiry
- allow AI to establish financial state

---

## 3. Incident Domain

### 3.1 Why Incident must be a persistent entity

Without a persistent `Incident` database record, the following are impossible:
- operator visibility into active cases
- reopening a case after new evidence arrives
- attaching escalation packets to a work unit
- durably tracking actions against a case
- audit trail spanning multiple pipeline executions

### 3.2 Incident entity

```
Incident
  ├── incident_id        (UUID PK)
  ├── created_at
  ├── updated_at
  ├── lifecycle_state    (see §3.3)
  ├── discrepancy_class  (from M3 classification)
  ├── discrepancy_description
  ├── payment_id         (FK → Payment, nullable)
  ├── order_id           (FK → Order, nullable)
  ├── refund_id          (FK → Refund, nullable)
  ├── investigation_id   (FK → Investigation, nullable)
  ├── action_id          (FK → Action, nullable — latest authorized action)
  ├── escalation_id      (FK → Escalation, nullable)
  └── outcome            (RESOLVED / RECOVERED / ESCALATED / BLOCKED / OPEN)
```

### 3.3 Incident lifecycle state machine

```
DETECTED
   ↓
INVESTIGATING
   ↓
┌──────────────┬──────────────┬───────────────────┐
│  VERIFIED    │  UNCERTAIN   │  CONTRADICTED     │
└──────┬───────┴──────┬───────┴────────┬──────────┘
       ↓              ↓                ↓
RESOLUTION_DECISION  ESCALATE     ESCALATE / BLOCK
       ↓
ACTION_PENDING
       ↓
ACTION_EXECUTED
       ↓
OUTCOME_VERIFICATION
       ↓
┌──────────────────┬─────────────────┐
│    RESOLVED      │    FAILED       │
│    RECOVERED     │   (reopen?)     │
│    ESCALATED     │                 │
│    BLOCKED       │                 │
└──────────────────┴─────────────────┘
```

**Terminal states:** RESOLVED, RECOVERED, ESCALATED, BLOCKED.  
**Reopen rule:** A terminal incident may be reopened only if new provider evidence arrives that contradicts the terminal outcome. This requires an explicit `REOPEN` event with provenance.

---

## 4. Action Domain

### 4.1 Why Action must be a persistent entity

The audit identified that V0 returns action results as in-memory dicts. If the worker crashes mid-execution, the action is lost. V1 must not allow this for any financial operation.

### 4.2 Action entity

```
Action
  ├── action_id            (UUID PK)
  ├── incident_id          (FK → Incident)
  ├── action_type          (enum — see §4.3)
  ├── idempotency_key      (stable, deterministic — survives crash/restart)
  ├── authorization_provenance_id (FK → AuthorizationProvenance)
  ├── requested_at
  ├── executed_at          (nullable)
  ├── provider_reference   (nullable — provider's action ID, e.g. Razorpay refund_id)
  ├── execution_state      (PENDING / IN_FLIGHT / COMPLETED / FAILED / UNKNOWN)
  ├── outcome_verified     (bool)
  └── verification_result  (RESOLVED / VERIFICATION_FAILED / UNKNOWN / ERROR)
```

### 4.3 Action types

```
ActionType (enum):
  STATE_REPAIR          — Non-monetary; update internal state
  EVENT_REPROCESS       — Replay a previously ingested event through processing
  CONTROLLED_REFUND     — Monetary; initiate refund via provider API
  PROVIDER_STATUS_QUERY — Read-only; re-query provider for current state
  PAYMENT_RETRY         — Monetary; initiate retry (future — requires separate policy)
  ESCALATE              — Non-monetary; produce structured escalation packet
  WAIT                  — Non-action; set MONITOR state on incident
```

**PAYMENT_RETRY** is listed here for completeness but is `NOT_YET_DESIGNED` — it requires separate policy design covering retry limits, authorization conditions, and customer notification, none of which exist in the original V0 PRD.

### 4.4 Idempotency key construction

```
idempotency_key = sha256(incident_id + action_type + target_entity_id + authorization_provenance_id)
```

This key is stable across crash/restart. It must be passed as the provider idempotency header for any monetary action.

---

## 5. Escalation Domain

This is the most structurally significant addition from the gap audit. Escalation must become a real domain object, not a log string.

### 5.1 Escalation entity (all 9 PRD §25 fields)

```
Escalation
  ├── escalation_id
  ├── incident_id                (FK)
  ├── created_at
  ├── summary                    (§25 field 1 — incident description)
  ├── financial_entities         (§25 field 2 — Payment/Order/Refund IDs + current states)
  ├── verified_evidence          (§25 field 3 — evidence items that passed deterministic checks)
  ├── unresolved_evidence        (§25 field 4 — missing evidence types with epistemic limitation)
  ├── hypotheses_considered      (§25 field 5 — all hypothesis selections with rank/rationale)
  ├── hypotheses_rejected        (§25 field 6 — hypotheses with rejection reason)
  ├── automation_block_reason    (§25 field 7 — exact control plane rejection reason)
  ├── recommended_next_step      (§25 field 8 — derived from top EVIDENCE_INSUFFICIENT reason)
  └── required_human_action      (§25 field 9 — explicit instruction to operator)
```

### 5.2 Escalation production rule

An escalation is produced when the control plane emits `NO_ACTION`. The current `_reject()` function in `policy.py` must be extended to populate all 9 fields and persist an `Escalation` record.

The escalation must be operator-accessible via API. A log event is not sufficient.

### 5.3 What V0 already provides toward escalation

`AuthorizationProvenance` already contains field 7 (`automation_block_reason`) and a subset of field 3 (`verified_facts`). These are the kernel of the escalation — they are correct and must not be changed. The V1 escalation extends around them.

---

## 6. Evidence Model

The V0 evidence model (`EvidenceItem`, `EvidenceDefinition`, `HypothesisDefinition`, `EvidenceCoverage`) is well-designed and must remain intact.

### What V1 extends

**Evidence freshness.** The audit identified that evidence is gathered once at investigation time and not re-verified before action execution. V1 must add a `gathered_at` timestamp to the `EvidencePacket` and the control plane must check freshness before emitting `ALLOW_REPAIR`. If evidence is stale (configurable threshold), the incident must be re-investigated.

**Contradictory evidence.** Currently, contradictory evidence causes the hypothesis rank to be poorly scored but produces no explicit contradictory evidence classification. V1 should produce an explicit `CONTRADICTED` incident state when two trusted observations cannot currently be reconciled.

**Evidence lifetime.** Raw `ProviderObservation` records are already immutable. That must not change. Derived `EvidenceItem` structures are ephemeral per-investigation. That is correct — they should not be persisted as a separate table.

### Evidence model invariant

```
Evidence (observed fact) ≠ Claim (derived statement) ≠ Hypothesis (proposed explanation) ≠ Verified conclusion
```

This distinction, already present in `EVIDENCE_DEFINITIONS` and `HYPOTHESIS_DEFINITIONS`, must be preserved in all V1 extensions.

---

## 7. Reconciliation / State Engine (M3 Extension)

### What must not change

The classifier logic in `src/reconciliation/classifier.py` is deterministic, pure, and tested. It must not be touched. Specifically:
- Pure function with no side effects
- Returns explicit classification with all sub-checks (identity, amount, currency, state)
- Fails closed on unknown merchant states

### What V1 extends

**New discrepancy classes required by the corpus:**

```python
class DiscrepancyClassification(str, Enum):
    # V0 — frozen, do not change
    CONSISTENT                          = "CONSISTENT"
    CAPTURED_PAYMENT_STALE_ORDER        = "CAPTURED_PAYMENT_STALE_ORDER"
    CAPTURED_PAYMENT_AMOUNT_MISMATCH    = "CAPTURED_PAYMENT_AMOUNT_MISMATCH"
    CAPTURED_PAYMENT_CURRENCY_MISMATCH  = "CAPTURED_PAYMENT_CURRENCY_MISMATCH"
    PAYMENT_ORDER_IDENTITY_UNKNOWN      = "PAYMENT_ORDER_IDENTITY_UNKNOWN"
    PAYMENT_NOT_CAPTURED                = "PAYMENT_NOT_CAPTURED"

    # V1 — new, per PRD §14
    UNKNOWN_PROVIDER_OUTCOME            = "UNKNOWN_PROVIDER_OUTCOME"   # §13, §14
    OUT_OF_ORDER_EVENT                  = "OUT_OF_ORDER_EVENT"         # §14
    DELAYED_EVENT                       = "DELAYED_EVENT"              # §14
    MISSING_EVENT                       = "MISSING_EVENT"              # §14
    CONTRADICTORY_EVIDENCE              = "CONTRADICTORY_EVIDENCE"     # §14
```

**Canonical state reconstruction.** The pipeline's current inline payload extraction (`pipeline.py` L45-88) should be replaced by a proper `StateEngine` layer that:
- receives raw `ProviderObservation` records
- constructs typed `ProviderPayment` / `ProviderOrder` observations
- applies temporal ordering (handles out-of-order events)
- produces `ReconciliationInput` for M3

This is the `src/state/` layer that V0 left empty.

---

## 8. Investigation Engine (M4)

### What must not change

The M4 architecture is correct:
- AI receives a bounded `EvidencePacket` (not raw DB access)
- AI produces a schema-validated `InvestigationProposal` (not free-form text)
- Semantic validator (`validator.py`) gates on hallucinated evidence IDs, cardinality, rank uniqueness
- `HYPOTHESIS_DEFINITIONS` and `EVIDENCE_DEFINITIONS` are the single source of truth
- AI has zero database connections

**None of this changes.**

### What V1 extends

**Hypothesis vocabulary.** The current `V0HypothesisType` vocabulary is narrow and specific to the stale-order case. V1 must introduce hypothesis vocabularies per discrepancy class. Each vocabulary must be formally defined in the same `HYPOTHESIS_DEFINITIONS` pattern before being used with M4.

```
V0HypothesisType        → StaleOrderHypothesisType (rename, keep frozen)
                        + RefundUncertaintyHypothesisType (new, for secondary incident)
                        + GeneralHypothesisType (future, for expanded M3 classes)
```

**Provider re-query for UNKNOWN outcome.** For the secondary incident (`UNKNOWN_PROVIDER_OUTCOME`), M4 must be able to signal that provider re-query is required. This signal goes to the control plane, which decides whether re-query is safe and authorized. M4 does not execute the re-query.

---

## 9. Deterministic Control Kernel — Frozen Components

The following V0 components are frozen and must not be redesigned:

| Component | File | Frozen guarantee |
|---|---|---|
| Semantic validator | `src/investigation/validator.py` | Evidence ID admissibility check |
| Control policy (stale-order case) | `src/control/policy.py` | 8 sequential gates for ALLOW_REPAIR |
| Atomic repair action | `src/recovery/action.py` | `UPDATE WHERE status='UNPAID'` predicate |
| Authorization provenance | `src/control/provenance.py` | Immutable record of what authorized the action |
| Audit event emission | `src/control/audit.py` | Structured audit log per stage |
| M3 classifier | `src/reconciliation/classifier.py` | Pure deterministic classification function |

**The V1 control plane extends by adding new policy functions** for new action types. It does not modify existing policy functions.

### Control plane extension pattern

```
evaluate_repair_eligibility()           ← V0 frozen
evaluate_refund_eligibility()           ← V1 new (secondary incident)
evaluate_event_reprocess_eligibility()  ← V1 new
evaluate_provider_requery_eligibility() ← V1 new (UNKNOWN outcome handling)
```

Each policy function:
- receives `(discrepancy, investigation_result, evidence, relevant_entities)`
- returns `ControlDecision(decision, reason, provenance)`
- is a deterministic pure function
- has no LLM dependencies
- has no external side effects

---

## 10. Recovery Engine — Safety Contract Per Action

Each action type must satisfy a formal safety contract before it can be authorized.

### STATE_REPAIR safety contract (V0 frozen)
```
Required evidence:   payment_captured=True, webhook_exists=True, processing_processed=True, transition_coverage=COMPLETE
Forbidden when:      merchant_state != UNPAID
Monetary risk:       NONE (internal state only)
Idempotency:         SQL atomic predicate (rowcount check)
Verification:        Independent DB read confirming new state
```

### PROVIDER_STATUS_QUERY safety contract (new, read-only)
```
Required evidence:   provider_payment_id or provider_refund_id verified
Forbidden when:      NEVER (read-only operation, cannot cause duplicate financial effect)
Monetary risk:       NONE
Idempotency:         Inherently idempotent (read)
Verification:        Response must be persisted as new ProviderObservation
```

### CONTROLLED_REFUND safety contract (new, monetary)
```
Required evidence:   payment_captured=True, refund_not_already_issued=True, 
                     amount <= refundable_amount, currency_match=True
Forbidden when:      refund already exists for this payment+amount+idempotency_key
                     OR provider_refund_state == REFUNDED
                     OR OutcomeState == UNKNOWN (must resolve UNKNOWN first)
Monetary risk:       HIGH — requires higher evidence threshold than STATE_REPAIR
Idempotency:         Provider-side idempotency key (Razorpay idempotency header)
                     + internal action idempotency_key uniqueness check
Verification:        Provider re-query confirming REFUNDED state + independent DB verification
```

### WAIT / MONITOR (new, non-action)
```
Purpose:             Set incident to MONITORING state pending provider resolution
Required evidence:   OutcomeState == UNKNOWN or PROCESSING
Forbidden when:      OutcomeState is terminal (SUCCESS or FAILED)
Monetary risk:       NONE (no action taken)
Timeout policy:      Must define maximum wait duration; escalate on timeout
```

**PAYMENT_RETRY** is not yet designed. It requires a separate safety contract covering: retry eligibility per payment type, customer notification semantics, maximum retry count, idempotency across provider retry APIs, and authorization conditions. Do not implement it as part of V1 without a full contract.

---

## 11. Refund Uncertainty Flow (Secondary Incident)

This is the most important dropped V0 requirement (PRD §13).

### The dangerous epistemic condition

```
REFUND REQUEST SENT
       ↓
NETWORK TIMEOUT / PROVIDER RESPONSE LOST
       ↓
  OutcomeState = UNKNOWN

  UNKNOWN ≠ FAILED
  UNKNOWN ≠ REFUNDED
  UNKNOWN = "The system cannot currently establish the final state."
```

### Required resolution flow

```
OutcomeState = UNKNOWN
       ↓
1. Create Incident (UNKNOWN_PROVIDER_OUTCOME class)
       ↓
2. M3 classifies as UNKNOWN_PROVIDER_OUTCOME
       ↓
3. M4 investigates:
   - What do we know about the refund request?
   - Do we have provider idempotency evidence?
   - How long has the state been UNKNOWN?
       ↓
4. Control plane evaluates PROVIDER_STATUS_QUERY eligibility
       ↓
5. Execute read-only provider re-query (PROVIDER_STATUS_QUERY action)
       ↓
6. Persist new ProviderObservation from re-query response
       ↓
7. Re-run M3 on updated observation
       ↓
┌──────────────────────────────────────────────────┐
│ Provider says REFUNDED                           │
│   → OutcomeState = SUCCESS                       │
│   → Verify internally                            │
│   → Close incident: RESOLVED                    │
├──────────────────────────────────────────────────┤
│ Provider says NOT_REFUNDED / FAILED              │
│   → OutcomeState = FAILED                        │
│   → Evaluate CONTROLLED_REFUND eligibility       │
│   → If eligible: issue refund with idempotency   │
│   → If not eligible: ESCALATE                   │
├──────────────────────────────────────────────────┤
│ Provider still PROCESSING or UNKNOWN             │
│   → OutcomeState = PROCESSING                    │
│   → WAIT with configured timeout                 │
│   → On timeout: ESCALATE                        │
└──────────────────────────────────────────────────┘
```

### The critical invariant for this flow

```
DO NOT ISSUE REFUND WHILE OUTCOME IS UNKNOWN.
```

Issuing a refund while the provider may have already processed the original refund creates a double-refund. The system must establish `NOT_REFUNDED` deterministically before a retry is authorized.

---

## 12. Event / Job Architecture

### V0 gap identified

V0 uses FastAPI `BackgroundTasks` which is not durable. A worker crash between webhook ingestion and investigation means the investigation is lost silently.

### V1 required architecture

```
Webhook arrives
       ↓
1. Signature verified (stays synchronous — must validate before any persistence)
       ↓
2. ProviderObservation persisted  ──┐
3. InvestigationJob created         │  (single DB transaction — transactional outbox)
       ↓                            │
HTTP 200 OK                         │
                                    ▼
                           Worker polls InvestigationJob table
                                    ↓
                           Runs investigation pipeline
                                    ↓
                           Updates Incident lifecycle state
```

**Outbox table:**
```
InvestigationJob
  ├── job_id
  ├── observation_id    (FK → ProviderObservation)
  ├── created_at
  ├── status            (PENDING / IN_FLIGHT / COMPLETED / FAILED)
  ├── attempts
  ├── last_attempted_at
  └── completed_at
```

**Why PostgreSQL outbox rather than a message broker:** 02-arch §9 and §16 are explicit — do not introduce infrastructure without demonstrated requirement. The transactional outbox satisfies durability with no additional infrastructure. Move to a broker only if poll latency or throughput becomes a demonstrated problem.

### Scheduled sweeps (required for UNKNOWN state handling)

```
Every configurable interval N:
  - Find all incidents with OutcomeState = UNKNOWN older than threshold
  - Issue PROVIDER_STATUS_QUERY for each
  - Find all WAIT/MONITOR incidents past timeout
  - Escalate those that have exceeded maximum wait duration
```

---

## 13. Operator Product — API Boundary

The operator surface (§26–27 PRD) requires these API endpoints. No implementation detail — only the boundary.

```
GET  /api/incidents                    — list active incidents, filterable by state/class
GET  /api/incidents/{id}               — full incident detail
GET  /api/incidents/{id}/evidence      — evidence timeline for incident
GET  /api/incidents/{id}/investigation — hypotheses, rankings, rationale
GET  /api/incidents/{id}/actions       — action history with provenance
GET  /api/incidents/{id}/escalation    — structured escalation packet if escalated
GET  /api/escalations                  — all open escalations
GET  /api/audit/{incident_id}          — full audit trail for incident
```

All endpoints are **read-only for operators**. No operator-initiated action endpoints in V1. The product resolves autonomously or escalates. An operator reading an escalation is the product outcome.

---

## 14. Future Revenue Recovery Layer

This belongs to §37 "Future Direction" of the PRD, not V1. Included here to establish the boundary.

**Correct dependency:** Revenue recovery requires historical outcome data. You cannot compute recovery probability without a history of: which interventions succeeded, on which discrepancy classes, under which evidence conditions. That data does not exist yet.

**Premature implementation risk:** Building a revenue recovery prioritization model before incident outcome data exists will produce a model trained on synthetic assumptions. That is worse than no model.

**The correct sequence:**
```
V1 incident + action + outcome data accumulates
       ↓
V2 — retrospective analysis of outcomes
       ↓
V3 — recovery prioritization based on real outcome data
```

---

## 15. Learning Loop

Last. Same reasoning as §14.

**The invariant that must never be violated:**

```
Learning may influence investigation RECOMMENDATIONS.
Learning must NEVER influence financial authorization decisions.
```

Authorization must remain deterministic regardless of what the learning model predicts. A model that has learned "refunds usually succeed for this merchant" cannot relax the `NOT_REFUNDED` pre-condition check on `CONTROLLED_REFUND`.

---

## 16. V0 → V1 Migration Boundary

| V0 component | V1 treatment |
|---|---|
| `src/reconciliation/classifier.py` | FROZEN. No changes. |
| `src/reconciliation/models.py` | EXTEND with new DiscrepancyClassification values only. |
| `src/reconciliation/engine.py` | EXTEND to handle new classes. Existing logic untouched. |
| `src/investigation/models.py` | EXTEND with new hypothesis vocabularies. V0 vocabulary frozen. |
| `src/investigation/validator.py` | EXTEND to support new hypothesis vocabulary per discrepancy class. |
| `src/investigation/ai.py` | EXTEND with new system prompts per discrepancy class. |
| `src/control/policy.py` | EXTEND with new policy functions. `evaluate_repair_eligibility()` frozen. |
| `src/control/provenance.py` | EXTEND to populate full escalation fields. |
| `src/control/audit.py` | EXTEND with new audit event types. |
| `src/recovery/action.py` | EXTEND with new action type executors. `execute_repair_action()` frozen. |
| `src/recovery/verifier.py` | EXTEND with new verification functions. |
| `src/evidence/gatherer.py` | EXTEND with freshness timestamp. Core gather logic unchanged. |
| `src/orchestration/pipeline.py` | REFACTOR into proper layer-based orchestration using Incident lifecycle. |
| `src/api/webhooks.py` | REFACTOR to use transactional outbox instead of BackgroundTasks. |
| `src/state/` | IMPLEMENT (currently empty). |
| `src/domain/incidents/` | IMPLEMENT (currently empty). |
| `src/domain/refunds/` | IMPLEMENT (currently empty). |
| `src/merchant/models.py` | EXTEND with richer state model. |
| `apps/` | IMPLEMENT Next.js operator frontend. |

---

## 17. V1 Non-Goals

The following are explicitly excluded from V1. They are not gaps — they are deliberate boundaries.

| Non-goal | Reason |
|---|---|
| PAYMENT_RETRY automation | Requires separate safety contract not in original corpus. |
| Subscription lifecycle | §37 Future Direction only; not in PRD domain model. |
| Payout uncertainty (general) | §37 Future Direction only. |
| Checkout abandonment recovery | Not in PRD at all. |
| Revenue recovery prioritization | Requires outcome history not yet collected. |
| Learning loop | Requires outcome history not yet collected. |
| Multi-tenant authorization | §36 Non-Goal. |
| Kafka / message broker | Use PostgreSQL outbox first. |
| Kubernetes / microservices | §36 Non-Goal. |
| Generic rules DSL | §36 Non-Goal + 00-constitution §103. |
| Multi-provider support | §36 Non-Goal. |
| Predictive fraud detection | §36 Non-Goal. |
| Financial ledger replacement | §36 Non-Goal. |
| Autonomous multi-agent orchestration | Violates AI boundary principle. |

---

## 18. Architecture Invariants — Non-Negotiable

These invariants survive V0, V1, and every subsequent version. They are the architectural constitution.

1. **AI has no financial authority.** AI outputs are advisory inputs to deterministic systems. An AI output alone cannot authorize, execute, or verify any financial action.

2. **Financial identity is deterministic.** Provider-issued IDs are the only admissible identity mechanism. Amount, timestamp, embedding similarity, or AI judgment may never establish financial identity.

3. **Monetary amounts are integer minor units.** Float arithmetic is prohibited on monetary values.

4. **UNKNOWN is a valid and explicit state.** The system must never silently convert UNKNOWN to FAILED or SUCCESS. UNKNOWN must trigger re-query or escalation, not action.

5. **Every consequential action has a pre-condition check.** Actions must verify that the state against which the decision was made is still the current state at execution time. Race conditions produce CONFLICT, not false success.

6. **Every action has an idempotency key.** Repeated delivery, crash/restart, or network uncertainty must never create a duplicate financial effect.

7. **Every action has independent verification.** An action is not complete because the API request returned 200. The resulting state must be independently read from the data layer.

8. **Raw provider evidence is immutable.** `ProviderObservation` records may never be modified or deleted. Derived state may be recalculated.

9. **Escalation is a product outcome, not a fallback.** When the system cannot safely act, it must produce an escalation containing everything the human needs to make the remaining decision. A log line is not an escalation.

10. **Actions are durably recorded before execution.** An `Action` record must be persisted before any provider API call. If the system crashes between persistence and execution, the recovery worker must detect the pending action and resume idempotently.

11. **The control plane is never bypassed.** No code path from AI output to financial mutation may skip policy evaluation, authorization provenance, or atomic precondition checking.

12. **Fail closed.** When the system cannot establish sufficient evidence, cannot determine safe action, or cannot verify an outcome, it must produce NO_ACTION or ESCALATE. It must not proceed on partial evidence.

---

## A. What V1 Adds

- Persistent Incident entity with full lifecycle state machine
- Persistent Action entity with idempotency identity
- Persistent Escalation entity with all 9 PRD §25 fields
- Secondary incident: refund uncertainty with UNKNOWN outcome handling
- PROVIDER_STATUS_QUERY as a deterministic, read-only action type
- CONTROLLED_REFUND with full monetary safety contract
- Expanded M3 classification (UNKNOWN_PROVIDER_OUTCOME, OUT_OF_ORDER, DELAYED, MISSING, CONTRADICTORY)
- Expanded M4 hypothesis vocabulary per discrepancy class
- Transactional outbox replacing BackgroundTasks
- Scheduled sweeps for UNKNOWN state resolution and WAIT timeout escalation
- Operator API surface (read-only — 8 endpoints)
- Next.js operator frontend
- Evidence freshness check at action execution time
- Canonical State Engine layer (currently empty `src/state/`)

## B. What V0 Already Solved

- The entire trust boundary architecture (AI investigates, deterministic controls decide, atomic systems execute, independent verification closes the loop)
- Webhook ingestion + signature verification + duplicate idempotency
- M3 deterministic classification for 5 discrepancy classes
- M4 investigation with bounded hypothesis vocabulary and semantic validation
- Hallucination rejection (evidence ID admissibility)
- Control plane with 8 sequential gates
- Atomic precondition mutation (TOCTOU protection)
- Independent verification
- Authorization provenance
- Structured audit log
- Idempotency (replay protection)
- All adversarial cases in the V0 threat model

## C. What Remains Deliberately Deferred

Payment retry, subscription lifecycle, payout uncertainty, checkout abandonment, revenue recovery prioritization, learning loop, multi-tenant infrastructure, distributed systems. See §17.

## D. The Most Dangerous Architectural Mistake We Could Make During V1

**Allowing the investigation engine to select the action type.**

The moment M4 is permitted to say "I recommend a CONTROLLED_REFUND" and that recommendation flows directly to the recovery engine without an independent deterministic policy evaluation, the control boundary is broken. The history of unsafe AI financial integrations is largely the history of this mistake in different forms.

Every new action type in V1 must have its own `evaluate_*_eligibility()` deterministic policy function. M4's job ends at hypothesis ranking. The control plane decides whether any action is authorized. This separation must be enforced structurally, not by convention.

---

*Architecture design complete. Read-only. No code changes made.*
