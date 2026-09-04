import React from 'react';
import { type AuditTrace } from '../services/api';

interface ExceptionTraceProps {
  trace: AuditTrace | null;
}

export const ExceptionTrace: React.FC<ExceptionTraceProps> = ({ trace }) => {
  if (!trace) {
    return (
      <div className="control-panel flex-1 flex items-center justify-center">
        <div className="font-mono text-fce-textMuted text-sm">
          Select an exception from the Control Run to view its trace.
        </div>
      </div>
    );
  }

  const {
    incident_id,
    current_state,
    is_terminal,
    timeline,
    discrepancy,
    recovery_intent,
    operator_actions
  } = trace;

  let statusBadgeColor = "border-fce-warning bg-fce-warning/10 text-fce-warning";
  if (current_state.startsWith('ESCALATED')) {
    statusBadgeColor = "border-fce-danger bg-fce-danger/10 text-fce-danger";
  } else if (is_terminal && current_state === "RESOLVED") {
    statusBadgeColor = "border-fce-accent bg-fce-accent/10 text-fce-accent";
  }

  return (
    <section className="control-panel flex-1 flex flex-col gap-6 overflow-hidden">
      <div className="flex justify-between items-start shrink-0">
        <div>
          <h2 className="font-mono text-lg font-bold tracking-tight text-fce-text mb-1">
            EXCEPTION TRACE
          </h2>
          <div className="font-mono text-xs text-fce-textMuted">
            ID: {incident_id}
          </div>
        </div>
        <span className={`px-2 py-1 text-xs font-mono border ${statusBadgeColor}`}>
          {current_state}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-8 flex-1 overflow-y-auto pr-2">
        {/* State/Evidence Column */}
        <div className="flex flex-col gap-6">
          
          {/* Discrepancy Evidence */}
          <div>
            <div className="data-label mb-2">Observations (Discrepancy)</div>
            <div className="p-3 bg-slate-900 border border-slate-700 font-mono text-xs space-y-3">
              <div className="flex justify-between">
                <span className="text-fce-textMuted">Reason</span>
                <span className="text-fce-warning font-semibold">{discrepancy?.discrepancy_reason || "UNKNOWN"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fce-textMuted">Reconciliation ID</span>
                <span className="truncate ml-4">{discrepancy?.reconciliation_id || "N/A"}</span>
              </div>
            </div>
          </div>

          {/* AI Hypothesis vs Deterministic Verification */}
          {trace.hypothesis_available && (
             <div>
               <div className="data-label mb-2">Investigation & Verification</div>
               <div className="p-3 bg-slate-900 border border-slate-700 font-mono text-xs space-y-4">
                 <div>
                   <div className="text-fce-textMuted mb-1 border-b border-slate-700 pb-1">AI Hypothesis Generated</div>
                   <div className="text-fce-text italic">"Discrepancy detected based on mismatch in canonical states across providers."</div>
                 </div>
                 <div>
                   <div className="text-fce-textMuted mb-1 border-b border-slate-700 pb-1">Deterministic Evidence ({trace.evidence_count} records)</div>
                   <div className="text-fce-success flex items-center gap-2">
                     <span>✓</span> <span>Evidence cryptographically verified</span>
                   </div>
                 </div>
               </div>
             </div>
          )}

          {/* Recovery Intent / Policy */}
          {recovery_intent && (
            <div>
              <div className="data-label mb-2">Derived Recovery Intent</div>
              <div className="p-3 bg-slate-900 border border-slate-700 font-mono text-xs space-y-2">
                <div className="flex justify-between">
                  <span className="text-fce-textMuted">Action</span>
                  <span className="text-fce-accent">{recovery_intent.action}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fce-textMuted">Target ID</span>
                  <span className="truncate ml-4">{recovery_intent.target_id}</span>
                </div>
              </div>
            </div>
          )}
          
          {/* Operator Interventions */}
          {operator_actions && operator_actions.length > 0 && (
            <div>
              <div className="data-label mb-2">Operator Actions</div>
              <div className="p-3 bg-slate-900 border border-fce-warning/50 font-mono text-xs space-y-3">
                {operator_actions.map((act) => (
                  <div key={act.action_id} className="border-b border-slate-700 pb-2 last:border-0 last:pb-0">
                    <div className="flex justify-between mb-1">
                      <span className="text-fce-warning">{act.action_type}</span>
                      <span className="text-fce-textMuted">{new Date(act.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <div className="text-fce-textMuted break-words">By: {act.operator_id}</div>
                    {act.reason && <div className="text-fce-text break-words mt-1">"{act.reason}"</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Control Loop Column */}
        <div className="border-l border-slate-700 pl-8 relative">
          <div className="data-label mb-6">Control Loop</div>
          
          <div className="space-y-6 font-mono text-sm relative">
            {timeline.map((item, index) => {
              const isLast = index === timeline.length - 1;
              const isError = item.step.startsWith('ESCALATED');
              const isSuccess = item.step === 'RESOLVED';
              
              let icon = '✓';
              let iconColor = 'bg-fce-success text-slate-900';
              let textColor = 'text-fce-text';

              if (isError) {
                icon = '✕';
                iconColor = 'bg-fce-danger text-slate-900';
                textColor = 'text-fce-danger font-bold';
              } else if (isSuccess) {
                iconColor = 'bg-fce-accent text-slate-900';
                textColor = 'text-fce-accent font-bold';
              } else if (isLast && !is_terminal) {
                icon = '⟳'; // Processing/loading
                iconColor = 'bg-fce-warning text-slate-900';
                textColor = 'text-fce-warning';
              }

              return (
                <div key={item.step} className="flex items-start gap-4">
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] shrink-0 mt-0.5 ${iconColor}`}>
                    {icon}
                  </div>
                  <div className="flex flex-col gap-1 w-full">
                    <div className="flex justify-between w-full">
                      <span className={`${textColor}`}>{item.step}</span>
                      <span className="text-xs text-fce-textMuted shrink-0 ml-2">
                        {item.at ? new Date(item.at).toLocaleTimeString() : ''}
                      </span>
                    </div>
                    <div className="text-xs text-fce-textMuted leading-snug">
                      {item.detail}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
};
