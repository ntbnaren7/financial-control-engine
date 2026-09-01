# Security & Threat Model Lock (v0.1.0-hero-flow)

This document formalizes the exact security boundaries and safety guarantees established in the V0 architecture of the Financial Control Engine.

## Architectural Security Premise

**"AI investigates. Deterministic controls decide. Atomic systems execute. Independent verification proves the outcome."**

The V0 system actively treats the underlying Large Language Model (M4) as an untrusted, highly capable reasoning engine that is prone to hallucination, non-determinism, and adversarial manipulation. 

## What V0 Guarantees

1. **LLM cannot directly mutate financial state.** The AI outputs a JSON `InvestigationProposal`, which is purely advisory.
2. **LLM output cannot bypass deterministic validation.** All AI output is strictly validated against a known semantic schema, and hallucinated evidence IDs or structurally invalid outputs are hard-rejected.
3. **Financial mutation requires deterministic authorization.** A hard-coded control plane (`src/control/policy.py`) executes an independent read of the original evidence packet and evaluates strict admissibility rules before returning an `ALLOW_REPAIR` token.
4. **Mutation requires expected-state predicate.** The SQL mutation is bounded by a conditional `UPDATE` matching the exact primary key and expecting the exact prior state (`status='UNPAID'`). 
5. **Concurrent state changes produce conflict rather than false success.** Because of the atomic database predicate, TOCTOU (Time-Of-Check to Time-Of-Use) race conditions result in a `rowcount == 0` rollback, returning `CONFLICT` instead of a false positive success.
6. **Successful resolution requires independent verification.** The orchestration pipeline executes a fresh database read *after* the mutation commits to guarantee the data layer accepted the change and matches the intended target state.
7. **Replay does not produce another financial mutation.** Stale, duplicate, or malformed webhook replays are idempotently blocked by the `UNPAID` gate.

## What V0 Does NOT Claim

The current scope is tightly bounded. To prevent misrepresentation in production reviews, V0 explicitly **does not** claim to solve:

- Generalized autonomous financial operations
- Distributed durable workflow guarantees (currently executed within a basic async event loop)
- Production-scale throughput
- Multi-tenant authorization
- Complete fraud detection
- Arbitrary payment-state repair
- Zero possibility of infrastructure failure (node crashes mid-execution will safely abort without state corruption, but lack durable queues for guaranteed resumption in V0)

## Authorization Provenance
Every successful repair emits a structured, immutable `AuthorizationProvenance` record representing the deterministic facts (e.g. `payment_captured=True`, `merchant_status=UNPAID`) that authorized the mutation, entirely separate from the LLM's rationale.
