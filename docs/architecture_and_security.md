# Architecture & Security Guarantees

## 1. The 7-Stage Control Architecture

The Financial Control Engine (FCE) pipeline is explicitly designed to isolate probabilistic AI reasoning from deterministic financial execution.

```
01 DETECT ➔ 02 INVESTIGATE ➔ [ D4 BOUNDARY ] ➔ 03 VERIFY ➔ 04 DECIDE ➔ 05 ACT ➔ 06 RE-OBSERVE ➔ 07 OUTCOME
```

| Stage | Name | Worker | Core Operation | Deterministic Invariant |
| :---: | :--- | :--- | :--- | :--- |
| **01** | `DETECT` | Deterministic Kernel | Pure state comparison: Ledger vs Provider | Flags `STATE_MISMATCH` with 0% AI invocation |
| **02** | `INVESTIGATE` | Local LLM (`qwen3:8b`) | Analyzes 4 SHA-256 hashed evidence records | Proposes structured `CausalHypothesis` |
| **03** | `VERIFY` | Deterministic Verifier | Validates citations + queries Razorpay API | Halts on ungrounded IDs; proves external fact |
| **04** | `DECIDE` | Governance Gate | Evaluates policy + checks budget & kill-switch | Blocks action if budget exceeded or switch flipped |
| **05** | `ACT` | Idempotent Actuator | Claims OCC CAS lease (`v1 → v2`) + dispatches refund | Deterministic idempotency key prevents double spend |
| **06** | `RE-OBSERVE` | Provider Gateway | Re-polls Razorpay API post-mutation | Verifies external status actually flipped to `refunded` |
| **07** | `OUTCOME` | State Substrate | Re-runs kernel on fresh facts; commits audit trail | Transitions to `RESOLVED`; seals cryptographic record |

---

## 2. Safety Guarantees & Control Mechanisms

| Operational Risk | Control Mechanism | Technical Enforcement |
| :--- | :--- | :--- |
| **LLM Hallucination** | D4 Referential Validator | Rejects any hypothesis citing evidence IDs outside the bounded case |
| **Prompt Injection** | Isolated Verifier | Target parameters derived strictly from verified case records, never model text |
| **Runaway Spend** | Governance Gate | Action budget enforcement and emergency kill-switch |
| **Race Conditions** | Optimistic Concurrency (OCC) | Atomic CAS version increments (`v1 → v2`) prevent concurrent multi-worker execution |
| **Network Duplication** | Deterministic Idempotency | SHA-256 idempotency key (`idem_refund_{id}_v{version}`) persisted prior to call |
| **Silent Provider Failure** | Post-Action Re-Observation | Return codes (HTTP 200) not trusted; external ledger re-polled for proof |
| **Missing / Ambiguous Data** | Honest Escalation | Refuses to guess on 404s or amount mismatches; escalates to human review |
