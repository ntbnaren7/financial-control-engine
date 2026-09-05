import { useState, useEffect } from 'react';
import { api } from './services/api';
import { ForensicConsole } from './components/ForensicConsole';
import { BatchSummaryModal } from './components/BatchSummaryModal';
import { DEMO_SCENARIOS } from './scenarios/demoScenarios';
import type { PipelineStageId, ScenarioPresetId, ProofItem, BatchRecord } from './types';

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

  // Accumulate machine proofs up to the current stage
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
    <>
      <ForensicConsole
        currentScenario={currentScenario}
        currentScenarioId={currentScenarioId}
        onSelectScenario={handleSelectScenario}
        currentStageIndex={currentStageIndex}
        selectedStageId={selectedStageId}
        onSelectStage={setSelectedStageId}
        isPlaying={isPlaying}
        onTogglePlay={() => setIsPlaying(!isPlaying)}
        onStepForward={handleStepForward}
        onReset={handleReset}
        playbackSpeed={playbackSpeed}
        onChangeSpeed={setPlaybackSpeed}
        proofs={accumulatedProofs}
        onOpenBatchModal={() => setIsBatchModalOpen(true)}
        onInjectCustomWebhook={handleInjectCustomWebhook}
        isInjecting={isInjecting}
      />

      <BatchSummaryModal
        isOpen={isBatchModalOpen}
        onClose={() => setIsBatchModalOpen(false)}
        onSelectRecordForTrace={handleSelectRecordForTrace}
      />
    </>
  );
}

export default App;
