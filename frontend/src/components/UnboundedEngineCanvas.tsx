import React, { useRef, useEffect, useState } from 'react';
import { Search, Cpu, ShieldAlert, Zap, CheckCircle2, RotateCcw, Flag } from 'lucide-react';
import { NodeCard } from './NodeCard';
import type { NodeCardProps } from './NodeCard';
import { ConnectionCables } from './ConnectionCables';
import type { Connection } from './ConnectionCables';
import { TelemetryDock } from './TelemetryDock';
import type { ScenarioDefinition, ScenarioPresetId, PipelineStageId } from '../types';

interface UnboundedEngineCanvasProps {
  currentScenario: ScenarioDefinition;
  currentScenarioId: ScenarioPresetId;
  onSelectScenario: (scenarioId: ScenarioPresetId) => void;
  currentStageIndex: number;
  selectedStageId: PipelineStageId | 'READY';
  onSelectStage: (stageId: PipelineStageId | 'READY') => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onStepForward: () => void;
  onReset: () => void;
}

export const UnboundedEngineCanvas: React.FC<UnboundedEngineCanvasProps> = ({
  currentScenario,
  currentScenarioId,
  onSelectScenario,
  currentStageIndex,
  isPlaying,
  onTogglePlay,
  onStepForward,
  onReset,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [metrics, setMetrics] = useState({
    tps: '14,204',
    discrepancy: '0.00%',
    audit: 'SHA-256'
  });

  // Jitter TPS slightly for live feel
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      const base = 14200;
      const jitter = Math.floor(Math.random() * 50) - 25;
      setMetrics(prev => ({
        ...prev,
        tps: (base + jitter).toLocaleString()
      }));
    }, 2000);
    return () => clearInterval(interval);
  }, [isPlaying]);

  // Derived state from scenario
  const detectStage = currentScenario.stages['DETECT']?.detectData;
  const expectedAmt = detectStage?.expected?.amount ?? 0;
  const observedAmt = detectStage?.observed?.amount ?? 0;
  const delta = Math.abs(expectedAmt - observedAmt);

  const getStatus = (stageIdx: number): NodeCardProps['status'] => {
    if (currentStageIndex > stageIdx) return 'VERIFIED';
    if (currentStageIndex === stageIdx) return 'EVALUATING';
    return 'PENDING';
  };

  const isStageActive = (stageIdx: number) => currentStageIndex === stageIdx || currentStageIndex > stageIdx;

  const nodes: NodeCardProps[] = [
    {
      id: 'DETECT',
      index: 1,
      title: 'INGEST & DETECT',
      status: getStatus(0),
      icon: Search,
      x: 0,
      y: 120,
      hasInput: false,
      isActive: currentStageIndex === 0,
      metrics: [
        { label: 'Expected (Ledger)', value: `₹${expectedAmt.toLocaleString()}` },
        { label: 'Observed (Gateway)', value: `₹${observedAmt.toLocaleString()}` },
        { label: 'Delta Discrepancy', value: delta > 0 ? `₹${delta.toLocaleString()}` : '0.00' }
      ]
    },
    {
      id: 'INVESTIGATE',
      index: 2,
      title: 'A3 REASONER',
      status: getStatus(1),
      icon: Cpu,
      x: 320,
      y: 20,
      isActive: currentStageIndex === 1,
      metrics: [
        { label: 'Agent State', value: isStageActive(1) ? 'ACTIVE' : 'IDLE' },
        { label: 'Telemetry', value: '12 logs parsed' }
      ]
    },
    {
      id: 'VERIFY',
      index: 3,
      title: 'A4 VERIFIER',
      status: getStatus(2),
      icon: ShieldAlert,
      x: 320,
      y: 220,
      isActive: currentStageIndex === 2,
      metrics: [
        { label: 'Policy Enforced', value: 'Strict' },
        { label: 'Confidence Score', value: isStageActive(2) ? '99.8%' : '--' }
      ]
    },
    {
      id: 'DECIDE',
      index: 4,
      title: 'POLICY & GOV',
      status: getStatus(3),
      icon: Zap,
      x: 640,
      y: 120,
      isActive: currentStageIndex === 3,
      metrics: [
        { label: 'Execution', value: isStageActive(3) ? 'RESOLVE_AUTO' : 'AWAITING' },
        { label: 'Escalation', value: 'false' }
      ]
    },
    {
      id: 'ACT',
      index: 5,
      title: 'OCC ACTUATOR',
      status: getStatus(4),
      icon: CheckCircle2,
      x: 960,
      y: 20,
      isActive: currentStageIndex === 4,
      metrics: [
        { label: 'API Target', value: 'stripe_v1_refund' },
        { label: 'Idempotency', value: isStageActive(4) ? 'SET' : 'PENDING' }
      ]
    },
    {
      id: 'REOBSERVE',
      index: 6,
      title: 'RE-OBSERVE',
      status: getStatus(5),
      icon: RotateCcw,
      x: 960,
      y: 220,
      isActive: currentStageIndex === 5,
      metrics: [
        { label: 'Fetch State', value: 'Polling...' },
        { label: 'Verification', value: isStageActive(5) ? 'PASS' : 'WAIT' }
      ]
    },
    {
      id: 'OUTCOME',
      index: 7,
      title: 'TERMINAL STATE',
      status: currentStageIndex >= 6 ? (currentScenario.terminalState === 'RESOLVED' ? 'VERIFIED' : 'ERROR') : 'PENDING',
      icon: Flag,
      x: 1280,
      y: 120,
      hasOutput: false,
      isActive: currentStageIndex >= 6,
      metrics: [
        { label: 'Final State', value: currentStageIndex >= 6 ? currentScenario.terminalState : 'PENDING' },
        { label: 'Receipt', value: currentStageIndex >= 6 ? '0x8f7a9...' : '---' }
      ]
    }
  ];

  const connections: Connection[] = [
    { sourceId: 'DETECT', targetId: 'INVESTIGATE', isActive: currentStageIndex >= 0 },
    { sourceId: 'DETECT', targetId: 'VERIFY', isActive: currentStageIndex >= 0 },
    { sourceId: 'INVESTIGATE', targetId: 'DECIDE', isActive: currentStageIndex >= 1 },
    { sourceId: 'VERIFY', targetId: 'DECIDE', isActive: currentStageIndex >= 2 },
    { sourceId: 'DECIDE', targetId: 'ACT', isActive: currentStageIndex >= 3 },
    { sourceId: 'DECIDE', targetId: 'REOBSERVE', isActive: currentStageIndex >= 3 },
    { sourceId: 'ACT', targetId: 'OUTCOME', isActive: currentStageIndex >= 4 },
    { sourceId: 'REOBSERVE', targetId: 'OUTCOME', isActive: currentStageIndex >= 5 },
  ];

  // Auto-scroll to keep active node in view on smaller screens
  useEffect(() => {
    if (containerRef.current) {
      const scrollPos = (currentStageIndex * (1536 / 7)) - (containerRef.current.clientWidth / 2) + 128;
      containerRef.current.scrollTo({
        left: Math.max(0, scrollPos),
        behavior: 'smooth'
      });
    }
  }, [currentStageIndex]);

  return (
    <div className="relative w-full h-[600px] mt-12 mb-0 rounded-2xl border border-white/10 bg-[#050505] overflow-hidden shadow-2xl">
      
      {/* Premium canvas dot grid with radial fade mask */}
      <div className="absolute inset-0 canvas-dot-grid pointer-events-none" />
      
      {/* Vercel-style ambient top glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[80%] h-[300px] bg-[radial-gradient(ellipse_60%_50%_at_50%_0%,rgba(59,130,246,0.1),transparent_70%)] pointer-events-none" />

      {/* Main Canvas Scroll Area */}
      <div 
        ref={containerRef}
        className="w-full h-full overflow-x-auto overflow-y-hidden custom-scrollbar relative"
      >
        {/* Inner container to hold absolute positioned nodes */}
        <div className="relative min-w-[1600px] h-full mx-auto flex items-center pt-8">
          
          <div className="relative w-[1536px] h-[360px] mx-12">
            <ConnectionCables nodes={nodes} connections={connections} />
            
            {nodes.map(node => (
              <NodeCard 
                key={node.id} 
                {...node} 
              />
            ))}
          </div>

        </div>
      </div>

      {/* Floating HUD */}
      <TelemetryDock
        currentScenarioId={currentScenarioId}
        onSelectScenario={onSelectScenario}
        isPlaying={isPlaying}
        hasStarted={currentStageIndex >= 0}
        onTogglePlay={onTogglePlay}
        onStepForward={onStepForward}
        onReset={onReset}
        metrics={metrics}
      />

    </div>
  );
};
