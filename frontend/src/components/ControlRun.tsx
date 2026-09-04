import React from 'react';
import { type IncidentSummary, type PaginatedIncidents } from '../services/api';

interface ControlRunProps {
  summary: IncidentSummary | null;
  incidents: PaginatedIncidents | null;
  onSelectIncident: (id: string) => void;
  selectedIncidentId: string | null;
}

export const ControlRun: React.FC<ControlRunProps> = ({ 
  summary, 
  incidents, 
  onSelectIncident,
  selectedIncidentId 
}) => {
  // Hardcoded for the batch demo as per requirement to show 100 records
  const totalProcessed = 100;
  const matchCount = 8; // The remaining 92 are the exceptions in our backend

  const exceptionsCount = summary ? summary.total : 0;
  const resolvedCount = summary ? summary.resolved : 0;
  const escalatedCount = summary ? summary.escalated : 0;

  return (
    <div className="flex flex-col gap-6 h-full">
      <section className="control-panel flex flex-col gap-4">
        <div className="flex justify-between items-center">
          <h2 className="font-mono text-sm font-semibold uppercase text-fce-textMuted tracking-wider">
            Control Run #001
          </h2>
          <span className="font-mono text-xs text-fce-textMuted">
            {totalProcessed} RECORDS
          </span>
        </div>
        
        <div className="grid grid-cols-4 gap-4">
          <div>
            <div className="data-label">Matched</div>
            <div className="data-value text-fce-success">{matchCount}</div>
          </div>
          <div>
            <div className="data-label">Exceptions</div>
            <div className="data-value text-fce-danger">{exceptionsCount}</div>
          </div>
          <div>
            <div className="data-label">Resolved</div>
            <div className="data-value text-fce-accent">{resolvedCount}</div>
          </div>
          <div>
            <div className="data-label">Escalated</div>
            <div className="data-value text-fce-warning">{escalatedCount}</div>
          </div>
        </div>
      </section>

      <section className="control-panel flex-1 flex flex-col overflow-hidden">
        <div className="flex justify-between items-center mb-4">
          <h2 className="font-mono text-sm font-semibold uppercase text-fce-textMuted tracking-wider">
            Exceptions ({exceptionsCount})
          </h2>
        </div>
        
        <div className="flex-1 border border-slate-700 bg-slate-900 overflow-y-auto">
          {incidents?.items.map((incident) => {
            const isSelected = selectedIncidentId === incident.incident_id;
            
            // Determine border color based on terminal status
            let statusColor = "border-transparent";
            let statusText = "text-fce-textMuted";
            let statusLabel = incident.state;

            if (incident.is_escalated) {
              statusColor = "border-fce-danger";
              statusText = "text-fce-danger";
            } else if (incident.is_terminal && incident.state === "RESOLVED") {
              statusColor = "border-fce-accent";
              statusText = "text-fce-accent";
            } else {
              statusColor = "border-fce-warning"; // active processing
              statusText = "text-fce-warning";
            }

            return (
              <div 
                key={incident.incident_id}
                onClick={() => onSelectIncident(incident.incident_id)}
                className={`
                  text-xs font-mono flex items-center p-3 cursor-pointer border-l-2 border-b border-b-slate-800
                  ${isSelected ? 'bg-fce-surfaceHover' : 'hover:bg-fce-surface'}
                  ${statusColor}
                `}
              >
                <div className="flex flex-col gap-1 w-full">
                  <div className="flex justify-between w-full">
                    <span className="text-fce-text font-semibold">{incident.incident_id}</span>
                    <span className={`${statusText}`}>{statusLabel}</span>
                  </div>
                  <div className="flex justify-between w-full text-fce-textMuted">
                    <span className="truncate max-w-[200px]">{incident.discrepancy_reason}</span>
                    <span>{new Date(incident.created_at).toLocaleTimeString()}</span>
                  </div>
                </div>
              </div>
            );
          })}
          
          {incidents?.items.length === 0 && (
            <div className="p-4 text-center font-mono text-sm text-fce-textMuted">
              No exceptions currently active.
            </div>
          )}
        </div>
      </section>
    </div>
  );
};
