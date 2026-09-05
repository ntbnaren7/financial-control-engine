import type {
  CanonicalEngineState,
  ExecutionMode,
  NormalizedControlEvent,
  PipelineStageId,
  ScenarioPresetId,
  ScenarioDefinition,
  SystemReadiness
} from '../types';
import { DEMO_SCENARIOS } from '../scenarios/demoScenarios';

export const STAGE_ORDER: PipelineStageId[] = [
  'DETECT',
  'INVESTIGATE',
  'VERIFY',
  'DECIDE',
  'ACT',
  'REOBSERVE',
  'TERMINAL'
];

export function createInitialEngineState(
  scenarioId: ScenarioPresetId = 'SCENARIO_A',
  mode: ExecutionMode = 'SIMULATION',
  readiness: SystemReadiness = { backend: 'OFFLINE', ollama: 'NOT_DETECTED', provider: 'CONFIGURED' }
): CanonicalEngineState {
  const scenario = DEMO_SCENARIOS[scenarioId] || DEMO_SCENARIOS.SCENARIO_A;
  return {
    mode,
    scenarioId,
    currentStageIndex: -1, // -1 = READY / QUEUED FOR RECONCILIATION
    selectedStageId: 'READY',
    isPlaying: false,
    playbackSpeed: 1,
    status: 'QUEUED',
    discrepancyEstablished: false,
    caseIdentity: {
      paymentId: scenario.paymentId,
      orderId: scenario.orderId,
      amount: scenario.amount,
      currency: scenario.currency
    },
    discrepancy: {
      reason: null,
      expectedStatus: null,
      observedStatus: null,
      terminalOutcome: null
    },
    accumulatedProofs: [],
    timeline: [
      {
        step: 'QUEUED',
        at: '11:57:00 UTC',
        detail: 'Transaction event stream ingested · Queued for deterministic reconciliation'
      }
    ],
    currentScenario: scenario,
    readiness,
    isLiveRunning: false
  };
}

export type StateListener = (state: CanonicalEngineState) => void;

export class ExecutionController {
  private state: CanonicalEngineState;
  private listeners: Set<StateListener> = new Set();
  private playTimer: ReturnType<typeof setTimeout> | null = null;
  private livePollTimer: ReturnType<typeof setInterval> | null = null;

  constructor(initialScenario: ScenarioPresetId = 'SCENARIO_A') {
    this.state = createInitialEngineState(initialScenario);
    this.checkReadiness();
  }

  public getState(): CanonicalEngineState {
    return this.state;
  }

  public subscribe(listener: StateListener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  private emitStateChange() {
    this.listeners.forEach(l => l(this.state));
  }

  // ---------------------------------------------------------------------------
  // Normalized Event Ingestion (Canonical State Machine)
  // ---------------------------------------------------------------------------
  public applyEvent(event: NormalizedControlEvent) {
    const s = { ...this.state };
    const scenario = s.currentScenario;

    switch (event.type) {
      case 'RESET_TO_READY':
        this.clearTimers();
        this.state = {
          ...createInitialEngineState(s.scenarioId, s.mode, s.readiness),
          playbackSpeed: s.playbackSpeed
        };
        this.emitStateChange();
        return;

      case 'RECONCILIATION_ESTABLISHED':
        s.currentStageIndex = 0;
        s.selectedStageId = 'DETECT';
        s.status = 'INVESTIGATING';
        s.discrepancyEstablished = true;
        s.discrepancy = {
          reason: scenario.discrepancyReason,
          expectedStatus: scenario.expectedStatus,
          observedStatus: scenario.observedStatus,
          terminalOutcome: null // MUST NOT leak terminal outcome!
        };
        s.accumulatedProofs = [...(scenario.proofsByStage['DETECT'] || [])];
        s.timeline = [
          ...s.timeline,
          { step: 'DETECTED', at: event.timestamp, detail: event.detail }
        ];
        break;

      case 'INVESTIGATION_BOUNDED':
        s.currentStageIndex = 1;
        s.selectedStageId = 'INVESTIGATE';
        s.status = 'INVESTIGATING';
        s.accumulatedProofs = this.accumulateProofsUpTo(1, scenario);
        s.timeline = [
          ...s.timeline,
          { step: 'INVESTIGATING', at: event.timestamp, detail: event.detail }
        ];
        break;

      case 'VERIFICATION_ASSERTED':
        s.currentStageIndex = 2;
        s.selectedStageId = 'VERIFY';
        s.status = 'INVESTIGATING';
        s.accumulatedProofs = this.accumulateProofsUpTo(2, scenario);
        s.timeline = [
          ...s.timeline,
          { step: 'VERIFYING', at: event.timestamp, detail: event.detail }
        ];
        break;

      case 'GOVERNANCE_EVALUATED':
        s.currentStageIndex = 3;
        s.selectedStageId = 'DECIDE';
        s.status = 'INVESTIGATING';
        s.accumulatedProofs = this.accumulateProofsUpTo(3, scenario);
        s.timeline = [
          ...s.timeline,
          { step: 'ACTIONABLE', at: event.timestamp, detail: event.detail }
        ];
        break;

      case 'ACTUATION_DISPATCHED':
        s.currentStageIndex = 4;
        s.selectedStageId = 'ACT';
        s.status = 'INVESTIGATING';
        s.accumulatedProofs = this.accumulateProofsUpTo(4, scenario);
        s.timeline = [
          ...s.timeline,
          { step: 'ACTUATING', at: event.timestamp, detail: event.detail }
        ];
        break;

      case 'OBSERVATION_COLLECTED':
        s.currentStageIndex = 5;
        s.selectedStageId = 'REOBSERVE';
        s.status = 'INVESTIGATING';
        s.accumulatedProofs = this.accumulateProofsUpTo(5, scenario);
        s.timeline = [
          ...s.timeline,
          { step: 'REOBSERVING', at: event.timestamp, detail: event.detail }
        ];
        break;

      case 'TERMINAL_CONVERGED':
      case 'TERMINAL_ESCALATED':
        s.currentStageIndex = 6;
        s.selectedStageId = 'TERMINAL';
        s.isPlaying = false;
        s.status = scenario.terminalState === 'RESOLVED' ? 'RESOLVED' : 'ESCALATED';
        s.discrepancy = {
          ...s.discrepancy,
          terminalOutcome: scenario.terminalState
        };
        s.accumulatedProofs = this.accumulateProofsUpTo(6, scenario);
        s.timeline = [
          ...s.timeline,
          {
            step: scenario.terminalState,
            at: event.timestamp,
            detail: event.detail
          }
        ];
        break;
    }

    this.state = s;
    this.emitStateChange();
  }

  private accumulateProofsUpTo(index: number, scenario: ScenarioDefinition) {
    const accumulated: typeof scenario.proofsByStage['DETECT'] = [];
    for (let i = 0; i <= index; i++) {
      const stageId = STAGE_ORDER[i];
      if (stageId && scenario.proofsByStage[stageId]) {
        accumulated.push(...scenario.proofsByStage[stageId]);
      }
    }
    return accumulated;
  }

  // ---------------------------------------------------------------------------
  // Control Interface
  // ---------------------------------------------------------------------------
  public setMode(mode: ExecutionMode) {
    if (this.state.mode === mode) return;
    this.clearTimers();
    this.state = {
      ...this.state,
      mode,
      isPlaying: false,
      isLiveRunning: false
    };
    this.checkReadiness();
    this.emitStateChange();
  }

  public setScenario(id: ScenarioPresetId) {
    this.clearTimers();
    this.state = createInitialEngineState(id, this.state.mode, this.state.readiness);
    this.emitStateChange();
  }

  public selectStage(stageId: PipelineStageId | 'READY') {
    if (stageId === 'READY') {
      this.state.selectedStageId = 'READY';
      this.emitStateChange();
      return;
    }
    const idx = STAGE_ORDER.indexOf(stageId);
    if (idx <= this.state.currentStageIndex) {
      this.state.selectedStageId = stageId;
      this.emitStateChange();
    }
  }

  public setPlaybackSpeed(speed: number) {
    this.state.playbackSpeed = speed;
    this.emitStateChange();
  }

  public reset() {
    this.applyEvent({
      type: 'RESET_TO_READY',
      stageIndex: -1,
      stageId: 'READY',
      timestamp: new Date().toISOString(),
      detail: 'Control loop reset to initial un-reconciled state'
    });
  }

  public stepForward() {
    this.pause();
    this.advanceOneStep();
  }

  public togglePlay() {
    if (this.state.isPlaying) {
      this.pause();
    } else {
      this.play();
    }
  }

  public play() {
    if (this.state.currentStageIndex >= STAGE_ORDER.length - 1) {
      this.reset();
    }
    this.state.isPlaying = true;
    this.emitStateChange();
    this.scheduleNextPlaybackTick();
  }

  public pause() {
    this.state.isPlaying = false;
    if (this.playTimer) {
      clearTimeout(this.playTimer);
      this.playTimer = null;
    }
    this.emitStateChange();
  }

  private advanceOneStep() {
    const nextIdx = this.state.currentStageIndex + 1;
    if (nextIdx > STAGE_ORDER.length - 1) {
      this.pause();
      return;
    }

    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false }) + ' UTC';
    const currentScen = this.state.currentScenario;

    switch (nextIdx) {
      case 0: // DETECT
        this.applyEvent({
          type: 'RECONCILIATION_ESTABLISHED',
          stageIndex: 0,
          stageId: 'DETECT',
          timestamp,
          detail: `Expected ${currentScen.expectedStatus} ≠ Observed ${currentScen.observedStatus} (${currentScen.discrepancyReason})`
        });
        break;

      case 1: // INVESTIGATE
        this.applyEvent({
          type: 'INVESTIGATION_BOUNDED',
          stageIndex: 1,
          stageId: 'INVESTIGATE',
          timestamp,
          detail: '4 bounded evidence records assembled · Bounded A3 hypothesis generated'
        });
        break;

      case 2: // VERIFY
        this.applyEvent({
          type: 'VERIFICATION_ASSERTED',
          stageIndex: 2,
          stageId: 'VERIFY',
          timestamp,
          detail:
            this.state.scenarioId === 'SCENARIO_B'
              ? 'Provider returned HTTP 404 NOT FOUND · Truth unestablished'
              : this.state.scenarioId === 'SCENARIO_C'
              ? 'D4 Invariant Violation: ev_hallucinated_fabricated_id_99999 NOT FOUND'
              : 'D4 containment verified · Provider query returned 200 OK'
        });
        break;

      case 3: // DECIDE
        this.applyEvent({
          type: 'GOVERNANCE_EVALUATED',
          stageIndex: 3,
          stageId: 'DECIDE',
          timestamp,
          detail:
            this.state.scenarioId === 'SCENARIO_B' || this.state.scenarioId === 'SCENARIO_C'
              ? 'Governance Gate: Mutation blocked · Policy: ESCALATE'
              : 'Governance Gate: Action authorized · Policy: REFUND_PAYMENT'
        });
        break;

      case 4: // ACT
        this.applyEvent({
          type: 'ACTUATION_DISPATCHED',
          stageIndex: 4,
          stageId: 'ACT',
          timestamp,
          detail:
            this.state.scenarioId === 'SCENARIO_B' || this.state.scenarioId === 'SCENARIO_C'
              ? 'Actuation skipped · Zero mutations dispatched to external provider'
              : 'OCC lease acquired · Idempotency key locked · Mutation dispatched'
        });
        break;

      case 5: // REOBSERVE
        this.applyEvent({
          type: 'OBSERVATION_COLLECTED',
          stageIndex: 5,
          stageId: 'REOBSERVE',
          timestamp,
          detail:
            this.state.scenarioId === 'SCENARIO_B' || this.state.scenarioId === 'SCENARIO_C'
              ? 'Re-observation skipped'
              : 'Post-actuation provider state re-observed: status="refunded"'
        });
        break;

      case 6: // OUTCOME
        if (currentScen.terminalState === 'RESOLVED') {
          this.applyEvent({
            type: 'TERMINAL_CONVERGED',
            stageIndex: 6,
            stageId: 'TERMINAL',
            timestamp,
            detail: 'External and internal state converged · Proof sealed'
          });
        } else {
          this.applyEvent({
            type: 'TERMINAL_ESCALATED',
            stageIndex: 6,
            stageId: 'TERMINAL',
            timestamp,
            detail: `Deterministic escalation: ${currentScen.terminalState}`
          });
        }
        break;
    }
  }

  private scheduleNextPlaybackTick() {
    if (!this.state.isPlaying) return;
    if (this.state.currentStageIndex >= STAGE_ORDER.length - 1) {
      this.pause();
      return;
    }

    const delay =
      this.state.playbackSpeed === 0 ? 350 : this.state.playbackSpeed === 2 ? 1400 : 2500;

    this.playTimer = setTimeout(() => {
      this.advanceOneStep();
      if (this.state.currentStageIndex < STAGE_ORDER.length - 1 && this.state.isPlaying) {
        this.scheduleNextPlaybackTick();
      }
    }, delay);
  }

  // ---------------------------------------------------------------------------
  // Live Backend Source Adapter
  // ---------------------------------------------------------------------------
  public async checkReadiness() {
    try {
      const res = await fetch('http://localhost:8000/health/readiness', { method: 'GET' });
      if (res.ok) {
        const data = await res.json();
        this.state.readiness = {
          backend: data.backend === 'CONNECTED' ? 'CONNECTED' : 'OFFLINE',
          ollama: data.ollama === 'READY' ? 'READY' : 'NOT_DETECTED',
          provider: data.provider === 'CONFIGURED' ? 'CONFIGURED' : 'UNCONFIGURED'
        };
      } else {
        this.state.readiness = { backend: 'OFFLINE', ollama: 'NOT_DETECTED', provider: 'CONFIGURED' };
      }
    } catch {
      this.state.readiness = { backend: 'OFFLINE', ollama: 'NOT_DETECTED', provider: 'CONFIGURED' };
    }
    this.emitStateChange();
  }

  public async beginLiveRun(customPayload?: { paymentId: string; orderId: string; amount: number }) {
    if (this.state.isLiveRunning) return;
    this.reset();
    this.state.isLiveRunning = true;
    this.emitStateChange();

    const paymentId = customPayload?.paymentId || `pay_live_${Date.now().toString().slice(-6)}`;
    const orderId = customPayload?.orderId || `ord_live_${Date.now().toString().slice(-6)}`;
    const amount = customPayload?.amount || 4500;

    this.state.caseIdentity = {
      paymentId,
      orderId,
      amount,
      currency: 'INR'
    };
    this.emitStateChange();

    try {
      // 1. Dispatch authoritative live run request to backend
      const res = await fetch('http://localhost:8000/incidents/trigger-live', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          payment_id: paymentId,
          order_id: orderId,
          amount,
          currency: 'INR',
        })
      });

      if (!res.ok) {
        throw new Error(`Backend trigger-live responded with HTTP ${res.status}`);
      }

      const data = await res.json();
      if (data.scenario_data) {
        this.state.currentScenario = data.scenario_data as ScenarioDefinition;
        this.state.scenarioId = 'LIVE_WEBHOOK';
        this.state.caseIdentity = {
          paymentId: data.payment_id || paymentId,
          orderId: data.order_id || orderId,
          amount: data.amount || amount,
          currency: data.currency || 'INR',
        };
        this.emitStateChange();
      }

      // 2. Play back the authoritative normalized events progressively
      const events: NormalizedControlEvent[] = data.events || [];
      const delay =
        this.state.playbackSpeed === 0 ? 350 : this.state.playbackSpeed === 2 ? 800 : 1300;

      for (let i = 0; i < events.length; i++) {
        await new Promise(resolve => setTimeout(resolve, delay));
        this.applyEvent(events[i]);
      }
    } catch (err) {
      console.warn('Live backend execution failed, running simulated fallback:', err);
      // Fallback: run progressive playback so the demo never stalls
      this.play();
    } finally {
      this.state.isLiveRunning = false;
      this.emitStateChange();
    }
  }

  private clearTimers() {
    if (this.playTimer) {
      clearTimeout(this.playTimer);
      this.playTimer = null;
    }
    if (this.livePollTimer) {
      clearInterval(this.livePollTimer);
      this.livePollTimer = null;
    }
  }
}
