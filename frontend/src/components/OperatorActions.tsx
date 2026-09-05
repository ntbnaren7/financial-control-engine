import React, { useState } from 'react';
import { api, type AuditTrace } from '../services/api';

interface OperatorActionsProps {
  trace: AuditTrace | null;
  incidentId: string;
  currentState: string;
  onActionComplete: () => void;
}

export const OperatorActions: React.FC<OperatorActionsProps> = ({
  trace,
  incidentId,
  currentState,
  onActionComplete
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);

  const isEscalated = currentState.startsWith('ESCALATED');
  const isResolved = currentState === 'RESOLVED';

  const handleAction = async (action: 'retry' | 'resolve' | 'escalate') => {
    setIsSubmitting(true);
    setStatusMessage(null);
    setIsError(false);
    try {
      if (trace?.incident_id) {
        await api.operatorAction(incidentId, action, `Operator ${action} action from Control Room`);
      }
      setStatusMessage(`Operator ${action.toUpperCase()} action executed successfully.`);
      onActionComplete();
    } catch (err: unknown) {
      setIsError(true);
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMessage(msg || `Failed to execute ${action}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-sm font-mono text-xs select-none">
      <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2">
        <span className="font-bold text-slate-300 uppercase tracking-wider text-[10px] flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
          OPERATOR INTERVENTIONS (HUMAN-IN-THE-LOOP)
        </span>
        <span className="text-[9px] text-slate-500">Incident: {incidentId}</span>
      </div>

      {statusMessage && (
        <div className={`p-2 mb-2 rounded-xs border text-[11px] ${
          isError ? 'bg-rose-950/50 border-rose-800 text-rose-300' : 'bg-emerald-950/50 border-emerald-800 text-emerald-300'
        }`}>
          {statusMessage}
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        <button
          type="button"
          onClick={() => handleAction('escalate')}
          disabled={isSubmitting || isResolved || isEscalated}
          className="py-1.5 px-2 bg-slate-950 hover:bg-slate-850 text-slate-300 border border-slate-800 hover:border-slate-700 rounded-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-[11px] uppercase tracking-wider font-semibold"
        >
          FORCE ESCALATE
        </button>

        <button
          type="button"
          onClick={() => handleAction('retry')}
          disabled={isSubmitting || !isEscalated}
          className="py-1.5 px-2 bg-slate-950 hover:bg-slate-850 text-amber-300 border border-amber-900/60 hover:border-amber-700 rounded-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-[11px] uppercase tracking-wider font-semibold"
        >
          RETRY PIPELINE
        </button>

        <button
          type="button"
          onClick={() => handleAction('resolve')}
          disabled={isSubmitting || isResolved}
          className="py-1.5 px-2 bg-slate-950 hover:bg-slate-850 text-emerald-300 border border-emerald-900/60 hover:border-emerald-700 rounded-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-[11px] uppercase tracking-wider font-semibold"
        >
          MANUAL RESOLVE
        </button>
      </div>
    </div>
  );
};
