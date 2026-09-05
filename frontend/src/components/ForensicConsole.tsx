import React, { useState } from 'react';
import type {
  ScenarioDefinition,
  ScenarioPresetId,
  PipelineStageId,
  ProofItem,
  ExecutionMode,
  SystemReadiness,
  StageExecutionPayload
} from '../types';

interface ForensicConsoleProps {
  currentScenario: ScenarioDefinition;
  currentScenarioId: ScenarioPresetId;
  onSelectScenario: (scenarioId: ScenarioPresetId) => void;
  currentStageIndex: number;
  selectedStageId: PipelineStageId | 'READY';
  onSelectStage: (stageId: PipelineStageId | 'READY') => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onStepForward: () => void;
  onReset: () => void;
  playbackSpeed: number;
  onChangeSpeed: (speed: number) => void;
  proofs: ProofItem[];
  onOpenBatchModal: () => void;
  onInjectCustomWebhook: (payload: { paymentId: string; orderId: string; amount: number }) => void;
  isInjecting: boolean;

  // Dual Execution & Progressive Reveal extensions
  executionMode: ExecutionMode;
  onSelectMode: (mode: ExecutionMode) => void;
  caseIdentity: {
    paymentId: string;
    orderId: string;
    amount: number;
    currency: string;
  };
  readiness: SystemReadiness;
  isLiveRunning: boolean;
  onBeginLiveRun: () => void;
}

const STAGE_CONFIG: Array<{ id: PipelineStageId; num: string; label: string; sublabel: string }> = [
  { id: 'DETECT', num: '1', label: 'DETECT', sublabel: 'Ingest / Reconcile' },
  { id: 'INVESTIGATE', num: '2', label: 'INVESTIGATE', sublabel: 'A3 Reasoner' },
  { id: 'VERIFY', num: '3', label: 'VERIFY', sublabel: 'A4 Verifier' },
  { id: 'DECIDE', num: '4', label: 'DECIDE', sublabel: 'Policy & Gov' },
  { id: 'ACT', num: '5', label: 'ACT', sublabel: 'OCC Actuator' },
  { id: 'REOBSERVE', num: '6', label: 'RE-OBSERVE', sublabel: 'Fresh State' },
  { id: 'TERMINAL', num: '7', label: 'OUTCOME', sublabel: 'Resolved / Escalated' }
];

export const ForensicConsole: React.FC<ForensicConsoleProps> = ({
  currentScenario,
  currentScenarioId,
  onSelectScenario,
  currentStageIndex,
  selectedStageId,
  onSelectStage,
  isPlaying,
  onTogglePlay,
  onStepForward,
  onReset,
  playbackSpeed,
  onChangeSpeed,
  proofs,
  onOpenBatchModal,
  onInjectCustomWebhook,
  isInjecting,
  executionMode,
  onSelectMode,
  caseIdentity,
  readiness,
  isLiveRunning,
  onBeginLiveRun
}) => {
  // Custom webhook fields
  const [customPaymentId, setCustomPaymentId] = useState('pay_live_3819482');
  const [customOrderId, setCustomOrderId] = useState('ord_live_5601928');
  const [customAmount, setCustomAmount] = useState('4500');

  // Operator feedback notice
  const [operatorNotice, setOperatorNotice] = useState<string | null>(null);

  // Copy notice state
  const [copiedText, setCopiedText] = useState<string | null>(null);

  // Audit view toggle
  const [showAuditSection, setShowAuditSection] = useState(false);

  // Expandable accordion state for stage trails
  const [expandedStageIds, setExpandedStageIds] = useState<Record<string, boolean>>({});

  const toggleStageExpanded = (stageId: string) => {
    setExpandedStageIds(prev => ({
      ...prev,
      [stageId]: !prev[stageId]
    }));
  };

  const expandAllStages = () => {
    const next: Record<string, boolean> = {};
    STAGE_CONFIG.forEach(s => {
      next[s.id] = true;
    });
    setExpandedStageIds(next);
  };

  const collapseAllStages = () => {
    setExpandedStageIds({});
  };

  const areAllStagesExpanded = STAGE_CONFIG.every(s => !!expandedStageIds[s.id]);

  const effectiveStageId: PipelineStageId = selectedStageId === 'READY' ? 'DETECT' : selectedStageId;
  const activeStagePayload = currentScenario.stages[effectiveStageId];

  const handleCopy = (text: string) => {
    navigator.clipboard?.writeText(text);
    setCopiedText(text);
    setTimeout(() => setCopiedText(null), 1500);
  };

  // Concise single-line summary when a stage is in the collapsed past trail
  const getStageTrailSummary = (stageId: PipelineStageId) => {
    switch (stageId) {
      case 'DETECT':
        return `Expected ${currentScenario.expectedStatus} ≠ Observed ${currentScenario.observedStatus} · ${currentScenario.discrepancyReason} (₹${currentScenario.amount.toLocaleString()})`;
      case 'INVESTIGATE':
        return `4 bounded records assembled · Verification Intent: READ_PAYMENT_STATE · Authority: NONE`;
      case 'VERIFY':
        if (currentScenarioId === 'SCENARIO_B') {
          return `Razorpay returned HTTP 404 NOT FOUND · Truth unestablished · Actuation prohibited`;
        }
        if (currentScenarioId === 'SCENARIO_C') {
          return `D4 Invariant Violation: ev_hallucinated_fabricated_id_99999 NOT FOUND · Query blocked`;
        }
        return `D4 referential containment valid · Razorpay GET /payments/${currentScenario.paymentId} returned 200 OK (captured: true)`;
      case 'DECIDE':
        if (currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C') {
          return `Governance containment: Mutation DENIED · Policy matched: ESCALATE`;
        }
        return `Policy: REFUND_PAYMENT · Kill switch: RUNNING · Budget quota: ₹${currentScenario.amount.toLocaleString()} authorized`;
      case 'ACT':
        if (currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C') {
          return `Actuation skipped · Zero mutations dispatched to external provider`;
        }
        return `OCC lease v1 → v2 acquired · Idempotency key persisted · Refund rfnd_019482710398 dispatched`;
      case 'REOBSERVE':
        if (currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C') {
          return `Re-observation skipped`;
        }
        return `Fresh provider state re-queried: refunded · Reconciliation against expectation: MATCH · Converged`;
      case 'TERMINAL':
        return currentScenario.terminalState === 'RESOLVED'
          ? `Terminal state: RESOLVED · Closed-loop control completed without human intervention`
          : `Terminal state: ${currentScenario.terminalState} · Honest safety escalation preserved`;
      default:
        return '';
    }
  };

  const getStagePendingSummary = (stageId: PipelineStageId) => {
    switch (stageId) {
      case 'INVESTIGATE': return 'Awaiting bounded context assembly and A3 causal hypothesis';
      case 'VERIFY': return 'Awaiting D4 containment validation and deterministic gateway query';
      case 'DECIDE': return 'Awaiting recovery policy match and governance budget allowance';
      case 'ACT': return 'Awaiting OCC atomic lease and idempotent mutation dispatch';
      case 'REOBSERVE': return 'Awaiting post-action provider state re-observation';
      case 'TERMINAL': return 'Awaiting closed-loop convergence';
      default: return 'Pending';
    }
  };

  // Reusable Stage-Specific Forensic Evidence Renderer
  const renderStageForensicContent = (stageId: PipelineStageId, stagePayload?: StageExecutionPayload) => {
    if (!stagePayload) return null;

    return (
      <>
        {/* 1. DETECT: Expected vs Observed Comparison */}
        {stageId === 'DETECT' && stagePayload.detectData && (
          <div className="mt-4 border-t border-[#E2E8F0] pt-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs font-sans">
              {/* Expected Column */}
              <div>
                <div className="text-[10px] font-sans font-bold uppercase text-slate-400 tracking-wider mb-2.5">
                  EXPECTED (Internal Ledger)
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between border-b border-slate-100 pb-1.5">
                    <span className="text-slate-500">Ledger Status:</span>
                    <span className="font-bold text-[#00B37E] font-sans">{stagePayload.detectData.expected.status}</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-100 pb-1.5 font-mono">
                    <span className="text-slate-500 font-sans">Amount:</span>
                    <span className="font-semibold text-[#0C1A30]">
                      ₹{stagePayload.detectData.expected.amount.toLocaleString()}.00 {stagePayload.detectData.expected.currency}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-slate-100 pb-1.5">
                    <span className="text-slate-500">Source:</span>
                    <span className="text-slate-700 font-mono text-[11px]">{stagePayload.detectData.expected.source}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Order ID:</span>
                    <span className="text-slate-700 font-mono">{stagePayload.detectData.expected.id || currentScenario.orderId}</span>
                  </div>
                </div>
              </div>

              {/* Observed Column */}
              <div>
                <div className="text-[10px] font-sans font-bold uppercase text-slate-400 tracking-wider mb-2.5">
                  OBSERVED (Provider Webhook)
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between border-b border-slate-100 pb-1.5">
                    <span className="text-slate-500">Webhook Status:</span>
                    <span className={`font-bold font-sans ${
                      stagePayload.detectData.observed.status === 'UNKNOWN' ? 'text-rose-600' : 'text-amber-700'
                    }`}>
                      {stagePayload.detectData.observed.status}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-slate-100 pb-1.5 font-mono">
                    <span className="text-slate-500 font-sans">Amount:</span>
                    <span className="font-semibold text-[#0C1A30]">
                      ₹{stagePayload.detectData.observed.amount.toLocaleString()} {stagePayload.detectData.observed.currency}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-slate-100 pb-1.5">
                    <span className="text-slate-500">Provider:</span>
                    <span className="text-slate-700 font-mono text-[11px]">{stagePayload.detectData.observed.provider}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Payment ID:</span>
                    <span className="text-slate-700 font-mono">{stagePayload.detectData.observed.id || '—'}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Discrepancy Note */}
            <div className="mt-3.5 pt-3 border-t border-[#E2E8F0] text-xs text-slate-600 flex items-start gap-2 font-sans">
              <span className="text-amber-600 font-bold shrink-0">ⓘ</span>
              <span><strong className="text-[#0C1A30]">Discrepancy:</strong> {stagePayload.detectData.differenceSummary}</span>
            </div>
          </div>
        )}

        {/* 2. INVESTIGATE: Bounded Context + AI Reasoning Transition */}
        {stageId === 'INVESTIGATE' && stagePayload.investigateData && (
          <div className="mt-4 border-t border-[#E2E8F0] pt-4 space-y-4">
            {/* Bounded Evidence List */}
            <div>
              <div className="text-[10px] font-sans font-bold uppercase text-slate-400 tracking-wider mb-2 flex items-center justify-between pb-1.5 border-b border-slate-100">
                <span>BOUNDED EVIDENCE CONTEXT ({stagePayload.investigateData.boundedEvidence.length} RECORDS)</span>
                <span className="text-slate-400 font-mono text-[10px]">SHA256 Cryptographic Substrate</span>
              </div>
              <div className="divide-y divide-slate-100">
                {stagePayload.investigateData.boundedEvidence.map((ev: any) => (
                  <div key={ev.id} className="py-2 flex items-center justify-between gap-4 text-xs">
                    <div className="truncate">
                      <span className="text-[#0C6BF5] font-mono font-bold">{ev.id}</span>
                      <span className="text-slate-700 font-sans ml-3">{ev.summary}</span>
                    </div>
                    <span className="text-slate-400 text-[10px] shrink-0 font-mono">{ev.payloadHash?.slice(0, 16)}...</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Proposed Causal Hypothesis */}
            <div className="pt-3 border-t border-[#E2E8F0]">
              <div className="text-[10px] font-sans font-bold uppercase tracking-wider text-slate-400 mb-1">
                Causal Hypothesis (A3 Reasoner)
              </div>
              <div className="text-slate-700 font-sans text-xs leading-relaxed">
                "{stagePayload.investigateData.llmOutput.hypothesis}"
              </div>
              <div className="flex flex-wrap gap-6 pt-2.5 mt-2 border-t border-slate-100 text-[11px] font-sans text-slate-500">
                <div>
                  <span className="text-slate-400 uppercase text-[10px]">Verification Intent:</span>{' '}
                  <span className="text-slate-800 font-mono font-semibold">{stagePayload.investigateData.llmOutput.verificationIntent}</span>
                </div>
                <div>
                  <span className="text-slate-400 uppercase text-[10px]">Target ID:</span>{' '}
                  <span className="text-slate-800 font-mono font-semibold">{stagePayload.investigateData.llmOutput.targetId}</span>
                </div>
                <div>
                  <span className="text-slate-400 uppercase text-[10px]">Authority:</span>{' '}
                  <span className="text-rose-700 font-semibold">NONE (0% · Read-Only)</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 3. VERIFY: D4 Validation + Provider Verification */}
        {stageId === 'VERIFY' && stagePayload.verifyData && (
          <div className="mt-4 border-t border-[#E2E8F0] pt-4 space-y-4">
            {/* Containment Halt Status Strip if Scenario B */}
            {currentScenarioId === 'SCENARIO_B' && (
              <div className="border-l-2 border-rose-500 pl-3 py-1 font-sans text-xs">
                <div className="text-[10px] font-bold uppercase text-rose-700 tracking-wider">
                  Containment Halt · Truth Not Established
                </div>
                <div className="flex items-center gap-1.5 text-xs text-rose-900 font-mono mt-0.5 flex-wrap">
                  <span className="font-semibold">404 NOT FOUND</span>
                  <span className="text-rose-400">→</span>
                  <span className="font-semibold">TRUTH NOT ESTABLISHED</span>
                  <span className="text-rose-400">→</span>
                  <span className="font-semibold">MUTATION BLOCKED</span>
                  <span className="text-rose-400">→</span>
                  <span className="font-bold text-rose-800">ESCALATED_MISSING_EVIDENCE</span>
                </div>
              </div>
            )}

            {/* Containment Halt Status Strip if Scenario C */}
            {currentScenarioId === 'SCENARIO_C' && (
              <div className="border-l-2 border-rose-500 pl-3 py-1 font-sans text-xs">
                <div className="text-[10px] font-bold uppercase text-rose-700 tracking-wider">
                  D4 Invariant Violation · Adversarial Hallucination Caught
                </div>
                <div className="flex items-center gap-1.5 text-xs text-rose-900 font-mono mt-0.5 flex-wrap">
                  <span className="font-semibold">FABRICATED EVIDENCE ID</span>
                  <span className="text-rose-400">→</span>
                  <span className="font-semibold">D4 CONTAINMENT VIOLATION</span>
                  <span className="text-rose-400">→</span>
                  <span className="font-semibold">PROVIDER ACCESS BLOCKED</span>
                  <span className="text-rose-400">→</span>
                  <span className="font-semibold">MUTATION BLOCKED</span>
                  <span className="text-rose-400">→</span>
                  <span className="font-bold text-rose-800">ESCALATED_UNKNOWN</span>
                </div>
              </div>
            )}

            {/* D4 Deterministic Output Validation */}
            <div>
              <div className="text-[10px] font-sans font-bold uppercase text-slate-400 tracking-wider flex items-center justify-between pb-2 border-b border-slate-100">
                <span>D4 DETERMINISTIC OUTPUT VALIDATION</span>
                <span className={`font-sans font-bold text-xs ${stagePayload.verifyData.d4Validation.passed ? 'text-[#00B37E]' : 'text-rose-700'}`}>
                  {stagePayload.verifyData.d4Validation.passed ? 'PASSED ✓' : 'FAILED ✕'}
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2.5 text-xs font-sans">
                <div>
                  <span className="text-slate-500">Evidence Containment:</span>{' '}
                  <strong className={stagePayload.verifyData.d4Validation.evidenceContainmentValid ? 'text-[#00B37E]' : 'text-rose-700'}>
                    {stagePayload.verifyData.d4Validation.evidenceContainmentValid ? 'VALID' : 'VIOLATION'}
                  </strong>
                </div>
                <div>
                  <span className="text-slate-500">Intent Schema:</span>{' '}
                  <strong className="text-[#00B37E]">VALID</strong>
                </div>
                <div>
                  <span className="text-slate-500">Mutation Authority:</span>{' '}
                  <strong className="text-rose-700">DENIED · READ-ONLY</strong>
                </div>
              </div>
              {stagePayload.verifyData.d4Validation.rejectionReason && (
                <div className="text-rose-700 text-xs font-sans pt-2 mt-2 border-t border-rose-100">
                  {stagePayload.verifyData.d4Validation.rejectionReason}
                </div>
              )}
            </div>

            {/* Deterministic Verifier · Razorpay Developer Terminal Block */}
            <div className="pt-3 border-t border-[#E2E8F0]">
              <div className="text-[10px] font-sans font-bold uppercase text-slate-400 tracking-wider pb-2">
                DETERMINISTIC VERIFIER · RAZORPAY API
              </div>
              <div className="bg-[#0B1528] border border-[#1E2E4A] rounded overflow-hidden font-mono text-xs">
                {(() => {
                  const rawEndpoint = stagePayload.verifyData.providerVerification.endpoint || '';
                  const cleanPath = rawEndpoint.replace(/^GET\s+/i, '').replace(/^\/+/, '');
                  return (
                    <>
                      <div className="bg-[#0F1D33] px-3.5 py-2 border-b border-[#1E2E4A] flex items-center justify-between text-[11px]">
                        <div className="flex items-center gap-2">
                          <span className="px-1.5 py-0.5 rounded bg-[#1A2C4B] text-[#38BDF8] font-bold text-[10px]">
                            cURL
                          </span>
                          <span className="text-slate-300 font-semibold truncate">
                            GET /{cleanPath}
                          </span>
                        </div>
                        <span className={`font-mono font-bold text-[11px] px-2 py-0.5 rounded ${
                          stagePayload.verifyData.providerVerification.captured
                            ? 'bg-[#00B37E]/20 text-[#00B37E]'
                            : 'bg-rose-500/20 text-rose-400'
                        }`}>
                          HTTP {stagePayload.verifyData.providerVerification.responseStatus || 'BLOCKED'} · {stagePayload.verifyData.providerVerification.providerPaymentStatus}
                        </span>
                      </div>
                      <div className="p-3 text-[11px] space-y-1 text-slate-300">
                        <div className="text-slate-400">
                          <span className="text-[#38BDF8]">GET</span> https://api.razorpay.com/{cleanPath}
                        </div>
                        <div className="text-slate-400 text-[10px]">
                          Host: <span className="text-slate-200">api.razorpay.com</span> · Authorization: <span className="text-slate-200">Basic [RZP_KEY:RZP_SECRET]</span>
                        </div>
                        {stagePayload.verifyData.providerVerification.error ? (
                          <div className="text-rose-400 font-semibold pt-1.5 border-t border-[#1E2E4A] text-xs">
                            ✕ Provider Error: {stagePayload.verifyData.providerVerification.error}
                          </div>
                        ) : (
                          <div className="text-[#34D399] font-semibold pt-1.5 border-t border-[#1E2E4A] text-xs">
                            ✓ Provider response: status="{stagePayload.verifyData.providerVerification.providerPaymentStatus}" · captured={String(stagePayload.verifyData.providerVerification.captured)}
                          </div>
                        )}
                      </div>
                    </>
                  );
                })()}
              </div>
            </div>
          </div>
        )}

        {/* 4. DECIDE: Governance Gate & Recovery Policy */}
        {stageId === 'DECIDE' && stagePayload.decideData && (
          <div className="mt-4 border-t border-[#E2E8F0] pt-4 space-y-4 font-sans text-xs">
            <div>
              <div className="text-[10px] font-bold uppercase text-slate-400 tracking-wider pb-1.5 border-b border-slate-100 flex items-center justify-between">
                <span>POLICY EVALUATION</span>
                <span className="text-[#0C6BF5] font-mono font-bold text-xs">{stagePayload.decideData.policyAction}</span>
              </div>
              <div className="pt-2 text-slate-700 text-xs leading-relaxed">
                {stagePayload.decideData.decisionReason}
              </div>
            </div>

            <div className="pt-2 border-t border-slate-100">
              <div className="text-[10px] font-bold uppercase text-slate-400 tracking-wider pb-1.5">
                GOVERNANCE GATE CHECKS
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs pt-1">
                <div>
                  <span className="text-slate-500">Kill Switch:</span>{' '}
                  <strong className="text-[#00B37E] font-bold">{stagePayload.decideData.governance.killSwitchState}</strong>
                </div>
                <div>
                  <span className="text-slate-500">Action Budget:</span>{' '}
                  <strong className="text-[#0C1A30] font-mono font-bold">
                    ₹{stagePayload.decideData.governance.budgetUsed?.toLocaleString()} / ₹{stagePayload.decideData.governance.budgetLimit?.toLocaleString()}
                  </strong>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 5. ACT: Idempotent Actuation */}
        {stageId === 'ACT' && stagePayload.actData && (
          <div className="mt-4 border-t border-[#E2E8F0] pt-4 font-sans text-xs space-y-3">
            <div className="text-[10px] font-bold uppercase text-slate-400 tracking-wider pb-1.5 border-b border-slate-100">
              IDEMPOTENT ACTUATION
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between border-b border-slate-100 pb-1.5">
                <span className="text-slate-500">OCC Lease:</span>
                <span className="text-[#0C6BF5] font-mono font-bold">CAS Lease v{stagePayload.actData.actuation.occVersion.from} → v{stagePayload.actData.actuation.occVersion.to} Acquired</span>
              </div>
              <div className="flex justify-between border-b border-slate-100 pb-1.5">
                <span className="text-slate-500">Idempotency Key:</span>
                <span className="text-slate-800 font-mono text-[11px]">{stagePayload.actData.actuation.idempotencyKey}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Mutation Dispatched:</span>
                <span className="text-[#00B37E] font-mono font-bold">{stagePayload.actData.actuation.mutationDispatched}</span>
              </div>
            </div>
          </div>
        )}

        {/* 6. RE-OBSERVE: Fresh State Re-observation */}
        {stageId === 'REOBSERVE' && stagePayload.reobserveData && (
          <div className="mt-4 border-t border-[#E2E8F0] pt-4 font-sans text-xs space-y-3">
            <div className="text-[10px] font-bold uppercase text-slate-400 tracking-wider pb-1.5 border-b border-slate-100">
              FRESH STATE RE-OBSERVATION
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between border-b border-slate-100 pb-1.5">
                <span className="text-slate-500">Fresh Provider State:</span>
                <span className="text-[#00B37E] font-mono font-bold">{stagePayload.reobserveData.reobservation.rePolledState}</span>
              </div>
              <div className="flex justify-between border-b border-slate-100 pb-1.5">
                <span className="text-slate-500">Re-reconciliation Outcome:</span>
                <span className="text-[#00B37E] font-bold">{stagePayload.reobserveData.reobservation.reconciliationOutcome}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Loop Status:</span>
                <span className="text-[#0C6BF5] font-bold">VERIFIED CONVERGED</span>
              </div>
            </div>
          </div>
        )}

        {/* 7. OUTCOME: Final Incident Disposition */}
        {stageId === 'TERMINAL' && stagePayload.terminalData && (
          <div className="mt-4 border-t border-[#E2E8F0] pt-4 font-sans text-xs">
            <div className="text-[10px] font-bold uppercase text-slate-400 tracking-wider pb-1.5 border-b border-slate-100">
              FINAL INCIDENT DISPOSITION
            </div>
            <div className={`text-base font-bold pt-2 ${
              stagePayload.terminalData.finalState === 'RESOLVED' ? 'text-[#00B37E]' : 'text-rose-700'
            }`}>
              {stagePayload.terminalData.finalState}
            </div>
            <div className="text-slate-700 text-xs mt-1.5 leading-relaxed">
              {stagePayload.terminalData.resolutionSummary}
            </div>
            {stagePayload.terminalData.honestEscalationReason && (
              <div className="text-rose-800 text-xs pt-2 mt-2 border-t border-rose-100">
                <strong>Halt reason:</strong> {stagePayload.terminalData.honestEscalationReason}
              </div>
            )}
          </div>
        )}
      </>
    );
  };

  // Running control trace timeline items
  const timeline = [
    ...(currentStageIndex === -1 ? [{ time: '11:57:00', stage: 'READY', detail: 'Event stream ingested · Queued for reconciliation' }] : []),
    ...(currentStageIndex >= 0 ? [{ time: '11:57:01', stage: 'DETECT', detail: `discrepancy confirmed: ${currentScenario.discrepancyReason}` }] : []),
    ...(currentStageIndex >= 1 ? [{ time: '11:57:02', stage: 'INVESTIGATE', detail: '4 bounded evidence records assembled; intent derived' }] : []),
    ...(currentStageIndex >= 2 ? [{
      time: '11:57:03',
      stage: 'VERIFY',
      detail: currentScenarioId === 'SCENARIO_B'
        ? 'provider returned 404 NOT FOUND; verification failed'
        : currentScenarioId === 'SCENARIO_C'
          ? 'D4 caught fabricated evidence ID; rejected reasoning'
          : 'provider verified: 200 OK captured: true'
    }] : []),
    ...(currentStageIndex >= 3 ? [{
      time: '11:57:04',
      stage: 'DECIDE',
      detail: currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C'
        ? 'mutation denied; containment halt triggered'
        : `governance authorized mutation quota: ₹${currentScenario.amount.toLocaleString()}`
    }] : []),
    ...(currentStageIndex >= 4 ? [{
      time: '11:57:05',
      stage: 'ACT',
      detail: currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C'
        ? 'actuation blocked'
        : 'OCC lock acquired v1 -> v2; refund dispatched'
    }] : []),
    ...(currentStageIndex >= 5 ? [{
      time: '11:57:06',
      stage: 'REOBSERVE',
      detail: currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C'
        ? 'skipped'
        : 'fresh provider state re-queried: refunded (MATCH)'
    }] : []),
    ...(currentStageIndex >= 6 ? [{
      time: '11:57:07',
      stage: 'TERMINAL',
      detail: currentScenario.terminalState
    }] : [])
  ];

  return (
    <div className="min-h-screen bg-[#F4F8FC] text-[#0C1A30] flex flex-col font-sans select-none">
      {/* 1. Topmost Header Bar: Razorpay-inspired visual system, FCE-owned identity */}
      <header className="bg-white border-b border-[#E2E8F0] px-8 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 font-bold tracking-tight">
            <span className="text-[#0C6BF5] font-black text-xl leading-none">↗</span>
            <span className="text-xl font-extrabold text-[#0C1A30] tracking-tight">FCE</span>
          </div>
          <div className="h-6 w-[1px] bg-[#E2E8F0]" />
          <div>
            <div className="text-xs font-bold text-[#0C1A30] uppercase tracking-wider leading-tight">
              Financial Control Engine
            </div>
            <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wide">
              V2 Kernel / Deterministic Test Matrix
            </div>
          </div>
        </div>

        {/* Center Nav Links */}
        <div className="hidden md:flex items-center gap-8 text-xs font-semibold text-slate-600">
          <button
            type="button"
            onClick={onTogglePlay}
            className="hover:text-[#0C6BF5] transition-colors cursor-pointer"
          >
            Run
          </button>
          <button
            type="button"
            onClick={() => onSelectScenario(currentScenarioId === 'SCENARIO_A' ? 'SCENARIO_B' : 'SCENARIO_A')}
            className="hover:text-[#0C6BF5] transition-colors cursor-pointer"
          >
            Scenarios
          </button>
          <button
            type="button"
            onClick={onOpenBatchModal}
            className="hover:text-[#0C6BF5] transition-colors cursor-pointer"
          >
            Batch
          </button>
          <button
            type="button"
            onClick={() => setShowAuditSection(!showAuditSection)}
            className={`hover:text-[#0C6BF5] transition-colors cursor-pointer ${showAuditSection ? 'text-[#0C6BF5] font-bold' : ''}`}
          >
            Audit
          </button>
        </div>

        {/* Far-Right: Restrained Execution Mode Selector + User Avatar */}
        <div className="flex items-center gap-5">
          {/* Execution Mode Segment Selector */}
          <div className="flex items-center bg-[#F1F5F9] p-0.5 rounded border border-[#E2E8F0] text-[11px] font-semibold">
            <button
              type="button"
              onClick={() => onSelectMode('SIMULATION')}
              className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                executionMode === 'SIMULATION'
                  ? 'bg-white text-[#0C6BF5] font-bold shadow-xs'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              SIMULATION
            </button>
            <button
              type="button"
              onClick={() => onSelectMode('LIVE')}
              className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                executionMode === 'LIVE'
                  ? 'bg-white text-[#0C6BF5] font-bold shadow-xs'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              LIVE
            </button>
          </div>

          <div className="text-right hidden sm:block">
            <div className="text-xs font-bold text-[#0C1A30] leading-tight flex items-center gap-1.5 justify-end">
              <span className={`w-2 h-2 rounded-full shrink-0 ${
                executionMode === 'SIMULATION'
                  ? 'bg-[#00B37E]'
                  : readiness.backend === 'CONNECTED'
                    ? 'bg-[#0C6BF5]'
                    : 'bg-amber-500'
              }`} />
              <span>{executionMode === 'SIMULATION' ? 'SIMULATION' : 'LIVE'}</span>
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              {executionMode === 'SIMULATION'
                ? 'PRESET SCENARIO'
                : readiness.backend === 'CONNECTED'
                  ? 'BACKEND CONNECTED'
                  : 'BACKEND OFFLINE'}
            </div>
          </div>

          <div className="w-8 h-8 rounded-full bg-[#EDF5FF] border border-[#D0E4FF] text-xs font-bold text-[#0C6BF5] flex items-center justify-center">
            N
          </div>
        </div>
      </header>

      {/* 2. Subheader Controls Bar */}
      <div className="bg-white border-b border-[#E2E8F0] px-8 py-2.5 flex flex-wrap items-center justify-between text-xs gap-4">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 font-medium">Scenario:</span>
          <select
            value={currentScenarioId}
            onChange={e => onSelectScenario(e.target.value as ScenarioPresetId)}
            className="bg-white border border-[#D8E2EE] rounded px-3 py-1.5 text-xs font-semibold text-[#0C1A30] focus:outline-none focus:border-[#0C6BF5] cursor-pointer hover:border-slate-300 transition-colors"
          >
            <option value="SCENARIO_B">Scenario B - Missing Provider Evidence (404)</option>
            <option value="SCENARIO_A">Scenario A — Autonomous Refund & Convergence</option>
            <option value="SCENARIO_C">Scenario C — Adversarial Hallucination Catch</option>
            <option value="LIVE_WEBHOOK">Live Webhook Injection</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onTogglePlay}
            className={`px-3.5 py-1.5 rounded text-xs font-bold flex items-center gap-1.5 transition-colors cursor-pointer ${
              isPlaying
                ? 'bg-amber-600 hover:bg-amber-700 text-white'
                : 'bg-[#0C6BF5] hover:bg-[#0957C7] text-white'
            }`}
          >
            {isPlaying ? '⏸ PAUSE' : '▶ RUN'}
          </button>

          <button
            type="button"
            onClick={onStepForward}
            className="px-3 py-1.5 bg-white hover:bg-slate-50 text-[#0C1A30] border border-[#D8E2EE] rounded text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            ⏭ STEP
          </button>

          <button
            type="button"
            onClick={onReset}
            className="px-3 py-1.5 bg-white hover:bg-slate-50 text-slate-600 border border-[#D8E2EE] rounded text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            ↺ RESET
          </button>

          <div className="bg-slate-100 p-0.5 rounded flex items-center text-xs font-medium text-slate-600 ml-2 border border-slate-200">
            {[1, 2, 0].map(s => (
              <button
                key={s}
                type="button"
                onClick={() => onChangeSpeed(s)}
                className={`px-2.5 py-0.5 rounded transition-colors cursor-pointer ${
                  playbackSpeed === s ? 'bg-white text-[#0C6BF5] font-bold shadow-2xs' : 'hover:text-slate-900'
                }`}
              >
                {s === 0 ? 'Fast' : `${s}x`}
              </button>
            ))}
          </div>
        </div>

        <div>
          <button
            type="button"
            onClick={onOpenBatchModal}
            className="bg-white hover:bg-slate-50 text-slate-700 hover:text-[#0C1A30] border border-[#D8E2EE] hover:border-slate-300 px-3 py-1.5 rounded text-xs font-medium flex items-center gap-2 transition-colors cursor-pointer"
          >
            <span className="text-slate-400 text-sm font-mono">⛶</span>
            <span>60 Batch Records · 85% Resolved →</span>
          </button>
        </div>
      </div>

      {/* Live Webhook Injection Drawer (If Live Mode selected) */}
      {currentScenarioId === 'LIVE_WEBHOOK' && (
        <div className="bg-[#FAFBFC] border-b border-slate-200 px-8 py-3 flex flex-wrap gap-4 items-end font-mono text-xs">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-slate-600 text-[10px] uppercase font-semibold mb-1">Payment ID</label>
            <input
              type="text"
              value={customPaymentId}
              onChange={e => setCustomPaymentId(e.target.value)}
              className="w-full bg-white border border-slate-200 px-2.5 py-1 text-slate-900 text-xs focus:outline-none focus:border-blue-500 rounded"
            />
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="block text-slate-600 text-[10px] uppercase font-semibold mb-1">Order ID</label>
            <input
              type="text"
              value={customOrderId}
              onChange={e => setCustomOrderId(e.target.value)}
              className="w-full bg-white border border-slate-200 px-2.5 py-1 text-slate-900 text-xs focus:outline-none focus:border-blue-500 rounded"
            />
          </div>
          <div className="w-32">
            <label className="block text-slate-600 text-[10px] uppercase font-semibold mb-1">Amount (INR)</label>
            <input
              type="number"
              value={customAmount}
              onChange={e => setCustomAmount(e.target.value)}
              className="w-full bg-white border border-slate-200 px-2.5 py-1 text-slate-900 text-xs focus:outline-none focus:border-blue-500 rounded"
            />
          </div>
          <button
            type="button"
            disabled={isInjecting}
            onClick={() => onInjectCustomWebhook({
              paymentId: customPaymentId,
              orderId: customOrderId,
              amount: parseInt(customAmount, 10) || 4500
            })}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs rounded transition-colors disabled:opacity-50 cursor-pointer"
          >
            {isInjecting ? 'Injecting...' : 'Inject Webhook →'}
          </button>
        </div>
      )}

      {/* 3. Main Investigation Workspace: The Operational Document */}
      <main className="flex-1 w-full max-w-6xl mx-auto px-6 py-8 flex flex-col">
        <div className="bg-white border border-[#D8E2EE] rounded-md p-8 flex flex-col">
          {/* Case Identity Section */}
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <div className="text-[10px] font-sans font-bold uppercase tracking-widest text-slate-400 mb-1">
                CASE FILE · TRANSACTION INVESTIGATION
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-2xl font-bold text-[#0C1A30] tracking-tight">
                  {currentScenario.paymentId}
                </span>
                <span className="font-mono text-sm text-slate-400 font-normal">
                  {currentScenario.orderId}
                </span>
                <button
                  type="button"
                  onClick={() => handleCopy(currentScenario.paymentId)}
                  className="text-slate-400 hover:text-[#0C6BF5] text-sm cursor-pointer transition-colors"
                  title="Copy payment ID"
                >
                  {copiedText === currentScenario.paymentId ? '✓' : '❐'}
                </button>
              </div>
              <div className="font-mono text-lg font-bold text-[#0C1A30] mt-1 tracking-tight">
                ₹{currentScenario.amount.toLocaleString()}.00 {currentScenario.currency}
              </div>
              <div className="text-xs text-slate-500 font-normal mt-1 font-sans">
                Merchant Order Lifecycle • Provider Webhook Settlement Stream
              </div>
            </div>

            <div className="text-right">
              {currentStageIndex === -1 ? (
                <>
                  <div className="text-xs font-sans font-bold uppercase tracking-wider text-slate-400">
                    AWAITING RECONCILIATION
                  </div>
                  <div className="text-xs text-slate-500 mt-1 font-sans">
                    Status: <strong className="text-[#0C6BF5] font-bold">QUEUED FOR RECONCILIATION</strong>
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1 font-mono">
                    Control Loop: READY
                  </div>
                </>
              ) : (
                <>
                  <div className={`text-xs font-sans font-bold uppercase tracking-wider ${
                    currentScenario.discrepancyReason === 'STATE_MISMATCH'
                      ? 'text-amber-700'
                      : 'text-rose-700'
                  }`}>
                    {currentScenario.discrepancyReason}
                  </div>
                  <div className="text-xs text-slate-600 mt-1 font-sans">
                    Expected: <strong className="text-[#00B37E] font-bold">{currentScenario.expectedStatus}</strong>
                    {' → '}
                    Observed: <strong className={currentScenario.observedStatus === 'SETTLED' ? 'text-[#00B37E] font-bold' : 'text-rose-600 font-bold'}>{currentScenario.observedStatus}</strong>
                  </div>
                  <div className="text-xs text-slate-500 mt-1 font-mono">
                    {currentStageIndex === 6 ? (
                      <>
                        Terminal: <strong className={currentScenario.terminalState === 'RESOLVED' ? 'text-[#00B37E] font-bold' : 'text-rose-600 font-bold'}>{currentScenario.terminalState}</strong>
                      </>
                    ) : (
                      <>
                        Status: <strong className="text-[#0C6BF5] font-semibold">INVESTIGATION IN PROGRESS</strong>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          <hr className="border-[#E2E8F0] my-6" />

          {/* Two-Column Investigation Layout (Left Stepper + Right Active Stage) */}
          <div className="grid grid-cols-1 lg:grid-cols-[220px,1fr] gap-10 items-start">
            {/* Left Column: Vertical Stepper Pipeline Navigation */}
            <div className="relative flex flex-col space-y-6">
              {/* Connecting line behind circles */}
              <div className="absolute left-[10px] top-2.5 bottom-5 w-[1px] bg-[#E2E8F0] z-0" />

              {STAGE_CONFIG.map((stage, idx) => {
                const isCompleted = idx < currentStageIndex;
                const isActive = idx === currentStageIndex;
                const isSelected = selectedStageId === stage.id;
                const isHaltStage = (currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C') && (stage.id === 'VERIFY' || stage.id === 'DECIDE');

                return (
                  <div key={stage.id} className="relative z-10 flex items-center justify-between group">
                    <button
                      type="button"
                      onClick={() => {
                        if (idx <= currentStageIndex) {
                          onSelectStage(stage.id);
                        }
                      }}
                      className={`flex items-start gap-3 text-left flex-1 ${
                        idx <= currentStageIndex ? 'cursor-pointer' : 'cursor-default'
                      }`}
                    >
                      {/* Compact Restrained Circle Node */}
                      {isCompleted ? (
                        <div className={`w-5 h-5 rounded-full text-white font-bold text-[10px] flex items-center justify-center shrink-0 ${
                          isHaltStage ? 'bg-rose-600' : 'bg-[#00B37E]'
                        }`}>
                          {isHaltStage ? '✕' : '✓'}
                        </div>
                      ) : isActive ? (
                        <div className="w-5 h-5 rounded-full bg-[#0C6BF5] text-white font-bold text-[10px] flex items-center justify-center shrink-0">
                          {stage.num}
                        </div>
                      ) : (
                        <div className="w-5 h-5 rounded-full bg-white border border-[#D8E2EE] text-slate-400 font-medium text-[10px] flex items-center justify-center shrink-0">
                          {stage.num}
                        </div>
                      )}

                      {/* Stage Label & Subtitle */}
                      <div className="pt-0.5">
                        <div className={`text-xs font-bold uppercase tracking-wider font-sans transition-colors ${
                          isActive
                            ? 'text-[#0C6BF5]'
                            : isSelected
                              ? 'text-[#0C1A30] underline'
                              : isCompleted
                                ? 'text-slate-800'
                                : 'text-slate-400'
                        }`}>
                          {stage.label}
                        </div>
                        <div className="text-[11px] text-slate-400 font-sans mt-0.5 leading-tight">
                          {stage.sublabel}
                        </div>
                      </div>
                    </button>

                    {/* Active Stage Rail Indicator: 3px Razorpay-blue rail */}
                    {isActive && (
                      <div className="w-[3px] h-6 bg-[#0C6BF5] rounded-full shrink-0 ml-2" />
                    )}
                  </div>
                );
              })}
            </div>

            {/* Right Column: Active Stage Investigation Details */}
            {currentStageIndex === -1 ? (
              <div className="flex-1 min-w-0 font-sans">
                {/* Top Meta Line */}
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span className="font-sans font-bold uppercase tracking-wider text-[10px] text-slate-400">
                    STAGE 0 OF 7 · PRE-RECONCILIATION
                  </span>
                  <span className="text-slate-400 text-xs font-mono">
                    Sep 5, 2026 11:57:00 AM
                  </span>
                </div>

                {/* Title */}
                <h2 className="text-xl font-bold text-[#0C1A30] font-sans mt-1 tracking-tight">
                  {executionMode === 'LIVE' ? 'Live Execution Pre-Flight' : 'Queued for Reconciliation'}
                </h2>

                {/* Headline */}
                <p className="text-xs text-slate-600 mt-1.5 font-sans leading-relaxed">
                  {executionMode === 'LIVE'
                    ? 'Pre-flight verification of backend daemon, local Ollama runtime, and provider sandbox.'
                    : 'Transaction stream ingested from provider webhook and internal order ledger.'}
                </p>

                {/* Rationale */}
                <p className="text-xs text-slate-500 mt-1 font-sans">
                  <strong className="text-[#0C1A30] font-semibold">Execution State:</strong>{' '}
                  {executionMode === 'LIVE'
                    ? 'Awaiting live run trigger. Real HTTP queries and mutations will be governed by OCC lease safety.'
                    : 'No control execution has run. Click "▶ RUN" for autonomous loop or "⏭ STEP" to inspect step 01 (DETECT).'}
                </p>

                {/* Content: Pre-flight Gate for LIVE vs Clean Inputs for SIMULATION */}
                {executionMode === 'LIVE' ? (
                  <div className="mt-5 border-t border-[#E2E8F0] pt-4 font-sans text-xs space-y-4">
                    <div className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                      SYSTEM READINESS PRE-FLIGHT
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="border border-[#E2E8F0] bg-white p-3 rounded">
                        <div className="text-[10px] uppercase text-slate-400 font-bold mb-1">Backend API</div>
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${readiness.backend === 'CONNECTED' ? 'bg-[#00B37E]' : 'bg-rose-500'}`} />
                          <span className="font-mono font-bold text-xs">{readiness.backend}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1 font-mono">http://localhost:8000</div>
                      </div>

                      <div className="border border-[#E2E8F0] bg-white p-3 rounded">
                        <div className="text-[10px] uppercase text-slate-400 font-bold mb-1">Local Ollama</div>
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${readiness.ollama === 'READY' ? 'bg-[#00B37E]' : 'bg-amber-500'}`} />
                          <span className="font-mono font-bold text-xs">{readiness.ollama}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1 font-mono">qwen3:8b (Ollama)</div>
                      </div>

                      <div className="border border-[#E2E8F0] bg-white p-3 rounded">
                        <div className="text-[10px] uppercase text-slate-400 font-bold mb-1">Provider API</div>
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-[#0C6BF5]" />
                          <span className="font-mono font-bold text-xs">{readiness.provider}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1 font-mono">Razorpay Sandbox</div>
                      </div>
                    </div>

                    <div className="pt-2 flex items-center gap-3">
                      <button
                        type="button"
                        onClick={onBeginLiveRun}
                        disabled={isLiveRunning}
                        className="bg-[#0C6BF5] hover:bg-[#0A58CA] text-white font-bold text-xs px-4 py-2 rounded transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-2"
                      >
                        {isLiveRunning ? 'Running Live Pipeline...' : '[ BEGIN LIVE RUN ]'}
                      </button>
                      <span className="text-[11px] text-slate-500">
                        Dispatches live payment event and observes autonomous reconciliation in real time.
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="mt-5 border-t border-[#E2E8F0] pt-4 font-sans text-xs">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 text-xs font-sans">
                      <div>
                        <div className="text-[10px] font-sans font-bold uppercase text-slate-400 tracking-wider mb-3">
                          INPUT A: INTERNAL ORDER LEDGER
                        </div>
                        <div className="space-y-2">
                          <div className="flex justify-between border-b border-slate-100 pb-1.5 font-mono">
                            <span className="text-slate-500">Order ID:</span>
                            <span className="font-medium text-slate-700">{caseIdentity.orderId}</span>
                          </div>
                          <div className="flex justify-between border-b border-slate-100 pb-1.5">
                            <span className="text-slate-500">Amount:</span>
                            <span className="font-bold text-[#0C1A30]">₹{caseIdentity.amount.toLocaleString()}.00 {caseIdentity.currency}</span>
                          </div>
                          <div className="flex justify-between border-b border-slate-100 pb-1.5 font-mono">
                            <span className="text-slate-500">Source:</span>
                            <span className="text-slate-700">merchant_order_ledger</span>
                          </div>
                          <div className="flex justify-between border-b border-slate-100 pb-1.5">
                            <span className="text-slate-500">Recorded Status:</span>
                            <span className="font-mono text-slate-600">SETTLED</span>
                          </div>
                        </div>
                      </div>

                      <div>
                        <div className="text-[10px] font-sans font-bold uppercase text-slate-400 tracking-wider mb-3">
                          INPUT B: INCOMING PROVIDER WEBHOOK
                        </div>
                        <div className="space-y-2">
                          <div className="flex justify-between border-b border-slate-100 pb-1.5 font-mono">
                            <span className="text-slate-500">Payment ID:</span>
                            <span className="font-medium text-slate-700">{caseIdentity.paymentId}</span>
                          </div>
                          <div className="flex justify-between border-b border-slate-100 pb-1.5">
                            <span className="text-slate-500">Reported Amount:</span>
                            <span className="font-bold text-[#0C1A30]">₹{caseIdentity.amount.toLocaleString()}.00 {caseIdentity.currency}</span>
                          </div>
                          <div className="flex justify-between border-b border-slate-100 pb-1.5 font-mono">
                            <span className="text-slate-500">Provider:</span>
                            <span className="text-slate-700">razorpay_webhook</span>
                          </div>
                          <div className="flex justify-between border-b border-slate-100 pb-1.5">
                            <span className="text-slate-500">Reported Status:</span>
                            <span className="font-mono text-slate-600">PENDING</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-5 p-3 bg-slate-50 border border-slate-200 rounded text-xs text-slate-600">
                      ℹ Deterministic reconciliation pending. Click <strong>▶ RUN</strong> to execute the autonomous control loop, or <strong>⏭ STEP</strong> to inspect step 01 (DETECT).
                    </div>
                  </div>
                )}

                {/* 7-stage pending overview with Accordion */}
                <div className="mt-6 border-t border-slate-100 pt-3">
                  <div className="flex items-center justify-between pb-2">
                    <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                      7-STAGE CONTROL PIPELINE PRE-FLIGHT OVERVIEW
                    </span>
                    <button
                      type="button"
                      onClick={areAllStagesExpanded ? collapseAllStages : expandAllStages}
                      className="text-[11px] font-sans text-[#0C6BF5] hover:text-[#0A58CA] font-medium cursor-pointer"
                    >
                      {areAllStagesExpanded ? 'Collapse All Stages' : 'Expand All Stages'}
                    </button>
                  </div>

                  <div className="divide-y divide-slate-100">
                    {STAGE_CONFIG.map((stage, idx) => {
                      const isExpanded = !!expandedStageIds[stage.id];
                      const stagePayload = currentScenario.stages[stage.id];

                      return (
                        <div key={stage.id} className="py-1">
                          <div
                            onClick={() => toggleStageExpanded(stage.id)}
                            className="flex items-center justify-between py-2 px-1 text-xs font-sans hover:bg-slate-50 cursor-pointer rounded transition-colors group select-none"
                          >
                            <div className="flex items-center gap-3 truncate min-w-0">
                              <span className="w-3.5 text-center text-xs text-slate-400 font-bold shrink-0">○</span>
                              <span className="font-bold text-slate-600 group-hover:text-[#0C6BF5] shrink-0 w-32">0{idx + 1} {stage.label}</span>
                              <span className="text-slate-500 font-normal truncate">
                                {stage.sublabel} · Queued for execution
                              </span>
                            </div>
                            <span
                              className={`text-slate-400 text-sm font-mono ml-4 shrink-0 transition-transform duration-150 inline-block ${
                                isExpanded ? 'rotate-90 text-[#0C6BF5] font-bold' : 'group-hover:text-[#0C6BF5]'
                              }`}
                            >
                              ›
                            </span>
                          </div>

                          {isExpanded && (
                            <div className="px-3.5 py-3 mt-1 mb-2 bg-slate-50/70 border border-slate-200 rounded text-xs font-sans shadow-sm">
                              <div className="font-bold text-[#0C1A30] text-sm">
                                {stagePayload?.title || `0${idx + 1} ${stage.label}`}
                              </div>
                              <div className="text-slate-500 text-[11px] mt-0.5">
                                {stagePayload?.headline || stage.sublabel}
                              </div>
                              {stagePayload?.whyThisHappened && (
                                <p className="text-[11px] text-slate-500 mt-2 font-sans">
                                  <strong className="text-[#0C1A30] font-semibold">Planned Invariants:</strong> {stagePayload.whyThisHappened}
                                </p>
                              )}
                              {renderStageForensicContent(stage.id, stagePayload)}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-1 min-w-0">
                {/* Top Meta Line */}
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span className="font-sans font-bold uppercase tracking-wider text-[10px] text-slate-400">
                    STAGE {STAGE_CONFIG.findIndex(s => s.id === selectedStageId) + 1} OF {STAGE_CONFIG.length}
                  </span>
                  <span className="flex items-center gap-1.5 text-slate-400 text-xs font-mono">
                    <span>Sep 5, 2026 11:57:03 AM</span>
                    <button
                      type="button"
                      onClick={() => handleCopy(`STAGE: ${activeStagePayload?.title}`)}
                      className="hover:text-slate-600 cursor-pointer"
                      title="Copy stage reference"
                    >
                      {copiedText?.startsWith('STAGE:') ? '✓' : '❐'}
                    </button>
                  </span>
                </div>

                {/* Title */}
                <h2 className="text-xl font-bold text-[#0C1A30] font-sans mt-1 tracking-tight">
                  {activeStagePayload?.title}
                </h2>

                {/* Headline */}
                <p className="text-xs text-slate-600 mt-1.5 font-sans leading-relaxed">
                  {activeStagePayload?.headline}
                </p>

                {/* Rationale */}
                <p className="text-xs text-slate-500 mt-1 font-sans">
                  <strong className="text-[#0C1A30] font-semibold">Rationale:</strong> {activeStagePayload?.whyThisHappened}
                </p>

              {/* STAGE-SPECIFIC FORENSIC EVIDENCE */}
              {renderStageForensicContent(effectiveStageId, activeStagePayload)}

              {/* Pipeline Stage Trail with Accordion */}
              <div className="mt-6 border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between pb-2">
                  <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                    PIPELINE STAGE TRAIL &amp; DETAILED FORENSICS
                  </span>
                  <button
                    type="button"
                    onClick={areAllStagesExpanded ? collapseAllStages : expandAllStages}
                    className="text-[11px] font-sans text-[#0C6BF5] hover:text-[#0A58CA] font-medium cursor-pointer"
                  >
                    {areAllStagesExpanded ? 'Collapse All Stages' : 'Expand All Stages'}
                  </button>
                </div>

                <div className="divide-y divide-slate-100">
                  {STAGE_CONFIG.map((stage, stageIdx) => {
                    const isCompleted = stageIdx < currentStageIndex;
                    const isActive = stageIdx === currentStageIndex;
                    const isSelectedAtTop = selectedStageId === stage.id;
                    const isExpanded = !!expandedStageIds[stage.id];
                    const isHaltStage = (currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C') && (stage.id === 'VERIFY' || stage.id === 'DECIDE');
                    const stagePayload = currentScenario.stages[stage.id];

                    return (
                      <div key={stage.id} className="py-1">
                        <div
                          onClick={() => toggleStageExpanded(stage.id)}
                          className="flex items-center justify-between py-2 px-1 text-xs font-sans hover:bg-slate-50 cursor-pointer rounded transition-colors group select-none"
                        >
                          <div className="flex items-center gap-3 truncate min-w-0">
                            <span className={`w-3.5 text-center text-xs shrink-0 ${
                              isHaltStage
                                ? 'text-rose-600 font-bold'
                                : isCompleted
                                  ? 'text-[#00B37E] font-bold'
                                  : isActive
                                    ? 'text-[#0C6BF5] font-bold'
                                    : 'text-slate-400'
                            }`}>
                              {isHaltStage ? '✕' : isCompleted ? '✓' : isActive ? '●' : '○'}
                            </span>
                            <span className={`font-bold shrink-0 w-32 ${
                              isActive || isSelectedAtTop
                                ? 'text-[#0C6BF5]'
                                : stageIdx <= currentStageIndex
                                  ? 'text-[#0C1A30] group-hover:text-[#0C6BF5]'
                                  : 'text-slate-500'
                            }`}>
                              0{stageIdx + 1} {stage.label}
                            </span>
                            {isSelectedAtTop && (
                              <span className="hidden sm:inline-block px-1.5 py-0.2 rounded text-[10px] font-bold bg-[#0C6BF5]/10 text-[#0C6BF5] shrink-0 font-mono">
                                ACTIVE VIEW
                              </span>
                            )}
                            <span className="text-slate-500 font-normal truncate">
                              {stageIdx <= currentStageIndex ? getStageTrailSummary(stage.id) : getStagePendingSummary(stage.id)}
                            </span>
                          </div>
                          <span
                            className={`text-slate-400 text-sm font-mono ml-4 shrink-0 transition-transform duration-150 inline-block ${
                              isExpanded ? 'rotate-90 text-[#0C6BF5] font-bold' : 'group-hover:text-[#0C6BF5]'
                            }`}
                          >
                            ›
                          </span>
                        </div>

                        {/* Inline Expandable Accordion Body */}
                        {isExpanded && (
                          <div className="px-3.5 py-3 mt-1 mb-2 bg-slate-50/70 border border-slate-200 rounded text-xs font-sans shadow-sm">
                            <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                              <div>
                                <div className="font-bold text-[#0C1A30] text-sm">
                                  {stagePayload?.title || `0${stageIdx + 1} ${stage.label}`}
                                </div>
                                <div className="text-slate-500 text-[11px] mt-0.5">
                                  {stagePayload?.headline || stage.sublabel}
                                </div>
                              </div>
                              {!isSelectedAtTop && (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onSelectStage(stage.id);
                                  }}
                                  className="text-[11px] font-medium text-[#0C6BF5] hover:underline cursor-pointer ml-2 shrink-0 flex items-center gap-1"
                                  title="Set as primary view in header"
                                >
                                  <span>Focus Hero View</span>
                                  <span>↗</span>
                                </button>
                              )}
                            </div>

                            {stagePayload?.whyThisHappened && (
                              <p className="text-[11px] text-slate-500 mt-2 font-sans">
                                <strong className="text-[#0C1A30] font-semibold">Rationale:</strong> {stagePayload.whyThisHappened}
                              </p>
                            )}

                            {stageIdx <= currentStageIndex ? (
                              renderStageForensicContent(stage.id, stagePayload)
                            ) : (
                              <div className="mt-3 p-2.5 bg-white border border-slate-200 rounded text-slate-500 text-xs italic">
                                Stage queued. Awaiting execution of preceding pipeline stages in the control loop.
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
          </div>

          {/* Integrated Audit & Machine Proof Section (Expandable/Toggleable) */}
          {showAuditSection && (
            <div className="mt-8 pt-6 border-t border-[#E2E8F0]">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8 text-xs font-sans">
                {/* Left: Machine Proof Assertions */}
                <div>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2.5 pb-1 border-b border-slate-100">
                    MACHINE PROOF ASSERTIONS ({proofs.length})
                  </div>
                  <div className="space-y-1.5 text-slate-700">
                    {proofs.map(p => (
                      <div key={p.id} className="flex items-start gap-2">
                        <span className={`shrink-0 font-bold ${p.status === 'BLOCKED' ? 'text-rose-600' : 'text-[#00B37E]'}`}>
                          {p.status === 'BLOCKED' ? '✕' : '✓'}
                        </span>
                        <div>
                          <span className="font-semibold text-[#0C1A30]">{p.title}</span>
                          {p.subtitle && <span className="text-slate-500 text-[11px] ml-2 font-mono">— {p.subtitle}</span>}
                        </div>
                      </div>
                    ))}
                    {proofs.length === 0 && (
                      <div className="text-slate-400 text-xs italic">
                        Run or step through the loop to accumulate verified substrate assertions.
                      </div>
                    )}
                  </div>
                </div>

                {/* Right: Running Control Trace */}
                <div>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2.5 pb-1 border-b border-slate-100 flex items-center justify-between">
                    <span>RUNNING CONTROL TRACE</span>
                    <span className="text-slate-400 font-normal font-mono">{timeline.length} events</span>
                  </div>
                  <div className="space-y-1 text-slate-600 text-[11px]">
                    {timeline.map((item, i) => (
                      <div key={i} className="flex items-baseline gap-3 font-mono">
                        <span className="text-slate-400 shrink-0 text-[10px]">{item.time}</span>
                        <span className="text-[#0C6BF5] font-bold shrink-0">{item.stage}</span>
                        <span className="text-[#0C1A30] truncate">{item.detail}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Operator Controls Bar */}
              <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between text-xs text-slate-500 gap-2 font-sans">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">OPERATOR CONTROLS:</span>
                  {operatorNotice && <span className="text-[#00B37E] text-[11px] font-semibold">{operatorNotice}</span>}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setOperatorNotice('Operator manual resolution recorded.')}
                    className="px-3 py-1 bg-white hover:bg-slate-50 border border-[#D8E2EE] rounded text-[#0C1A30] hover:border-slate-300 transition-colors font-semibold text-xs cursor-pointer"
                  >
                    MANUAL RESOLVE
                  </button>
                  <button
                    type="button"
                    onClick={() => setOperatorNotice('Pipeline retry scheduled.')}
                    className="px-3 py-1 bg-white hover:bg-amber-50 border border-amber-200 rounded text-amber-800 hover:border-amber-300 transition-colors font-semibold text-xs cursor-pointer"
                  >
                    RETRY PIPELINE
                  </button>
                  <button
                    type="button"
                    onClick={() => setOperatorNotice('Forced escalation logged.')}
                    className="px-3 py-1 bg-white hover:bg-rose-50 border border-rose-200 rounded text-rose-700 hover:border-rose-300 transition-colors font-semibold text-xs cursor-pointer"
                  >
                    FORCE ESCALATE
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* 4. Bottom Page Footer Bar */}
      <footer className="border-t border-[#E2E8F0] px-8 py-3 bg-white mt-auto flex items-center justify-between text-xs font-mono text-slate-400">
        <div>Financial Control Engine v2.0.0 | Deterministic Test Matrix</div>
        <div>Detect → Investigate → Verify → Decide → Act → Re-observe</div>
      </footer>
    </div>
  );
};
