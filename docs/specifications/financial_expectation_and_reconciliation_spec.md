# Financial Expectation & Deterministic Reconciliation Specification

**Status:** APPROVED FOR SPECIFICATION  
**Scope:** Layer Above V1 Control Kernel (Expectation Modeling, Correlation, and Deterministic Reconciliation)  
**Authority Boundary:** Pure Classification Only (Financial Authorization remains locked in V1 Control Kernel)  
**Date:** September 2026  

---

## 1. Executive Summary & Purpose

The V1 Financial Control Engine establishes a deterministic, side-effect-free control kernel that safely adjudicates refund eligibility, resolves epistemic uncertainty, and dispatches actions through an atomic transactional outbox.

However, the V1 kernel is an **adjudication valve, not a radar**. It answers:
> *"Given these observations and this refund intent, is a mutation safe?"*

The broader Financial Control Engine (FCE) requires an upstream system that answers:
> *"What did the business expect to happen, what does provider reality show, where do discrepancies exist, and what can be authoritatively proven?"*

This specification establishes the formal semantics for:
1. **Internal Financial Expectations**: Immutable representations of business intent.
2. **Provider Reality Inputs**: Strict reuse of V1 `ReconstructedState` and `ProviderObservation`.
3. **Correlation Algebra**: Associating internal intents with external provider artifacts.
4. **Deterministic Reconciliation**: A pure function classifying the delta between expectation and reality into typed discrepancies without side effects or mutations.
5. **The Boundary of Authority**: Ensuring reconciliation strictly classifies discrepancies, leaving financial authorization exclusively to the locked V1 Control Kernel.

---

## 2. Core Domain Contracts

### 2.1 The `FinancialExpectation` Abstraction

`FinancialExpectation` defines the immutable base contract for any internal business intent across the enterprise (OMS, ERP, Billing, Ledger, Customer Service).

```python
class FinancialExpectation(Protocol):
    """
    Immutable specification of an expected financial event originating from business systems.
    """
    expectation_id: str             # Unique immutable identifier (UUID)
    intent_id: str                  # Business correlation key (e.g. refund_intent_id)
    entity_type: EntityType         # Target entity (PAYMENT, REFUND_INTENT, SETTLEMENT)
    expected_amount: Decimal        # Exact expected financial value
    currency: str                   # ISO-4217 currency code (e.g. 'INR')
    created_at: datetime            # When the expectation was born (UTC)
    sla_seconds: int                # Maximum acceptable latency before absence is flagged
    source_system: str              # Originating business service ('OMS', 'BILLING', 'CS')
    business_reason: str            # Audit rationale for the expected mutation

    def reconciliation_deadline(self) -> datetime:
        """Returns the UTC timestamp after which absence constitutes a potential SLA violation."""
        ...
```

### 2.2 The `ExpectedRefund` Specialization (V1 Focus)

To prevent premature abstraction while building a concrete, production-shaped engine, V1 specializes on **`ExpectedRefund`**:

```python
@dataclass(frozen=True)
class ExpectedRefund:
    """
    Concrete expectation of a customer or operational refund.
    """
    expectation_id: str             # UUIDv4
    refund_intent_id: str           # Stable, immutable intent key (e.g. 'ref_01HZX...')
    provider_payment_id: str        # Provider target (e.g. 'pay_01HZX...')
    amount: Decimal                 # Exact monetary amount (e.g. Decimal('500.00'))
    currency: str                   # ISO-4217 (e.g. 'INR')
    created_at: datetime            # UTC timestamp
    sla_seconds: int                # Maximum execution grace period (e.g. 300 seconds)
    source_system: str              # e.g. 'OMS_RETURNS'
    business_reason: str            # e.g. 'Customer Return Item #882'
    originating_trace_id: str       # Distributed tracing correlation ID

    @property
    def intent_id(self) -> str:
        return self.refund_intent_id

    @property
    def entity_type(self) -> EntityType:
        return EntityType.REFUND_INTENT

    def reconciliation_deadline(self) -> datetime:
        return self.created_at + timedelta(seconds=self.sla_seconds)

    def get_provider_idempotency_key(self) -> str:
        """Derives the deterministic provider idempotency key directly from intent."""
        return hashlib.sha256(f"refund:{self.refund_intent_id}".encode()).hexdigest()[:32]
```

### 2.3 Provider Reality Inputs

The reconciliation engine **never** makes network calls, reads raw database rows, or parses JSON payloads. It consumes provider reality exclusively via the outputs of the V1 StateEngine:

1. **`ReconstructedState`**: The pure epistemic state reconstructed over accumulated `ProviderObservation` records:
   - `knowledge_state: KnowledgeState` (`VERIFIED`, `UNKNOWN`, `CONTRADICTED`)
   - `observed_financial_state: Optional[ObservedFinancialState]` (`CAPTURED`, `REFUNDED`, `FAILED`, `PROCESSING`, `VOIDED`, `None`)
   - `execution: Optional[ExecutionState]` (`EXECUTED`, `NOT_EXECUTED`, `None`)
   - `observation_ids: Tuple[str, ...]`
2. **`ProviderObservation` Sequence**: Used when multi-execution or cardinality checks require verifying observation counts.

---

## 3. Correlation Algebra

Correlation is the deterministic mapping between internal expectations and provider states.

### 3.1 Primary Correlation Key
For refund operations, correlation is strictly bipartite:
$$\text{CorrelationKey} = (\text{provider\_payment\_id}, \text{refund\_intent\_id})$$

* Internal: `(ExpectedRefund.provider_payment_id, ExpectedRefund.refund_intent_id)`
* Provider: Extracted from `ProviderObservation` where:
  - `entity_type == EntityType.REFUND_INTENT` and `entity_id == refund_intent_id`
  - OR `payload["receipt"] == refund_intent_id`
  - OR `payload["notes"]["refund_intent_id"] == refund_intent_id`

### 3.2 Cardinality Invariant (V1: Strict 1-to-1)
* **Single Match**: Exactly one provider refund entity must correspond to an `ExpectedRefund`.
* **Multi-Match Violation (`EXCESS_EFFECT`)**: If more than one provider refund execution matches the same `refund_intent_id` or `receipt`, reconciliation flags a fatal duplicate financial effect.
* **Orphaned Mutation (`ORPHANED_EXECUTION`)**: If a provider refund execution exists on `provider_payment_id` with a `receipt` that does not match any internal `ExpectedRefund`, it is classified as an out-of-band/orphaned execution.

---

## 4. Discrepancy Taxonomy

Reconciliation maps every `(FinancialExpectation, Optional[ReconstructedState])` pair to a strictly typed `DiscrepancyType`.

```python
class DiscrepancyType(str, Enum):
    # ── Non-Discrepant States ──────────────────────────────────────────
    MATCH = "MATCH"
    """Expectation perfectly satisfied by provider execution within limits."""

    IN_FLIGHT_PENDING = "IN_FLIGHT_PENDING"
    """Within configured SLA grace period; provider execution not yet proven.
    Normal operational state, no action required."""

    # ── Epistemic Gaps (Actionable via Probe) ───────────────────────────
    EPISTEMIC_STALEMATE = "EPISTEMIC_STALEMATE"
    """SLA has expired OR an in-flight mutation occurred, but provider reality
    is UNKNOWN, incomplete, or non-authoritative. Demands status query probe."""

    # ── Invariant Breaches (Actionable via Control Kernel) ──────────────
    ABSENT_EXECUTION = "ABSENT_EXECUTION"
    """SLA has expired AND provider reality is AUTHORITATIVELY PROVEN to be
    NOT_EXECUTED. Actionable: eligible for V1 Control Policy evaluation."""

    # ── Operational Invariant Violations (Informational / Escalation) ───
    VALUE_MISMATCH = "VALUE_MISMATCH"
    """Provider executed refund, but amount differs from expected_amount."""

    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    """Provider executed refund, but currency differs from expected currency."""

    CONTRADICTORY_TERMINALITY = "CONTRADICTORY_TERMINALITY"
    """Provider executed a terminal failure (e.g. chargeback closed/failed),
    incompatible with fulfillment."""

    ORPHANED_EXECUTION = "ORPHANED_EXECUTION"
    """Provider executed a mutation on this payment with no matching internal
    intent. Potential fraud, rogue script, or manual dashboard action."""

    EXCESS_EFFECT = "EXCESS_EFFECT"
    """Multiple provider executions detected for a single intent.
    Direct financial loss / duplicate refund. Requires immediate containment."""
```

---

## 5. Temporal and Epistemic Semantics

### 5.1 Temporal Semantics & Pure Evaluation
To preserve deterministic testability and replayability, the reconciler **must never evaluate wall-clock time (`datetime.now()`)**. 
The evaluation timestamp `reconciliation_timestamp: datetime` is an explicit, required argument:

```python
reconciliation_deadline = expectation.created_at + timedelta(seconds=expectation.sla_seconds)
is_past_deadline = reconciliation_timestamp >= reconciliation_deadline
```

### 5.2 Epistemic Semantics: The Proof of Absence
The fundamental law of the Financial Control Engine is:
$$\text{Absence of Evidence} \neq \text{Evidence of Absence}$$

`ABSENT_EXECUTION` is a **positive proof**, not a default assumption. It can be declared **if and only if**:
1. `reconciliation_timestamp >= reconciliation_deadline` (the grace period has expired).
2. `reconstructed_state.knowledge_state == KnowledgeState.VERIFIED`.
3. `reconstructed_state.execution == ExecutionState.NOT_EXECUTED`.
4. `reconstructed_state.observed_financial_state is None`.

### 5.3 Demoting Incomplete Evidence to `EPISTEMIC_STALEMATE`
If `reconciliation_timestamp >= reconciliation_deadline` but:
- `reconstructed_state.knowledge_state == KnowledgeState.UNKNOWN`, OR
- `reconstructed_state.knowledge_state == KnowledgeState.CONTRADICTED`, OR
- Provider query confidence was `NON_AUTHORITATIVE_QUERY` or `QUERY_FAILED`, OR
- No query has been performed and observations are completely silent:

The reconciler **MUST NOT** classify this as `ABSENT_EXECUTION`. It must classify it as **`EPISTEMIC_STALEMATE`**. 
Downgrading `UNKNOWN` into `ABSENT_EXECUTION` is an invariant violation because it could trigger a duplicate financial mutation for a transaction that already executed silently.

---

## 6. Exhaustive Terminal-State Truth Table

Given an `ExpectedRefund` with amount $A$ and currency $C$, evaluated at `reconciliation_timestamp`:

| Temporal Boundary | Provider `KnowledgeState` | Provider `ObservedFinancialState` | Provider `ExecutionState` | Provider Amount & Currency | Derived `DiscrepancyType` | Actionable Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Any | `VERIFIED` | `REFUNDED` | `EXECUTED` | Matches $A$ and $C$ | **`MATCH`** | Informational (Satisfied) |
| Any | `VERIFIED` | `REFUNDED` | `EXECUTED` | Amount $\neq A$ | **`VALUE_MISMATCH`** | Escalation / Human Review |
| Any | `VERIFIED` | `REFUNDED` | `EXECUTED` | Currency $\neq C$ | **`CURRENCY_MISMATCH`** | Escalation / Human Review |
| Any | `VERIFIED` | `REFUNDED` | Count $> 1$ executions | Any | **`EXCESS_EFFECT`** | Escalation / Emergency Containment |
| Any | `VERIFIED` | `FAILED` | `NOT_EXECUTED` | Any | **`CONTRADICTORY_TERMINALITY`** | Escalation / Operational Review |
| $t < t_{\text{deadline}}$ | `UNKNOWN` / `None` | `None` / `PROCESSING` | `None` | N/A | **`IN_FLIGHT_PENDING`** | Informational (Awaiting SLA) |
| $t \ge t_{\text{deadline}}$ | `VERIFIED` | `None` | `NOT_EXECUTED` | N/A | **`ABSENT_EXECUTION`** | **Actionable (V1 Kernel Evaluation)** |
| $t \ge t_{\text{deadline}}$ | `UNKNOWN` | Any | Any | N/A | **`EPISTEMIC_STALEMATE`** | **Actionable (Diagnostic Probe)** |
| $t \ge t_{\text{deadline}}$ | `CONTRADICTED`| Any | Any | N/A | **`EPISTEMIC_STALEMATE`** | Escalation (Split-brain evidence) |
| Any | `VERIFIED` | `REFUNDED` (Unmatched intent) | `EXECUTED` | N/A | **`ORPHANED_EXECUTION`** | Escalation / Fraud Review |

---

## 7. The `ReconciliationResult` Contract

The reconciler produces an immutable, strongly-typed result:

```python
@dataclass(frozen=True)
class ReconciliationResult:
    """
    Deterministic output of reconcile(expectation, reconstructed_state).
    """
    expectation_id: str
    intent_id: str
    discrepancy_type: DiscrepancyType
    is_actionable: bool
    reconciliation_timestamp: datetime
    expected_amount: Decimal
    expected_currency: str
    observed_amount: Optional[Decimal]
    observed_currency: Optional[str]
    observed_knowledge_state: KnowledgeState
    reconstructed_state_ids: Tuple[str, ...]
    details: Dict[str, Any]

    @property
    def is_clean_match(self) -> bool:
        return self.discrepancy_type == DiscrepancyType.MATCH

    @property
    def requires_investigation(self) -> bool:
        return self.discrepancy_type in (
            DiscrepancyType.EPISTEMIC_STALEMATE,
            DiscrepancyType.ABSENT_EXECUTION,
            DiscrepancyType.VALUE_MISMATCH,
            DiscrepancyType.EXCESS_EFFECT,
            DiscrepancyType.CONTRADICTORY_TERMINALITY,
            DiscrepancyType.ORPHANED_EXECUTION
        )
```

---

## 8. Deterministic Reconciliation Invariants

These invariants are mathematical axioms of the system. Any implementation violating them is defective:

1. **Purity & Replayability Invariant**:
   `reconcile()` is a side-effect-free, deterministic pure function:
   $$\text{reconcile}(E, R, t) = \text{reconcile}(E, R, t) \quad \forall E, R, t$$
   It must never invoke I/O, network requests, database transactions, or read un-injected system clocks.
2. **Anti-Hallucination of Absence**:
   `KnowledgeState.UNKNOWN` or absent evidence must **never** be translated into `ABSENT_EXECUTION`. Absence requires an authoritative, verified proof of non-existence.
3. **Identity Invariance**:
   Reconciliation must never synthesize, truncate, or alter `refund_intent_id`, `provider_payment_id`, or `idempotency_key`.
4. **Monotonicity of Excess**:
   Once an `EXCESS_EFFECT` or `VALUE_MISMATCH` is identified, it cannot be cleared or demoted by subsequent asynchronous events without an explicit tombstone and human sign-off.
5. **Separation of Classification from Mutation**:
   The reconciler classifies discrepancies; it **never authorizes, creates, or dispatches mutations**.

---

## 9. Interface Boundary into the V1 Control Kernel

The output of reconciliation bridges into the Incident and Control layers as follows:

```
[Internal System]             [Provider Ingress]
       │                              │
(ExpectedRefund)             (ProviderObservation)
       │                              │
       │                      [StateEngine.reconstruct]
       │                              │
       │                      (ReconstructedState)
       │                              │
       └──────────────┬───────────────┘
                      ▼
            [ReconciliationEngine]
                      │
            (ReconciliationResult)
                      │
       ┌──────────────┴──────────────┐
       │ (requires_investigation)    │ (is_clean_match)
       ▼                             ▼
   [Incident Created]           [Ledger Settled]
       │
       ├───────────────────────────────┐
       ▼                               ▼
 (DiscrepancyType:               (DiscrepancyType:
  ABSENT_EXECUTION)               EPISTEMIC_STALEMATE)
       │                               │
       ▼                               ▼
[V1 ControlPolicy]              [V1 Uncertainty Workflow]
 evaluate_refund_eligibility     resolve_refund_uncertainty
       │                               │
       ▼                               ▼
(AUTHORIZE / BLOCK)             (Query Probe → Observation)
       │                               │
       ▼                               ▼
[TransactionalOutbox]           [Re-Reconcile with Fresh State]
       │
       ▼
[Razorpay Dispatch]
       │
       ▼
(Provider Observation)
       │
       ▼
[Re-Reconcile: Terminal MATCH]
```

### Boundary Rules:
1. **`ABSENT_EXECUTION` Hand-off**:
   - When `discrepancy_type == ABSENT_EXECUTION`, an Incident is opened.
   - The incident routes the expectation to `ControlPolicy.evaluate_refund_eligibility`.
   - The policy inspects `reconstructed_state` and `provider_query_confidence == AUTHORITATIVE_NOT_EXECUTED`.
   - If eligible, it writes an `Action` to the `TransactionalOutbox`.
2. **`EPISTEMIC_STALEMATE` Hand-off**:
   - When `discrepancy_type == EPISTEMIC_STALEMATE`, an Incident is opened.
   - The incident invokes `resolve_refund_uncertainty`, which executes an active probe via `RazorpayProviderAdapter.query_refund_status`.
   - The query generates a new `ProviderObservation`.
   - The state is reconstructed, and reconciliation is re-run.
   - It transitions either to `MATCH` (if executed) or `ABSENT_EXECUTION` (if not executed), or remains stalemated (if probe failed).
3. **`MATCH` Post-Execution Hand-off**:
   - Dispatching to Razorpay does **not** terminate the product loop.
   - Only when a post-mutation observation flows through `StateEngine` and produces `ReconciliationResult.MATCH` is the Incident formally closed.

---

## 10. Adversarial Conceptual Walkthrough of Canonical Traces

We now adversarially stress-test this specification against the three canonical V1 traces.

### Trace A: Ambiguous Execution (Refund Executed but Response Lost)
1. **Initial Expectation**: `ExpectedRefund` (₹100, `ref_A`, `pay_123`, SLA: 60s).
2. **Initial Event**: Outbox dispatches `POST /payments/pay_123/refund`. Gateway drops connection (timeout).
3. **Initial Recon ($t = 10s < 60s$)**: State is `UNKNOWN`. Result: **`IN_FLIGHT_PENDING`**. No duplicate action.
4. **Subsequent Recon ($t = 70s \ge 60s$)**: State is still `UNKNOWN`. Result: **`EPISTEMIC_STALEMATE`**. 
   - *Crucial Test*: Did the reconciler declare `ABSENT_EXECUTION` and retry? **NO.** Because evidence is `UNKNOWN`, it emitted `EPISTEMIC_STALEMATE`.
5. **Investigation / Uncertainty Recovery**: Query probe runs `GET /payments/pay_123/refunds`. Razorpay returns refund with receipt `ref_A`.
6. **Observation Ingested**: `ProviderObservation(query_confidence=AUTHORITATIVE_EXECUTED)`.
7. **State Reconstructed**: `reconstructed_state.execution == EXECUTED`, `knowledge_state == VERIFIED`.
8. **Final Recon**: `reconcile(ExpectedRefund, ReconstructedState)`.
   - Result: **`MATCH`**.
   - Duplicate refunds attempted: **0**. Invariants preserved.

---

### Trace B: Safe Recovery (Ambiguous Non-Execution with Safe Retry)
1. **Initial Expectation**: `ExpectedRefund` (₹100, `ref_B`, `pay_456`, SLA: 60s).
2. **Initial Event**: Outbox dispatches `POST /payments/pay_456/refund`. Razorpay edge drops with 504. Zero execution on Razorpay.
3. **Recon ($t = 70s \ge 60s$)**: State is `UNKNOWN`. Result: **`EPISTEMIC_STALEMATE`**.
4. **Investigation / Uncertainty Recovery**: Query probe runs `GET /payments/pay_456/refunds`. Authoritative lookup confirms 0 refunds for `ref_B`.
5. **Observation Ingested**: `ProviderObservation(query_confidence=AUTHORITATIVE_NOT_EXECUTED)`.
6. **State Reconstructed**: `knowledge_state == VERIFIED`, `execution == NOT_EXECUTED`, `observed_financial_state is None`.
7. **Re-Recon**:
   - Condition: $t \ge t_{\text{deadline}}$ AND `VERIFIED` AND `NOT_EXECUTED`.
   - Result: **`ABSENT_EXECUTION`** (Actionable).
8. **Control Kernel Invocation**:
   - `ControlPolicy.evaluate_refund_eligibility` authorizes retry using the **exact same `ref_B` intent and idempotency key**.
9. **Execution**: Outbox dispatches second attempt. Succeeds. Webhook arrives.
10. **Final Recon**: State becomes `VERIFIED + EXECUTED`. Result: **`MATCH`**.
    - Total financial effects: **Exactly 1**. Invariants preserved.

---

### Trace C: Insufficient Evidence (Query Fails / Network Down)
1. **Initial Expectation**: `ExpectedRefund` (₹100, `ref_C`, `pay_789`, SLA: 60s).
2. **Initial Event**: Outbox dispatches. Ambiguous timeout.
3. **Recon ($t = 70s \ge 60s$)**: State is `UNKNOWN`. Result: **`EPISTEMIC_STALEMATE`**.
4. **Investigation / Uncertainty Recovery**: Query probe runs `GET /payments/pay_789/refunds`. Razorpay returns 500 Internal Server Error.
5. **Observation Ingested**: `ProviderObservation(query_confidence=QUERY_FAILED)`.
6. **State Reconstructed**: `knowledge_state == UNKNOWN`.
7. **Re-Recon**:
   - Condition: $t \ge t_{\text{deadline}}$ BUT `knowledge_state == UNKNOWN`.
   - Result: **`EPISTEMIC_STALEMATE`**.
8. **Control Kernel Hand-off**:
   - `resolve_refund_uncertainty` emits status `ESCALATE`.
   - No financial action is authorized. Retry is **BLOCKED**.
   - Incident remains flagged for operator investigation.
   - Safety violations: **0**. Duplicate effects: **0**. Invariants preserved.

---

## 11. Conclusion & Readiness

This specification:
1. Locks the exact domain schema for internal expectations (`ExpectedRefund`).
2. Enforces pure, replayable reconciliation via injected `reconciliation_timestamp`.
3. Mathematically prevents `UNKNOWN` from ever decaying into `ABSENT_EXECUTION`.
4. Enforces strict 1:1 cardinality for V1 while detecting excess/duplicate effects.
5. Preserves the locked V1 Control Kernel as the sole financial authority.
6. Proves complete invariant adherence across Traces A, B, and C.

**Readiness:** The domain contracts, truth tables, and boundaries are completely frozen and ready for pure, deterministic implementation.
