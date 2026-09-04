import React from 'react';
import { type AuditTrace } from '../services/api';

interface ControlPipelineProps {
  trace: AuditTrace | null;
}

type NodeState = 'COMPLETE' | 'ACTIVE' | 'BLOCKED' | 'NOT_REACHED';

interface PipelineStage {
  id: string;
  label: string;
  state: NodeState;
  evidence?: string | React.ReactNode;
}

function calculatePipelineNodes(trace: AuditTrace | null): PipelineStage[] {
  const stages: PipelineStage[] = [
    { id: 'ingestion', label: 'Ingestion', state: 'NOT_REACHED' },
    { id: 'observation', label: 'Observation', state: 'NOT_REACHED' },
    { id: 'reconciliation', label: 'Reconciliation', state: 'NOT_REACHED' },
    { id: 'investigation', label: 'Investigation', state: 'NOT_REACHED' },
    { id: 'verification', label: 'Verification', state: 'NOT_REACHED' },
    { id: 'policy', label: 'Policy', state: 'NOT_REACHED' },
    { id: 'governance', label: 'Governance', state: 'NOT_REACHED' },
    { id: 'actuation', label: 'Actuation', state: 'NOT_REACHED' },
    { id: 'reobservation', label: 'Re-observation', state: 'NOT_REACHED' },
    { id: 'resolution', label: 'Resolution / Escalation', state: 'NOT_REACHED' },
  ];

  if (!trace) return stages;

  const tl = trace.timeline.map(t => t.step);
  const s = trace.current_state;
  const has = (step: string) => tl.includes(step);

  const setStage = (id: string, state: NodeState, evidence?: string | React.ReactNode) => {
    const idx = stages.findIndex(st => st.id === id);
    if (idx !== -1) {
      stages[idx].state = state;
      if (evidence) stages[idx].evidence = evidence;
    }
  };

  // Ingestion & Observation
  setStage('ingestion', 'COMPLETE', 'Payload Persisted');
  setStage('observation', 'COMPLETE', 'Canonical Observation');

  // Reconciliation
  const reconState = has('DISCREPANCY_DETECTED') ? 'COMPLETE' : (trace.discrepancy ? 'COMPLETE' : 'ACTIVE');
  setStage('reconciliation', reconState, trace.discrepancy?.discrepancy_reason || 'Evaluating');

  // Investigation
  let invState: NodeState = 'NOT_REACHED';
  if (reconState === 'COMPLETE') {
    if (s.startsWith('ESCALATED')) {
      invState = 'COMPLETE';
    } else if (trace.hypothesis_available) {
      invState = 'COMPLETE';
    } else if (s === 'DETECTED' || s === 'INVESTIGATING') {
      invState = 'ACTIVE';
    }
  }
  setStage('investigation', invState, trace.hypothesis_available ? 'Hypothesis Generated' : (invState === 'ACTIVE' ? 'LLM Analyzing' : undefined));

  // Verification
  let verState: NodeState = 'NOT_REACHED';
  if (invState === 'COMPLETE') {
    if (s === 'ESCALATED_MISSING_EVIDENCE' || s === 'ESCALATED_AMBIGUOUS_EVIDENCE') {
      verState = 'BLOCKED';
    } else if (trace.evidence_count > 0) {
      verState = 'COMPLETE';
    } else {
      verState = 'ACTIVE';
    }
  }
  setStage('verification', verState, verState === 'BLOCKED' ? 'Missing Evidence' : (verState === 'COMPLETE' ? `${trace.evidence_count} evidence records` : undefined));

  // Policy
  let polState: NodeState = 'NOT_REACHED';
  if (verState === 'COMPLETE') {
    if (trace.recovery_intent) {
      polState = 'COMPLETE';
    } else if (s === 'ESCALATED_UNSAFE_ACTUATION') {
      polState = 'BLOCKED';
    } else {
      polState = 'ACTIVE';
    }
  }
  setStage('policy', polState, trace.recovery_intent?.action || (polState === 'BLOCKED' ? 'Unsafe Action' : undefined));

  // Governance
  let govState: NodeState = 'NOT_REACHED';
  if (polState === 'COMPLETE') {
    if (s === 'ESCALATED_GOVERNANCE_REJECTED') {
      govState = 'BLOCKED';
    } else if (has('ACTUATION_PENDING') || has('ACTUATING') || has('REOBSERVING') || trace.actuation) {
      govState = 'COMPLETE';
    } else {
      govState = 'ACTIVE';
    }
  }
  setStage('governance', govState, govState === 'BLOCKED' ? 'Rejected by Gate' : (govState === 'COMPLETE' ? 'Passed Gate' : undefined));

  // Actuation
  let actState: NodeState = 'NOT_REACHED';
  let actEvidence: string | undefined = undefined;
  if (govState === 'COMPLETE') {
    if (trace.actuation) {
      if (trace.actuation.state === 'COMPLETED' || trace.actuation.state === 'SUCCESS') {
        actState = 'COMPLETE';
        actEvidence = 'Action Executed';
      } else if (trace.actuation.state === 'FAILED' || s === 'ESCALATED_MUTATION_FAILED') {
        actState = 'BLOCKED';
        actEvidence = 'Mutation Failed';
      } else {
        actState = 'ACTIVE';
        actEvidence = 'Executing Action';
      }
    } else {
      actState = 'ACTIVE';
    }
  }
  setStage('actuation', actState, actEvidence);

  // Re-observation
  let reoState: NodeState = 'NOT_REACHED';
  if (actState === 'COMPLETE') {
     if (has('RE_OBSERVATION')) {
       reoState = 'COMPLETE';
     } else {
       reoState = 'ACTIVE';
     }
  }
  setStage('reobservation', reoState);

  // Resolution / Escalation
  let resState: NodeState = 'NOT_REACHED';
  let resEvidence = '';
  if (s === 'RESOLVED') {
     resState = 'COMPLETE';
     resEvidence = 'Resolved via Autonomous Control';
  } else if (s.startsWith('ESCALATED')) {
     resState = 'ACTIVE';
     resEvidence = `Escalated: ${s.replace('ESCALATED_', '')}`;
  }
  setStage('resolution', resState, resEvidence);

  return stages;
}

const PipelineSummary: React.FC<{ trace: AuditTrace }> = ({ trace }) => {
  const discrepancy = trace.discrepancy?.discrepancy_reason || 'Anomaly Detected';
  const escalated = trace.current_state.startsWith('ESCALATED');
  
  let fceAction = 'Investigated → Verified Evidence';
  if (trace.recovery_intent) {
    fceAction += ' → Evaluated Policy';
  }

  let stopReason = 'Resolved';
  if (escalated) {
    stopReason = `${trace.current_state.replace('ESCALATED_', '')} → Human Review Required`;
  }

  return (
    <div className="flex flex-col gap-4 mt-6 p-4 bg-slate-900 border border-slate-700 rounded-sm">
      <div>
        <div className="font-mono text-[10px] text-fce-textMuted uppercase tracking-wider mb-1">1. What happened?</div>
        <div className="font-mono text-xs text-fce-text">Event Ingested → <span className="text-fce-warning">{discrepancy}</span></div>
      </div>
      <div>
        <div className="font-mono text-[10px] text-fce-textMuted uppercase tracking-wider mb-1">2. What did FCE do about it?</div>
        <div className="font-mono text-xs text-fce-text">{fceAction}</div>
      </div>
      <div>
        <div className="font-mono text-[10px] text-fce-textMuted uppercase tracking-wider mb-1">3. Why did it stop?</div>
        <div className={`font-mono text-xs font-semibold ${escalated ? 'text-fce-danger' : 'text-fce-success'}`}>
          {stopReason}
        </div>
      </div>
    </div>
  );
};

export const ControlPipeline: React.FC<ControlPipelineProps> = ({ trace }) => {
  const nodes = calculatePipelineNodes(trace);

  if (!trace) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 border border-slate-700 bg-slate-900/50 rounded-sm">
        <div className="text-fce-textMuted font-mono uppercase tracking-widest text-xs">Waiting for Event Injection</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-900/50 border border-slate-700 p-6 rounded-sm overflow-y-auto">
      <div className="mb-8">
         <h2 className="text-lg font-mono text-fce-text font-semibold uppercase tracking-widest border-b border-slate-700 pb-3">
           Control Execution Trace
         </h2>
         <PipelineSummary trace={trace} />
      </div>

      <div className="flex flex-col gap-0 relative ml-2">
        {/* Vertical line connecting nodes */}
        <div className="absolute left-[11px] top-4 bottom-4 w-px bg-slate-700 z-0"></div>
        
        {nodes.map(node => {
          let nodeColor = 'bg-slate-800 border-slate-700 text-slate-600';
          let textColor = 'text-slate-500';
          let stateText = 'NOT REACHED';

          if (node.state === 'COMPLETE') {
            nodeColor = 'bg-fce-success border-fce-success text-slate-900';
            textColor = 'text-fce-text';
            stateText = 'COMPLETE';
          } else if (node.state === 'ACTIVE') {
            nodeColor = 'bg-fce-warning border-fce-warning text-slate-900 shadow-[0_0_8px_rgba(245,158,11,0.4)]';
            textColor = 'text-fce-warning';
            stateText = 'ACTIVE';
          } else if (node.state === 'BLOCKED') {
            nodeColor = 'bg-slate-800 border-fce-danger text-fce-danger';
            textColor = 'text-fce-danger';
            stateText = 'BLOCKED';
          }

          if (node.id === 'resolution' && node.state === 'ACTIVE') {
            nodeColor = 'bg-fce-danger border-fce-danger text-slate-900 shadow-[0_0_8px_rgba(239,68,68,0.4)]';
            textColor = 'text-fce-danger';
            stateText = 'ESCALATED';
          }

          return (
            <div key={node.id} className="flex items-start group relative z-10 py-3">
              <div className={`w-6 h-6 rounded-sm border flex items-center justify-center mt-0.5 shrink-0 transition-all duration-300 ${nodeColor}`}>
                {node.state === 'COMPLETE' && <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" /></svg>}
                {node.state === 'BLOCKED' && <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" /></svg>}
                {node.id === 'resolution' && node.state === 'ACTIVE' && <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}
              </div>
              <div className="ml-5 flex flex-col w-full">
                <div className="flex items-baseline justify-between">
                  <span className={`font-mono text-[13px] uppercase tracking-wider font-semibold ${textColor}`}>
                    {node.label}
                  </span>
                  <span className={`font-mono text-[10px] tracking-wider ${textColor}`}>
                    {stateText}
                  </span>
                </div>
                {node.evidence && (
                  <div className={`font-mono text-xs mt-1 ${node.state === 'NOT_REACHED' ? 'text-slate-600' : 'text-fce-textMuted'}`}>
                    {node.evidence}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
