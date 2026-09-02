# V1 Architectural Decisions (Extracted from historical documents)

## 1. Idempotency Anchor
- **Decision:** The production database invariant for idempotency is anchored directly to the `refund_intent_id`, ensuring at most one executable action is committed for the stable refund intent identity represented by that key.
- **Context:** Provenance is evidence of authorization reasoning, not financial intent.

## 2. Refund Retry Eligibility
- **Decision:** `NOT_REFUNDED` ≠ `PROVEN_NOT_EXECUTED`. A refund retry is only eligible if the state is explicitly `PROVEN_NOT_EXECUTED` (Authoritative Not Executed).
- **Context:** An epistemic gap exists where a network failure can leave a transaction in an `UNKNOWN` state. The FCE refuses to retry unless the lack of financial effect is authoritatively proven by the provider.

## 3. Strict Separation of Investigation and Control
- **Decision:** AI (M4) is relegated purely to semantic orchestration and advisory hypotheses. 
- **Context:** The Control Plane (ControlPolicy) must independently evaluate deterministic facts (e.g., `KnowledgeState`, `ExecutionState`, `ProviderQueryConfidence`) to authorize any financial mutation. AI output must never bypass this evaluation.

## 4. Authorization Provenance
- **Decision:** Every execution must emit a structured, immutable `AuthorizationProvenance` log.
- **Context:** An auditor must be able to look at any resolved order and see exactly what deterministic facts authorized the mutation, independently of what the AI said.

*For full historical context, see the documents in `docs/historical/`.*
