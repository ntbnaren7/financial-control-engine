import type { ProofItem } from '../types';

interface ControlProofPanelProps {
  proofs: ProofItem[];
  currentScenarioName: string;
  isTerminal: boolean;
  terminalState?: string;
}

export const ControlProofPanel: React.FC<ControlProofPanelProps> = ({
  proofs,
  currentScenarioName,
  isTerminal,
  terminalState = 'RESOLVED'
}) => {
  return (
    <div className="flex flex-col h-full bg-slate-950/80 border-l border-slate-800/80 p-4 font-mono text-xs select-none overflow-hidden">
      {/* Top Title Banner */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3 shrink-0">
        <div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-bold tracking-widest uppercase bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded-xs text-sky-400">
              LAYER 3 • PROOF
            </span>
            <span className="font-bold text-slate-200 uppercase tracking-wider text-xs">
              CONTROL PROOF
            </span>
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            Machine evidence for {currentScenarioName}
          </div>
        </div>

        <span className={`text-[9px] font-bold px-2 py-0.5 rounded-xs border ${
          terminalState === 'RESOLVED'
            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
            : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
        }`}>
          {proofs.length} Assertions
        </span>
      </div>

      {/* Proof List Ledger */}
      <div className="flex-1 overflow-y-auto pr-1 flex flex-col gap-2.5">
        {proofs.length === 0 && (
          <div className="h-48 flex flex-col items-center justify-center p-4 border border-dashed border-slate-800 rounded-sm text-center">
            <span className="text-slate-500 text-xs">Run or step through the control loop to accumulate cryptographic & governance proofs.</span>
          </div>
        )}

        {proofs.map((proof, idx) => {
          const isBlocked = proof.status === 'BLOCKED';
          const isUntrusted = proof.authority === 'UNTRUSTED_AI';

          return (
            <div
              key={proof.id || idx}
              className={`p-2.5 rounded-sm border transition-all ${
                isBlocked
                  ? 'bg-rose-950/30 border-rose-600/50 text-rose-200'
                  : isUntrusted
                    ? 'bg-amber-950/20 border-amber-600/40 text-amber-200'
                    : 'bg-slate-900/80 border-slate-800 text-slate-200'
              }`}
            >
              {/* Proof Item Header */}
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-1.5">
                  <span className={`w-4 h-4 rounded-xs flex items-center justify-center text-[10px] font-bold shrink-0 ${
                    isBlocked
                      ? 'bg-rose-500 text-slate-950'
                      : isUntrusted
                        ? 'bg-amber-500 text-slate-950'
                        : 'bg-emerald-500 text-slate-950'
                  }`}>
                    {isBlocked ? '✕' : isUntrusted ? '⚠' : '✓'}
                  </span>
                  <span className="font-bold text-[11px] text-slate-100 uppercase tracking-tight">
                    {proof.title}
                  </span>
                </div>

                <span className={`text-[8px] font-bold uppercase px-1 py-0.2 rounded-xs border ${
                  isBlocked
                    ? 'bg-rose-950 text-rose-300 border-rose-800'
                    : isUntrusted
                      ? 'bg-amber-950 text-amber-300 border-amber-800'
                      : 'bg-emerald-950 text-emerald-300 border-emerald-800'
                }`}>
                  {proof.authority === 'UNTRUSTED_AI' ? 'UNTRUSTED' : 'VERIFIED'}
                </span>
              </div>

              {proof.subtitle && (
                <div className="text-[10px] text-slate-400 mb-2 leading-tight">
                  {proof.subtitle}
                </div>
              )}

              {/* Detailed Machine Assertions */}
              <div className="flex flex-col gap-1 bg-slate-950/60 p-2 rounded-xs border border-slate-800/80 text-[10px]">
                {proof.details.map((detail, dIdx) => (
                  <div key={dIdx} className="flex justify-between items-baseline gap-2">
                    <span className="text-slate-400 shrink-0">{detail.label}:</span>
                    <span className={`text-right truncate font-medium ${
                      detail.isBlocked
                        ? 'text-rose-400 font-bold'
                        : detail.isFlag
                          ? 'text-amber-300 font-bold'
                          : 'text-slate-200'
                    }`}>
                      {detail.value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Terminal Proof Anchor */}
      {isTerminal && (
        <div className="mt-3 pt-3 border-t border-slate-800 shrink-0">
          <div className={`p-2 rounded-sm border text-center ${
            terminalState === 'RESOLVED'
              ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-300'
              : 'bg-rose-950/40 border-rose-500/50 text-rose-300'
          }`}>
            <div className="font-bold text-[11px] uppercase tracking-wider">
              {terminalState === 'RESOLVED' ? '✓ PROVED: CONVERGED' : '⚠ PROVED: CONTAINED & ESCALATED'}
            </div>
            <div className="text-[9px] text-slate-400 mt-0.5">
              Every boundary transition verified by deterministic substrate
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
