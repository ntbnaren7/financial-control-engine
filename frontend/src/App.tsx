import { useState, useEffect, useMemo } from 'react';
import { LandingPage } from './LandingPage';
import { ExecutionController } from './engine/executionController';

function App() {
  const controller = useMemo(() => new ExecutionController('SCENARIO_A'), []);
  const [engineState, setEngineState] = useState(controller.getState());

  useEffect(() => {
    const unsubscribe = controller.subscribe(setEngineState);
    return () => unsubscribe();
  }, [controller]);

  return (
    <>
      <LandingPage
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
        caseIdentity={engineState.caseIdentity}
      />
    </>
  );
}

export default App;

