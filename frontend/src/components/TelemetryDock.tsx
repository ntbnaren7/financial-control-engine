import React from 'react';
import { Play, Pause, StepForward, RotateCcw } from 'lucide-react';
import type { ScenarioPresetId } from '../types';

interface TelemetryDockProps {
  currentScenarioId: ScenarioPresetId;
  onSelectScenario: (scenarioId: ScenarioPresetId) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onStepForward: () => void;
  onReset: () => void;
  metrics: {
    tps: string;
    discrepancy: string;
    audit: string;
  };
}

export const TelemetryDock: React.FC<TelemetryDockProps> = ({
  currentScenarioId,
  onSelectScenario,
  isPlaying,
  onTogglePlay,
  onStepForward,
  onReset,
  metrics
}) => {
  return (
    <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-50 flex items-center gap-4 bg-zinc-950/80 backdrop-blur-xl border border-white/10 rounded-full px-4 py-2.5 shadow-[0_20px_40px_rgba(0,0,0,0.5)]">
      
      {/* Live Status */}
      <div className="flex items-center gap-2 px-3 border-r border-white/10 whitespace-nowrap">
        <div className="relative flex items-center justify-center w-2 h-2">
          <div className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-75" />
          <div className="relative w-1.5 h-1.5 rounded-full bg-emerald-400" />
        </div>
        <span className="font-mono text-[10px] tracking-widest text-zinc-300">ENGINE ONLINE</span>
      </div>

      {/* Telemetry Metrics */}
      <div className="hidden md:flex items-center gap-4 px-3 font-mono text-[10px] tracking-wide text-zinc-400 border-r border-white/10 whitespace-nowrap">
        <div className="flex gap-1.5">
          <span>TPS:</span>
          <span className="text-zinc-200">{metrics.tps}</span>
        </div>
        <div className="flex gap-1.5">
          <span>DISCREPANCY:</span>
          <span className="text-zinc-200">{metrics.discrepancy}</span>
        </div>
        <div className="flex gap-1.5">
          <span>AUDIT:</span>
          <span className="text-zinc-200">{metrics.audit}</span>
        </div>
      </div>

      {/* Scenario Switcher */}
      <div className="px-3 border-r border-white/10">
        <select
          value={currentScenarioId}
          onChange={(e) => onSelectScenario(e.target.value as ScenarioPresetId)}
          className="appearance-none bg-zinc-900 border border-zinc-800 hover:border-zinc-700 text-zinc-300 font-mono text-[10px] tracking-wide rounded px-3 py-1.5 outline-none cursor-pointer transition-colors"
        >
          <option value="SCENARIO_A">SCENARIO A: AUTO-REFUND</option>
          <option value="SCENARIO_B">SCENARIO B: MISSING EVIDENCE</option>
          <option value="SCENARIO_C">SCENARIO C: HALLUCINATION GUARD</option>
        </select>
      </div>

      {/* Transport Controls */}
      <div className="flex items-center gap-1.5 px-2">
        <button
          onClick={onTogglePlay}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded font-mono text-[10px] tracking-widest transition-all ${
            isPlaying 
              ? 'bg-amber-500/10 text-amber-500 hover:bg-amber-500/20'
              : 'bg-white text-black hover:bg-zinc-200'
          }`}
        >
          {isPlaying ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" fill="currentColor" />}
          {isPlaying ? 'PAUSE' : 'RUN'}
        </button>
        <button
          onClick={onStepForward}
          className="p-1.5 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          title="Step Forward"
        >
          <StepForward className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onReset}
          className="p-1.5 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          title="Reset Engine"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

    </div>
  );
};
