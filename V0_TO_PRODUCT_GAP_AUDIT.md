# V0 → Product Gap Audit

**Role:** Skeptical principal engineer + product architect + due-diligence analyst  
**Date:** 2026-09-01  
**Frozen V0 tag:** `v0.1.0-hero-flow`  
**Primary question:** *How much of the original product have we actually built?*

> **Read-only audit. No code changes. No implementation plan. Evidence sourced from the original corpus and inspected source tree.**

---

## A. Executive Conclusion

**What did we actually build?**

We built the **control kernel** of the Financial Control & Recovery product. That kernel is excellent engineering — it is the hardest, highest-risk component of the overall system, and it is genuinely production-minded. The trust boundary (AI investigates, deterministic systems authorize, atomic operations execute, independent verification closes the loop) is correctly designed, adversarially tested, and empirically validated. This is not a trivial slice.

However, the original product was not just this kernel. The PRD (§3) is explicit: *"When money enters an uncertain or contradictory state, determine what actually happened, verify the explanation using financial evidence, and—when safe—take the correct recovery action. Otherwise, escalate with the exact reason and evidence required."* The full product loop includes six stages: Observe, Understand, Verify, Decide, Act, Verify Again. V0 implements a narrow but deep vertical slice through all six stages for exactly **one discrepancy class** (`CAPTURED_PAYMENT_STALE_ORDER`) and **one recovery action** (`UNPAID → PAID` state repair).

The major structural gaps fall into four categories. First, **recovery breadth**: V0 has one repair action; the PRD explicitly describes both operational repair and monetary recovery as distinct requirements (§21). The secondary hero incident (refund with uncertain provider outcome, §13) was never implemented and is absent from the git history. Second, **escalation**: the PRD specifies a structured escalation containing 9 required fields (§25). V0's escalation output is a structured log message with a rejection reason — it is not a persistent, operator-accessible structured artifact. Third, **operator surface**: the PRD requires an operator UI (§26–27). The Next.js frontend defined in the constitution (§8) does not exist. Fourth, the secondary incident failure class (refund uncertainty, §13) was never implemented, despite being an explicit V0 requirement.

What was deliberately deferred is well-bounded by §36 (V0 Non-Goals), which explicitly excludes monetary recovery at production scale, payment retry across arbitrary providers, multi-tenant infrastructure, and distributed systems. These are correctly classified as deferred, not missing.

The original product's core thesis remains fully intact and is the right foundation for V1. Nothing needs to be redesigned. The control kernel should be extended, not replaced.

---

## B. Original Product Capability Matrix

| Capability | Original intent | V0 status | Classification | Importance |
|---|---|---|---|---|
| Webhook ingestion + signature verification | §35, 02-arch §8, §30 | `src/api/webhooks.py` — HMAC verified before parse, persisted, dispatched | IMPLEMENTED | Critical |
| Duplicate webhook idempotency | §23, §14 "Duplicate event" | `IntegrityError` on `event_id` unique constraint | IMPLEMENTED | Critical |
| Provider observation persistence (immutable) | §16, 03-domain §2 | `ProviderObservation` append-only; raw payload retained | IMPLEMENTED | Critical |
| Canonical financial state reconstruction | 03-domain §6, 02-arch §10 | Not implemented. Pipeline extracts raw payload fields inline. | ACCIDENTALLY_DROPPED | High |
| State Engine (architectural layer) | 02-arch §2 HLD | `src/state/` directory exists and is **completely empty** | ACCIDENTALLY_DROPPED | High |
| Incident Engine (architectural layer) | 02-arch §2 HLD | `src/domain/incidents/` exists and is **completely empty** | ACCIDENTALLY_DROPPED | High |
| M3 deterministic discrepancy detection | §14, PRD §10 | `M3Engine` in `src/reconciliation/` — deterministic classifier | IMPLEMENTED | Critical |
| Discrepancy class: CAPTURED_PAYMENT_STALE_ORDER | §14, §10 primary | Implemented, tested, proven | IMPLEMENTED | Critical |
| Discrepancy class: PAYMENT_NOT_CAPTURED | §14 | Implemented (classified, refused) | IMPLEMENTED | High |
| Discrepancy class: AMOUNT_MISMATCH | §14 | Implemented (classified, refused) | IMPLEMENTED | High |
| Discrepancy class: CURRENCY_MISMATCH | §14 | Implemented (classified, refused) | IMPLEMENTED | High |
| Discrepancy class: IDENTITY_UNKNOWN | §14 "Identity mismatch" | Implemented (classified, refused) | IMPLEMENTED | High |
| Discrepancy class: Duplicate event (M3 level) | §14 "Duplicate event" | Webhook-level dedup only; no M3 classification | PARTIALLY_IMPLEMENTED | Medium |
| Discrepancy class: Out-of-order event | §14 | No enum value, no test, no classification | ACCIDENTALLY_DROPPED | Medium |
| Discrepancy class: Missing event (general) | §14 "Missing event" | STALE_ORDER partially covers one case; general detection absent | PARTIALLY_IMPLEMENTED | High |
| Discrepancy class: Delayed event | §14 | Not classified at all | ACCIDENTALLY_DROPPED | Medium |
| Discrepancy class: Unknown provider outcome | §14, §13 | Never implemented; entire secondary incident absent | ACCIDENTALLY_DROPPED | High |
| Discrepancy class: Duplicate action risk | §14, §23 | Idempotency gate exists; no M3 classification | PARTIALLY_IMPLEMENTED | High |
| Discrepancy class: Stale authorization | §14, §22 | Atomic precondition check + policy freshness check | IMPLEMENTED | Critical |
| Discrepancy class: Contradictory evidence | §14 | No dedicated handling; rejected at control plane if hypothesis wrong | ACCIDENTALLY_DROPPED | Medium |
| AI hypothesis generation (M4) | §18 | `InvestigationEngine` produces structured `InvestigationProposal` | IMPLEMENTED | Critical |
| AI evidence correlation | §18 | AI receives typed `EvidencePacket`; ranks hypotheses | IMPLEMENTED | Critical |
| AI missing evidence identification | §18 | `missing_evidence_types` field in `HypothesisSelection` | IMPLEMENTED | High |
| AI confined to advisory role (no financial authority) | §6, §18 | Fully enforced — schema-validated JSON only; no DB connection | IMPLEMENTED | Critical |
| AI hallucination rejection | §18, §33 | Semantic validator + Qwen3 hallucination proven | IMPLEMENTED | Critical |
| AI unavailability safety | 02-arch §15 | Pipeline returns NO_ACTION on LLM failure | IMPLEMENTED | High |
| Deterministic verification (independent of LLM) | §19, 02-arch §12 | Control plane re-reads evidence independently | IMPLEMENTED | Critical |
| Control plane — 8 sequential invariant gates | §22, 02-arch §12 | `policy.py` L94-123 — all gates present | IMPLEMENTED | Critical |
| Atomic mutation with expected-state predicate | §22, §23 | `UPDATE ... WHERE status='UNPAID'`; rowcount == 0 → CONFLICT | IMPLEMENTED | Critical |
| TOCTOU protection | §14 "Stale authorization" | Atomic predicate catches race; returns CONFLICT | IMPLEMENTED | Critical |
| Idempotency — replay protection | §23 | Second execution on PAID order produces CONFLICT; proven 1→0→0 | IMPLEMENTED | Critical |
| Independent outcome verification | §24, §7.6 | `verify_resolution` does fresh DB read after mutation | IMPLEMENTED | Critical |
| Audit provenance log | §28 | `AuthorizationProvenance` on every decision; 6 audit stages in pipeline | IMPLEMENTED | Critical |
| Observability chain (event→outcome) | §29 | WEBHOOK_INGESTED → DISCREPANCY_DETECTED → INVESTIGATION_COMPLETED → AUTHORIZATION → MUTATION → VERIFICATION | IMPLEMENTED | High |
| Evidence provenance (source, timestamp, coverage) | §16 | `EvidenceItem` has type, content, ID, coverage enum | IMPLEMENTED | High |
| Evidence vs Claim vs Hypothesis distinction | §16, 03-domain §7 | Schema enforced; ConfidenceBand advisory only | IMPLEMENTED | High |
| DECIDE outcome: RESOLVE | §20 | ALLOW_REPAIR → state fix → verified | IMPLEMENTED | Critical |
| DECIDE outcome: RECOVER (monetary) | §20 | No monetary recovery path | DELIBERATELY_DEFERRED (§36) | High |
| DECIDE outcome: BLOCK | §20 | NO_ACTION when safety rule violated | IMPLEMENTED | Critical |
| DECIDE outcome: ESCALATE (structured, persistent) | §20, §25 | Log + provenance only; no persistent structured artifact | ACCIDENTALLY_DROPPED | High |
| Structured escalation — all 9 required fields (§25) | §25 | Only `reason` string + 4 boolean verified facts; 5 of 9 fields missing | ACCIDENTALLY_DROPPED | High |
| Escalation: hypotheses considered and rejected | §25 | Absent from control decision output | ACCIDENTALLY_DROPPED | High |
| Escalation: recommended next investigation step | §25 | Not implemented | ACCIDENTALLY_DROPPED | High |
| Operational recovery: state repair | §21, §7.4 | UNPAID → PAID atomic conditional UPDATE | IMPLEMENTED | Critical |
| Operational recovery: event reprocessing | §21, 02-arch §13 | Not implemented | ACCIDENTALLY_DROPPED | Medium |
| Monetary recovery: controlled refund execution | §21, 02-arch §13 | Not implemented | DELIBERATELY_DEFERRED (§36) | High |
| Secondary incident: refund with uncertain provider outcome | §13 | Never implemented; absent from all commits | ACCIDENTALLY_DROPPED | High |
| UNKNOWN outcome state (not FAILED, not SUCCESS) | §7.3, §24 | No explicit UNKNOWN state; CONFLICT covers race only | ACCIDENTALLY_DROPPED | High |
| Provider state freshness re-check at execution time | §24 | Evidence gathered once at investigation; no re-check at action time | ACCIDENTALLY_DROPPED | High |
| Operator experience — active incident view | §26 | No UI, no API endpoint for incident listing | ACCIDENTALLY_DROPPED | Critical |
| Operator experience — evidence timeline / hypothesis inspection | §26, §27 | Not implemented | ACCIDENTALLY_DROPPED | High |
| Frontend (Next.js) | 00-constitution §8, 02-arch §5 | Not implemented | ACCIDENTALLY_DROPPED | High |
| PostgreSQL-backed durable job/outbox | 02-arch §9 | FastAPI `BackgroundTasks` used — not durable | ACCIDENTALLY_DROPPED | Medium |
| `Incident` domain entity + lifecycle | 03-domain §2, §8 | `src/domain/incidents/` is empty; no DB model | ACCIDENTALLY_DROPPED | High |
| `Action` entity with idempotency identity | 03-domain §9 | No persistent Action record | ACCIDENTALLY_DROPPED | Medium |
| `Refund` entity | 03-domain §2 | `src/domain/refunds/` is empty | ACCIDENTALLY_DROPPED | High |
| Canonical `Payment` domain entity | 03-domain §2 | Only `ProviderPayment` dataclass in reconciliation module | PARTIALLY_IMPLEMENTED | High |
| Integer minor-unit monetary representation | 03-domain §5 | `amount: int` throughout; no float arithmetic | IMPLEMENTED | High |
| Razorpay API integration (payment retrieval) | §35 | `src/integrations/razorpay/client.py` exists | IMPLEMENTED | High |
| Adversarial: LLM hallucinated hypothesis | §33 | Proven with Qwen3 | IMPLEMENTED | Critical |
| Adversarial: TOCTOU concurrent attempt | §33 | Proven via test script | IMPLEMENTED | Critical |
| Adversarial: duplicate webhook | §33 | Tested via IntegrityError path | IMPLEMENTED | High |
| Adversarial: wrong payment/order ID | §33 | PAYMENT_ORDER_IDENTITY_UNKNOWN handles this | IMPLEMENTED | High |
| Adversarial: provider timeout / lost response | §33 | Not tested | ACCIDENTALLY_DROPPED | Medium |
| Adversarial: LLM unavailable | §33 | Pipeline returns NO_ACTION | IMPLEMENTED | High |
| Batch evaluation (50-record) | Track 4 | `run_batch_evaluation.py` with oracle conformance | IMPLEMENTED | High |

---

## C. Failure-Class Coverage Matrix

| Failure class | Originally intended? | M3 classification? | M4 investigation? | Deterministic control? | Recovery? | Escalation? |
|---|---|---|---|---|---|---|
| CAPTURED_PAYMENT_STALE_ORDER | ✅ Primary hero | ✅ | ✅ | ✅ | ✅ State repair | ⚠️ Log only |
| PAYMENT_NOT_CAPTURED | ✅ §14 | ✅ | ✅ (mocked in batch) | ✅ (refuses) | ❌ | ⚠️ Log only |
| AMOUNT_MISMATCH | ✅ §14 | ✅ | ✅ (mocked) | ✅ (refuses) | ❌ | ⚠️ Log only |
| CURRENCY_MISMATCH | ✅ §14 | ✅ | ✅ (mocked) | ✅ (refuses) | ❌ | ⚠️ Log only |
| IDENTITY_UNKNOWN | ✅ §14 | ✅ | ✅ (mocked) | ✅ (refuses) | ❌ | ⚠️ Log only |
| Duplicate event | ✅ §14 | ⚠️ Webhook-level only | ❌ | ❌ | ❌ | ❌ |
| Out-of-order event | ✅ §14 | ❌ | ❌ | ❌ | ❌ | ❌ |
| Missing event (general) | ✅ §14 | ⚠️ One case via STALE_ORDER | ❌ | ❌ | ❌ | ❌ |
| Delayed event | ✅ §14 | ❌ | ❌ | ❌ | ❌ | ❌ |
| Unknown provider outcome (refund) | ✅ §13, §14 | ❌ | ❌ | ❌ | ❌ | ❌ |
| Duplicate action risk | ✅ §14, §23 | ❌ explicit | ⚠️ Idempotency gate only | ✅ CONFLICT | ❌ | ⚠️ Log only |
| Stale authorization | ✅ §14, §22 | ❌ explicit | N/A | ✅ Atomic predicate | N/A | ❌ |
| Contradictory evidence | ✅ §14 | ❌ | ❌ | ⚠️ Fails control if hypothesis wrong | ❌ | ❌ |
| Invalid webhook | ✅ §14 | ⚠️ Caught at API layer | ❌ | ✅ Rejected before M3 | ❌ | ❌ |

---

## D. State-Machine Gap

### Original intended incident states (PRD §15, 03-domain §8)

```
DETECTED
   ↓
INVESTIGATING
   ↓
EVIDENCE_GATHERED
   ↓
VERIFICATION
   ↓
VERIFIED / UNCERTAIN / CONTRADICTED
   ↓
RESOLUTION_DECISION
   ↓
ACTION / ESCALATION
   ↓
OUTCOME_VERIFICATION
   ↓
RESOLVED / RECOVERED / ESCALATED / BLOCKED
```

### Actual V0 states

There is no state machine. There are no `Incident` database records. The pipeline is a single async function that returns a dict. Merchant order status toggles `UNPAID → PAID`. Pipeline terminal states:

```
"NO_ACTION"   (no discrepancy, or control refusal)
"RESOLVED"    (state repair succeeded and independently verified)
"CONFLICT"    (TOCTOU race at atomic precondition)
```

The intermediate states (INVESTIGATING, EVIDENCE_GATHERED, VERIFICATION, VERIFIED/UNCERTAIN/CONTRADICTED) exist only as audit log event strings, not as persistent state machine transitions on any domain entity.

**The gap:** No `Incident` entity, no persistent incident lifecycle, no `ESCALATED` state, no `RECOVERED` state distinct from `RESOLVED`, no `BLOCKED` state with persistent record.

---

## E. Recovery Gap

### Originally intended recovery actions (§21, §13, 02-arch §13)

| Recovery action | PRD source | Implemented? |
|---|---|---|
| Operational recovery: state repair | §21, §7.4 | ✅ UNPAID → PAID |
| Operational recovery: event reprocessing | 02-arch §13 | ❌ |
| Operational recovery: surface missing evidence | §21 | ❌ |
| Controlled refund execution | §21, 02-arch §13 | ❌ |
| Secondary incident — refund uncertainty resolution (no blind retry) | §13 | ❌ |
| Escalation as an explicit recovery outcome | §20, §25 | ⚠️ Partial |

**Critical PRD distinction (§21):** *A monetary action requires a higher safety threshold than an operational state repair.* V0 has the lower-threshold operational state repair correctly implemented. The higher-threshold monetary path is absent, not merely skipped.

**The secondary incident (§13) is the most important accidentally dropped requirement.** It was the single V0 case requiring UNKNOWN provider outcome handling, non-blind retry, and durable idempotency identity. Its absence means V0 never proved it could handle genuinely ambiguous failure states.

---

## F. Escalation Gap

### Original intent — §25 "Human-in-the-Loop" (9 required fields)

1. Incident summary
2. Financial entities involved
3. Verified evidence
4. Unresolved evidence
5. Hypotheses considered
6. Hypotheses rejected
7. Reason automation was blocked
8. Recommended next investigation step
9. Required human action

> *"Give the human the exact evidence required to make the remaining decision."*

### V0 actual escalation

`AuthorizationProvenance` contains: `incident_id`, `m3_discrepancy`, `m4_hypothesis` (top rank-1 only), `semantic_validation` (status string), `verified_facts` (4 boolean flags), `control_rule`, `fresh_merchant_state`, `authorized=False`, `reason` (single string). Emitted as a structured audit log event; no persistent DB record; no API endpoint; not operator-accessible.

**Present:** fields 1 (partial), 3 (partial), 7. **Absent:** 2, 4, 5, 6, 8, 9.

**Classification: ACCIDENTALLY_DROPPED.** §25 is a V0 requirement; 00-constitution §4 explicitly lists "escalation when evidence is insufficient" as a V0 deliverable.

---

## G. Track 4 / Track 3 Coverage

### Track 4 — Understand and verify financial state

| Capability | Status |
|---|---|
| 50+ record synthetic batch | ✅ |
| Reconciliation match rate (labeled) | ✅ 54.0% |
| Classification oracle conformance | ✅ 100% |
| Controller outcome conformance | ✅ 100% |
| Exception list with reasons | ✅ |
| Throughput measurement | ✅ |
| Trust boundary demonstration | ✅ |
| Operator-accessible incident view | ❌ |

**Track 4 status: STRONG on mechanics. Absent on operator product surface.**

### Track 3 — Safely recover what can be recovered

| Capability | Status |
|---|---|
| State repair (non-monetary) | ✅ |
| Measured resolved cases (8/50) | ✅ |
| Stopping rules (refusal + TOCTOU) | ✅ |
| Audit trail per decision | ✅ |
| Revenue recovery | ❌ |
| General monetary recovery | ❌ Deliberately deferred |
| Multi-class recovery workflow | ⚠️ One class only |

**Track 3 status: NOT claimable as a general Track 3 submission.**

---

## H. What We Accidentally Lost

These are V0 requirements — not in §36 Non-Goals — that disappeared during implementation without an explicit architectural decision to defer them.

| Dropped requirement | PRD source | Impact |
|---|---|---|
| Secondary incident: refund with uncertain provider outcome | §13 "Required behavior" | Proves UNKNOWN state handling; hardest V0 class |
| Incident domain entity + persistent lifecycle state machine | 03-domain §2, §8 | No audit trail for operators; no reopenable incident |
| Structured escalation packet (all 9 §25 fields) | §25 | Escalation is invisible log event, not a product outcome |
| Operator frontend (Next.js) | 00-constitution §8, 02-arch §5 | No operator surface at all |
| State Engine and Incident Engine as architectural layers | 02-arch §2 HLD | Both directories empty; pipeline performs their role ad hoc |
| Persistent Action entity with idempotency identity | 03-domain §9 | Action deduplication not durable across restarts |
| Transactional outbox / durable background processor | 02-arch §9 | Worker crash loses in-flight investigations |
| Out-of-order event classification | §14 | Not even a stub |
| Delayed event classification | §14 | Not even a stub |
| Unknown provider outcome classification | §14, §13 | UNKNOWN epistemic state absent from M3 entirely |
| Provider state freshness re-check at action execution time | §24 | Evidence gathered once at investigation; not re-verified before mutation |
| `Refund` entity | 03-domain §2 | `src/domain/refunds/` empty |
| UNKNOWN outcome state representation | §7.3, §24 | No explicit UNKNOWN state; only CONFLICT and NO_ACTION |

---

## I. What We Should NOT Build

| Item | Reason |
|---|---|
| Generic vector-search RAG for evidence | §36 Non-Goal. Semantic similarity prohibited for financial identity (03-domain §4). |
| Autonomous multi-agent orchestration | §36 Non-Goal. Violates core AI boundary principle. |
| Predictive fraud detection | §36 Non-Goal. Different domain entirely. |
| Generic workflow/rules DSL with pluggable rules | §36 + 00-constitution §103. Rules must be explicit and auditable, not configurable at runtime. |
| Kafka / RabbitMQ broker (for V1) | Use PostgreSQL outbox first per 02-arch §9 and §16. Broker only if outbox proves inadequate. |
| Multi-tenant SaaS infrastructure | §36 Non-Goal. |
| Complete financial ledger replacement | §36 Non-Goal. |
| Enterprise reporting suite | §36 Non-Goal. |
| Learning loop that modifies financial authorization rules | AI cannot override deterministic controls. Learning may influence recommendations only. |
| Checkout abandonment / subscription / receivables recovery | Not in PRD §36, but also not in the PRD domain model or requirements. These are §37 "Future Direction" items only. Require a separate PRD before V1 scope. |

---

## J. V1 Product Boundary

The smallest coherent V1 that transforms V0 into the original product, based strictly on ACCIDENTALLY_DROPPED V0 requirements:

**V1 must implement (in dependency order):**

1. **Secondary incident: refund uncertainty (§13)** — dropped V0 requirement. Needs new M3 class, new M4 hypothesis types, UNKNOWN outcome state, non-blind provider re-query, durable idempotency identity.

2. **Persistent Incident domain entity + lifecycle state machine** — every subsequent capability depends on incidents having persistent identity and traversable lifecycle.

3. **Structured escalation packet (§25 — all 9 fields)** — must be a persistent DB record accessible via API, not a log event.

4. **Persistent Action entity with idempotency identity** — prerequisite for any monetary recovery path and for durable deduplication.

5. **Operator frontend (Next.js — §26, §27)** — the product surface. Without it the system is a CLI tool.

6. **Controlled refund execution (monetary recovery, §21)** — depends on Action entity (step 4) for idempotency and Incident entity (step 2) to track outcome.

**V1 may also include:**

7. Expanded M3 classification: out-of-order, delayed, unknown provider outcome class.
8. Durable transactional outbox replacing FastAPI `BackgroundTasks`.
9. Provider state freshness re-check at action execution time.
10. Canonical State Engine and Incident Engine architectural layers.

---

## K. Recommended Build Order

```
V0 Control Kernel (DONE — v0.1.0-hero-flow)
        │
        ▼
[1] Secondary Incident — Refund Uncertainty (§13)
    Reason: Dropped V0 requirement. Proves UNKNOWN state handling.
    All monetary recovery paths require this pattern.
        │
        ▼
[2] Incident Domain Entity + Lifecycle State Machine (03-domain §8)
    Reason: Escalation, actions, frontend all require persistent incidents.
        │
        ▼
[3] Structured Escalation — all 9 §25 fields (persistent DB record)
    Reason: Second outcome path alongside RESOLVE. Required for operator product.
        │
        ▼
[4] Persistent Action Entity + Idempotency Identity (03-domain §9)
    Reason: Prerequisite for any monetary recovery path.
        │
        ▼
[5] Operator Frontend (Next.js — §26, §27)
    Reason: The product surface. Incidents, evidence timelines, escalations.
        │
        ▼
[6] Controlled Refund Execution (§21 monetary recovery)
    Reason: Depends on steps 2 and 4. First genuine monetary recovery action.
        │
        ▼
[7] Expanded M3 Classification (out-of-order, delayed, unknown outcome)
    Reason: Broader detection. Does not require frontend or action changes.
        │
        ▼
[8] Architectural cleanup: State Engine, Incident Engine layers
    Reason: Replace inline pipeline payload extraction. Not urgent but required pre-production.
```

> **The governing principle for every step remains unchanged:**
>
> *AI investigates. Deterministic controls decide. Atomic systems execute. Independent verification proves the outcome.*
>
> No step requires redesigning the control kernel. It is extended, not replaced.

---

*Audit complete. Read-only. No code changes made.*
