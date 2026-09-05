import { useState } from 'react';
import type { ScenarioDefinition, ScenarioPresetId } from '../types';

interface ActiveExceptionPanelProps {
  currentScenario: ScenarioDefinition;
  onSelectScenario: (scenarioId: ScenarioPresetId) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onStepForward: () => void;
  onReset: () => void;
  playbackSpeed: number;
  onChangeSpeed: (speed: number) => void;
  onInjectCustomWebhook: (payload: { paymentId: string; orderId: string; amount: number }) => void;
  isInjecting: boolean;
}

export const ActiveExceptionPanel: React.FC<ActiveExceptionPanelProps> = ({
  currentScenario,
  onSelectScenario,
  isPlaying,
  onTogglePlay,
  onStepForward,
  onReset,
  playbackSpeed,
  onChangeSpeed,
  onInjectCustomWebhook,
  isInjecting
}) => {
  // Custom injection state
  const [customPaymentId, setCustomPaymentId] = useState('pay_live_3819482');
  const [customOrderId, setCustomOrderId] = useState('ord_live_5601928');
  const [customAmount, setCustomAmount] = useState('4500');

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onInjectCustomWebhook({
      paymentId: customPaymentId,
      orderId: customOrderId,
      amount: parseInt(customAmount, 10) || 4500
    });
  };

  return (
    <div className="flex flex-col h-full bg-slate-950/80 border-r border-slate-800/80 p-4 gap-4 overflow-y-auto select-none">
      {/* 1. Scenario Selector Tabs */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="font-mono text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            DEMO SCENARIOS
          </span>
          <span className="font-mono text-[9px] text-slate-400 uppercase tracking-widest bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded-xs">
            Preset Switcher
          </span>
        </div>

        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            onClick={() => onSelectScenario('SCENARIO_A')}
            className={`w-full text-left p-2 rounded-sm border transition-all duration-150 font-mono ${
              currentScenario.id === 'SCENARIO_A'
                ? 'bg-emerald-950/40 border-emerald-500/70 text-emerald-200 ring-1 ring-emerald-500/40'
                : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-300'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold">Scenario A: Happy Refund</span>
              <span className="text-[9px] px-1.5 py-0.2 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-xs">
                RESOLVED
              </span>
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5 truncate">
              State mismatch → Verify → Refund → Converged
            </div>
          </button>

          <button
            type="button"
            onClick={() => onSelectScenario('SCENARIO_B')}
            className={`w-full text-left p-2 rounded-sm border transition-all duration-150 font-mono ${
              currentScenario.id === 'SCENARIO_B'
                ? 'bg-amber-950/40 border-amber-500/70 text-amber-200 ring-1 ring-amber-500/40'
                : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-300'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold">Scenario B: Missing 404</span>
              <span className="text-[9px] px-1.5 py-0.2 bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-xs">
                ESCALATED
              </span>
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5 truncate">
              Provider 404 → Truth unestablished → Actuation BLOCKED
            </div>
          </button>

          <button
            type="button"
            onClick={() => onSelectScenario('SCENARIO_C')}
            className={`w-full text-left p-2 rounded-sm border transition-all duration-150 font-mono ${
              currentScenario.id === 'SCENARIO_C'
                ? 'bg-rose-950/40 border-rose-500/70 text-rose-200 ring-1 ring-rose-500/40'
                : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-300'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold">Scenario C: Hallucination Block</span>
              <span className="text-[9px] px-1.5 py-0.2 bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-xs">
                QUARANTINED
              </span>
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5 truncate">
              Fabricated evidence ID → D4 catches it → Mutation BLOCKED
            </div>
          </button>

          <button
            type="button"
            onClick={() => onSelectScenario('LIVE_WEBHOOK')}
            className={`w-full text-left p-2 rounded-sm border transition-all duration-150 font-mono ${
              currentScenario.id === 'LIVE_WEBHOOK'
                ? 'bg-sky-950/40 border-sky-500/70 text-sky-200 ring-1 ring-sky-500/40'
                : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-300'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold">Live Webhook Injection</span>
              <span className="text-[9px] px-1.5 py-0.2 bg-sky-500/20 text-sky-400 border border-sky-500/30 rounded-xs">
                CUSTOM
              </span>
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5 truncate">
              Inject custom payload to active backend worker
            </div>
          </button>
        </div>
      </div>

      {/* 2. Custom Webhook Injection Drawer (Only in LIVE_WEBHOOK mode) */}
      {currentScenario.id === 'LIVE_WEBHOOK' && (
        <form onSubmit={handleCustomSubmit} className="bg-slate-900/80 border border-slate-800 p-3 rounded-sm font-mono text-xs flex flex-col gap-2.5">
          <div className="font-semibold text-sky-300 uppercase tracking-wider text-[11px] border-b border-slate-800 pb-1 flex items-center justify-between">
            <span>INJECT PROVIDER EVENT</span>
            <span className="text-[9px] text-slate-500">POST /webhooks</span>
          </div>

          <div>
            <label className="block text-slate-400 text-[10px] mb-0.5">Payment Reference</label>
            <input
              type="text"
              value={customPaymentId}
              onChange={e => setCustomPaymentId(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-sky-500"
            />
          </div>

          <div>
            <label className="block text-slate-400 text-[10px] mb-0.5">Order Reference</label>
            <input
              type="text"
              value={customOrderId}
              onChange={e => setCustomOrderId(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-sky-500"
            />
          </div>

          <div>
            <label className="block text-slate-400 text-[10px] mb-0.5">Amount (₹ INR)</label>
            <input
              type="number"
              value={customAmount}
              onChange={e => setCustomAmount(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-sky-500"
            />
          </div>

          <button
            type="submit"
            disabled={isInjecting}
            className="mt-1 w-full bg-sky-600 hover:bg-sky-500 text-white font-mono py-1.5 px-3 rounded-sm text-xs font-semibold uppercase tracking-wider transition-colors disabled:opacity-50"
          >
            {isInjecting ? 'Injecting Event...' : 'Inject Webhook →'}
          </button>
        </form>
      )}

      {/* 3. The Active Exception Card (The Thing Being Controlled) */}
      <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-sm flex flex-col gap-2.5 shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <span className="font-mono text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            ACTIVE EXCEPTION
          </span>
          <span className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded-xs border ${
            currentScenario.discrepancyReason === 'STATE_MISMATCH'
              ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
              : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
          }`}>
            {currentScenario.discrepancyReason}
          </span>
        </div>

        {/* Comparison grid */}
        <div className="grid grid-cols-2 gap-2 font-mono text-xs">
          <div className="bg-slate-950/60 p-2 rounded-xs border border-slate-800/80">
            <div className="text-[10px] text-slate-400 uppercase tracking-tight mb-0.5">EXPECTED</div>
            <div className="font-bold text-emerald-400">{currentScenario.expectedStatus}</div>
            <div className="text-[10px] text-slate-400 mt-1">₹{currentScenario.amount.toLocaleString()} {currentScenario.currency}</div>
          </div>
          <div className="bg-slate-950/60 p-2 rounded-xs border border-slate-800/80">
            <div className="text-[10px] text-slate-400 uppercase tracking-tight mb-0.5">OBSERVED</div>
            <div className="font-bold text-amber-400">{currentScenario.observedStatus}</div>
            <div className="text-[10px] text-slate-400 mt-1">₹{currentScenario.amount.toLocaleString()} {currentScenario.currency}</div>
          </div>
        </div>

        <div className="font-mono text-[11px] text-slate-400 bg-slate-950/40 p-2 rounded-xs border border-slate-800/60 flex flex-col gap-1">
          <div className="flex justify-between">
            <span className="text-slate-400">Payment ID:</span>
            <span className="text-slate-200 truncate ml-2 font-semibold">{currentScenario.paymentId}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Order ID:</span>
            <span className="text-slate-200 truncate ml-2">{currentScenario.orderId}</span>
          </div>
          <div className="text-[10px] text-amber-400/90 pt-1 border-t border-slate-800/60 italic">
            "Expected state ≠ observed provider state"
          </div>
        </div>
      </div>

      {/* 4. Playback & Pitch Narration Controls */}
      <div className="bg-slate-900/60 border border-slate-800 p-3 rounded-sm flex flex-col gap-2 font-mono">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            CONTROL REPLAY & STEPPER
          </span>
          <div className="flex items-center gap-1">
            {[1, 2, 0].map(spd => (
              <button
                key={spd}
                type="button"
                onClick={() => onChangeSpeed(spd)}
                className={`text-[9px] px-1.5 py-0.5 rounded-xs border ${
                  playbackSpeed === spd
                    ? 'bg-sky-500/20 text-sky-300 border-sky-500/40'
                    : 'bg-slate-950 text-slate-500 border-slate-800 hover:text-slate-400'
                }`}
              >
                {spd === 0 ? 'INSTANT' : `${spd}x`}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 mt-1">
          <button
            type="button"
            onClick={onTogglePlay}
            className={`py-2 px-2 text-xs font-semibold rounded-sm border flex items-center justify-center gap-1 transition-all ${
              isPlaying
                ? 'bg-amber-600/30 text-amber-300 border-amber-500/50 hover:bg-amber-600/40'
                : 'bg-sky-600/30 text-sky-200 border-sky-500/50 hover:bg-sky-600/40'
            }`}
          >
            {isPlaying ? (
              <>
                <svg className="w-3 h-3 fill-current" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>
                <span>PAUSE</span>
              </>
            ) : (
              <>
                <svg className="w-3 h-3 fill-current" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                <span>RUN</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={onStepForward}
            className="py-2 px-2 text-xs font-semibold bg-slate-800 hover:bg-slate-750 text-slate-200 border border-slate-700 rounded-sm flex items-center justify-center gap-1 transition-colors"
            title="Step to next lifecycle boundary"
          >
            <svg className="w-3 h-3 fill-current" viewBox="0 0 24 24"><path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z"/></svg>
            <span>STEP ⏭</span>
          </button>

          <button
            type="button"
            onClick={onReset}
            className="py-2 px-2 text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 rounded-sm flex items-center justify-center gap-1 transition-colors"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
            <span>RESET</span>
          </button>
        </div>
      </div>

      {/* 5. Recent Control Runs (Secondary Compact Element) */}
      <div className="flex-1 overflow-hidden flex flex-col font-mono min-h-[140px]">
        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5 flex items-center justify-between border-b border-slate-800 pb-1">
          <span>RECENT CONTROL RUNS</span>
          <span className="text-[9px] text-slate-400">Past Audit Traces</span>
        </div>

        <div className="overflow-y-auto flex flex-col gap-1.5 pr-1">
          {[
            { id: 'pay_3819482701', scenario: 'SCENARIO_A' as const, state: 'RESOLVED', stateColor: 'text-emerald-400 bg-emerald-950/40 border-emerald-800', amt: '₹4,500', icon: '✓' },
            { id: 'pay_missing_404', scenario: 'SCENARIO_B' as const, state: 'MISSING', stateColor: 'text-amber-400 bg-amber-950/40 border-amber-800', amt: '₹2,100', icon: '⚠' },
            { id: 'pay_adv_9921820', scenario: 'SCENARIO_C' as const, state: 'UNKNOWN', stateColor: 'text-rose-400 bg-rose-950/40 border-rose-800', amt: '₹12,000', icon: '✕' },
            { id: 'pay_8819201948', scenario: 'SCENARIO_A' as const, state: 'RESOLVED', stateColor: 'text-emerald-400 bg-emerald-950/40 border-emerald-800', amt: '₹8,900', icon: '✓' },
            { id: 'pay_4421948102', scenario: 'SCENARIO_B' as const, state: 'MISSING', stateColor: 'text-amber-400 bg-amber-950/40 border-amber-800', amt: '₹1,250', icon: '⚠' }
          ].map(run => (
            <button
              key={run.id}
              type="button"
              onClick={() => onSelectScenario(run.scenario)}
              className="text-left p-2 rounded-xs bg-slate-900/50 hover:bg-slate-850 border border-slate-800/80 hover:border-slate-700 flex items-center justify-between transition-colors text-xs"
            >
              <div className="flex items-center gap-1.5 truncate">
                <span className="text-[11px] font-bold text-slate-300 truncate">{run.id}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-[9px] px-1 py-0.2 rounded-xs border ${run.stateColor}`}>
                  {run.icon} {run.state}
                </span>
                <span className="text-slate-400 text-[10px]">{run.amt}</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
