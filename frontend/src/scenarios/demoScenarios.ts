import type { ScenarioDefinition, ScenarioPresetId } from '../types';

export const DEMO_SCENARIOS: Record<ScenarioPresetId, ScenarioDefinition> = {
  SCENARIO_A: {
    id: 'SCENARIO_A',
    name: 'Autonomous Refund & Convergence',
    shortTag: 'Scenario A: Autonomous Repair',
    badgeColor: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
    description: 'Merchant cancelled order while Razorpay captured payment. FCE detects mismatch, verifies provider, obtains governance authorization, executes refund, and confirms convergence.',
    paymentId: 'pay_3819482701',
    orderId: 'ord_5601928472',
    amount: 4500,
    currency: 'INR',
    discrepancyReason: 'STATE_MISMATCH',
    expectedStatus: 'SETTLED',
    observedStatus: 'PENDING',
    terminalState: 'RESOLVED',
    stages: {
      DETECT: {
        stageId: 'DETECT',
        title: 'Deterministic Reconciliation',
        headline: 'Reconciliation Engine detected financial discrepancy between ledger and provider',
        whyThisHappened: 'Internal merchant order state is SETTLED, but incoming Razorpay webhook reports PENDING.',
        authorityBadge: { text: 'DETERMINISTIC CONTROL (0% LLM)', domain: 'DETERMINISTIC' },
        detectData: {
          expected: {
            id: 'exp_ord_5601928472',
            source: 'merchant_order_ledger',
            status: 'SETTLED',
            amount: 4500,
            currency: 'INR'
          },
          observed: {
            id: 'obs_pay_3819482701',
            provider: 'razorpay_webhook',
            status: 'PENDING',
            amount: 4500,
            currency: 'INR'
          },
          discrepancyType: 'STATE_MISMATCH',
          differenceSummary: 'Expected state (SETTLED) ≠ Observed provider state (PENDING). Both agree on amount ₹4,500.'
        }
      },
      INVESTIGATE: {
        stageId: 'INVESTIGATE',
        title: 'Bounded AI Investigation (A3)',
        headline: 'Local LLM reasoned over strictly bounded evidence context',
        whyThisHappened: 'Discrepancy escalated to A3 Investigator to propose causal hypothesis and verification intent.',
        authorityBadge: { text: 'UNTRUSTED AI REASONING (AUTHORITY: NONE)', domain: 'UNTRUSTED_AI' },
        investigateData: {
          boundedEvidence: [
            {
              id: 'ev_expectation_01',
              type: 'EXPECTATION',
              source: 'merchant_order_ledger',
              summary: 'Order ord_5601928472 cancelled with settlement expectation',
              payloadHash: '7f9c2d1b8e4f3a60a8c51234abcd5678ef0123456789abcdef0123456789abcd',
              timestamp: '10:14:02 UTC'
            },
            {
              id: 'ev_observation_01',
              type: 'OBSERVATION',
              source: 'razorpay_webhook',
              summary: 'Webhook payment.captured received with status pending',
              payloadHash: '3a1b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b',
              timestamp: '10:14:05 UTC'
            },
            {
              id: 'ev_payment_01',
              type: 'PAYMENT_METADATA',
              source: 'internal_payment_index',
              summary: 'Payment pay_3819482701 linked to customer cust_9921',
              payloadHash: '9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d',
              timestamp: '10:14:06 UTC'
            },
            {
              id: 'ev_order_01',
              type: 'ORDER_LIFECYCLE',
              source: 'ecommerce_backend',
              summary: 'Inventory returned to warehouse prior to settlement',
              payloadHash: '2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d',
              timestamp: '10:14:07 UTC'
            }
          ],
          llmOutput: {
            hypothesis: 'Provider state webhook lagged behind gateway capture; merchant cancelled order while settlement batch remained open. Payment requires refund to reconcile ledger.',
            confidence: 0.94,
            verificationIntent: 'READ_PAYMENT_STATE',
            targetId: 'pay_3819482701',
            referencedEvidenceIds: ['ev_expectation_01', 'ev_observation_01', 'ev_payment_01', 'ev_order_01'],
            authorityGranted: 'NONE'
          }
        }
      },
      VERIFY: {
        stageId: 'VERIFY',
        title: 'Deterministic Verification & D4 Gate (A4)',
        headline: 'D4 validated LLM containment; DeterministicVerifier queried Razorpay API',
        whyThisHappened: 'LLM reasoning cannot execute mutations. The engine verified provider ground truth deterministically.',
        authorityBadge: { text: 'DETERMINISTIC MACHINE TRUTH', domain: 'DETERMINISTIC' },
        verifyData: {
          d4Validation: {
            passed: true,
            evidenceContainmentValid: true,
            schemaValid: true,
            intentPermitted: true,
            providerQueryPermitted: true,
            mutationAuthority: 'DENIED'
          },
          providerVerification: {
            providerQueried: 'Razorpay Payments API v1',
            endpoint: 'GET /v1/payments/pay_3819482701',
            responseStatus: 200,
            providerPaymentStatus: 'captured',
            amount: 4500,
            currency: 'INR',
            captured: true,
            evidenceIdGenerated: 'ev_verified_provider_01',
            evidenceHash: 'b5f8c3d2e1a49076bcde891234567890abcdef1234567890abcdef1234567890'
          }
        }
      },
      DECIDE: {
        stageId: 'DECIDE',
        title: 'Policy Evaluation & Governance Gate',
        headline: 'Deterministic recovery policy matched; Governance Gate authorized mutation quota',
        whyThisHappened: 'Verified payment state captured + merchant cancelled order maps to REFUND_PAYMENT policy.',
        authorityBadge: { text: 'GOVERNANCE GATEWAY (HARD LIMITS)', domain: 'DETERMINISTIC' },
        decideData: {
          policyAction: 'REFUND_PAYMENT',
          decisionReason: 'Merchant cancelled order ord_5601928472 + Provider captured ₹4,500 requires full customer refund.',
          governance: {
            killSwitchState: 'RUNNING',
            budgetAvailable: true,
            budgetUsed: 4500,
            budgetLimit: 1000000,
            currency: 'INR',
            policyMatched: 'RULE_MERCHANT_CANCELLED_PROVIDER_CAPTURED',
            mutationAllowed: true
          }
        }
      },
      ACT: {
        stageId: 'ACT',
        title: 'Idempotent Actuation',
        headline: 'OCC lease acquired; refund dispatched with cryptographic idempotency key',
        whyThisHappened: 'Governance authorized refund mutation. FCE acquired OCC lock to guarantee single-execution semantics.',
        authorityBadge: { text: 'OCC IDEMPOTENT ACTUATOR', domain: 'DETERMINISTIC' },
        actData: {
          actuation: {
            occVersion: { from: 1, to: 2, acquired: true },
            idempotencyKey: 'idem_refund_pay_3819482701_v1',
            mutationDispatched: 'POST /v1/payments/pay_3819482701/refund',
            targetId: 'pay_3819482701',
            resultStatus: 'SUCCEEDED',
            refundId: 'rfnd_019482710398'
          }
        }
      },
      REOBSERVE: {
        stageId: 'REOBSERVE',
        title: 'Fresh Re-observation & Convergence Check',
        headline: 'Queried Razorpay post-mutation; confirmed external state convergence',
        whyThisHappened: 'FCE does not assume mutation succeeded. It re-observes the external provider to prove convergence.',
        authorityBadge: { text: 'CONVERGENCE VERIFICATION', domain: 'DETERMINISTIC' },
        reobserveData: {
          reobservation: {
            rePolledState: 'REFUNDED',
            reconciliationOutcome: 'MATCH',
            converged: true,
            terminalState: 'RESOLVED'
          }
        }
      },
      TERMINAL: {
        stageId: 'TERMINAL',
        title: 'Incident Resolved',
        headline: 'Closed-loop control completed successfully without human intervention',
        whyThisHappened: 'Provider refund confirmed. Ledger and Razorpay are now 100% reconciled.',
        authorityBadge: { text: 'CONTROL LOOP CONVERGED', domain: 'DETERMINISTIC' },
        terminalData: {
          finalState: 'RESOLVED',
          resolutionSummary: 'Autonomous refund of ₹4,500 completed via rfnd_019482710398. Both internal ledger and Razorpay reflect settlement/refund convergence.',
          isRemediated: true
        }
      }
    },
    proofsByStage: {
      DETECT: [
        {
          id: 'proof_recon_01',
          stageId: 'DETECT',
          title: 'A1 — Deterministic Reconciliation',
          subtitle: 'Engine compared expectations against canonical observations',
          status: 'VALID',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Comparison Engine', value: 'V2ReconciliationEngine (Deterministic)' },
            { label: 'Expected Status', value: 'SETTLED' },
            { label: 'Observed Status', value: 'PENDING' },
            { label: 'Discrepancy Code', value: 'STATE_MISMATCH', isFlag: true }
          ]
        }
      ],
      INVESTIGATE: [
        {
          id: 'proof_inv_01',
          stageId: 'INVESTIGATE',
          title: 'A3 — Bounded AI Investigation',
          subtitle: 'Substrate assembled bounded evidence context for Local LLM',
          status: 'VALID',
          authority: 'UNTRUSTED_AI',
          details: [
            { label: 'Input Records', value: '4 strictly bounded evidence objects' },
            { label: 'LLM Authority', value: 'NONE (Zero financial mutation access)', isFlag: true },
            { label: 'Direct Gateway Access', value: 'BLOCKED (Must route via Verifier)' },
            { label: 'Proposed Intent', value: 'READ_PAYMENT_STATE' }
          ]
        }
      ],
      VERIFY: [
        {
          id: 'proof_d4_01',
          stageId: 'VERIFY',
          title: 'D4 — Deterministic Output Validation',
          subtitle: 'Enforced syntactic and referential containment invariants',
          status: 'VALID',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Referenced IDs Exist', value: '4/4 valid in substrate context' },
            { label: 'Output Schema', value: 'Valid Pydantic model' },
            { label: 'Intent Permitted', value: 'READ_PAYMENT_STATE (Permitted)' },
            { label: 'Mutation Authority', value: 'DENIED (Read-only query allowed)' }
          ]
        },
        {
          id: 'proof_a4_01',
          stageId: 'VERIFY',
          title: 'A4 — Deterministic Provider Verification',
          subtitle: 'Direct runtime query to Razorpay API',
          status: 'VALID',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Gateway Endpoint', value: 'GET /v1/payments/pay_3819482701' },
            { label: 'HTTP Status', value: '200 OK' },
            { label: 'Provider State', value: 'captured = true' },
            { label: 'Evidence Persisted', value: 'ev_verified_provider_01 (SHA256 hashed)' }
          ]
        }
      ],
      DECIDE: [
        {
          id: 'proof_gov_01',
          stageId: 'DECIDE',
          title: 'Governance Gate Authorization',
          subtitle: 'Evaluated system kill switch, quotas, and action blast radius',
          status: 'VALID',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'System Kill Switch', value: 'RUNNING (Active)' },
            { label: 'Action Budget Check', value: '₹4,500 <= ₹10,00,000 daily limit' },
            { label: 'Recovery Policy', value: 'REFUND_PAYMENT' },
            { label: 'Mutation Gate', value: 'APPROVED' }
          ]
        }
      ],
      ACT: [
        {
          id: 'proof_act_01',
          stageId: 'ACT',
          title: 'Idempotent Actuation',
          subtitle: 'OCC lease acquired & idempotency key persisted before mutation',
          status: 'VALID',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'OCC Version', value: '1 → 2 (Atomic CAS lease)' },
            { label: 'Idempotency Key', value: 'idem_refund_pay_3819482701_v1' },
            { label: 'Provider Mutation', value: 'POST /v1/payments/pay_381.../refund' },
            { label: 'Gateway Transaction ID', value: 'rfnd_019482710398' }
          ]
        }
      ],
      REOBSERVE: [
        {
          id: 'proof_reo_01',
          stageId: 'REOBSERVE',
          title: 'Fresh Re-observation & Convergence Proof',
          subtitle: 'Independent query confirmed external state converged',
          status: 'VALID',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Post-Mutation Poll', value: 'GET /v1/payments/pay_381...' },
            { label: 'Fresh Provider State', value: 'refunded' },
            { label: 'Re-reconciliation', value: 'MATCH (Discrepancy cleared)' },
            { label: 'Loop Status', value: 'CONVERGED', isFlag: true }
          ]
        }
      ],
      TERMINAL: [
        {
          id: 'proof_term_01',
          stageId: 'TERMINAL',
          title: 'Terminal Convergence Resolution',
          subtitle: 'Financial discrepancy reconciled with verified audit trail',
          status: 'VALID',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Final Incident State', value: 'RESOLVED' },
            { label: 'Audit Timeline', value: '6 stages executed, 0 retries' },
            { label: 'Operator Action Required', value: 'NONE (Autonomous)' }
          ]
        }
      ]
    }
  },

  SCENARIO_B: {
    id: 'SCENARIO_B',
    name: 'Missing Evidence (Provider 404)',
    shortTag: 'Scenario B: Missing 404 Escalation',
    badgeColor: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
    description: 'Internal ledger expects payment pay_miss_057, but Razorpay returns 404 Not Found. FCE halts actuation and safely escalates.',
    paymentId: 'pay_miss_057',
    orderId: 'ord_miss_057',
    amount: 6700,
    currency: 'INR',
    discrepancyReason: 'ABSENT_EXECUTION',
    expectedStatus: 'SETTLED',
    observedStatus: 'UNKNOWN',
    terminalState: 'ESCALATED_MISSING_EVIDENCE',
    stages: {
      DETECT: {
        stageId: 'DETECT',
        title: 'Deterministic Reconciliation',
        headline: 'Reconciliation detected absence of provider payment execution.',
        whyThisHappened: 'Internal order ord_missing_88210 created, but no matching provider event found.',
        authorityBadge: { text: 'DETERMINISTIC CONTROL', domain: 'DETERMINISTIC' },
        detectData: {
          expected: {
            id: 'ord_missing_88210',
            source: 'merchant_order_ledger',
            status: 'SETTLED',
            amount: 6700,
            currency: 'INR'
          },
          observed: {
            id: '-',
            provider: 'razorpay',
            status: 'UNKNOWN',
            amount: 0,
            currency: 'INR'
          },
          discrepancyType: 'ABSENT_EXECUTION',
          differenceSummary: 'Expected payment execution for ₹6,700, but no matching provider event exists in substrate.'
        }
      },
      INVESTIGATE: {
        stageId: 'INVESTIGATE',
        title: 'Bounded AI Investigation (A3)',
        headline: 'LLM proposed verifying whether payment exists on external gateway',
        whyThisHappened: 'LLM generated hypothesis that payment was created but webhook dropped.',
        authorityBadge: { text: 'UNTRUSTED AI REASONING (AUTHORITY: NONE)', domain: 'UNTRUSTED_AI' },
        investigateData: {
          boundedEvidence: [
            {
              id: 'ev_expectation_b1',
              type: 'EXPECTATION',
              source: 'merchant_order_ledger',
              summary: 'Expected payment of ₹2,100 for order ord_missing_88210',
              payloadHash: '4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b',
              timestamp: '10:20:00 UTC'
            }
          ],
          llmOutput: {
            hypothesis: 'Payment may have succeeded on Razorpay without webhook delivery. Verify pay_missing_404_99 directly.',
            confidence: 0.78,
            verificationIntent: 'READ_PAYMENT_STATE',
            targetId: 'pay_missing_404_99',
            referencedEvidenceIds: ['ev_expectation_b1'],
            authorityGranted: 'NONE'
          }
        }
      },
      VERIFY: {
        stageId: 'VERIFY',
        title: 'Deterministic Verification (404 Not Found)',
        headline: 'Razorpay returned 404; verification cannot establish financial truth',
        whyThisHappened: 'Required provider evidence could not be established. Actuation must be blocked.',
        authorityBadge: { text: 'VERIFICATION FAILED (SAFETY HALT)', domain: 'DETERMINISTIC' },
        verifyData: {
          d4Validation: {
            passed: true,
            evidenceContainmentValid: true,
            schemaValid: true,
            intentPermitted: true,
            providerQueryPermitted: true,
            mutationAuthority: 'DENIED'
          },
          providerVerification: {
            providerQueried: 'Razorpay Payments API v1',
            endpoint: 'GET /v1/payments/pay_missing_404_99',
            responseStatus: 404,
            providerPaymentStatus: 'NOT_FOUND',
            amount: 0,
            currency: 'INR',
            captured: false,
            error: 'BAD_REQUEST_ERROR: The id provided does not exist'
          }
        }
      },
      DECIDE: {
        stageId: 'DECIDE',
        title: 'Policy Safety Halt',
        headline: 'Missing evidence halts control loop; financial mutation strictly prohibited',
        whyThisHappened: 'System refuses to mutate financial ledger when provider ground truth cannot be verified.',
        authorityBadge: { text: 'ACTUATION BLOCKED (SAFETY)', domain: 'DETERMINISTIC' },
        decideData: {
          policyAction: 'ESCALATE',
          decisionReason: 'Missing provider evidence: Razorpay returned 404 for pay_missing_404_99.',
          governance: {
            killSwitchState: 'RUNNING',
            budgetAvailable: true,
            budgetUsed: 0,
            budgetLimit: 1000000,
            currency: 'INR',
            policyMatched: 'ESCALATE_ON_UNVERIFIED_EVIDENCE',
            mutationAllowed: false
          }
        }
      },
      ACT: {
        stageId: 'ACT',
        title: 'Actuation Blocked',
        headline: 'Zero financial mutations executed; zero provider side-effects permitted',
        whyThisHappened: 'FCE safety invariant: Actuation requires deterministic verification proof.',
        authorityBadge: { text: 'MUTATION PROHIBITED', domain: 'DETERMINISTIC' },
        actData: {
          actuation: {
            occVersion: { from: 1, to: 1, acquired: false },
            idempotencyKey: 'NONE',
            mutationDispatched: 'BLOCKED',
            targetId: 'pay_missing_404_99',
            resultStatus: 'BLOCKED'
          }
        }
      },
      REOBSERVE: {
        stageId: 'REOBSERVE',
        title: 'Re-observation Skipped',
        headline: 'Re-observation skipped due to safety halt at verification boundary',
        whyThisHappened: 'No mutations were executed to re-observe.',
        authorityBadge: { text: 'SKIPPED', domain: 'DETERMINISTIC' },
        reobserveData: {
          reobservation: {
            rePolledState: 'UNKNOWN',
            reconciliationOutcome: 'DISCREPANCY',
            converged: false,
            terminalState: 'ESCALATED_MISSING_EVIDENCE'
          }
        }
      },
      TERMINAL: {
        stageId: 'TERMINAL',
        title: 'Honest Escalation: Missing Evidence',
        headline: 'Incident safely escalated to human finance ops queue without data corruption',
        whyThisHappened: 'Required provider evidence could not be established.',
        authorityBadge: { text: 'HONEST ESCALATION', domain: 'DETERMINISTIC' },
        terminalData: {
          finalState: 'ESCALATED_MISSING_EVIDENCE',
          resolutionSummary: 'Escalated to human operator. Zero unsupported assumptions made. Payment ID does not exist on gateway.',
          honestEscalationReason: 'Provider returned 404 NOT FOUND for pay_missing_404_99.',
          isRemediated: false
        }
      }
    },
    proofsByStage: {
      DETECT: [
        {
          id: 'proof_recon_b1',
          stageId: 'DETECT',
          title: 'A1 — Deterministic Reconciliation',
          subtitle: 'Discrepancy detected in execution status',
          status: 'VALID',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Expected Status', value: 'SETTLED' },
            { label: 'Observed Status', value: 'UNKNOWN (Absent in provider webhook stream)' },
            { label: 'Discrepancy Code', value: 'ABSENT_EXECUTION', isFlag: true }
          ]
        }
      ],
      INVESTIGATE: [
        {
          id: 'proof_inv_b1',
          stageId: 'INVESTIGATE',
          title: 'A3 — Bounded AI Investigation',
          subtitle: 'LLM requested payment status lookup',
          status: 'VALID',
          authority: 'UNTRUSTED_AI',
          details: [
            { label: 'Input Records', value: '1 bounded expectation record' },
            { label: 'LLM Authority', value: 'NONE (Zero mutation authority)' },
            { label: 'Proposed Intent', value: 'READ_PAYMENT_STATE' }
          ]
        }
      ],
      VERIFY: [
        {
          id: 'proof_ver_b1',
          stageId: 'VERIFY',
          title: 'A4 — Deterministic Verification Failure',
          subtitle: 'Provider returned 404; verification cannot establish financial truth',
          status: 'BLOCKED',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Queried Target', value: 'pay_missing_404_99' },
            { label: 'Razorpay Status', value: '404 NOT FOUND', isBlocked: true },
            { label: 'Verification Result', value: 'FAILED (Required provider evidence missing)', isBlocked: true }
          ]
        }
      ],
      DECIDE: [
        {
          id: 'proof_gov_b1',
          stageId: 'DECIDE',
          title: 'Control Boundary Enforcement',
          subtitle: 'Safety invariants prohibit mutation without verified ground truth',
          status: 'BLOCKED',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Financial Mutation', value: 'BLOCKED', isBlocked: true },
            { label: 'Actuation Authority', value: 'DENIED', isBlocked: true },
            { label: 'Policy Action', value: 'ESCALATE_MISSING_EVIDENCE' }
          ]
        }
      ],
      ACT: [
        {
          id: 'proof_act_b1',
          stageId: 'ACT',
          title: 'Actuation Prohibited',
          subtitle: 'Zero mutations dispatched to provider',
          status: 'BLOCKED',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Mutations Attempted', value: '0' },
            { label: 'Blast Radius Risk', value: 'ZERO' }
          ]
        }
      ],
      REOBSERVE: [],
      TERMINAL: [
        {
          id: 'proof_term_b1',
          stageId: 'TERMINAL',
          title: 'Safe Terminal Escalation',
          subtitle: 'FCE prevented unverified state mutations',
          status: 'BLOCKED',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Terminal State', value: 'ESCALATED_MISSING_EVIDENCE', isBlocked: true },
            { label: 'Why it stopped', value: 'Required provider evidence could not be established.' }
          ]
        }
      ]
    }
  },

  SCENARIO_C: {
    id: 'SCENARIO_C',
    name: 'Adversarial Hallucination Catch',
    shortTag: 'Scenario C: Hallucination Block',
    badgeColor: 'bg-rose-500/20 text-rose-400 border-rose-500/40',
    description: 'Adversarial or hallucinating LLM generates fabricated evidence ID ev_hallucinated_fabricated_id_99999. D4 validator intercepts and blocks all gateway calls.',
    paymentId: 'pay_adv_9921820',
    orderId: 'ord_adv_881920',
    amount: 12000,
    currency: 'INR',
    discrepancyReason: 'STATE_MISMATCH',
    expectedStatus: 'SETTLED',
    observedStatus: 'PENDING',
    terminalState: 'ESCALATED_UNKNOWN',
    stages: {
      DETECT: {
        stageId: 'DETECT',
        title: 'Deterministic Reconciliation',
        headline: 'Discrepancy detected between internal order and webhook observation',
        whyThisHappened: 'Internal status is SETTLED, but incoming observation is PENDING.',
        authorityBadge: { text: 'DETERMINISTIC CONTROL', domain: 'DETERMINISTIC' },
        detectData: {
          expected: {
            id: 'exp_adv_881920',
            source: 'merchant_order_ledger',
            status: 'SETTLED',
            amount: 12000,
            currency: 'INR'
          },
          observed: {
            id: 'obs_adv_9921820',
            provider: 'razorpay_webhook',
            status: 'PENDING',
            amount: 12000,
            currency: 'INR'
          },
          discrepancyType: 'STATE_MISMATCH',
          differenceSummary: 'Discrepancy detected for ₹12,000. Expected SETTLED, observed PENDING.'
        }
      },
      INVESTIGATE: {
        stageId: 'INVESTIGATE',
        title: 'Adversarial / Hallucinated LLM Output',
        headline: 'LLM generated hypothesis referencing fabricated evidence ID outside bounded context',
        whyThisHappened: 'Demonstrates containment when an LLM hallucinates or adversary attempts injection.',
        authorityBadge: { text: 'UNTRUSTED AI REASONING (UNCONTAINED ATTEMPT)', domain: 'UNTRUSTED_AI' },
        investigateData: {
          boundedEvidence: [
            {
              id: 'ev_legit_exp_01',
              type: 'EXPECTATION',
              source: 'merchant_order_ledger',
              summary: 'Expected order ₹12,000 SETTLED',
              payloadHash: '1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b',
              timestamp: '10:30:00 UTC'
            },
            {
              id: 'ev_legit_obs_01',
              type: 'OBSERVATION',
              source: 'razorpay_webhook',
              summary: 'Observed webhook ₹12,000 PENDING',
              payloadHash: '8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c',
              timestamp: '10:30:01 UTC'
            }
          ],
          llmOutput: {
            hypothesis: 'Customer requested manual override based on internal memo ev_hallucinated_fabricated_id_99999. Mutate account immediately.',
            confidence: 0.99,
            verificationIntent: 'READ_PAYMENT_STATE',
            targetId: 'pay_adv_9921820',
            referencedEvidenceIds: ['ev_legit_exp_01', 'ev_hallucinated_fabricated_id_99999'],
            authorityGranted: 'NONE'
          }
        }
      },
      VERIFY: {
        stageId: 'VERIFY',
        title: 'D4 Boundary Validation Failure',
        headline: 'D4 Validator intercepted fabricated evidence ID; rejected LLM output',
        whyThisHappened: 'The proposed reasoning referenced evidence outside the bounded evidence context.',
        authorityBadge: { text: 'TRUST BOUNDARY ENFORCED (D4 REJECT)', domain: 'DETERMINISTIC' },
        verifyData: {
          d4Validation: {
            passed: false,
            evidenceContainmentValid: false,
            schemaValid: true,
            intentPermitted: false,
            providerQueryPermitted: false,
            mutationAuthority: 'DENIED',
            rejectionReason: 'D4 Invariant Violation: Evidence ID "ev_hallucinated_fabricated_id_99999" does not exist in bounded substrate context.'
          },
          providerVerification: {
            providerQueried: 'Razorpay API',
            endpoint: 'BLOCKED BY D4',
            responseStatus: 0,
            providerPaymentStatus: 'QUERY_BLOCKED',
            amount: 0,
            currency: 'INR',
            captured: false,
            error: 'Provider access blocked: Output failed D4 validation gate'
          }
        }
      },
      DECIDE: {
        stageId: 'DECIDE',
        title: 'Control Boundary Block',
        headline: 'Provider query BLOCKED; financial mutation BLOCKED; governance halted',
        whyThisHappened: 'Architecture enforces zero-trust containment against unverified AI outputs.',
        authorityBadge: { text: 'ZERO-TRUST CONTAINMENT', domain: 'DETERMINISTIC' },
        decideData: {
          policyAction: 'ESCALATE',
          decisionReason: 'LLM output violated referential containment. Escalating to ESCALATED_UNKNOWN.',
          governance: {
            killSwitchState: 'RUNNING',
            budgetAvailable: true,
            budgetUsed: 0,
            budgetLimit: 1000000,
            currency: 'INR',
            policyMatched: 'SECURITY_CONTAINMENT_BREACH',
            mutationAllowed: false
          }
        }
      },
      ACT: {
        stageId: 'ACT',
        title: 'Actuation Blocked',
        headline: 'Financial mutation strictly blocked; zero risk of unauthorized execution',
        whyThisHappened: 'Engine prevents hallucinations from triggering real-world provider actions.',
        authorityBadge: { text: 'MUTATION PROHIBITED', domain: 'DETERMINISTIC' },
        actData: {
          actuation: {
            occVersion: { from: 1, to: 1, acquired: false },
            idempotencyKey: 'BLOCKED',
            mutationDispatched: 'BLOCKED',
            targetId: 'pay_adv_9921820',
            resultStatus: 'BLOCKED'
          }
        }
      },
      REOBSERVE: {
        stageId: 'REOBSERVE',
        title: 'Re-observation Skipped',
        headline: 'Skipped due to containment halt',
        whyThisHappened: 'Zero state mutations occurred.',
        authorityBadge: { text: 'SKIPPED', domain: 'DETERMINISTIC' },
        reobserveData: {
          reobservation: {
            rePolledState: 'UNKNOWN',
            reconciliationOutcome: 'DISCREPANCY',
            converged: false,
            terminalState: 'ESCALATED_UNKNOWN'
          }
        }
      },
      TERMINAL: {
        stageId: 'TERMINAL',
        title: 'Escalated: Unknown Reason (Safety Halt)',
        headline: 'Incident safely escalated; untrusted AI reasoning quarantined',
        whyThisHappened: 'The proposed reasoning referenced evidence outside the bounded evidence context.',
        authorityBadge: { text: 'AI QUARANTINED', domain: 'DETERMINISTIC' },
        terminalData: {
          finalState: 'ESCALATED_UNKNOWN',
          resolutionSummary: 'Quarantined and escalated to security/compliance. LLM referenced non-existent evidence ID ev_hallucinated_fabricated_id_99999.',
          honestEscalationReason: 'Referential containment breach intercepted by D4 Validator.',
          isRemediated: false
        }
      }
    },
    proofsByStage: {
      DETECT: [
        {
          id: 'proof_recon_c1',
          stageId: 'DETECT',
          title: 'A1 — Deterministic Reconciliation',
          subtitle: 'Discrepancy detected for ₹12,000',
          status: 'VALID',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Expected Status', value: 'SETTLED' },
            { label: 'Observed Status', value: 'PENDING' },
            { label: 'Discrepancy Code', value: 'STATE_MISMATCH' }
          ]
        }
      ],
      INVESTIGATE: [
        {
          id: 'proof_inv_c1',
          stageId: 'INVESTIGATE',
          title: 'A3 — Untrusted AI Hypothesis',
          subtitle: 'LLM generated reasoning referencing invalid evidence',
          status: 'BLOCKED',
          authority: 'UNTRUSTED_AI',
          details: [
            { label: 'Valid Evidence Supplied', value: 'ev_legit_exp_01, ev_legit_obs_01' },
            { label: 'Hallucinated Reference', value: 'ev_hallucinated_fabricated_id_99999', isBlocked: true },
            { label: 'LLM Authority', value: 'NONE (Zero direct action power)' }
          ]
        }
      ],
      VERIFY: [
        {
          id: 'proof_d4_c1',
          stageId: 'VERIFY',
          title: 'D4 — Trust Boundary Enforced',
          subtitle: 'Output Validator caught fabricated evidence reference',
          status: 'BLOCKED',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Evidence Check', value: '✕ ev_hallucinated_fabricated_id_99999 NOT FOUND', isBlocked: true },
            { label: 'LLM Output Status', value: 'REJECTED', isBlocked: true },
            { label: 'Provider Query', value: 'BLOCKED', isBlocked: true },
            { label: 'Mutation Access', value: 'BLOCKED', isBlocked: true }
          ]
        }
      ],
      DECIDE: [
        {
          id: 'proof_gov_c1',
          stageId: 'DECIDE',
          title: 'Governance Containment Gate',
          subtitle: 'Unvalidated requests denied gateway execution',
          status: 'BLOCKED',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Containment Status', value: 'ENFORCED' },
            { label: 'Financial Action', value: 'DENIED', isBlocked: true },
            { label: 'Safety Trigger', value: 'ESCALATED_UNKNOWN' }
          ]
        }
      ],
      ACT: [],
      REOBSERVE: [],
      TERMINAL: [
        {
          id: 'proof_term_c1',
          stageId: 'TERMINAL',
          title: 'Terminal Quarantine',
          subtitle: 'The judge watches the system catch the hallucination in real time',
          status: 'BLOCKED',
          authority: 'DETERMINISTIC',
          details: [
            { label: 'Terminal State', value: 'ESCALATED_UNKNOWN', isBlocked: true },
            { label: 'Why it stopped', value: 'The proposed reasoning referenced evidence outside the bounded evidence context.' }
          ]
        }
      ]
    }
  },

  LIVE_WEBHOOK: {
    id: 'LIVE_WEBHOOK',
    name: 'Live Webhook / Custom Injection',
    shortTag: 'Live Webhook Mode',
    badgeColor: 'bg-sky-500/20 text-sky-400 border-sky-500/40',
    description: 'Directly inject custom Razorpay webhooks and watch the live control loop process backend events.',
    paymentId: 'pay_custom_live',
    orderId: 'ord_custom_live',
    amount: 4500,
    currency: 'INR',
    discrepancyReason: 'STATE_MISMATCH',
    expectedStatus: 'SETTLED',
    observedStatus: 'PENDING',
    terminalState: 'RESOLVED',
    stages: {
      DETECT: {
        stageId: 'DETECT',
        title: 'Reconciliation Engine',
        headline: 'Waiting for live webhook event injection...',
        whyThisHappened: 'Inject a provider event using the left panel.',
        authorityBadge: { text: 'LIVE BACKEND MODE', domain: 'DETERMINISTIC' }
      },
      INVESTIGATE: {
        stageId: 'INVESTIGATE',
        title: 'A3 Investigation',
        headline: 'Awaiting discrepancy confirmation...',
        whyThisHappened: 'Engine will assemble bounded context if discrepancy exists.',
        authorityBadge: { text: 'UNTRUSTED AI REASONING', domain: 'UNTRUSTED_AI' }
      },
      VERIFY: {
        stageId: 'VERIFY',
        title: 'A4 Verification',
        headline: 'Awaiting investigation output...',
        whyThisHappened: 'DeterministicVerifier will validate and query provider.',
        authorityBadge: { text: 'DETERMINISTIC MACHINE TRUTH', domain: 'DETERMINISTIC' }
      },
      DECIDE: {
        stageId: 'DECIDE',
        title: 'Governance Gate',
        headline: 'Awaiting verification proof...',
        whyThisHappened: 'Gate evaluates budget and kill switch before actuation.',
        authorityBadge: { text: 'GOVERNANCE GATE', domain: 'DETERMINISTIC' }
      },
      ACT: {
        stageId: 'ACT',
        title: 'Idempotent Actuation',
        headline: 'Awaiting governance approval...',
        whyThisHappened: 'Lease and idempotency key will be persisted prior to mutation.',
        authorityBadge: { text: 'OCC ACTUATOR', domain: 'DETERMINISTIC' }
      },
      REOBSERVE: {
        stageId: 'REOBSERVE',
        title: 'Re-observation',
        headline: 'Awaiting actuation completion...',
        whyThisHappened: 'Fresh state will be re-queried to confirm convergence.',
        authorityBadge: { text: 'CONVERGENCE VERIFICATION', domain: 'DETERMINISTIC' }
      },
      TERMINAL: {
        stageId: 'TERMINAL',
        title: 'Terminal Outcome',
        headline: 'Awaiting loop completion...',
        whyThisHappened: 'Incident will reach terminal state (RESOLVED or ESCALATED).',
        authorityBadge: { text: 'CONTROL RESOLUTION', domain: 'DETERMINISTIC' }
      }
    },
    proofsByStage: {
      DETECT: [],
      INVESTIGATE: [],
      VERIFY: [],
      DECIDE: [],
      ACT: [],
      REOBSERVE: [],
      TERMINAL: []
    }
  }
};
