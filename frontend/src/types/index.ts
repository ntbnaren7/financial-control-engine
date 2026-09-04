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
