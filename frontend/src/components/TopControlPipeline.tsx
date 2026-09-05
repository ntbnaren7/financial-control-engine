import type { PipelineStageId, StageStatus, AuthorityDomain } from '../types';

interface StageDefinition {
  id: PipelineStageId;
  stepNumber: string;
  label: string;
  sublabel: string;
  authority: AuthorityDomain;
}

const STAGES: StageDefinition[] = [
  {
    id: 'DETECT',
    stepNumber: '①',
    label: 'DETECT',
    sublabel: 'Ingest / Reconcile',
    authority: 'DETERMINISTIC'
  },
  {
    id: 'INVESTIGATE',
    stepNumber: '②',
    label: 'INVESTIGATE',
    sublabel: 'A3 Reasoner',
    authority: 'UNTRUSTED_AI'
  },
  {
    id: 'VERIFY',
    stepNumber: '③',
    label: 'VERIFY',
    sublabel: 'A4 Verifier',
    authority: 'DETERMINISTIC'
  },
  {
    id: 'DECIDE',
    stepNumber: '④',
    label: 'DECIDE',
    sublabel: 'Policy & Gov',
    authority: 'DETERMINISTIC'
  },
  {
    id: 'ACT',
    stepNumber: '⑤',
    label: 'ACT',
    sublabel: 'OCC Actuator',
    authority: 'DETERMINISTIC'
  },
  {
    id: 'REOBSERVE',
    stepNumber: '⑥',
    label: 'RE-OBSERVE',
    sublabel: 'Fresh State',
    authority: 'DETERMINISTIC'
  },
  {
    id: 'TERMINAL',
    stepNumber: '⑦',
    label: 'OUTCOME',
    sublabel: 'Terminal State',
    authority: 'DETERMINISTIC'
  }
];

interface TopControlPipelineProps {
  currentStageId: PipelineStageId;
  selectedStageId: PipelineStageId;
  stageStatuses: Record<PipelineStageId, StageStatus>;
  onSelectStage: (stageId: PipelineStageId) => void;
  terminalStateName?: string;
}

export const TopControlPipeline: React.FC<TopControlPipelineProps> = ({
  currentStageId,
  selectedStageId,
  stageStatuses,
  onSelectStage,
  terminalStateName = 'RESOLVED'
}) => {
  return (
    <div className="w-full bg-slate-950 border-b border-slate-800 px-4 py-3 shrink-0 select-none shadow-md">
      {/* Top Narrative Anchor & Authority Boundaries */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-sky-400"></span>
            6 Control Stages + Terminal Outcome
          </span>
          <span className="text-slate-600 text-xs">•</span>
          <span className="font-mono text-[10px] text-slate-400">
            Engine Position: <span className="text-emerald-300 font-semibold">{currentStageId}</span>
            <span className="text-slate-600 mx-1.5">•</span>
            Viewing: <span className="text-sky-300 font-semibold">{selectedStageId}</span>
          </span>
        </div>

        {/* Authority Boundaries legend */}
        <div className="hidden lg:flex items-center gap-3 font-mono text-[10px]">
          <span className="flex items-center gap-1 text-emerald-400/90 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded-sm">
            <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            DETERMINISTIC CONTROL (Machine Truth)
          </span>
          <span className="flex items-center gap-1 text-amber-400 bg-amber-950/40 border border-amber-800/50 px-2 py-0.5 rounded-sm">
            <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            UNTRUSTED AI REASONING (Authority: NONE)
          </span>
        </div>
      </div>

      {/* Horizontal Pipeline Grid */}
      <div className="grid grid-cols-7 gap-2 relative">
        {STAGES.map((stage, idx) => {
          const status = stageStatuses[stage.id] || 'PENDING';
          const isSelected = selectedStageId === stage.id;
          const isUntrustedAI = stage.authority === 'UNTRUSTED_AI';

          // Node styling based on state
          let badgeBg = 'bg-slate-900 border-slate-800 text-slate-500';
          let statusIcon = <span className="text-[11px] font-mono">{stage.stepNumber}</span>;
          let labelColor = 'text-slate-400';
          let sublabelColor = 'text-slate-600';

          if (status === 'COMPLETED') {
            badgeBg = 'bg-emerald-950/70 border-emerald-500/60 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.2)]';
            statusIcon = (
              <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            );
            labelColor = 'text-emerald-200';
            sublabelColor = 'text-emerald-400/70';
          } else if (status === 'ACTIVE') {
            if (isUntrustedAI) {
              badgeBg = 'bg-amber-950/80 border-amber-400 text-amber-300 shadow-[0_0_16px_rgba(245,158,11,0.4)] animate-pulse';
              statusIcon = <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping"></span>;
              labelColor = 'text-amber-300 font-bold';
              sublabelColor = 'text-amber-400/90';
            } else {
              badgeBg = 'bg-sky-950/80 border-sky-400 text-sky-300 shadow-[0_0_16px_rgba(56,189,248,0.4)] animate-pulse';
              statusIcon = <span className="inline-block w-2.5 h-2.5 rounded-full bg-sky-400 animate-ping"></span>;
              labelColor = 'text-sky-300 font-bold';
              sublabelColor = 'text-sky-400/90';
            }
          } else if (status === 'BLOCKED') {
            badgeBg = 'bg-rose-950/90 border-rose-500 text-rose-400 shadow-[0_0_16px_rgba(244,63,94,0.4)]';
            statusIcon = (
              <svg className="w-3.5 h-3.5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
              </svg>
            );
            labelColor = 'text-rose-300 font-bold';
            sublabelColor = 'text-rose-400/90';
          } else if (status === 'SKIPPED') {
            badgeBg = 'bg-slate-900/40 border-slate-800/40 text-slate-600';
            statusIcon = <span className="text-[11px] font-mono">—</span>;
            labelColor = 'text-slate-600';
            sublabelColor = 'text-slate-700';
          }

          const isLast = idx === STAGES.length - 1;

          return (
            <div key={stage.id} className="relative group">
              <button
                type="button"
                onClick={() => onSelectStage(stage.id)}
                className={`w-full text-left p-2 rounded-sm border transition-all duration-150 flex flex-col justify-between relative overflow-hidden ${
                  isSelected
                    ? 'ring-1 ring-sky-400 bg-slate-800/90 border-sky-500/80'
                    : 'hover:bg-slate-800/50 hover:border-slate-700'
                } ${isUntrustedAI ? 'border-dashed' : 'border-solid'} ${badgeBg}`}
              >
                {/* Active indicator bar */}
                {isSelected && (
                  <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-sky-400 via-sky-300 to-sky-500"></div>
                )}

                <div className="flex items-center justify-between w-full mb-1">
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-4 flex items-center justify-center shrink-0">
                      {statusIcon}
                    </div>
                    <span className={`font-mono text-[11px] tracking-wider uppercase ${labelColor}`}>
                      {stage.label}
                    </span>
                  </div>

                  {isUntrustedAI && (
                    <span className="text-[8px] font-mono uppercase bg-amber-500/20 text-amber-300 border border-amber-500/30 px-1 py-0.2 rounded-xs">
                      AI A3
                    </span>
                  )}
                  {stage.id === 'TERMINAL' && (
                    <span className={`text-[8px] font-mono uppercase px-1 py-0.2 rounded-xs border ${
                      terminalStateName.startsWith('ESCALATED')
                        ? 'bg-rose-500/20 text-rose-300 border-rose-500/30'
                        : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                    }`}>
                      {terminalStateName === 'RESOLVED' ? 'CONVERGED' : 'ESCALATED'}
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-between w-full">
                  <span className={`font-mono text-[10px] truncate ${sublabelColor}`}>
                    {stage.id === 'TERMINAL' ? terminalStateName : stage.sublabel}
                  </span>
                  <span className="font-mono text-[8px] text-slate-400 shrink-0 uppercase tracking-tighter">
                    {status === 'ACTIVE' ? 'RUNNING' : status}
                  </span>
                </div>
              </button>

              {/* Connecting arrow line between stages */}
              {!isLast && (
                <div className="hidden md:block absolute -right-2 top-1/2 -translate-y-1/2 z-10 text-slate-700 pointer-events-none">
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
