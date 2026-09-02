# V1 Architecture Review

**Purpose:** Resolve the 8 open architectural ambiguities in V1_PRODUCT_ARCHITECTURE.md before implementation.  
**Format:** Each issue stated, decision made, rejected alternatives documented.  
**Output:** This document amends V1_PRODUCT_ARCHITECTURE.md. Where sections conflict, this document takes precedence.  
**Date:** 2026-09-01  
**Read-only. No code changes.**

---

## Issue 1 — UNKNOWN definition is too narrow

### The problem

V1_PRODUCT_ARCHITECTURE.md §2 defined:

> `UNKNOWN = Cannot determine. System has not yet queried provider.`

This is wrong. It describes one specific cause, not the epistemic condition itself.

`UNKNOWN` may arise from:
- request sent, provider response lost
- provider returned a non-final, indeterminate result
- provider API returned a result but the query was not authoritative
- our observation window is insufficient to establish completeness
- the system has not yet queried the provider at all

All of these produce the same system behavior: **the financial outcome cannot currently be established with sufficient authoritative evidence.** The cause is secondary.

### Decision

**`UNKNOWN` is an epistemic condition, not a workflow position.**

Correct definition:

> **`UNKNOWN` = the system cannot currently establish the financial outcome with sufficient authoritative evidence, regardless of the reason.**

This definition governs all behavior that depends on `UNKNOWN`: the system must treat the state as epistemically open, not as failed, not as succeeded, and not as "just needs a query."

### Rejected alternative

> "Split into UNQUERIED / QUERIED_UNCERTAIN / INSUFFICIENT_EVIDENCE."

Rejected because behavioral response to all three is identical: do not act on insufficient evidence; escalate or re-query. The cause matters for investigation but not for safety gating.

---

## Issue 2 — OutcomeState and EpistemicState are conceptually overlapping

### The problem

V1_PRODUCT_ARCHITECTURE.md defined a single `OutcomeState` enum containing:

```
SUCCESS / FAILED / PROCESSING / UNKNOWN / TIMED_OUT
```

This conflates two distinct things:

- **what the financial world did** — the refund either happened, failed, or is in flight
- **what the system can currently establish** — we may or may not know which

Putting `UNKNOWN` inside `OutcomeState` conflates:

> "The refund is unknown to us" (knowledge gap)

with:

> "The refund itself has an UNKNOWN financial state" (no such thing — money either moved or it did not)

### Decision

**Replace the single `OutcomeState` enum with a two-layer model:**

```
FinancialState        — What occurred in the financial world (provider-side)
KnowledgeState        — What the system can currently establish about it
```

#### FinancialState

Represents what the provider's financial system has actually done. This is a world-state — not a system state.

```
FinancialState:
  CAPTURED      — payment captured
  REFUNDED      — refund processed
  FAILED        — transaction explicitly failed
  PROCESSING    — provider has accepted the request but not finalized
  VOIDED        — authorization voided before capture
```

Note: `FinancialState` values correspond to actual financial outcomes, not our knowledge of them. A transaction in the real world has exactly one FinancialState — even if we cannot currently observe it.

#### KnowledgeState

Represents the system's current epistemic status about a financial entity's state.

```
KnowledgeState:
  VERIFIED       — Established by authoritative, deterministic evidence
  UNVERIFIED     — The system has a belief but it has not passed deterministic checks
  UNKNOWN        — Cannot currently be established with sufficient authoritative evidence
  CONTRADICTED   — Two trusted observations are mutually incompatible
```

#### How they compose

```
FinancialState = REFUNDED
KnowledgeState = VERIFIED
→ The refund happened and we can prove it. Safe to close incident.

FinancialState = PROCESSING
KnowledgeState = VERIFIED
→ The provider has confirmed in-flight. Do not retry. Wait.

FinancialState = ?
KnowledgeState = UNKNOWN
→ We do not know what the financial world did. Do not act.

FinancialState = REFUNDED
KnowledgeState = CONTRADICTED
→ Two trusted sources disagree. Escalate immediately.
```

#### Where UNKNOWN lives

`UNKNOWN` belongs exclusively in `KnowledgeState`. It is never a `FinancialState`. Money either moved or it did not — the uncertainty is always on the knowledge side.

### Rejected alternative

> "Use a single combined status enum like REFUND_VERIFIED / REFUND_UNKNOWN / REFUND_FAILED."

Rejected because it collapses into an exponential matrix of combined states as financial entities grow. The two-layer model is more composable and more honest about what the system actually knows vs. what the world actually contains.

---

## Issue 3 — Action idempotency formula binds to the wrong anchor

### The problem

V1_PRODUCT_ARCHITECTURE.md proposed:

```
idempotency_key = sha256(incident_id + action_type + target_entity_id + authorization_provenance_id)
```

This is wrong for monetary actions.

If a new incident is created for the same underlying financial operation — which can happen legitimately (incident reopened, new investigation triggered) — the `incident_id` changes and therefore the idempotency key changes. This potentially permits a duplicate monetary effect against the same financial entity.

### Decision

**Monetary action idempotency must bind to the financial intent, not the investigative container.**

The incident is an investigation artifact. It should not be what defines whether a financial operation is a duplicate.

#### Per action type

**CONTROLLED_REFUND:**
```
idempotency_key = stable_hash(
    provider_payment_id,    # which payment
    "REFUND",               # action class
    amount_minor_units,     # exact amount in minor units
    currency                # currency
)
```

Rationale: If you attempt a refund of ₹5,000 on payment `pay_abc123`, the idempotency key is the same regardless of which incident triggered it, which investigation ran, or which provenance record was generated. The financial intent is the anchor.

**STATE_REPAIR:**
```
idempotency_key = stable_hash(
    internal_order_id,      # which order
    "STATE_REPAIR",         # action class
    target_state            # PAID
)
```

Rationale: State repair is idempotent by SQL predicate (`WHERE status='UNPAID'`). The key here serves as a deduplication check before the SQL is even attempted, preventing redundant DB round-trips.

**PROVIDER_STATUS_QUERY:**
```
correlation_id = stable_hash(
    provider_entity_id,     # which provider entity
    entity_type,            # PAYMENT / REFUND
    requested_at_epoch      # approximate time window (to allow fresh queries)
)
```

Rationale: Read-only queries are not financial idempotency concerns. They need request correlation for tracing, not a financial idempotency key. Using a time-windowed correlation ID allows fresh queries when staleness is detected without confusing them with duplicate financial effects.

**EVENT_REPROCESS:**
```
idempotency_key = stable_hash(
    provider_event_id,      # which event
    "REPROCESS"
)
```

Rationale: Bound to the provider event identity — the same event reprocessed twice is still one event.

#### The incident_id role

`incident_id` is a **correlating reference** on the Action record, not an idempotency component for monetary operations. The action record stores `incident_id` to enable audit trail traversal. It does not influence whether the action is a duplicate.

### Rejected alternative

> "Use a UUID generated at action creation time as the idempotency key."

Rejected. A fresh UUID on each action creation means a crash between creation and execution produces an unrecoverable orphan action with no way to detect the duplicate on retry.

> "Bind to authorization_provenance_id."

Rejected. A new investigation of the same incident produces a new `authorization_provenance_id`, potentially unlocking duplicate execution. Provenance is evidence of authorization reasoning, not financial intent.

---

## Issue 4 — Refund retry eligibility: NOT_REFUNDED ≠ PROVEN_NOT_EXECUTED

### The problem

V1_PRODUCT_ARCHITECTURE.md stated:

> Provider says `NOT_REFUNDED / FAILED` → controlled refund may be issued.

This is insufficient. A provider returning "refund not found" does not establish:

> "The original refund request definitively had no financial effect."

The provider might respond "not found" because:
- The refund was never processed (safe to retry)
- The refund is queued but not yet reflected in the lookup API
- The idempotency lookup itself timed out
- The refund was processed under a different idempotency key than expected
- The API response is a stale cached snapshot

The difference:

```
NOT_CURRENTLY_OBSERVED     — We queried; the provider did not return a record.
PROVEN_NOT_EXECUTED        — We queried authoritatively; we can establish the refund has no financial effect.
```

Only `PROVEN_NOT_EXECUTED` is sufficient for monetary retry authorization.

### Decision

**Introduce `ProviderQueryConfidence` as a required parameter in the CONTROLLED_REFUND safety contract.**

```
ProviderQueryConfidence:
  AUTHORITATIVE_NOT_EXECUTED   — Provider API confirmed, with sufficient query authority,
                                  that no refund of this idempotency key has executed.
  AUTHORITATIVE_EXECUTED       — Provider confirmed refund completed.
  NON_AUTHORITATIVE_QUERY      — Query returned a result but the query itself was not
                                  fully authoritative (timeout, cached response, etc.)
  QUERY_FAILED                 — Query could not be completed.
```

**CONTROLLED_REFUND safety contract — revised refund retry precondition:**

```
Required for retry authorization:
  ProviderQueryConfidence == AUTHORITATIVE_NOT_EXECUTED
  AND
  idempotency_key_lookup_confirmed_empty == True
  AND
  query_was_not_itself_ambiguous == True
```

**If `ProviderQueryConfidence != AUTHORITATIVE_NOT_EXECUTED`:**
```
→ KnowledgeState = UNKNOWN
→ Do not retry
→ ESCALATE with reason:
    "Provider query did not authoritatively establish non-execution.
     Cannot safely authorize refund retry."
```

### Why this matters

The system's job is to prove absence of execution, not merely observe absence of a record. These are different epistemic claims. The architecture must enforce this distinction at the control plane level, not leave it to the caller.

### Rejected alternative

> "Just check `refund_not_found == True` from the provider response."

Rejected. Provider APIs return "not found" for multiple reasons, not all of which establish non-execution. The query authority matters as much as the query result.

---

## Issue 5 — WAIT should not be an ActionType

### The problem

V1_PRODUCT_ARCHITECTURE.md listed `WAIT` as an entry in the `ActionType` enum.

Waiting is not a financial action. It produces no financial effect, no provider API call, no audit event of consequence, and no outcome that needs independent verification. Putting it in the action ledger pollutes the action record with non-actions.

`ESCALATE` has the same problem — it is a state transition that produces an `Escalation` artifact, not a financial action.

### Decision

**Remove `WAIT` and `ESCALATE` from `ActionType`.**

#### WAIT → becomes an Incident lifecycle state: `MONITORING`

```
Incident.lifecycle_state = MONITORING

Monitoring metadata (stored on Incident, not as an Action):
  next_evaluation_at    — when the worker should re-query provider state
  deadline_at           — maximum time before escalation is forced
  monitoring_reason     — why the system is waiting
  query_count           — how many re-queries have been attempted
```

The scheduled sweep (§12 of V1_PRODUCT_ARCHITECTURE.md) evaluates `MONITORING` incidents and either re-queries or transitions to `ESCALATED` on deadline expiry.

#### ESCALATE → becomes an Incident outcome state with an Escalation artifact

```
Incident.lifecycle_state = ESCALATED

Escalation record produced and linked to Incident:
  escalation_id
  incident_id
  ...all 9 §25 fields...
```

Escalation is triggered by:
- Control plane emitting `NO_ACTION` + reason
- MONITORING deadline exceeded
- `CONTRADICTED` evidence state
- `ProviderQueryConfidence != AUTHORITATIVE_*` after configured retry limit

#### Revised ActionType

```
ActionType (enum) — only actual financial and operational effects:
  STATE_REPAIR              — internal state correction (non-monetary)
  EVENT_REPROCESS           — replay provider event through processing (non-monetary)
  PROVIDER_STATUS_QUERY     — read-only provider re-query (no financial effect)
  CONTROLLED_REFUND         — monetary; initiate refund via provider API
  PAYMENT_RETRY             — monetary; NOT_YET_DESIGNED — excluded from V1
```

### Rejected alternative

> "Keep WAIT as an Action but with a special flag `has_financial_effect = False`."

Rejected. The semantic model of an Action is a thing that was executed against a financial or operational system. Waiting is not that. The distinction should be in the type system, not a boolean flag.

---

## Issue 6 — "Every action has an idempotency key" is too broad

### The problem

Architecture Invariant #6 in V1_PRODUCT_ARCHITECTURE.md states:

> "Every action has an idempotency key."

This is overly broad and conflates three different idempotency mechanisms that have fundamentally different semantics.

### Decision

**Replace Invariant #6 with three precise sub-invariants, one per action category.**

#### Sub-invariant 6a — Financial effect actions (CONTROLLED_REFUND, future PAYMENT_RETRY)

> Every action that produces a financial effect against an external provider system must carry a **financial idempotency key** bound to the financial intent (see Issue 3 resolution). This key must be passed to the provider as the idempotency header. Duplicate submission of the same key to the provider must return the original result, not create a second effect.

#### Sub-invariant 6b — Internal state mutations (STATE_REPAIR, EVENT_REPROCESS)

> Every action that mutates internal state must be gated by an **atomic SQL precondition** that checks the expected pre-state at execution time (not at authorization time). Race conditions produce `CONFLICT`, not false success. The `rowcount == 0` check from V0 is the canonical implementation of this sub-invariant.

#### Sub-invariant 6c — Read-only queries (PROVIDER_STATUS_QUERY)

> Read-only queries must carry a **request correlation ID** for tracing and audit. They are not subject to financial idempotency constraints, but their results must be persisted as a new `ProviderObservation` before they are used as evidence. A query result that is not persisted does not become evidence.

The revised overall invariant:

> **Actions that can produce financial effects require financial idempotency keys bound to financial intent. Actions that mutate internal state require atomic preconditions. Read-only actions require persisted observation records.**

---

## Issue 7 — State Engine must not become a second source of truth

### The problem

V1_PRODUCT_ARCHITECTURE.md §7 described the State Engine as constructing "typed ProviderPayment / ProviderOrder observations" from raw records. Without an explicit authority hierarchy, the derived state can slowly acquire the status of a primary truth — a second mutable database that diverges from the immutable observations it was derived from.

This is the specific failure mode that has destroyed financial system reliability in production: a "canonical state" table that gets updated by application code and slowly drifts from the actual transaction history.

### Decision

**Establish an explicit, non-negotiable authority hierarchy. The State Engine is a deterministic function, not a database.**

```
AUTHORITY HIERARCHY

Level 1: Immutable ProviderObservation records
         — Append-only. Never modified. Never deleted.
         — The ground truth of what the system has observed.
         — Raw provider payloads preserved verbatim.

Level 2: StateEngine (deterministic reconstruction function)
         — Input: a set of ProviderObservation records for an entity
         — Output: the most defensible current FinancialState + KnowledgeState
         — Property: RECOMPUTABLE. Given the same observations, always produces
           the same output. No internal state.
         — The output is a VIEW of Level 1, not a new truth.

Level 3: Derived domain state (MerchantOrder.status, etc.)
         — Updated by the system as a consequence of authorized actions.
         — If Level 3 conflicts with a fresh Level 2 reconstruction: Level 2 wins.
         — Level 3 is a performance cache, not the authority.

Level 4: M3 classification
         — Input: Level 2 output
         — Output: discrepancy class
         — Deterministic, pure function.

Level 5: M4 hypothesis
         — Input: evidence derived from Level 1 + Level 3
         — Output: ranked hypothesis proposal
         — Advisory only. Cannot modify Level 1, 2, or 3.
```

#### Enforcement rule

**The State Engine must be a pure function.**

```python
def reconstruct_state(
    observations: List[ProviderObservation],   # immutable Level 1 inputs
    temporal_ordering: TemporalOrderingPolicy
) -> ReconstructedState:
    ...  # deterministic derivation, no side effects, no DB writes
```

The output of `reconstruct_state()` must never be written back to a database table that is subsequently used as the authoritative source of financial state. If caching is needed for performance, the cache must carry a staleness timestamp and be treated as invalidated if new observations arrive.

### Rejected alternative

> "Persist the StateEngine output in a `canonical_payment_state` table updated on each webhook."

Rejected. This creates a second mutable financial state database. Any code path that updates this table outside the StateEngine function becomes an uncontrolled state mutation. The StateEngine must be a function, not a database.

---

## Issue 8 — Read-only frontend is too restrictive

### The problem

V1_PRODUCT_ARCHITECTURE.md §13 stated:

> "All endpoints are read-only for operators. No operator-initiated action endpoints in V1."

This conflates two distinct categories of operator interaction:

1. **Operator financial actions** — operator initiates a refund, operator retries a payment
2. **Operator workflow actions** — operator acknowledges an escalation, operator marks external evidence as received, operator requests re-investigation, operator manually closes a resolved escalation

Category 1 is dangerous for the same reason autonomous AI financial actions are dangerous: it bypasses the deterministic control plane.

Category 2 is non-monetary workflow state — it is how a finance-ops product actually works. An operator who cannot acknowledge an escalation or mark it resolved cannot do their job.

### Decision

**Permit non-monetary operator workflow actions. Prohibit operator-initiated financial mutations.**

#### Permitted operator-initiated actions (non-monetary, non-financial-effect)

```
POST /api/escalations/{id}/acknowledge
     — Operator marks they have received and read the escalation
     
POST /api/escalations/{id}/resolve
     — Operator marks the escalation as resolved after manual intervention
     — Must include: resolution_summary, external_action_taken
     
POST /api/incidents/{id}/request-investigation
     — Operator requests the system re-investigate with current evidence
     
POST /api/incidents/{id}/add-evidence
     — Operator records that external evidence has been supplied
     — The evidence reference becomes an EvidenceItem in the next investigation
     
POST /api/escalations/{id}/extend-deadline
     — Operator extends the monitoring deadline for MONITORING incidents
```

#### Prohibited operator-initiated actions

```
POST /api/incidents/{id}/refund         — PROHIBITED. Goes through control plane.
POST /api/incidents/{id}/retry-payment  — PROHIBITED. Goes through control plane.
POST /api/incidents/{id}/repair-state   — PROHIBITED. Goes through control plane.
```

If an operator believes a financial action is warranted after reviewing an escalation, they take the action in the provider dashboard or internal system. The FCE then observes the outcome via webhook/polling and updates accordingly. The FCE never becomes the operator's financial action console.

#### Governing principle from PRD §6

> "If automation is unsafe, what should a human do? The system produces an escalation with the evidence, uncertainty, and required next step."

The human is expected to act on that escalation. The system must close the loop when the human has acted. That requires operator workflow endpoints, not financial action endpoints.

---

## Amended Architecture Invariants

The following invariants from V1_PRODUCT_ARCHITECTURE.md §18 are amended:

**Invariant #6 — REPLACED** by the three sub-invariants in Issue 6 resolution above.

**Invariant #7 (NEW):** The State Engine is a pure deterministic function over immutable observations. Its output is a view, not a database truth. Level 1 (immutable observations) always supersedes Level 3 (derived state) when they conflict.

**Invariant #8 (AMENDED):** The following are added:

> No derived state table may be used as the primary authority for a financial decision if that table is writable by application code outside of the State Engine's deterministic derivation path.

**Invariant #13 (NEW):** Operator workflow actions (escalation acknowledgement, re-investigation requests, evidence marking) are permitted. Operator-initiated financial mutations are not. Financial mutations must always pass through the deterministic control plane.

**Invariant #14 (NEW):** `UNKNOWN` is a KnowledgeState condition, not a FinancialState. The system must never infer a FinancialState from `UNKNOWN`. When KnowledgeState is `UNKNOWN`, the only permitted system actions are: PROVIDER_STATUS_QUERY, transition to MONITORING, or ESCALATE.

---

## Summary — What Changed

| Issue | Original | Amended |
|---|---|---|
| 1. UNKNOWN definition | "not yet queried" | Epistemic: "cannot establish with sufficient authoritative evidence" |
| 2. State model | Single `OutcomeState` with UNKNOWN inside | `FinancialState` (world) × `KnowledgeState` (epistemic) |
| 3. Idempotency anchor | `incident_id` + provenance | Financial intent (provider_entity_id + action + amount + currency) |
| 4. Refund retry precondition | `NOT_REFUNDED` response | `ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED` required |
| 5. WAIT/ESCALATE | `ActionType` entries | Incident lifecycle states (`MONITORING`, `ESCALATED`) with metadata |
| 6. Idempotency invariant | Universal "every action has a key" | Three sub-invariants by action category |
| 7. State Engine authority | Implied database | Explicit authority hierarchy; StateEngine is a pure function |
| 8. Operator frontend | Read-only | Non-monetary workflow actions permitted; financial mutations prohibited |

---

## What Is Now Ready for Architecture Sign-Off

With these eight decisions made, the following architectural contracts are stable enough for implementation:

| Component | Status |
|---|---|
| Incident entity + lifecycle | ✅ Ready |
| Action entity + idempotency key construction | ✅ Ready (amended) |
| Escalation entity (all 9 §25 fields) | ✅ Ready |
| FinancialState × KnowledgeState model | ✅ Ready (amended) |
| MONITORING incident state (replaces WAIT) | ✅ Ready |
| CONTROLLED_REFUND safety contract | ✅ Ready (amended with ProviderQueryConfidence) |
| PROVIDER_STATUS_QUERY action | ✅ Ready |
| STATE_REPAIR action | ✅ Frozen from V0 |
| State Engine as pure function | ✅ Ready |
| Operator workflow API endpoints | ✅ Ready (amended) |
| Transactional outbox | ✅ Ready |
| Authority hierarchy (7 levels) | ✅ Ready |

| Component | Status |
|---|---|
| PAYMENT_RETRY | ❌ Not yet designed — excluded from V1 |
| Revenue recovery prioritization | ❌ Deferred — requires outcome history |
| Learning loop | ❌ Deferred — requires outcome history |
| Subscription/Payout lifecycle | ❌ §37 Future Direction only |

---

*Review complete. Read-only. No code changes made.*
*Supersedes conflicting sections in V1_PRODUCT_ARCHITECTURE.md.*

---

## Final Amendment — State Model Corrections (sign-off pass)

*This section supersedes §Issue 2 of this document on the following two points.*

---

### Amendment A — Remove `FinancialState.UNKNOWN`

#### The problem

Issue 2 defined `FinancialState` as "what the financial world did" and then included:

```
FinancialState = ?
KnowledgeState = UNKNOWN
```

This diagram is conceptually correct, but implementing `FinancialState` as an enum creates the following trap: someone will eventually add `FinancialState.UNKNOWN` to handle the "no state yet established" case. At that point, the original problem — conflating epistemic uncertainty with financial state — has been recreated under a different name.

#### Decision

**`ObservedFinancialState` is concrete or absent. Never unknown.**

The implementation must treat "unestablished financial state" as **absence of an observation**, not as a special enum value.

```python
# Wrong — do not implement this
class FinancialState(str, Enum):
    CAPTURED   = "CAPTURED"
    REFUNDED   = "REFUNDED"
    FAILED     = "FAILED"
    PROCESSING = "PROCESSING"
    UNKNOWN    = "UNKNOWN"   # ← the trap

# Correct
class ObservedFinancialState(str, Enum):
    CAPTURED   = "CAPTURED"
    REFUNDED   = "REFUNDED"
    FAILED     = "FAILED"
    PROCESSING = "PROCESSING"
    # No UNKNOWN entry. Absence is represented as Optional[ObservedFinancialState] = None.
```

The reconstructed state tuple then becomes:

```python
@dataclass(frozen=True)
class ReconstructedState:
    observed_financial_state: Optional[ObservedFinancialState]  # None = not established
    knowledge_state: KnowledgeState
```

Interpretation:

| `observed_financial_state` | `knowledge_state` | Meaning |
|---|---|---|
| `CAPTURED` | `VERIFIED` | Payment captured and proven |
| `REFUNDED` | `VERIFIED` | Refund confirmed and proven |
| `PROCESSING` | `VERIFIED` | Provider confirms in-flight |
| `None` | `UNKNOWN` | Cannot establish financial state — do not act |
| `None` | `CONTRADICTED` | Two observations conflict — escalate |
| `CAPTURED` | `CONTRADICTED` | Evidence says captured but something contradicts it — escalate |

**The control plane gates on `KnowledgeState`, not on the presence or absence of `ObservedFinancialState`.**

#### Why Optional rather than a sentinel value

Optional(None) is explicit in the type system. A sentinel like `FinancialState.UNKNOWN` is a valid enum member that can accidentally match `== UNKNOWN` in comparisons, be stored in the database, and silently pass type checks that expect a real financial state. Optional forces the caller to handle the absence case explicitly.

#### Consequence for the control plane

The CONTROLLED_REFUND precondition from Issue 4 is now stated more precisely:

```
CONTROLLED_REFUND requires:
  knowledge_state == VERIFIED
  AND observed_financial_state == None (for the refund itself — not yet executed)
  AND provider_query_confidence == AUTHORITATIVE_NOT_EXECUTED
```

If `knowledge_state != VERIFIED`, the action is `NO_ACTION` regardless of what `observed_financial_state` contains.

---

### Amendment B — Remove `KnowledgeState.UNVERIFIED`

#### The problem

Issue 2 included `KnowledgeState.UNVERIFIED` defined as:

> "The system has a belief but it has not passed deterministic checks."

This is architecturally wrong. The system's "beliefs" are hypotheses and claims — they belong to the investigation layer, not the state model. Introducing `UNVERIFIED` into `KnowledgeState` creates a pathway where:

```
M4 thinks the refund probably happened
        ↓
system sets KnowledgeState = UNVERIFIED
        ↓
some code path treats UNVERIFIED as "close enough to VERIFIED to proceed"
```

That is exactly the class of error the architecture is designed to prevent.

#### Decision

**Remove `KnowledgeState.UNVERIFIED`. Beliefs live in hypotheses, not in state.**

```python
class KnowledgeState(str, Enum):
    VERIFIED      = "VERIFIED"      # Established by authoritative deterministic evidence
    UNKNOWN       = "UNKNOWN"       # Cannot currently be established
    CONTRADICTED  = "CONTRADICTED"  # Two trusted observations are mutually incompatible
```

Three values only.

#### Where M4 beliefs actually live

If M4 believes the refund probably happened, that is expressed as:

```python
HypothesisSelection(
    hypothesis_id = RefundHypothesisType.REFUND_PROCESSED_WEBHOOK_LOST,
    rank = 1,
    confidence_band = ConfidenceBand.HIGH,
    rationale = "...",
    supporting_evidence_ids = [...],
    missing_evidence_types = [EvidenceType.E_PROVIDER_REFUND_STATUS]
)
```

The `KnowledgeState` on the `ReconstructedState` remains `UNKNOWN` until the control plane receives deterministic evidence — specifically a `PROVIDER_STATUS_QUERY` result that passes the `ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED` check.

**M4's confidence never flows into `KnowledgeState`. This is not a convention. It is a type boundary.**

#### The clean epistemic boundary

```
INVESTIGATION LAYER
   M4 hypothesis
   confidence_band (HIGH / MEDIUM / LOW)
   supporting_evidence_ids
   ← lives here, does not cross

─────────────────────────────────── boundary

STATE LAYER
   ObservedFinancialState (concrete or None)
   KnowledgeState (VERIFIED | UNKNOWN | CONTRADICTED)
   ← only deterministic evidence can change these
```

Nothing from the investigation layer directly modifies `KnowledgeState`. Only new `ProviderObservation` records (persisted by `PROVIDER_STATUS_QUERY` or incoming webhooks) can cause `StateEngine` to produce a different `KnowledgeState`.

---

### Final State Model — Signed Off

```python
class ObservedFinancialState(str, Enum):
    """What the provider's financial system has done. Concrete only."""
    CAPTURED   = "CAPTURED"
    REFUNDED   = "REFUNDED"
    FAILED     = "FAILED"
    PROCESSING = "PROCESSING"
    VOIDED     = "VOIDED"
    # No UNKNOWN. Absence = Optional[ObservedFinancialState] = None.

class KnowledgeState(str, Enum):
    """What the system can currently establish about a financial entity's state."""
    VERIFIED     = "VERIFIED"      # Deterministic evidence established this
    UNKNOWN      = "UNKNOWN"       # Cannot currently establish — epistemic gap
    CONTRADICTED = "CONTRADICTED"  # Two trusted observations are mutually incompatible

@dataclass(frozen=True)
class ReconstructedState:
    """Output of the pure StateEngine function. A view over immutable observations."""
    observed_financial_state: Optional[ObservedFinancialState]
    knowledge_state: KnowledgeState
    observation_ids: tuple[str, ...]   # which ProviderObservation records produced this
    reconstructed_at: datetime
```

**Control plane admission rule (invariant):**

```
For any consequential action:

    knowledge_state MUST be VERIFIED

If knowledge_state is UNKNOWN:
    permitted actions: PROVIDER_STATUS_QUERY, MONITORING transition, ESCALATE

If knowledge_state is CONTRADICTED:
    permitted actions: ESCALATE only

No other action is authorized regardless of M4 hypothesis rank or confidence.
```

---

### Architecture sign-off summary

The two-layer state model is now:

```
IMMUTABLE OBSERVATIONS (ProviderObservation)
        │
        ▼
STATE ENGINE (pure deterministic function)
        │
        ▼
ReconstructedState
  ├── ObservedFinancialState  (concrete or absent)
  └── KnowledgeState          (VERIFIED | UNKNOWN | CONTRADICTED)
        │
        ▼
M3 discrepancy classification
        │
        ▼
Incident (work unit, not financial authority)
        │
        ▼
M4 advisory hypotheses (confidence bands, never modifies KnowledgeState)
        │
        ▼
Deterministic Control Plane
  (gates exclusively on KnowledgeState == VERIFIED)
        │
        ▼
Action (concrete, persisted, idempotency bound to financial intent)
        │
        ▼
New ProviderObservation (from provider response or webhook)
        │
        ▼
StateEngine re-run → new ReconstructedState
        │
        ▼
Independent Verification
```

**Architecture is now signed off for implementation.**

Implementation order (dependency-constrained, from user directive):

```
1.  Domain state primitives (ObservedFinancialState, KnowledgeState, ReconstructedState)
2.  Incident persistence + lifecycle state machine
3.  Refund domain entity (with Optional[ObservedFinancialState] + KnowledgeState)
4.  Escalation persistence (all 9 §25 fields)
5.  Action persistence + financial-intent idempotency
6.  Transactional outbox (replacing BackgroundTasks)
7.  State Engine (pure function over ProviderObservation)
8.  Refund uncertainty vertical slice (secondary incident)
9.  PROVIDER_STATUS_QUERY action + ProviderQueryConfidence
10. Deterministic refund policy (evaluate_refund_eligibility)
11. Independent verification for refund
12. Operator workflow API (non-monetary endpoints only)
```

UI is step 12. Not step 1.

*Amendment complete. Read-only. No code changes.*

---

## Final Amendment 2 — Four Remaining Corrections (architecture sign-off)

*This section supersedes the specific passages noted below. Everything else in this document stands.*

---

### Correction A — Refund idempotency must bind to a stable intent identity

**Supersedes:** Issue 3 (Amendment A to Issue 3) — CONTROLLED_REFUND idempotency key formula.

#### The problem with the prior formula

```
idempotency_key = stable_hash(provider_payment_id + "REFUND" + amount_minor_units + currency)
```

This formula produces the same key for two distinct legitimate refund intents against the same payment at the same amount in the same currency. A second legitimate ₹5,000 refund on `pay_abc123` — for a different line item, different reason, separate business decision — would be silently treated as a duplicate of the first.

Idempotency identifies **the same intended operation**, not merely **the same operation shape**.

#### Decision

**CONTROLLED_REFUND idempotency anchors to a `refund_intent_id`, not to operation parameters.**

```
Refund entity
  ├── refund_id           (internal PK — UUID)
  ├── refund_intent_id    (stable business identity — UUID, created once)
  ├── provider_payment_id (FK — which payment)
  ├── amount              (intent specification — validated against, not identity)
  ├── currency            (intent specification — validated against, not identity)
  └── ...
```

The provider idempotency key:

```
provider_idempotency_key = stable_hash(provider_payment_id + "REFUND" + refund_intent_id)
```

#### What `refund_intent_id` is and when it is created

`refund_intent_id` is a UUID assigned **once** when the refund business intent is first established — i.e., when the Refund entity is first persisted as part of the incident resolution decision. It is:

- **stable across retries** — the same intent retried after a crash uses the same `refund_intent_id`
- **stable across reinvestigations** — a new incident or new investigation for the same intent uses the same `refund_intent_id`
- **different for a genuinely distinct intent** — a new business decision to issue a separate refund creates a new Refund entity with a new `refund_intent_id`

This means the creation of a distinct `refund_intent_id` is itself a business-level decision that must pass through the control plane. The control plane does not generate a key at execution time — it authorizes against a pre-created persisted intent.

#### Revised CONTROLLED_REFUND safety contract preconditions

```
1. A Refund entity with a stable refund_intent_id exists and is authorized
2. The refund has not previously been executed (no prior Action with this refund_intent_id in SUCCESS state)
3. KnowledgeState == VERIFIED
4. observed_financial_state for this refund_intent_id is None
   (no execution established for this specific intent)
5. ProviderQueryConfidence == AUTHORITATIVE_NOT_EXECUTED for this refund_intent_id
6. amount and currency match the persisted Refund intent specification
7. payment is eligible for refund (not already fully refunded, not voided, etc.)
```

Amount and currency are **validation conditions checked against the persisted intent**, not identity components.

---

### Correction B — VERIFIED + None means a verified assertion, not absence of observation

**Supersedes:** Final Amendment A — the sentence "Absence is represented as `Optional[ObservedFinancialState] = None`."

#### The problem

The prior wording implied that `None` in `Optional[ObservedFinancialState]` means "there is no observation." That is wrong. A `ProviderObservation` may exist that authoritatively establishes:

> "No refund corresponding to this `refund_intent_id` has executed."

That is a real observation. What `None` represents is that **no concrete financial state has been established** — not that no observation exists.

#### Decision

**`None` in `ObservedFinancialState` means: no concrete financial state value is established.**

An authoritative "not found" from the provider is still a `ProviderObservation`. The `StateEngine` processes it and produces:

```python
ReconstructedState(
    observed_financial_state = None,      # no concrete financial outcome
    knowledge_state = KnowledgeState.VERIFIED,  # but we know the assertion is established
    observation_ids = ("obs_xyz",),       # the "not found" observation that proved it
    reconstructed_at = ...
)
```

#### What `KnowledgeState.VERIFIED` means — amended definition

> `KnowledgeState.VERIFIED` means the State Engine has deterministically established the applicable **financial assertion** about the entity in question. That assertion may be either:
> - a concrete financial state (e.g., REFUNDED, CAPTURED, FAILED), or
> - a verified condition of non-execution (i.e., no financial effect for the specified intent has been established by authoritative evidence).

#### Consequence for the control plane

The control plane must evaluate **what proposition has been verified**, not merely that verification occurred.

This prevents the dangerous generalization:

> `KnowledgeState == VERIFIED` → therefore action is safe

The correct check for CONTROLLED_REFUND authorization:

```python
# Wrong — too broad
if reconstructed_state.knowledge_state == KnowledgeState.VERIFIED:
    allow_refund()

# Correct — proposition-specific
if (
    reconstructed_state.knowledge_state == KnowledgeState.VERIFIED
    and reconstructed_state.observed_financial_state is None        # specifically: non-execution
    and provider_query_confidence == ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED
    and refund_intent.is_valid()
    and payment.is_eligible_for_refund()
):
    allow_refund()
```

The `VERIFIED` check alone is necessary but not sufficient. The control plane must also confirm that the verified proposition is specifically the one relevant to the action being authorized.

#### Updated state interpretation table

| `observed_financial_state` | `knowledge_state` | Verified assertion | System behavior |
|---|---|---|---|
| `REFUNDED` | `VERIFIED` | Refund executed for this intent | Close incident — RESOLVED |
| `PROCESSING` | `VERIFIED` | Refund in-flight | MONITORING — do not retry |
| `FAILED` | `VERIFIED` | Transaction explicitly failed | Evaluate retry eligibility |
| `None` | `VERIFIED` | Non-execution established for this intent | Retry may be authorized if all safety conditions met |
| `None` | `UNKNOWN` | Cannot establish what happened | PROVIDER_STATUS_QUERY or MONITORING or ESCALATE |
| any | `CONTRADICTED` | Two trusted observations conflict | ESCALATE only |

---

### Correction C — `AUTHORITATIVE_NOT_EXECUTED` is semantically self-contained

**Supersedes:** Issue 4 resolution — the three-condition CONTROLLED_REFUND precondition check.

#### The problem

The prior contract required the control plane to check:

```
ProviderQueryConfidence == AUTHORITATIVE_NOT_EXECUTED
AND idempotency_key_lookup_confirmed_empty == True
AND query_was_not_itself_ambiguous == True
```

If `AUTHORITATIVE_NOT_EXECUTED` requires additional boolean flags to be meaningful, the enum value is not semantically self-contained. The control plane should not need to verify properties that the confidence classification is supposed to guarantee.

#### Decision

**`AUTHORITATIVE_NOT_EXECUTED` may only be produced by the provider adapter when all internal authority criteria are satisfied.**

The adapter is responsible for:
- Verifying the query was not itself ambiguous
- Verifying the idempotency key lookup was comprehensive
- Verifying the response was not a stale cache or partial result
- Verifying the provider API confirms non-execution at the level of authority required

The **adapter alone** determines whether the response qualifies as `AUTHORITATIVE_NOT_EXECUTED`. It sets a lower confidence value (`NON_AUTHORITATIVE_QUERY`) if any of those criteria are not satisfied.

The **control plane** then checks only:

```python
# Provider semantics
provider_query_confidence == ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED

# Business conditions (these are NOT implied by the confidence value)
refund_intent.is_valid()
payment.is_eligible_for_refund()
refund_intent.amount <= payment.refundable_amount
refund_intent.currency == payment.currency
no_prior_action_succeeded_for_intent(refund_intent_id)
```

The business conditions are separate from the provider query confidence and must be checked independently by the control plane. The provider confidence enum handles one specific responsibility: the authority of the non-execution determination. Business eligibility is the control plane's responsibility.

---

### Final architecture sign-off

With these four corrections (Amendment 1 + Amendment 2), the architecture is signed off.

**What is locked:**

```
1. ObservedFinancialState — concrete enum values only, no UNKNOWN entry
2. KnowledgeState — VERIFIED | UNKNOWN | CONTRADICTED (three values only)
3. ReconstructedState — pure StateEngine output, not a mutable database table
4. refund_intent_id — stable business identity, anchor for monetary idempotency
5. AUTHORITATIVE_NOT_EXECUTED — semantically self-contained in the adapter layer
6. Control plane checks verified proposition, not merely VERIFIED status
7. WAIT and ESCALATE are lifecycle states, not ActionType entries
8. M4 confidence never modifies KnowledgeState
9. Level 1 (immutable observations) always supersedes Level 3 (derived state)
10. Operator workflow actions permitted; operator financial mutations prohibited
11. Implementation order: domain primitives → persistence → state engine → refund uncertainty → API
```

**Do not amend the architecture further.**

The next phase: adversarial implementation testing — crashes at every boundary, duplicate workers, stale observations, webhook/query races, concurrent refund attempts, provider timeout after accepted request, contradictory provider observations.

*Sign-off amendment complete. Read-only. No code changes.*
