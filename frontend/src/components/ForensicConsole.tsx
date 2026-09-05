import React, { useState } from 'react';
import type { ScenarioDefinition, ScenarioPresetId, PipelineStageId, ProofItem } from '../types';

interface ForensicConsoleProps {
  currentScenario: ScenarioDefinition;
  currentScenarioId: ScenarioPresetId;
  onSelectScenario: (scenarioId: ScenarioPresetId) => void;
  currentStageIndex: number;
  selectedStageId: PipelineStageId;
  onSelectStage: (stageId: PipelineStageId) => void;
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
}

const STAGE_CONFIG: Array<{ id: PipelineStageId; num: string; label: string }> = [
  { id: 'DETECT', num: '01', label: 'DETECT' },
  { id: 'INVESTIGATE', num: '02', label: 'INVESTIGATE' },
  { id: 'VERIFY', num: '03', label: 'VERIFY' },
  { id: 'DECIDE', num: '04', label: 'DECIDE' },
  { id: 'ACT', num: '05', label: 'ACT' },
  { id: 'REOBSERVE', num: '06', label: 'RE-OBSERVE' },
  { id: 'TERMINAL', num: '07', label: 'OUTCOME' }
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
  isInjecting
}) => {
  // Custom webhook fields
  const [customPaymentId, setCustomPaymentId] = useState('pay_live_3819482');
  const [customOrderId, setCustomOrderId] = useState('ord_live_5601928');
  const [customAmount, setCustomAmount] = useState('4500');

  // Operator feedback
  const [operatorNotice, setOperatorNotice] = useState<string | null>(null);

  const activeStagePayload = currentScenario.stages[selectedStageId];

  // Concise single-line summary when a stage is in the collapsed past trail
  const getStageTrailSummary = (stageId: PipelineStageId) => {
    switch (stageId) {
      case 'DETECT':
        return `Expected ${currentScenario.expectedStatus} ≠ Observed ${currentScenario.observedStatus} · Discrepancy: ${currentScenario.discrepancyReason} (₹${currentScenario.amount.toLocaleString()})`;
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
        return `Policy: REFUND_PAYMENT · Kill switch: RUNNING · Budget quota: ₹${currentScenario.amount} authorized`;
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

  // Mock timeline items
  const timeline = [
    { time: '11:13:01', stage: 'DETECT', detail: `discrepancy confirmed: ${currentScenario.discrepancyReason}` },
    ...(currentStageIndex >= 1 ? [{ time: '11:13:02', stage: 'INVESTIGATE', detail: '4 bounded evidence records assembled; intent derived' }] : []),
    ...(currentStageIndex >= 2 ? [{
      time: '11:13:03',
      stage: 'VERIFY',
      detail: currentScenarioId === 'SCENARIO_B'
        ? 'provider returned 404 NOT FOUND; verification failed'
        : currentScenarioId === 'SCENARIO_C'
          ? 'D4 caught fabricated evidence ID; rejected reasoning'
          : 'provider verified: 200 OK captured: true'
    }] : []),
    ...(currentStageIndex >= 3 ? [{
      time: '11:13:04',
      stage: 'DECIDE',
      detail: currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C'
        ? 'mutation denied; containment halt triggered'
        : 'governance authorized mutation quota: ₹4,500'
    }] : []),
    ...(currentStageIndex >= 4 ? [{
      time: '11:13:05',
      stage: 'ACT',
      detail: currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C'
        ? 'actuation blocked'
        : 'OCC lock acquired v1 -> v2; refund dispatched'
    }] : []),
    ...(currentStageIndex >= 5 ? [{
      time: '11:13:06',
      stage: 'REOBSERVE',
      detail: currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C'
        ? 'skipped'
        : 'fresh provider state re-queried: refunded (MATCH)'
    }] : []),
    ...(currentStageIndex >= 6 ? [{
      time: '11:13:07',
      stage: 'TERMINAL',
      detail: currentScenario.terminalState
    }] : [])
  ];

  return (
    <div className="min-h-screen bg-[#090a0f] text-slate-100 flex flex-col font-sans select-none overflow-y-auto">
      {/* 1. Header Bar: Pure Typography & System Controls */}
      <header className="border-b border-[#1a1c26] px-6 lg:px-12 py-3.5 flex flex-wrap items-center justify-between text-xs font-mono text-slate-400 gap-4 bg-[#090a0f] sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <span className="text-white font-bold tracking-wider text-sm">FINANCIAL CONTROL ENGINE</span>
          <span className="text-slate-600">/</span>
          <span className="text-slate-400 text-[11px]">V2 KERNEL</span>
          <span className="text-slate-600">/</span>
          <span className="text-[11px] text-slate-400">
            {currentScenarioId === 'LIVE_WEBHOOK' ? 'LIVE GATEWAY STREAM' : 'DETERMINISTIC TEST MATRIX'}
          </span>
        </div>

        <div className="flex items-center gap-4 flex-wrap">
          {/* Scenario Selector Dropdown */}
          <div className="flex items-center gap-2">
            <span className="text-slate-400 uppercase text-[10px] tracking-wider">SCENARIO:</span>
            <select
              value={currentScenarioId}
              onChange={e => onSelectScenario(e.target.value as ScenarioPresetId)}
              className="bg-[#12141c] border border-[#262938] text-slate-200 px-2.5 py-1 rounded-none text-xs focus:outline-none focus:border-sky-400 transition-colors cursor-pointer"
            >
              <option value="SCENARIO_A">Scenario A — Autonomous Refund & Convergence</option>
              <option value="SCENARIO_B">Scenario B — Missing Provider Evidence (404)</option>
              <option value="SCENARIO_C">Scenario C — Adversarial Hallucination Catch</option>
              <option value="LIVE_WEBHOOK">Live Webhook Injection</option>
            </select>
          </div>

          {/* Stepper Controls */}
          <div className="flex items-center gap-1.5 border-l border-[#1a1c26] pl-4">
            <button
              type="button"
              onClick={onTogglePlay}
              className={`px-3 py-1 text-xs font-semibold rounded-none border transition-colors ${
                isPlaying
                  ? 'bg-amber-500/10 text-amber-300 border-amber-500/40 hover:bg-amber-500/20'
                  : 'bg-sky-500/10 text-sky-300 border-sky-500/40 hover:bg-sky-500/20'
              }`}
            >
              {isPlaying ? 'PAUSE ⏸' : 'RUN ▶'}
            </button>

            <button
              type="button"
              onClick={onStepForward}
              className="px-3 py-1 text-xs font-semibold bg-[#12141c] hover:bg-[#1c1f2e] text-slate-200 border border-[#262938] rounded-none transition-colors"
            >
              STEP ⏭
            </button>

            <button
              type="button"
              onClick={onReset}
              className="px-2.5 py-1 text-xs font-semibold bg-[#12141c] hover:bg-[#1c1f2e] text-slate-400 hover:text-slate-200 border border-[#262938] rounded-none transition-colors"
            >
              RESET ↺
            </button>

            {/* Speed toggles */}
            <div className="flex items-center ml-2 border border-[#262938] text-[10px]">
              {[1, 2, 0].map(s => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onChangeSpeed(s)}
                  className={`px-1.5 py-0.5 ${
                    playbackSpeed === s ? 'bg-sky-500/20 text-sky-300 font-bold' : 'text-slate-400 hover:text-slate-300'
                  }`}
                >
                  {s === 0 ? 'FAST' : `${s}x`}
                </button>
              ))}
            </div>
          </div>

          {/* 60-Record Batch Button */}
          <button
            type="button"
            onClick={onOpenBatchModal}
            className="border border-[#262938] hover:border-slate-500 text-slate-300 hover:text-white px-3 py-1 rounded-none text-xs transition-colors bg-[#12141c]"
          >
            60 BATCH RECORDS · 85% RESOLVED →
          </button>
        </div>
      </header>

      {/* Main Single-Document Container */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 lg:px-12 py-8 flex flex-col">
        {/* 2. Transaction Identity (Transaction First — Always) */}
        <section className="border-b border-[#1a1c26] pb-6 mb-8 flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-baseline gap-3.5">
              <span className="font-mono text-2xl font-bold text-white tracking-tight">
                {currentScenario.paymentId}
              </span>
              <span className="font-mono text-sm text-slate-400">
                {currentScenario.orderId}
              </span>
              <span className="font-mono text-sm text-slate-600">·</span>
              <span className="font-mono text-sm font-semibold text-slate-200">
                ₹{currentScenario.amount.toLocaleString()}.00 {currentScenario.currency}
              </span>
            </div>
            <div className="text-xs text-slate-400 font-mono mt-1.5">
              Merchant Order Lifecycle · Provider Webhook Settlement Stream
            </div>
          </div>

          <div className="text-right font-mono">
            <div className="flex items-center gap-2 justify-end">
              <span className={`text-xs font-bold uppercase tracking-wider ${
                currentScenario.discrepancyReason === 'STATE_MISMATCH' ? 'text-amber-400' : 'text-rose-400'
              }`}>
                {currentScenario.discrepancyReason}
              </span>
              <span className="text-slate-600">·</span>
              <span className="text-xs text-slate-300">
                EXPECTED: <strong className="text-emerald-400">{currentScenario.expectedStatus}</strong> → OBSERVED: <strong className="text-amber-400">{currentScenario.observedStatus}</strong>
              </span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1">
              Terminal Outcome: <strong className={currentScenario.terminalState === 'RESOLVED' ? 'text-emerald-400' : 'text-rose-400'}>{currentScenario.terminalState}</strong>
            </div>
          </div>
        </section>

        {/* Live Webhook Injection Drawer (If Live Mode selected) */}
        {currentScenarioId === 'LIVE_WEBHOOK' && (
          <div className="p-4 mb-8 bg-[#10121a] border border-[#222533] font-mono text-xs flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-slate-400 text-[10px] uppercase mb-1">Payment ID</label>
              <input
                type="text"
                value={customPaymentId}
                onChange={e => setCustomPaymentId(e.target.value)}
                className="w-full bg-[#0a0b10] border border-[#262938] px-2.5 py-1 text-slate-200 text-xs"
              />
            </div>
            <div className="flex-1 min-w-[200px]">
              <label className="block text-slate-400 text-[10px] uppercase mb-1">Order ID</label>
              <input
                type="text"
                value={customOrderId}
                onChange={e => setCustomOrderId(e.target.value)}
                className="w-full bg-[#0a0b10] border border-[#262938] px-2.5 py-1 text-slate-200 text-xs"
              />
            </div>
            <div className="w-32">
              <label className="block text-slate-400 text-[10px] uppercase mb-1">Amount (INR)</label>
              <input
                type="number"
                value={customAmount}
                onChange={e => setCustomAmount(e.target.value)}
                className="w-full bg-[#0a0b10] border border-[#262938] px-2.5 py-1 text-slate-200 text-xs"
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
              className="px-4 py-1.5 bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs transition-colors disabled:opacity-50"
            >
              {isInjecting ? 'Injecting...' : 'Inject Webhook →'}
            </button>
          </div>
        )}

        {/* 3. Forensic Timeline (The Progressively Revealed Investigation Document) */}
        <section className="flex flex-col gap-0">
          {STAGE_CONFIG.map((stage, idx) => {
            const isCompleted = idx < currentStageIndex;
            const isActive = idx === currentStageIndex;
            const isPending = idx > currentStageIndex;
            const isSelected = selectedStageId === stage.id;
            const isUntrustedAI = stage.id === 'INVESTIGATE';

            // 3A. Thin trail of completed stages
            if (isCompleted) {
              const isHaltStage = (currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C') && (stage.id === 'VERIFY' || stage.id === 'DECIDE');

              return (
                <div
                  key={stage.id}
                  onClick={() => onSelectStage(stage.id)}
                  className={`py-3 px-3 flex items-baseline gap-4 font-mono text-xs border-b border-[#14161f] cursor-pointer hover:bg-[#12141c] transition-colors ${
                    isSelected ? 'bg-[#12141c]' : ''
                  }`}
                >
                  <span className={`font-bold shrink-0 text-xs ${isHaltStage ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {isHaltStage ? '✕' : '✓'} {stage.num} {stage.label}
                  </span>
                  <span className="text-slate-400 text-xs leading-relaxed truncate">
                    {getStageTrailSummary(stage.id)}
                  </span>
                  <span className="text-[10px] text-slate-400 ml-auto shrink-0 uppercase tracking-wider">
                    {isSelected ? 'INSPECTING' : 'VERIFIED'}
                  </span>
                </div>
              );
            }

            // 3B. Active Expanded Forensic Section (~80% attention)
            if (isActive || (isCompleted && isSelected)) {
              return (
                <div
                  key={stage.id}
                  className={`py-6 px-4 lg:px-6 my-4 border-y ${
                    isUntrustedAI
                      ? 'border-amber-500/40 bg-amber-950/10'
                      : stage.id === 'VERIFY' && (currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C')
                        ? 'border-rose-500/40 bg-rose-950/10'
                        : 'border-[#262938] bg-[#0d0f15]'
                  }`}
                >
                  {/* Active stage top banner */}
                  <div className="flex flex-wrap items-center justify-between pb-3 border-b border-[#1c1f2e] mb-5 gap-2">
                    <div className="flex items-center gap-3">
                      <span className={`font-mono text-sm font-bold ${
                        isUntrustedAI ? 'text-amber-400' : 'text-sky-400'
                      }`}>
                        ● {stage.num} {stage.label}
                      </span>
                      <span className="font-mono text-xs text-slate-200">
                        {activeStagePayload?.title}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 font-mono text-[10px]">
                      {isUntrustedAI ? (
                        <span className="text-amber-300 font-bold bg-amber-950/60 border border-amber-700/60 px-2 py-0.5">
                          UNTRUSTED AI REASONING · AUTHORITY: NONE
                        </span>
                      ) : (
                        <span className="text-emerald-300 font-bold bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5">
                          DETERMINISTIC MACHINE TRUTH
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Headline & rationale */}
                  <div className="mb-5 font-mono text-xs">
                    <div className="text-slate-200 font-medium leading-relaxed">
                      {activeStagePayload?.headline}
                    </div>
                    <div className="text-slate-400 text-[11px] mt-1.5 flex items-baseline gap-2">
                      <span className="text-slate-400 uppercase text-[9px] tracking-wider font-bold">RATIONALE:</span>
                      <span className="italic">{activeStagePayload?.whyThisHappened}</span>
                    </div>
                  </div>

                  {/* STAGE-SPECIFIC FORENSIC EVIDENCE */}
                  {/* 1. DETECT */}
                  {stage.id === 'DETECT' && activeStagePayload?.detectData && (
                    <div className="space-y-4 font-mono text-xs">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="p-3.5 bg-[#090a0f] border border-[#1a1c26]">
                          <div className="text-slate-400 text-[10px] uppercase font-bold mb-2">EXPECTED STATE</div>
                          <div className="space-y-1">
                            <div className="flex justify-between">
                              <span className="text-slate-400">Ledger Status:</span>
                              <span className="text-emerald-400 font-bold">{activeStagePayload.detectData.expected.status}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Amount:</span>
                              <span className="text-slate-200">₹{activeStagePayload.detectData.expected.amount.toLocaleString()} {activeStagePayload.detectData.expected.currency}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Source:</span>
                              <span className="text-slate-400 truncate">{activeStagePayload.detectData.expected.source}</span>
                            </div>
                          </div>
                        </div>

                        <div className="p-3.5 bg-[#090a0f] border border-[#1a1c26]">
                          <div className="text-slate-400 text-[10px] uppercase font-bold mb-2">OBSERVED PROVIDER STATE</div>
                          <div className="space-y-1">
                            <div className="flex justify-between">
                              <span className="text-slate-400">Webhook Status:</span>
                              <span className="text-amber-400 font-bold">{activeStagePayload.detectData.observed.status}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Amount:</span>
                              <span className="text-slate-200">₹{activeStagePayload.detectData.observed.amount.toLocaleString()} {activeStagePayload.detectData.observed.currency}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Provider:</span>
                              <span className="text-slate-400 truncate">{activeStagePayload.detectData.observed.provider}</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="p-3 bg-[#090a0f] border border-amber-900/40 text-amber-300 text-xs">
                        <strong>Discrepancy:</strong> {activeStagePayload.detectData.differenceSummary}
                      </div>
                    </div>
                  )}

                  {/* 2. INVESTIGATE */}
                  {stage.id === 'INVESTIGATE' && activeStagePayload?.investigateData && (
                    <div className="space-y-4 font-mono text-xs">
                      {/* Bounded Evidence List */}
                      <div>
                        <div className="text-[10px] font-bold uppercase text-slate-400 mb-2 flex items-center justify-between">
                          <span>BOUNDED EVIDENCE CONTEXT ({activeStagePayload.investigateData.boundedEvidence.length} RECORDS)</span>
                          <span className="text-slate-400">SHA256 Cryptographic Substrate</span>
                        </div>
                        <div className="space-y-1.5">
                          {activeStagePayload.investigateData.boundedEvidence.map(ev => (
                            <div key={ev.id} className="p-2 bg-[#090a0f] border border-[#1a1c26] flex items-center justify-between gap-4">
                              <div className="truncate">
                                <span className="text-sky-300 font-bold">{ev.id}</span>
                                <span className="text-slate-400 ml-3">{ev.summary}</span>
                              </div>
                              <span className="text-slate-400 text-[10px] shrink-0 font-mono">{ev.payloadHash.slice(0, 16)}...</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* AI Output */}
                      <div className="p-3 bg-[#090a0f] border border-amber-900/40 space-y-2">
                        <div className="text-[10px] text-amber-400 font-bold uppercase">PROPOSED CAUSAL HYPOTHESIS</div>
                        <div className="text-slate-200 italic font-sans text-xs leading-relaxed">
                          "{activeStagePayload.investigateData.llmOutput.hypothesis}"
                        </div>
                        <div className="flex flex-wrap gap-4 pt-2 border-t border-[#1a1c26] text-[11px]">
                          <div>
                            <span className="text-slate-400">Verification Intent:</span>{' '}
                            <span className="text-sky-300 font-bold">{activeStagePayload.investigateData.llmOutput.verificationIntent}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Target ID:</span>{' '}
                            <span className="text-slate-200">{activeStagePayload.investigateData.llmOutput.targetId}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Authority Granted:</span>{' '}
                            <span className="text-rose-400 font-bold">NONE (0%)</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 3. VERIFY */}
                  {stage.id === 'VERIFY' && activeStagePayload?.verifyData && (
                    <div className="space-y-4 font-mono text-xs">
                      {/* D4 Output Validation */}
                      <div className="p-3 bg-[#090a0f] border border-[#1a1c26] space-y-2">
                        <div className="text-[10px] font-bold uppercase text-slate-400 flex items-center justify-between">
                          <span>D4 DETERMINISTIC OUTPUT VALIDATION</span>
                          <span className={activeStagePayload.verifyData.d4Validation.passed ? 'text-emerald-400' : 'text-rose-400 font-bold'}>
                            {activeStagePayload.verifyData.d4Validation.passed ? 'PASSED ✓' : 'FAILED ✕'}
                          </span>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-[11px]">
                          <div className="text-slate-300">
                            • Evidence Containment: <strong className={activeStagePayload.verifyData.d4Validation.evidenceContainmentValid ? 'text-emerald-400' : 'text-rose-400'}>
                              {activeStagePayload.verifyData.d4Validation.evidenceContainmentValid ? 'VALID' : 'VIOLATION'}
                            </strong>
                          </div>
                          <div className="text-slate-300">
                            • Intent Schema: <strong className="text-emerald-400">VALID</strong>
                          </div>
                          <div className="text-slate-300">
                            • Mutation Authority: <strong className="text-rose-400">DENIED (Read-only)</strong>
                          </div>
                        </div>
                        {activeStagePayload.verifyData.d4Validation.rejectionReason && (
                          <div className="text-rose-300 text-[11px] pt-1 border-t border-rose-950">
                            {activeStagePayload.verifyData.d4Validation.rejectionReason}
                          </div>
                        )}
                      </div>

                      {/* Deterministic Verifier Query */}
                      <div className="p-3 bg-[#090a0f] border border-[#1a1c26] space-y-1.5">
                        <div className="text-[10px] font-bold uppercase text-slate-400">DETERMINISTIC VERIFIER · RAZORPAY API</div>
                        <div className="flex justify-between text-[11px]">
                          <span className="text-slate-400">Endpoint:</span>
                          <span className="text-sky-300">{activeStagePayload.verifyData.providerVerification.endpoint}</span>
                        </div>
                        <div className="flex justify-between text-[11px]">
                          <span className="text-slate-400">Provider Response:</span>
                          <span className={activeStagePayload.verifyData.providerVerification.captured ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                            HTTP {activeStagePayload.verifyData.providerVerification.responseStatus || 'BLOCKED'} · {activeStagePayload.verifyData.providerVerification.providerPaymentStatus}
                          </span>
                        </div>
                        {activeStagePayload.verifyData.providerVerification.error && (
                          <div className="text-rose-300 text-[11px] pt-1 border-t border-[#1a1c26]">
                            {activeStagePayload.verifyData.providerVerification.error}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* 4. DECIDE */}
                  {stage.id === 'DECIDE' && activeStagePayload?.decideData && (
                    <div className="space-y-3 font-mono text-xs">
                      <div className="p-3 bg-[#090a0f] border border-[#1a1c26] space-y-1.5">
                        <div className="text-[10px] font-bold uppercase text-slate-400">POLICY EVALUATION</div>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Matched Action:</span>
                          <span className="text-sky-300 font-bold">{activeStagePayload.decideData.policyAction}</span>
                        </div>
                        <div className="text-slate-300 text-[11px]">{activeStagePayload.decideData.decisionReason}</div>
                      </div>

                      <div className="p-3 bg-[#090a0f] border border-[#1a1c26] space-y-1.5">
                        <div className="text-[10px] font-bold uppercase text-slate-400">GOVERNANCE GATE CHECKS</div>
                        <div className="grid grid-cols-2 gap-2 text-[11px]">
                          <div className="text-slate-300">• Kill Switch: <strong className="text-emerald-400">{activeStagePayload.decideData.governance.killSwitchState}</strong></div>
                          <div className="text-slate-300">• Action Budget: <strong className="text-emerald-400">₹{activeStagePayload.decideData.governance.budgetUsed} / ₹{activeStagePayload.decideData.governance.budgetLimit.toLocaleString()}</strong></div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 5. ACT */}
                  {stage.id === 'ACT' && activeStagePayload?.actData && (
                    <div className="p-3 bg-[#090a0f] border border-[#1a1c26] space-y-1.5 font-mono text-xs">
                      <div className="text-[10px] font-bold uppercase text-slate-400">IDEMPOTENT ACTUATION</div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">OCC Lease:</span>
                        <span className="text-sky-300 font-bold">CAS Lease v{activeStagePayload.actData.actuation.occVersion.from} → v{activeStagePayload.actData.actuation.occVersion.to} Acquired</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Idempotency Key:</span>
                        <span className="text-slate-200">{activeStagePayload.actData.actuation.idempotencyKey}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Mutation Dispatched:</span>
                        <span className="text-emerald-400 font-bold">{activeStagePayload.actData.actuation.mutationDispatched}</span>
                      </div>
                    </div>
                  )}

                  {/* 6. RE-OBSERVE */}
                  {stage.id === 'REOBSERVE' && activeStagePayload?.reobserveData && (
                    <div className="p-3 bg-[#090a0f] border border-[#1a1c26] space-y-1.5 font-mono text-xs">
                      <div className="text-[10px] font-bold uppercase text-slate-400">FRESH STATE RE-OBSERVATION</div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Fresh Provider State:</span>
                        <span className="text-emerald-400 font-bold">{activeStagePayload.reobserveData.reobservation.rePolledState}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Re-reconciliation Outcome:</span>
                        <span className="text-emerald-400 font-bold">{activeStagePayload.reobserveData.reobservation.reconciliationOutcome}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Loop Status:</span>
                        <span className="text-sky-300 font-bold">VERIFIED CONVERGED</span>
                      </div>
                    </div>
                  )}

                  {/* 7. OUTCOME */}
                  {stage.id === 'TERMINAL' && activeStagePayload?.terminalData && (
                    <div className="p-3 bg-[#090a0f] border border-[#1a1c26] space-y-1.5 font-mono text-xs">
                      <div className="text-[10px] font-bold uppercase text-slate-400">FINAL INCIDENT DISPOSITION</div>
                      <div className="text-sm font-bold text-emerald-400">{activeStagePayload.terminalData.finalState}</div>
                      <div className="text-slate-300 text-xs">{activeStagePayload.terminalData.resolutionSummary}</div>
                      {activeStagePayload.terminalData.honestEscalationReason && (
                        <div className="text-rose-300 text-xs pt-1">
                          <strong>Halt reason:</strong> {activeStagePayload.terminalData.honestEscalationReason}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            }

            // 3C. Quiet pending stages
            if (isPending) {
              return (
                <div
                  key={stage.id}
                  className="py-2.5 px-3 flex items-baseline gap-4 font-mono text-xs text-slate-400 border-b border-[#14161f]"
                >
                  <span className="shrink-0 text-slate-400">○ {stage.num} {stage.label}</span>
                  <span className="text-slate-400 text-xs">{getStagePendingSummary(stage.id)}</span>
                </div>
              );
            }

            return null;
          })}
        </section>

        {/* 4. Operator Interventions: Minimal single-line row */}
        <section className="mt-8 pt-4 border-t border-[#1a1c26] flex flex-wrap items-center justify-between font-mono text-xs text-slate-400 gap-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">OPERATOR CONTROLS:</span>
            {operatorNotice && <span className="text-emerald-400 text-[11px]">{operatorNotice}</span>}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setOperatorNotice('Operator manual resolution recorded.')}
              className="px-2.5 py-1 bg-[#12141c] hover:bg-[#1a1c26] border border-[#262938] text-slate-300 hover:text-white transition-colors"
            >
              MANUAL RESOLVE
            </button>
            <button
              type="button"
              onClick={() => setOperatorNotice('Pipeline retry scheduled.')}
              className="px-2.5 py-1 bg-[#12141c] hover:bg-[#1a1c26] border border-[#262938] text-amber-400/80 hover:text-amber-300 transition-colors"
            >
              RETRY PIPELINE
            </button>
            <button
              type="button"
              onClick={() => setOperatorNotice('Forced escalation logged.')}
              className="px-2.5 py-1 bg-[#12141c] hover:bg-[#1a1c26] border border-[#262938] text-rose-400/80 hover:text-rose-300 transition-colors"
            >
              FORCE ESCALATE
            </button>
          </div>
        </section>

        {/* 5. Audit Footer: Machine Assertions + Timeline */}
        <footer className="mt-8 pt-6 border-t border-[#1a1c26] grid grid-cols-1 md:grid-cols-2 gap-8 font-mono text-xs">
          {/* Left Column: Machine Assertions */}
          <div>
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-3">
              MACHINE EVIDENCE ASSERTIONS ({proofs.length})
            </div>
            <div className="space-y-1.5 text-slate-300">
              {proofs.map(p => (
                <div key={p.id} className="flex items-start gap-2">
                  <span className={`shrink-0 ${p.status === 'BLOCKED' ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {p.status === 'BLOCKED' ? '✕' : '✓'}
                  </span>
                  <div>
                    <span className="font-semibold text-slate-200">{p.title}</span>
                    {p.subtitle && <span className="text-slate-400 text-[11px] ml-2">— {p.subtitle}</span>}
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

          {/* Right Column: Running Control Trace */}
          <div>
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center justify-between">
              <span>RUNNING CONTROL TRACE</span>
              <span className="text-slate-400">{timeline.length} events recorded</span>
            </div>
            <div className="space-y-1 text-slate-400 text-[11px]">
              {timeline.map((item, i) => (
                <div key={i} className="flex items-baseline gap-3">
                  <span className="text-slate-400 shrink-0 font-mono text-[10px]">{item.time}</span>
                  <span className="text-sky-300 font-bold shrink-0">{item.stage}</span>
                  <span className="text-slate-300 truncate">{item.detail}</span>
                </div>
              ))}
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
};
