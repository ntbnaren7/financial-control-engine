import { useState, useEffect } from 'react';
import { api, type AuditTrace } from './services/api';
import { usePolling } from './hooks/usePolling';
import { ExceptionTrace } from './components/ExceptionTrace';
import { ControlReplay } from './components/ControlReplay';
import { ControlPipeline } from './components/ControlPipeline';
import { OperatorActions } from './components/OperatorActions';

function App() {
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('incident') || null;
  });
  const [trace, setTrace] = useState<AuditTrace | null>(null);
  const [waitingSinceId, setWaitingSinceId] = useState<string | null>(null);
  const [isWaitingForNew, setIsWaitingForNew] = useState(false);

  // Update URL when selection changes
  useEffect(() => {
    const url = new URL(window.location.href);
    if (selectedIncidentId) {
      url.searchParams.set('incident', selectedIncidentId);
    } else {
      url.searchParams.delete('incident');
    }
    window.history.replaceState({}, '', url.toString());
  }, [selectedIncidentId]);

  // Poll for incidents list every 2 seconds
  const { data: incidents } = usePolling(() => api.getIncidents(), 2000);

  useEffect(() => {
    if (isWaitingForNew && incidents?.items && incidents.items.length > 0) {
       const latestId = incidents.items[0].incident_id;
       if (latestId !== waitingSinceId) {
          setSelectedIncidentId(latestId);
          setIsWaitingForNew(false);
          setWaitingSinceId(null);
       }
    }
  }, [incidents, isWaitingForNew, waitingSinceId]);

  // When a specific incident is selected, we want to fetch its trace.
  useEffect(() => {
    let active = true;
    let timeoutId: number;

    const fetchTrace = async () => {
      if (!selectedIncidentId) {
        setTrace(null);
        return;
      }
      try {
        const data = await api.getIncidentAudit(selectedIncidentId);
        if (active) {
          setTrace(data);
          // Only continue polling if it's not terminal
          if (!data.is_terminal) {
            timeoutId = window.setTimeout(fetchTrace, 2000);
          }
        }
      } catch (err) {
        console.error("Failed to fetch incident trace", err);
        // Continue polling on error to recover
        if (active) {
          timeoutId = window.setTimeout(fetchTrace, 5000);
        }
      }
    };
    
    fetchTrace();

    return () => {
      active = false;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [selectedIncidentId]);

  return (
    <div className="min-h-screen flex flex-col max-h-screen bg-slate-900">
      {/* Global Header */}
      <header className="border-b border-slate-700 bg-slate-900 px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="font-mono text-xl font-bold tracking-tight text-fce-text">
            FINANCIAL CONTROL ENGINE
          </h1>
          <span className="px-2 py-0.5 text-xs font-mono bg-fce-surface border border-slate-700 text-fce-textMuted rounded-sm">
            CONTROL ROOM
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-fce-success animate-pulse"></div>
          <span className="font-mono text-xs text-fce-success uppercase tracking-wider">
            Automation Active
          </span>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 overflow-hidden">
        {/* Left Column: Control Replay & History */}
        <div className="lg:col-span-3 h-full overflow-hidden flex flex-col gap-6">
          <ControlReplay onEventInjected={() => {
              const currentTop = incidents?.items?.[0]?.incident_id || null;
              setWaitingSinceId(currentTop);
              setIsWaitingForNew(true);
              setSelectedIncidentId(null);
              setTrace(null);
          }} />
          
          <div className="flex-1 overflow-y-auto bg-slate-900/50 border border-slate-700 p-4 rounded-sm">
             <h2 className="font-mono text-xs font-semibold text-fce-textMuted uppercase tracking-widest mb-4 border-b border-slate-700 pb-2">Recent Exceptions</h2>
             <div className="flex flex-col gap-2">
               {incidents?.items?.map(inc => (
                 <div 
                   key={inc.incident_id}
                   onClick={() => {
                     setIsWaitingForNew(false);
                     setSelectedIncidentId(inc.incident_id);
                   }}
                   className={`p-3 border cursor-pointer transition-colors duration-200 ${selectedIncidentId === inc.incident_id ? 'border-fce-accent bg-fce-accent/10' : 'border-slate-700 hover:border-slate-500'}`}
                 >
                   <div className="text-xs font-mono text-fce-text truncate mb-1">{inc.incident_id}</div>
                   <div className={`text-[10px] font-mono uppercase tracking-wider ${inc.state.startsWith('ESCALATED') ? 'text-fce-danger' : (inc.state === 'RESOLVED' ? 'text-fce-accent' : 'text-fce-warning')}`}>
                     {inc.state}
                   </div>
                 </div>
               ))}
             </div>
          </div>
        </div>

        {/* Center Column: Pipeline Details */}
        <div className="lg:col-span-5 h-full overflow-hidden flex flex-col gap-4">
          <div className="flex-1 overflow-y-auto">
            <ControlPipeline trace={trace} />
          </div>
          {trace && (
             <div className="shrink-0 max-h-[300px] overflow-y-auto">
               <OperatorActions trace={trace} onActionComplete={() => {}} />
             </div>
          )}
        </div>

        {/* Right Column: Exception Trace */}
        <div className="lg:col-span-4 h-full overflow-hidden flex flex-col">
          <ExceptionTrace trace={trace} />
        </div>
      </main>
    </div>
  );
}

export default App;
