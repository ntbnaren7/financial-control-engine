import { useState, useEffect, useMemo } from 'react';
import { ForensicConsole } from './components/ForensicConsole';
import { BatchSummaryModal } from './components/BatchSummaryModal';
import { ExecutionController } from './engine/executionController';
import type { BatchRecord } from './types';

function App() {
  const controller = useMemo(() => new ExecutionController('SCENARIO_A'), []);
  const [engineState, setEngineState] = useState(controller.getState());
  const [isBatchModalOpen, setIsBatchModalOpen] = useState<boolean>(false);

  useEffect(() => {
    const unsubscribe = controller.subscribe(setEngineState);
    return () => unsubscribe();
  }, [controller]);

  // Inspect record from batch modal
  const handleSelectRecordForTrace = (record: BatchRecord) => {
    setIsBatchModalOpen(false);
    if (record.scenarioType === 'MISSING') {
      controller.setScenario('SCENARIO_B');
    } else if (record.scenarioType === 'AMOUNT_MISMATCH') {
      controller.setScenario('SCENARIO_C');
    } else {
      controller.setScenario('SCENARIO_A');
    }
  };

  return (
    <>
      <ForensicConsole
        currentScenario={engineState.currentScenario}
        currentScenarioId={engineState.scenarioId}
        onSelectScenario={(id) => controller.setScenario(id)}
        currentStageIndex={engineState.currentStageIndex}
        selectedStageId={engineState.selectedStageId}
        onSelectStage={(stageId) => controller.selectStage(stageId)}
        isPlaying={engineState.isPlaying}
        onTogglePlay={() => controller.togglePlay()}
        onStepForward={() => controller.stepForward()}
        onReset={() => controller.reset()}
        playbackSpeed={engineState.playbackSpeed}
        onChangeSpeed={(speed) => controller.setPlaybackSpeed(speed)}
        proofs={engineState.accumulatedProofs}
        onOpenBatchModal={() => setIsBatchModalOpen(true)}
        onInjectCustomWebhook={(payload) => controller.beginLiveRun(payload)}
        isInjecting={engineState.isLiveRunning}
        executionMode={engineState.mode}
        onSelectMode={(mode) => controller.setMode(mode)}
        caseIdentity={engineState.caseIdentity}
        readiness={engineState.readiness}
        isLiveRunning={engineState.isLiveRunning}
        onBeginLiveRun={() => controller.beginLiveRun()}
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

