import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { INVARIANTS } from './StageInspectorModal';

interface Metric {
  label: string;
  value: string;
}

export interface NodeCardProps {
  id: string;
  index: number;
  title: string;
  status: 'PENDING' | 'EVALUATING' | 'VERIFIED' | 'SYNCED' | 'ERROR';
  icon: LucideIcon;
  metrics: Metric[];
  x: number;
  y: number;
  hasInput?: boolean;
  hasOutput?: boolean;
  isActive?: boolean;
}

const statusColors = {
  PENDING: 'bg-zinc-600',
  EVALUATING: 'bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.6)] animate-pulse',
  VERIFIED: 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]',
  SYNCED: 'bg-zinc-400',
  ERROR: 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]'
};

const statusTextColors = {
  PENDING: 'text-zinc-500',
  EVALUATING: 'text-blue-400',
  VERIFIED: 'text-emerald-400',
  SYNCED: 'text-zinc-400',
  ERROR: 'text-rose-400'
};

export const NodeCard: React.FC<NodeCardProps> = ({
  id,
  index,
  title,
  status,
  icon: Icon,
  metrics,
  x,
  y,
  hasInput = true,
  hasOutput = true,
  isActive = false
}) => {
  const stageInfo = INVARIANTS[id === 'OUTCOME' ? 'TERMINAL' : id];

  return (
    <div
      className={`absolute w-[280px] node-milled-border rounded-xl flex flex-col transition-all duration-300 group hover:ring-1 hover:ring-white/20 ${
        isActive ? 'ring-1 ring-white/20 shadow-[0_8px_30px_rgba(0,0,0,0.6)] -translate-y-1' : 'opacity-80 hover:opacity-100'
      }`}
      style={{ left: x, top: y }}
    >
      {/* Hover Tooltip */}
      {stageInfo && (
        <div className="absolute left-1/2 -translate-x-1/2 bottom-[calc(100%+12px)] w-60 opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none z-[100]">
          <div className="bg-[#0c0c0e] border border-white/10 rounded-lg p-3 shadow-2xl relative">
            <h4 className="text-[9px] font-mono text-zinc-500 mb-1.5 uppercase tracking-widest">Stage Info</h4>
            <p className="text-[10px] text-zinc-300 leading-relaxed font-medium">
              {stageInfo.role}
            </p>
            {/* Arrow pointing down */}
            <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-2.5 h-2.5 bg-[#0c0c0e] border-b border-r border-white/10 rotate-45" />
          </div>
        </div>
      )}
      {/* Input Socket */}
      {hasInput && (
        <div className="absolute top-1/2 -left-2 -translate-y-1/2 flex items-center justify-center w-4 h-4 z-10 group">
          <div className={`w-2 h-2 rounded-full border border-zinc-600 bg-zinc-950 transition-colors ${isActive ? 'border-blue-400 bg-blue-500/20' : ''}`} />
        </div>
      )}

      {/* Output Socket */}
      {hasOutput && (
        <div className="absolute top-1/2 -right-2 -translate-y-1/2 flex items-center justify-center w-4 h-4 z-10 group">
          <div className={`w-2 h-2 rounded-full border border-zinc-600 bg-zinc-950 transition-colors ${isActive ? 'border-blue-400 bg-blue-500/20' : ''}`} />
        </div>
      )}

      {/* Header */}
      <div className="px-3 py-2.5 border-b border-white/[0.06] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="bg-zinc-900 border border-zinc-800 rounded p-1">
            <Icon className="w-3.5 h-3.5 text-zinc-300" strokeWidth={2.5} />
          </div>
          <div className="font-mono text-[10px] tracking-wider uppercase text-zinc-400 whitespace-nowrap">
            {String(index).padStart(2, '0')} // {title}
          </div>
        </div>
        
        {/* Status Dot */}
        <div className="flex items-center gap-1.5">
          <span className={`font-mono text-[9px] tracking-wider uppercase ${statusTextColors[status]}`}>
            {status}
          </span>
          <div className={`w-1.5 h-1.5 rounded-full ${statusColors[status]}`} />
        </div>
      </div>

      {/* Body / Metrics */}
      <div className="p-3 flex flex-col gap-2 bg-zinc-950/30 rounded-b-xl">
        {metrics.map((metric, i) => (
          <div key={i} className="flex items-center justify-between font-mono text-[11px]">
            <span className="text-zinc-500">{metric.label}</span>
            <span className="text-zinc-200">{metric.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
