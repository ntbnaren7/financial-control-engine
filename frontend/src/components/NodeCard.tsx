import React from 'react';
import type { LucideIcon } from 'lucide-react';

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
  return (
    <div
      className={`absolute w-64 node-milled-border rounded-xl flex flex-col transition-all duration-300 ${
        isActive ? 'ring-1 ring-white/20 shadow-[0_8px_30px_rgba(0,0,0,0.6)] -translate-y-1' : 'opacity-80 hover:opacity-100'
      }`}
      style={{ left: x, top: y }}
    >
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
          <div className="font-mono text-[10px] tracking-wider uppercase text-zinc-400">
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
