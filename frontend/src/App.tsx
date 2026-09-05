import { useState, useEffect } from 'react';
import { api, type AuditTrace } from './services/api';
import { TopControlPipeline } from './components/TopControlPipeline';
import { ActiveExceptionPanel } from './components/ActiveExceptionPanel';
import { LiveExecutionCenter } from './components/LiveExecutionCenter';
import { ControlProofPanel } from './components/ControlProofPanel';
import { BatchSummaryModal } from './components/BatchSummaryModal';
import { OperatorActions } from './components/OperatorActions';
import { DEMO_SCENARIOS } from './scenarios/demoScenarios';
import type { PipelineStageId, ScenarioPresetId, StageStatus, ProofItem, BatchRecord } from './types';

const STAGE_ORDER: PipelineStageId[] = [
  'DETECT',
  'INVESTIGATE',
  'VERIFY',
  'DECIDE',
  'ACT',
  'REOBSERVE',
  'TERMINAL'
];

function App() {
  // Scenario state
  const [currentScenarioId, setCurrentScenarioId] = useState<ScenarioPresetId>('SCENARIO_A');
  const [currentScenario, setCurrentScenario] = useState(DEMO_SCENARIOS.SCENARIO_A);

  // Playback state: 0 to 6
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(0);
  const [selectedStageId, setSelectedStageId] = useState<PipelineStageId>('DETECT');
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1); // 1 = 1x, 2 = 2x, 0 = instant

  // Batch modal state
  const [isBatchModalOpen, setIsBatchModalOpen] = useState<boolean>(false);

  // Live backend state
  const [isInjecting, setIsInjecting] = useState<boolean>(false);
  const [liveTrace] = useState<AuditTrace | null>(null);

  // Sync scenario changes
  const handleSelectScenario = (id: ScenarioPresetId) => {
    setCurrentScenarioId(id);
    setCurrentScenario(DEMO_SCENARIOS[id]);
    setCurrentStageIndex(0);
    setSelectedStageId('DETECT');
    setIsPlaying(false);
  };

  // Playback timer
  useEffect(() => {
    if (!isPlaying || currentStageIndex >= STAGE_ORDER.length - 1) return;

    const delay = playbackSpeed === 0 ? 350 : playbackSpeed === 2 ? 1400 : 2500;
    const timer = setTimeout(() => {
      setCurrentStageIndex(prev => {
        const next = prev + 1;
        setSelectedStageId(STAGE_ORDER[next]);
        if (next >= STAGE_ORDER.length - 1) {
          setIsPlaying(false);
        }
        return next;
      });
    }, delay);

    return () => clearTimeout(timer);
  }, [isPlaying, currentStageIndex, playbackSpeed]);

  // Step forward
  const handleStepForward = () => {
    setIsPlaying(false);
    if (currentStageIndex < STAGE_ORDER.length - 1) {
      const nextIndex = currentStageIndex + 1;
      setCurrentStageIndex(nextIndex);
      setSelectedStageId(STAGE_ORDER[nextIndex]);
    }
  };

  // Reset
  const handleReset = () => {
    setIsPlaying(false);
    setCurrentStageIndex(0);
    setSelectedStageId('DETECT');
  };

  // Calculate stage statuses based on currentStageIndex and scenario failure modes
  const stageStatuses: Record<PipelineStageId, StageStatus> = {
    DETECT: 'PENDING',
    INVESTIGATE: 'PENDING',
    VERIFY: 'PENDING',
    DECIDE: 'PENDING',
    ACT: 'PENDING',
    REOBSERVE: 'PENDING',
    TERMINAL: 'PENDING'
  };

  STAGE_ORDER.forEach((stageId, idx) => {
    if (idx < currentStageIndex) {
      // Completed or blocked in past stages
      if (currentScenarioId === 'SCENARIO_B') {
        if (stageId === 'VERIFY' || stageId === 'DECIDE') {
          stageStatuses[stageId] = 'BLOCKED';
        } else if (stageId === 'ACT' || stageId === 'REOBSERVE') {
          stageStatuses[stageId] = 'SKIPPED';
        } else {
          stageStatuses[stageId] = 'COMPLETED';
        }
      } else if (currentScenarioId === 'SCENARIO_C') {
        if (stageId === 'VERIFY' || stageId === 'DECIDE') {
          stageStatuses[stageId] = 'BLOCKED';
        } else if (stageId === 'ACT' || stageId === 'REOBSERVE') {
          stageStatuses[stageId] = 'SKIPPED';
        } else {
          stageStatuses[stageId] = 'COMPLETED';
        }
      } else {
        stageStatuses[stageId] = 'COMPLETED';
      }
    } else if (idx === currentStageIndex) {
      // Active stage
      if (idx === STAGE_ORDER.length - 1) {
        // Terminal stage
        stageStatuses[stageId] = currentScenario.terminalState === 'RESOLVED' ? 'COMPLETED' : 'BLOCKED';
      } else {
        stageStatuses[stageId] = 'ACTIVE';
      }
    } else {
      // Future stage
      if (
        (currentScenarioId === 'SCENARIO_B' || currentScenarioId === 'SCENARIO_C') &&
        (stageId === 'ACT' || stageId === 'REOBSERVE') &&
        currentStageIndex >= 2
      ) {
        stageStatuses[stageId] = 'SKIPPED';
      } else {
        stageStatuses[stageId] = 'PENDING';
      }
    }
  });

  // Accumulate proofs up to the current stage
  const accumulatedProofs: ProofItem[] = [];
  STAGE_ORDER.slice(0, currentStageIndex + 1).forEach(stageId => {
    const proofs = currentScenario.proofsByStage[stageId] || [];
    accumulatedProofs.push(...proofs);
  });

  // Custom webhook injection
  const handleInjectCustomWebhook = async (payload: { paymentId: string; orderId: string; amount: number }) => {
    setIsInjecting(true);
    try {
      await api.triggerWebhook({
        event: 'payment.captured',
        payload: {
          payment: {
            entity: {
              id: payload.paymentId,
              order_id: payload.orderId,
              amount: payload.amount,
              currency: 'INR',
              status: 'captured'
            }
          }
        },
        created_at: Math.floor(Date.now() / 1000)
      });
      // Start loop
      setCurrentStageIndex(0);
      setSelectedStageId('DETECT');
      setIsPlaying(true);
    } catch (err) {
      console.warn('Backend webhook failed, running simulated loop', err);
      setCurrentStageIndex(0);
      setSelectedStageId('DETECT');
      setIsPlaying(true);
    } finally {
      setIsInjecting(false);
    }
  };

  // Inspect record from batch modal
  const handleSelectRecordForTrace = (record: BatchRecord) => {
    setIsBatchModalOpen(false);
    if (record.scenarioType === 'REFUND') {
      const scen = { ...DEMO_SCENARIOS.SCENARIO_A, paymentId: record.paymentId, orderId: record.orderId, amount: record.amount };
      setCurrentScenario(scen);
      setCurrentScenarioId('SCENARIO_A');
    } else if (record.scenarioType === 'MISSING') {
      const scen = { ...DEMO_SCENARIOS.SCENARIO_B, paymentId: record.paymentId, orderId: record.orderId, amount: record.amount };
      setCurrentScenario(scen);
      setCurrentScenarioId('SCENARIO_B');
    } else {
      const scen = { ...DEMO_SCENARIOS.SCENARIO_C, paymentId: record.paymentId, orderId: record.orderId, amount: record.amount };
      setCurrentScenario(scen);
      setCurrentScenarioId('SCENARIO_C');
    }
    setCurrentStageIndex(0);
    setSelectedStageId('DETECT');
    setIsPlaying(false);
  };

  return (
    <div className="min-h-screen max-h-screen flex flex-col bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* 1. Global Navigation Header */}
      <header className="bg-slate-950 border-b border-slate-800 px-5 py-3 flex items-center justify-between shrink-0 select-none z-20">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-sm bg-gradient-to-br from-sky-500 to-indigo-600 flex items-center justify-center font-mono font-bold text-white text-sm shadow-md">
            FC
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-mono text-sm md:text-base font-bold tracking-tight text-white">
                FINANCIAL CONTROL ENGINE
              </h1>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-xs bg-slate-900 border border-slate-800 text-sky-400 font-semibold tracking-wide">
                TRACK 04: AI FINANCE CONTROLLER
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono hidden md:block">
              Closed-Loop Financial Exception Control • Detect → Investigate → Verify → Decide → Act → Re-observe
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 font-mono">
          {/* Track 04 Batch Modal Button */}
          <button
            type="button"
            onClick={() => setIsBatchModalOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-sm bg-slate-900 hover:bg-slate-850 border border-sky-500/40 text-sky-300 hover:text-white transition-all text-xs font-semibold shadow-sm group"
          >
            <span className="inline-block w-2 h-2 rounded-full bg-sky-400 group-hover:animate-ping"></span>
            <span>60-Record Batch Run: 85.0% Resolution</span>
            <span className="text-slate-500 group-hover:text-slate-300">→</span>
          </button>

          {/* Telemetry Provenance Badge */}
          <div className="hidden xl:flex items-center gap-1.5 px-2 py-1 rounded-xs bg-slate-900 border border-slate-800 text-[9px] text-slate-400">
            <span className="text-slate-500 font-bold">SOURCE:</span>
            {currentScenarioId === 'LIVE_WEBHOOK' ? (
              <span className="text-sky-400 font-semibold">LIVE GATEWAY STREAM</span>
            ) : (
              <span className="text-emerald-400 font-semibold">DETERMINISTIC TEST MATRIX</span>
            )}
          </div>

          {/* Automation active badge */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-sm bg-emerald-950/40 border border-emerald-800 text-emerald-400 text-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span className="font-semibold uppercase tracking-wider text-[10px]">AUTOMATION ACTIVE</span>
          </div>
        </div>
      </header>

      {/* 2. Top Narrative Spine (6 Control Stages + Terminal Outcome) */}
      <TopControlPipeline
        currentStageId={STAGE_ORDER[currentStageIndex]}
        selectedStageId={selectedStageId}
        stageStatuses={stageStatuses}
        onSelectStage={setSelectedStageId}
        terminalStateName={currentScenario.terminalState}
      />

      {/* 3. Main Workspace: Three Simultaneous Layers of Visibility */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 overflow-hidden">
        {/* Left Column (3 cols): Active Exception, Controls & Scenario Switcher */}
        <div className="lg:col-span-3 h-full overflow-hidden">
          <ActiveExceptionPanel
            currentScenario={currentScenario}
            onSelectScenario={handleSelectScenario}
            isPlaying={isPlaying}
            onTogglePlay={() => setIsPlaying(!isPlaying)}
            onStepForward={handleStepForward}
            onReset={handleReset}
            playbackSpeed={playbackSpeed}
            onChangeSpeed={setPlaybackSpeed}
            onInjectCustomWebhook={handleInjectCustomWebhook}
            isInjecting={isInjecting}
          />
        </div>

        {/* Center Column (5 cols): Layer 2 - Mechanism (Live Execution Center) */}
        <div className="lg:col-span-5 h-full overflow-hidden flex flex-col border-r border-slate-800/80">
          <div className="flex-1 overflow-hidden">
            <LiveExecutionCenter
              currentStageId={STAGE_ORDER[currentStageIndex]}
              selectedStageId={selectedStageId}
              stagePayloads={currentScenario.stages}
              stageStatuses={stageStatuses}
              onAdvanceStage={handleStepForward}
              isTerminal={currentStageIndex >= STAGE_ORDER.length - 1}
            />
          </div>

          {/* Operator Interventions drawer at bottom of center */}
          <div className="shrink-0 p-3 bg-slate-950 border-t border-slate-800/80">
            <OperatorActions
              trace={liveTrace}
              incidentId={currentScenario.paymentId}
              currentState={currentScenario.terminalState}
              onActionComplete={() => {}}
            />
          </div>
        </div>

        {/* Right Column (4 cols): Layer 3 - Proof (Control Proof Panel) */}
        <div className="lg:col-span-4 h-full overflow-hidden">
          <ControlProofPanel
            proofs={accumulatedProofs}
            currentScenarioName={currentScenario.name}
            isTerminal={currentStageIndex >= STAGE_ORDER.length - 1}
            terminalState={currentScenario.terminalState}
          />
        </div>
      </main>

      {/* 4. Track 04 60-Record Batch Modal */}
      <BatchSummaryModal
        isOpen={isBatchModalOpen}
        onClose={() => setIsBatchModalOpen(false)}
        onSelectRecordForTrace={handleSelectRecordForTrace}
      />
    </div>
  );
}

export default App;
