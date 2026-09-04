import React, { useState } from 'react';
import { api, AuditTrace } from '../services/api';

interface OperatorActionsProps {
  trace: AuditTrace | null;
  onActionComplete: () => void;
}

export const OperatorActions: React.FC<OperatorActionsProps> = ({ trace, onActionComplete }) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!trace) return null;

  const isEscalated = trace.current_state.startsWith('ESCALATED');

  const handleAction = async (action: 'retry' | 'resolve' | 'escalate') => {
    setIsSubmitting(true);
    setError(null);
    try {
      await api.operatorAction(trace.incident_id, action, `Operator ${action} action from Control Room`);
      onActionComplete();
    } catch (err: any) {
      setError(err.message || `Failed to ${action}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mt-6 bg-slate-900 border border-slate-700 p-4 rounded-sm">
      <h3 className="font-mono text-[11px] text-fce-textMuted uppercase tracking-widest border-b border-slate-700 pb-2 mb-4">
        Operator Interventions
      </h3>
      
      {error && (
        <div className="mb-4 font-mono text-[11px] text-fce-danger bg-red-950/30 p-2 border border-red-900/50 rounded-sm">
          {error}
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-3">
        <button
          onClick={() => handleAction('escalate')}
          disabled={isSubmitting || trace.current_state === 'RESOLVED' || isEscalated}
          className="flex-1 font-mono text-xs py-2 bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          FORCE ESCALATE
        </button>
        <button
          onClick={() => handleAction('retry')}
          disabled={isSubmitting || !isEscalated}
          className="flex-1 font-mono text-xs py-2 bg-slate-800 text-fce-warning border border-slate-700 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          RETRY PIPELINE
        </button>
        <button
          onClick={() => handleAction('resolve')}
          disabled={isSubmitting || trace.current_state === 'RESOLVED'}
          className="flex-1 font-mono text-xs py-2 bg-slate-800 text-fce-success border border-slate-700 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          MANUAL RESOLVE
        </button>
      </div>

      {trace.operator_actions && trace.operator_actions.length > 0 && (
        <div className="mt-4">
          <div className="font-mono text-[10px] text-slate-500 uppercase tracking-widest mb-2">Past Interventions</div>
          <div className="flex flex-col gap-2">
            {trace.operator_actions.map((action, i) => (
              <div key={action.action_id || i} className="font-mono text-[10px] bg-slate-800/50 border border-slate-700/50 p-2 rounded-sm text-slate-400">
                <span className="text-fce-text">{action.action_type}</span> by {action.operator_id} — {action.reason}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
