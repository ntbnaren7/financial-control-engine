import type { PipelineStageId, StageExecutionPayload, StageStatus } from '../types';

interface LiveExecutionCenterProps {
  currentStageId: PipelineStageId;
  selectedStageId: PipelineStageId;
  stagePayloads: Record<PipelineStageId, StageExecutionPayload>;
  stageStatuses: Record<PipelineStageId, StageStatus>;
  onAdvanceStage: () => void;
  isTerminal: boolean;
}

export const LiveExecutionCenter: React.FC<LiveExecutionCenterProps> = ({
  selectedStageId,
  stagePayloads,
  stageStatuses,
  onAdvanceStage,
  isTerminal
}) => {
  const payload = stagePayloads[selectedStageId];
  const status = stageStatuses[selectedStageId] || 'PENDING';
  const isUntrustedAI = payload?.authorityBadge?.domain === 'UNTRUSTED_AI';

  if (!payload) {
    return (
      <div className="h-full flex items-center justify-center p-8 bg-slate-900/40 border border-slate-800 rounded-sm">
        <span className="font-mono text-xs text-slate-500">Stage payload not initialized</span>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950/60 p-4 overflow-y-auto font-mono text-xs select-none">
      {/* 1. Header Banner of the Active/Selected Stage */}
      <div className={`p-3 rounded-sm border mb-4 ${
        isUntrustedAI 
          ? 'bg-amber-950/30 border-amber-600/40 text-amber-200'
          : status === 'BLOCKED'
            ? 'bg-rose-950/30 border-rose-600/40 text-rose-200'
            : status === 'COMPLETED'
              ? 'bg-emerald-950/30 border-emerald-600/40 text-emerald-200'
              : 'bg-slate-900/60 border-slate-800 text-slate-300'
      }`}>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold tracking-widest uppercase bg-slate-950 px-2 py-0.5 rounded-xs border border-slate-800">
              LAYER 2 • MECHANISM
            </span>
            <span className="font-semibold text-sm text-slate-100 uppercase tracking-wide">
              {payload.title}
            </span>
          </div>

          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-xs border ${
            isUntrustedAI
              ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
              : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50'
          }`}>
            {payload.authorityBadge.text}
          </span>
        </div>

        <div className="text-xs text-slate-300 font-sans mt-1">
          {payload.headline}
        </div>

        <div className="text-[11px] text-slate-400 mt-1 border-t border-slate-800/80 pt-1 flex items-center gap-1.5">
          <span className="font-bold text-slate-500 uppercase tracking-wider text-[9px]">Why did this happen?</span>
          <span className="text-slate-300 italic">{payload.whyThisHappened}</span>
        </div>
      </div>

      {/* 2. Dynamic Content Area based on Stage */}
      <div className="flex-1 flex flex-col gap-4 overflow-y-auto pr-1">
        {/* STAGE: DETECT (Reconciliation Engine) */}
        {selectedStageId === 'DETECT' && payload.detectData && (
          <div className="flex flex-col gap-3">
            <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400 flex items-center justify-between">
              <span>DETERMINISTIC RECONCILIATION COMPARISON</span>
              <span className="text-sky-400">Zero LLM Involvement</span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {/* Expected Card */}
              <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm flex flex-col gap-2">
                <div className="flex justify-between items-center border-b border-slate-800 pb-1.5">
                  <span className="font-bold text-slate-300">EXPECTED (Internal Ledger)</span>
                  <span className="text-[10px] text-slate-500">{payload.detectData.expected.id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Status:</span>
                  <span className="text-emerald-400 font-bold">{payload.detectData.expected.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Amount:</span>
                  <span className="text-slate-200">₹{payload.detectData.expected.amount.toLocaleString()} {payload.detectData.expected.currency}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Source:</span>
                  <span className="text-slate-400 truncate">{payload.detectData.expected.source}</span>
                </div>
              </div>

              {/* Observed Card */}
              <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm flex flex-col gap-2">
                <div className="flex justify-between items-center border-b border-slate-800 pb-1.5">
                  <span className="font-bold text-slate-300">OBSERVED (Razorpay Webhook)</span>
                  <span className="text-[10px] text-slate-500">{payload.detectData.observed.id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Status:</span>
                  <span className="text-amber-400 font-bold">{payload.detectData.observed.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Amount:</span>
                  <span className="text-slate-200">₹{payload.detectData.observed.amount.toLocaleString()} {payload.detectData.observed.currency}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Provider:</span>
                  <span className="text-slate-400 truncate">{payload.detectData.observed.provider}</span>
                </div>
              </div>
            </div>

            {/* Discrepancy Highlight */}
            <div className="p-3 bg-amber-950/20 border border-amber-600/30 rounded-sm flex items-start gap-2.5">
              <span className="text-amber-400 text-sm mt-0.5">⚠</span>
              <div className="flex flex-col gap-1">
                <span className="font-bold text-amber-300 text-xs">
                  DISCREPANCY DETECTED: {payload.detectData.discrepancyType}
                </span>
                <span className="text-slate-300 font-sans text-xs">
                  {payload.detectData.differenceSummary}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* STAGE: INVESTIGATE (Bounded Context & AI Reasoning) */}
        {selectedStageId === 'INVESTIGATE' && payload.investigateData && (
          <div className="flex flex-col gap-4">
            {/* Bounded Evidence Table */}
            <div className="bg-slate-900/80 border border-slate-800 p-3 rounded-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold text-slate-300 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                  <svg className="w-3.5 h-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                  BOUNDED EVIDENCE CONTEXT ({payload.investigateData.boundedEvidence.length} Records)
                </span>
                <span className="text-[9px] text-emerald-400 bg-emerald-950/40 border border-emerald-800 px-1.5 py-0.2 rounded-xs">
                  Cryptographically Hashed
                </span>
              </div>

              <div className="flex flex-col gap-1.5">
                {payload.investigateData.boundedEvidence.map(ev => (
                  <div key={ev.id} className="p-2 bg-slate-950/60 border border-slate-800 rounded-xs flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sky-300">{ev.id}</span>
                      <span className="text-[10px] text-slate-400">{ev.source} • {ev.timestamp}</span>
                    </div>
                    <div className="text-slate-300 font-sans text-xs">{ev.summary}</div>
                    <div className="text-[9px] text-slate-400 truncate">SHA256: {ev.payloadHash}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Untrusted LLM Output */}
            <div className="bg-amber-950/20 border border-amber-600/40 p-3 rounded-sm flex flex-col gap-2.5">
              <div className="flex items-center justify-between border-b border-amber-900/40 pb-1.5">
                <span className="font-bold text-amber-300 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
                  UNTRUSTED AI REASONING OUTPUT
                </span>
                <span className="text-[9px] font-bold bg-amber-900/40 text-amber-300 border border-amber-700/50 px-2 py-0.5 rounded-xs">
                  FINANCIAL AUTHORITY: NONE
                </span>
              </div>

              <div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Causal Hypothesis:</div>
                <div className="p-2 bg-slate-950/80 border border-amber-900/30 rounded-xs text-amber-100/90 font-sans italic text-xs leading-relaxed">
                  "{payload.investigateData.llmOutput.hypothesis}"
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2 bg-slate-950/60 border border-slate-800 rounded-xs">
                  <span className="text-slate-400 block text-[10px]">Proposed Verification Intent:</span>
                  <span className="text-sky-300 font-semibold">{payload.investigateData.llmOutput.verificationIntent}</span>
                </div>
                <div className="p-2 bg-slate-950/60 border border-slate-800 rounded-xs">
                  <span className="text-slate-400 block text-[10px]">Verification Target:</span>
                  <span className="text-slate-200 font-semibold truncate">{payload.investigateData.llmOutput.targetId}</span>
                </div>
              </div>

              <div>
                <span className="text-[10px] text-slate-400 block mb-1">Referenced Evidence IDs:</span>
                <div className="flex flex-wrap gap-1">
                  {payload.investigateData.llmOutput.referencedEvidenceIds.map(id => {
                    const isHallucinated = id.includes('hallucinated') || id.includes('fabricated');
                    return (
                      <span
                        key={id}
                        className={`px-2 py-0.5 rounded-xs text-[10px] border ${
                          isHallucinated
                            ? 'bg-rose-950/80 text-rose-300 border-rose-500 font-bold animate-pulse'
                            : 'bg-slate-900 text-slate-300 border-slate-700'
                        }`}
                      >
                        {isHallucinated && '✕ '}
                        {id}
                      </span>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* STAGE: VERIFY (D4 Gate & Provider Verification) */}
        {selectedStageId === 'VERIFY' && payload.verifyData && (
          <div className="flex flex-col gap-4">
            {/* D4 Validation Check Card */}
            <div className={`p-3 rounded-sm border ${
              payload.verifyData.d4Validation.passed
                ? 'bg-emerald-950/20 border-emerald-600/40'
                : 'bg-rose-950/30 border-rose-600/50'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                  <span>D4 DETERMINISTIC OUTPUT VALIDATOR</span>
                </span>
                <span className={`px-2 py-0.5 text-[9px] font-bold rounded-xs border ${
                  payload.verifyData.d4Validation.passed
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                }`}>
                  {payload.verifyData.d4Validation.passed ? 'VALIDATED ✓' : 'REJECTED ✕'}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="flex items-center justify-between p-1.5 bg-slate-950/60 rounded-xs border border-slate-800">
                  <span className="text-slate-400">Evidence Containment:</span>
                  <span className={payload.verifyData.d4Validation.evidenceContainmentValid ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {payload.verifyData.d4Validation.evidenceContainmentValid ? 'CONTAINED ✓' : 'VIOLATION ✕'}
                  </span>
                </div>
                <div className="flex items-center justify-between p-1.5 bg-slate-950/60 rounded-xs border border-slate-800">
                  <span className="text-slate-400">Output Schema:</span>
                  <span className="text-emerald-400 font-bold">VALID ✓</span>
                </div>
                <div className="flex items-center justify-between p-1.5 bg-slate-950/60 rounded-xs border border-slate-800">
                  <span className="text-slate-400">Provider Query Authority:</span>
                  <span className={payload.verifyData.d4Validation.providerQueryPermitted ? 'text-sky-400 font-bold' : 'text-rose-400 font-bold'}>
                    {payload.verifyData.d4Validation.providerQueryPermitted ? 'READ-ONLY GRANTED' : 'BLOCKED ✕'}
                  </span>
                </div>
                <div className="flex items-center justify-between p-1.5 bg-slate-950/60 rounded-xs border border-slate-800">
                  <span className="text-slate-400">Financial Mutation Authority:</span>
                  <span className="text-rose-400 font-bold">DENIED (0% Permission)</span>
                </div>
              </div>

              {payload.verifyData.d4Validation.rejectionReason && (
                <div className="mt-2 p-2 bg-rose-950/60 border border-rose-800 rounded-xs text-rose-200 font-sans text-xs">
                  <strong>Rejection Notice:</strong> {payload.verifyData.d4Validation.rejectionReason}
                </div>
              )}
            </div>

            {/* Provider Verification Card */}
            <div className={`p-3 rounded-sm border ${
              payload.verifyData.providerVerification.responseStatus === 200
                ? 'bg-slate-900/80 border-slate-800'
                : 'bg-rose-950/20 border-rose-900/40'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                  A4 DETERMINISTIC VERIFIER • RAZORPAY API CALL
                </span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-xs border ${
                  payload.verifyData.providerVerification.responseStatus === 200
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                }`}>
                  HTTP {payload.verifyData.providerVerification.responseStatus || 'BLOCKED'}
                </span>
              </div>

              <div className="p-2 bg-slate-950/80 rounded-xs border border-slate-800 flex flex-col gap-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-400">API Endpoint:</span>
                  <span className="text-sky-300 font-bold">{payload.verifyData.providerVerification.endpoint}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Provider Status:</span>
                  <span className={payload.verifyData.providerVerification.captured ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {payload.verifyData.providerVerification.providerPaymentStatus}
                  </span>
                </div>
                {payload.verifyData.providerVerification.amount > 0 && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Confirmed Amount:</span>
                    <span className="text-slate-200">₹{payload.verifyData.providerVerification.amount.toLocaleString()} {payload.verifyData.providerVerification.currency}</span>
                  </div>
                )}
                {payload.verifyData.providerVerification.error && (
                  <div className="text-rose-300 font-mono text-[11px] pt-1 border-t border-slate-800">
                    {payload.verifyData.providerVerification.error}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* STAGE: DECIDE (Policy & Governance) */}
        {selectedStageId === 'DECIDE' && payload.decideData && (
          <div className="flex flex-col gap-3">
            <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm flex flex-col gap-2">
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
                <span className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                  RECOVERY POLICY RESOLUTION
                </span>
                <span className="text-sky-400 font-bold text-xs">
                  {payload.decideData.policyAction}
                </span>
              </div>
              <div className="text-slate-300 font-sans text-xs">
                {payload.decideData.decisionReason}
              </div>
            </div>

            <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm flex flex-col gap-2">
              <span className="font-bold text-slate-300 uppercase tracking-wider text-[11px] border-b border-slate-800 pb-1.5">
                GOVERNANCE GATEWAY CHECKS
              </span>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2 bg-slate-950/60 rounded-xs border border-slate-800 flex justify-between">
                  <span className="text-slate-400">Kill Switch:</span>
                  <span className="text-emerald-400 font-bold">{payload.decideData.governance.killSwitchState} ✓</span>
                </div>
                <div className="p-2 bg-slate-950/60 rounded-xs border border-slate-800 flex justify-between">
                  <span className="text-slate-400">Action Budget Quota:</span>
                  <span className={payload.decideData.governance.budgetAvailable ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {payload.decideData.governance.budgetAvailable ? 'AVAILABLE ✓' : 'EXHAUSTED ✕'}
                  </span>
                </div>
                <div className="p-2 bg-slate-950/60 rounded-xs border border-slate-800 flex justify-between">
                  <span className="text-slate-400">Daily Limit:</span>
                  <span className="text-slate-300">₹{payload.decideData.governance.budgetLimit.toLocaleString()}</span>
                </div>
                <div className="p-2 bg-slate-950/60 rounded-xs border border-slate-800 flex justify-between">
                  <span className="text-slate-400">Mutation Gate:</span>
                  <span className={payload.decideData.governance.mutationAllowed ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {payload.decideData.governance.mutationAllowed ? 'AUTHORIZED' : 'BLOCKED'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* STAGE: ACT (Idempotent Actuator) */}
        {selectedStageId === 'ACT' && payload.actData && (
          <div className="flex flex-col gap-3">
            <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm flex flex-col gap-2">
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
                <span className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                  OCC LEASE & IDEMPOTENCY LOCK
                </span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-xs border ${
                  payload.actData.actuation.resultStatus === 'SUCCEEDED'
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                }`}>
                  {payload.actData.actuation.resultStatus}
                </span>
              </div>

              <div className="p-2 bg-slate-950/80 rounded-xs border border-slate-800 flex flex-col gap-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-400">Atomic OCC Version:</span>
                  <span className="text-sky-300 font-bold">
                    v{payload.actData.actuation.occVersion.from} → v{payload.actData.actuation.occVersion.to}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Idempotency Key:</span>
                  <span className="text-slate-200 font-semibold">{payload.actData.actuation.idempotencyKey}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Dispatched Mutation:</span>
                  <span className="text-slate-200">{payload.actData.actuation.mutationDispatched}</span>
                </div>
                {payload.actData.actuation.refundId && (
                  <div className="flex justify-between pt-1 border-t border-slate-800">
                    <span className="text-slate-400">Provider Refund ID:</span>
                    <span className="text-emerald-400 font-bold">{payload.actData.actuation.refundId}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* STAGE: REOBSERVE (Fresh State & Convergence) */}
        {selectedStageId === 'REOBSERVE' && payload.reobserveData && (
          <div className="flex flex-col gap-3">
            <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm flex flex-col gap-2">
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
                <span className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                  POST-MUTATION FRESH RE-OBSERVATION
                </span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-xs border ${
                  payload.reobserveData.reobservation.converged
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                }`}>
                  {payload.reobserveData.reobservation.converged ? 'CONVERGED ✓' : 'DISCREPANCY PENDING'}
                </span>
              </div>

              <div className="p-2 bg-slate-950/80 rounded-xs border border-slate-800 flex flex-col gap-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-400">Fresh Provider State:</span>
                  <span className="text-emerald-400 font-bold">{payload.reobserveData.reobservation.rePolledState}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Reconciliation Outcome:</span>
                  <span className="text-emerald-400 font-bold">{payload.reobserveData.reobservation.reconciliationOutcome}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Control Loop State:</span>
                  <span className="text-sky-300 font-bold">{payload.reobserveData.reobservation.terminalState}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* STAGE: TERMINAL (Final Result) */}
        {selectedStageId === 'TERMINAL' && payload.terminalData && (
          <div className="flex flex-col gap-3">
            <div className={`p-4 rounded-sm border ${
              payload.terminalData.finalState === 'RESOLVED'
                ? 'bg-emerald-950/30 border-emerald-500/50 text-emerald-200'
                : 'bg-rose-950/30 border-rose-500/50 text-rose-200'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold uppercase tracking-wider text-xs">
                  {payload.terminalData.finalState}
                </span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-xs border bg-slate-950 border-slate-800">
                  {payload.terminalData.isRemediated ? 'AUTONOMOUS RESOLUTION' : 'SAFE ESCALATION'}
                </span>
              </div>

              <div className="font-sans text-xs text-slate-200 leading-relaxed mb-3">
                {payload.terminalData.resolutionSummary}
              </div>

              {payload.terminalData.honestEscalationReason && (
                <div className="p-2 bg-slate-950/80 border border-rose-900/60 rounded-xs text-[11px] text-rose-300">
                  <strong>Why did it stop?</strong> {payload.terminalData.honestEscalationReason}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 3. Footer / Next Stage Nav */}
      <div className="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between">
        <span className="text-[10px] text-slate-500">
          Showing Layer 2 Mechanism for <span className="text-slate-300 font-bold">{selectedStageId}</span>
        </span>

        {!isTerminal && (
          <button
            type="button"
            onClick={onAdvanceStage}
            className="bg-sky-600/30 hover:bg-sky-600/50 text-sky-200 border border-sky-500/50 px-3 py-1.5 rounded-sm text-xs font-semibold uppercase tracking-wider transition-colors flex items-center gap-1.5"
          >
            <span>Advance to Next Stage</span>
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
};
