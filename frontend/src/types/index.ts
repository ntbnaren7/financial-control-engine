export type BusinessStatus = 
  | "CREATED"
  | "OPEN"
  | "SATISFIED"
  | "FAILED"
  | "EXPIRED";

export type CanonicalStatus = 
  | "PENDING"
  | "SETTLED"
  | "FAILED"
  | "UNKNOWN"
  | "REFUNDED";

export interface FinancialEvent {
  event_type: string;
  amount?: number;
  currency?: string;
  timestamp: string;
}

export type ReconciliationOutcome = 
  | "MATCH"
  | "DISCREPANCY";

export type DiscrepancyReason = 
  | "ABSENT_EXECUTION"
  | "AMOUNT_MISMATCH"
  | "STATE_MISMATCH"
  | "DUPLICATE_EXECUTION"
  | "UNEXPECTED_EXECUTION"
  | "SLA_BREACH";

export interface CorrelationKeys {
  internal_ref?: string;
  provider_ref?: string;
  provider?: string;
  domain?: string;
  observation_type?: string;
}

export interface Expectation {
  expectation_id: string;
  domain: string;
  expected_canonical_status: CanonicalStatus;
  expected_amount: number;
  currency: string;
  source_system: string;
  expected_events: FinancialEvent[];
  correlation_keys: CorrelationKeys;
  business_status: BusinessStatus;
  created_at: string;
}

export interface Observation {
  observation_id: string;
  provider: string;
  provider_reference: string;
  observation_type: string;
  canonical_status: CanonicalStatus;
  observed_amount: number;
  currency: string;
  events: FinancialEvent[];
  evidence_ids: string[];
  correlation_keys: CorrelationKeys;
  provider_event_id?: string;
  provider_version?: string;
  observed_at: string;
  ingestion_event_id: string;
}

export interface ReconciliationResult {
  reconciliation_id: string;
  expectation_id?: string;
  observation_ids: string[];
  outcome: ReconciliationOutcome;
  reconciliation_reason: string;
  discrepancy_reason?: DiscrepancyReason;
  created_at: string;
}

export type RecoveryAction = 
  | "REPAIR_MERCHANT_STATE"
  | "REFUND_PAYMENT"
  | "ESCALATE";

export interface RecoveryIntent {
  intent_id: string;
  action: RecoveryAction;
  target_id: string;
  amount?: number;
  currency?: string;
  reason?: string;
  expected_provider_state?: string;
}

export type IncidentState = 
  | "DETECTED"
  | "INVESTIGATING"
  | "VERIFYING"
  | "ACTIONABLE"
  | "ACTUATION_PENDING"
  | "ACTUATING"
  | "REOBSERVING"
  | "ESCALATED_PAUSED_BY_KILL_SWITCH"
  | "ESCALATED_BUDGET_EXHAUSTED"
  | "ESCALATED_POLICY_BLOCKED"
  | "ESCALATED_MISSING_EVIDENCE"
  | "ESCALATED_MUTATION_FAILED"
  | "ESCALATED_CONVERGENCE_FAILED"
  | "ESCALATED_UNKNOWN"
  | "RESOLVED";

export interface Incident {
  incident_id: string;
  reconciliation_id: string;
  status: IncidentState;
  hypothesis?: string;
  intent?: RecoveryIntent;
  governance_decision?: GovernanceDecision;
  created_at: string;
  updated_at: string;
}

export interface GovernanceDecision {
  allowed: boolean;
  reason: string;
  policy_checked: boolean;
  kill_switch_active: boolean;
  budget_used?: number;
  budget_limit?: number;
}

// ---------------------------------------------------------------------------
// Control Pipeline Types (6 Control Stages + Terminal Outcome)
// ---------------------------------------------------------------------------

export type PipelineStageId = 
  | "DETECT"
  | "INVESTIGATE"
  | "VERIFY"
  | "DECIDE"
  | "ACT"
  | "REOBSERVE"
  | "TERMINAL";

export type StageStatus = 
  | "PENDING"
  | "ACTIVE"
  | "COMPLETED"
  | "BLOCKED"
  | "SKIPPED";

export type AuthorityDomain = 
  | "DETERMINISTIC"
  | "UNTRUSTED_AI";

export interface PipelineStageConfig {
  id: PipelineStageId;
  index: number;
  label: string;
  sublabel: string;
  authority: AuthorityDomain;
}

export interface ProofDetail {
  label: string;
  value: string;
  isFlag?: boolean;
  isBlocked?: boolean;
}

export interface ProofItem {
  id: string;
  stageId: PipelineStageId;
  title: string;
  subtitle?: string;
  status: "VALID" | "BLOCKED" | "PENDING";
  authority: AuthorityDomain;
  details: ProofDetail[];
  timestamp?: string;
}

// ---------------------------------------------------------------------------
// Bounded Evidence & Execution Stage Details (Layer 2: Why it happened)
// ---------------------------------------------------------------------------

export interface BoundedEvidenceRecord {
  id: string;
  type: string;
  source: string;
  summary: string;
  payloadHash: string;
  timestamp: string;
}

export interface LLMHypothesisOutput {
  hypothesis: string;
  confidence: number;
  verificationIntent: string;
  targetId: string;
  referencedEvidenceIds: string[];
  authorityGranted: "NONE";
}

export interface D4ValidationResult {
  passed: boolean;
  evidenceContainmentValid: boolean;
  schemaValid: boolean;
  intentPermitted: boolean;
  providerQueryPermitted: boolean;
  mutationAuthority: "DENIED";
  rejectionReason?: string;
}

export interface ProviderVerificationResult {
  providerQueried: string;
  endpoint: string;
  responseStatus: number;
  providerPaymentStatus: string;
  amount: number;
  currency: string;
  captured: boolean;
  evidenceIdGenerated?: string;
  evidenceHash?: string;
  error?: string;
}

export interface GovernanceCheckResult {
  killSwitchState: "RUNNING" | "PAUSED";
  budgetAvailable: boolean;
  budgetUsed: number;
  budgetLimit: number;
  currency: string;
  policyMatched: string;
  mutationAllowed: boolean;
}

export interface ActuationExecutionResult {
  occVersion: { from: number; to: number; acquired: boolean };
  idempotencyKey: string;
  mutationDispatched: string;
  targetId: string;
  resultStatus: "SUCCEEDED" | "FAILED" | "BLOCKED";
  refundId?: string;
}

export interface ReObservationResult {
  rePolledState: CanonicalStatus;
  reconciliationOutcome: ReconciliationOutcome;
  converged: boolean;
  terminalState: IncidentState;
}

export interface StageExecutionPayload {
  stageId: PipelineStageId;
  title: string;
  headline: string;
  whyThisHappened: string;
  authorityBadge: { text: string; domain: AuthorityDomain };
  detectData?: {
    expected: { status: CanonicalStatus; amount: number; currency: string; source: string; id: string };
    observed: { status: CanonicalStatus; amount: number; currency: string; provider: string; id: string };
    discrepancyType: DiscrepancyReason;
    differenceSummary: string;
  };
  investigateData?: {
    boundedEvidence: BoundedEvidenceRecord[];
    llmOutput: LLMHypothesisOutput;
  };
  verifyData?: {
    d4Validation: D4ValidationResult;
    providerVerification: ProviderVerificationResult;
  };
  decideData?: {
    governance: GovernanceCheckResult;
    policyAction: RecoveryAction;
    decisionReason: string;
  };
  actData?: {
    actuation: ActuationExecutionResult;
  };
  reobserveData?: {
    reobservation: ReObservationResult;
  };
  terminalData?: {
    finalState: IncidentState;
    resolutionSummary: string;
    honestEscalationReason?: string;
    isRemediated: boolean;
  };
}

// ---------------------------------------------------------------------------
// Scenario and Batch Types (Track 04)
// ---------------------------------------------------------------------------

export type ScenarioPresetId = 
  | "SCENARIO_A"   // Happy path refund & convergence
  | "SCENARIO_B"   // Provider 404 missing evidence escalation
  | "SCENARIO_C"   // Adversarial hallucination caught by D4
  | "LIVE_WEBHOOK"; // Real live backend injection

export interface ScenarioDefinition {
  id: ScenarioPresetId;
  name: string;
  shortTag: string;
  badgeColor: string;
  description: string;
  paymentId: string;
  orderId: string;
  amount: number;
  currency: string;
  discrepancyReason: DiscrepancyReason;
  expectedStatus: CanonicalStatus;
  observedStatus: CanonicalStatus;
  terminalState: IncidentState;
  stages: Record<PipelineStageId, StageExecutionPayload>;
  proofsByStage: Record<PipelineStageId, ProofItem[]>;
}

export interface BatchRecord {
  recordId: string;
  paymentId: string;
  orderId: string;
  scenarioType: "MATCH" | "REFUND" | "MISSING" | "AMOUNT_MISMATCH";
  amount: number;
  expectedStatus: CanonicalStatus;
  providerStatus: string;
  outcome: "MATCH" | "RESOLVED" | "ESCALATED";
  terminalState: string;
  cyclesTaken: number;
  remediated: boolean;
  notes: string;
}

export interface BatchRunSummary {
  totalRecords: number;
  directMatches: number;
  autonomousResolved: number;
  missingEvidenceEscalations: number;
  amountMismatchEscalations: number;
  directMatchRate: number; // e.g. 66.7%
  totalResolutionRate: number; // e.g. 85.0%
  timeouts: number;
  unsupportedResolutions: number;
  records: BatchRecord[];
}

// ---------------------------------------------------------------------------
// Execution Architecture & Normalized Events Layer
// ---------------------------------------------------------------------------

export type ExecutionMode = 'SIMULATION' | 'LIVE';

export type EngineStatus = 'QUEUED' | 'INVESTIGATING' | 'RESOLVED' | 'ESCALATED';

export interface SystemReadiness {
  backend: 'CONNECTED' | 'OFFLINE';
  ollama: 'READY' | 'NOT_DETECTED';
  provider: 'CONFIGURED' | 'UNCONFIGURED';
}

export type NormalizedEventType = 
  | 'RESET_TO_READY'
  | 'RECONCILIATION_ESTABLISHED'
  | 'INVESTIGATION_BOUNDED'
  | 'VERIFICATION_ASSERTED'
  | 'GOVERNANCE_EVALUATED'
  | 'ACTUATION_DISPATCHED'
  | 'OBSERVATION_COLLECTED'
  | 'TERMINAL_CONVERGED'
  | 'TERMINAL_ESCALATED';

export interface NormalizedControlEvent {
  type: NormalizedEventType;
  stageIndex: number;
  stageId: PipelineStageId | 'READY';
  timestamp: string;
  detail: string;
  payload?: Record<string, unknown>;
}

export interface CanonicalEngineState {
  mode: ExecutionMode;
  scenarioId: ScenarioPresetId;
  currentStageIndex: number; // -1 = READY / QUEUED, 0..6 = STAGES
  selectedStageId: PipelineStageId | 'READY';
  isPlaying: boolean;
  playbackSpeed: number; // 1 = 1x, 2 = 2x, 0 = fast
  status: EngineStatus;
  discrepancyEstablished: boolean;
  caseIdentity: {
    paymentId: string;
    orderId: string;
    amount: number;
    currency: string;
  };
  discrepancy: {
    reason: DiscrepancyReason | null;
    expectedStatus: CanonicalStatus | null;
    observedStatus: CanonicalStatus | null;
    terminalOutcome: IncidentState | null;
  };
  accumulatedProofs: ProofItem[];
  timeline: Array<{ step: string; at: string; detail: string }>;
  currentScenario: ScenarioDefinition;
  readiness: SystemReadiness;
  isLiveRunning: boolean;
}
