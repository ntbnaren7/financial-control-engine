import React from 'react';
import { motion } from 'framer-motion';
import { Database, CreditCard, ShieldCheck, AlertCircle } from 'lucide-react';
import type {
  ScenarioDefinition,
  ScenarioPresetId,
  PipelineStageId,
  ProofItem
} from '../types';

interface SimulationShowcaseProps {
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
  playbackSpeed: number;
  onChangeSpeed: (speed: number) => void;
  proofs: ProofItem[];
  caseIdentity: {
    paymentId: string;
    orderId: string;
    amount: number;
    currency: string;
  };
}

// Background Dot Grid
const DotGrid = () => (
  <div 
    className="absolute inset-0 pointer-events-none z-0" 
    style={{
      backgroundImage: 'radial-gradient(#CBD5E1 1px, transparent 1px)',
      backgroundSize: '24px 24px',
      opacity: 0.5
    }} 
  />
);

export const SimulationShowcase: React.FC<SimulationShowcaseProps> = ({
  currentScenario,
  currentScenarioId,
  onSelectScenario,
  currentStageIndex,
  isPlaying,
  onTogglePlay,
  onStepForward,
  onReset,
}) => {
  const detectStage = currentScenario.stages['DETECT']?.detectData;
  const expected = detectStage?.expected || { amount: 0, status: 'Missing entry', currency: 'INR' };
  const observed = detectStage?.observed || { amount: 2400, status: 'Success', currency: 'INR' };
  const terminalState = currentScenario.terminalState;

  const formatAmt = (amt: number) => `₹${amt.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

  const isOutputVisible = currentStageIndex >= 6;
  const isEngineActive = currentStageIndex >= 1 && currentStageIndex < 6;

  return (
    <div className="w-full h-full bg-[#f8fafc] flex flex-col font-sans text-slate-800 relative overflow-hidden rounded-t-[6px]">
      
      {/* 1. Canvas Background */}
      <DotGrid />

      {/* Top Controls Bar - Glassmorphism */}
      <div className="flex items-center justify-between px-6 py-4 bg-white/70 backdrop-blur-md border-b border-slate-200/50 z-20 relative">
        <div className="flex items-center gap-3">
          <select
            value={currentScenarioId}
            onChange={e => onSelectScenario(e.target.value as ScenarioPresetId)}
            className="bg-white border border-slate-200 rounded-md px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 cursor-pointer"
          >
            <option value="SCENARIO_A">Scenario A — Autonomous Refund</option>
            <option value="SCENARIO_B">Scenario B - Missing Evidence</option>
            <option value="SCENARIO_C">Scenario C — Hallucination Catch</option>
          </select>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={onTogglePlay}
            className={`px-4 py-1.5 rounded-md text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 ${
              isPlaying 
                ? 'bg-amber-500 hover:bg-amber-600 text-white' 
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            }`}
          >
            {isPlaying ? 'PAUSE' : 'RUN'}
          </button>
          <button
            onClick={onStepForward}
            className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 rounded-md text-xs font-semibold shadow-sm transition-all text-slate-600"
          >
            STEP
          </button>
          <button
            onClick={onReset}
            className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 rounded-md text-xs font-semibold shadow-sm transition-all text-slate-600"
          >
            RESET
          </button>
        </div>
      </div>

      {/* Flowchart Area */}
      <div className="flex-1 relative w-full flex items-center justify-center p-8 z-10">
        
        {/* SVG Connectors Container */}
        <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
           <svg width="800" height="400" viewBox="0 0 800 400" className="overflow-visible">
              <defs>
                <linearGradient id="lineGrad1" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#818CF8" /> {/* Indigo */}
                  <stop offset="100%" stopColor="#3B82F6" /> {/* Blue */}
                </linearGradient>
                <linearGradient id="lineGrad2" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#2DD4BF" /> {/* Teal */}
                  <stop offset="100%" stopColor="#3B82F6" /> {/* Blue */}
                </linearGradient>
                <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                  <polygon points="0 0, 10 3.5, 0 7" fill="#3B82F6" />
                </marker>
                
                {/* Glowing drop shadow for paths */}
                <filter id="glow">
                  <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                  <feMerge>
                    <feMergeNode in="coloredBlur"/>
                    <feMergeNode in="SourceGraphic"/>
                  </feMerge>
                </filter>
              </defs>

              {/* Gateway to Engine Line */}
              <motion.path 
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ duration: 1, ease: "easeInOut" }}
                d="M 240 116 C 295 116, 295 200, 350 200"
                fill="none"
                stroke="url(#lineGrad1)"
                strokeWidth="3"
                filter={isEngineActive ? "url(#glow)" : ""}
                strokeDasharray={isEngineActive ? "8 4" : "0"}
                className={isEngineActive ? "animate-[dash_1s_linear_infinite]" : ""}
              />

              {/* Ledger to Engine Line */}
              <motion.path 
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ duration: 1, ease: "easeInOut", delay: 0.2 }}
                d="M 240 296 C 295 296, 295 200, 350 200"
                fill="none"
                stroke="url(#lineGrad2)"
                strokeWidth="3"
                filter={isEngineActive ? "url(#glow)" : ""}
                strokeDasharray={isEngineActive ? "8 4" : "0"}
                className={isEngineActive ? "animate-[dash_1s_linear_infinite]" : ""}
              />

              {/* Engine to Output Line */}
              <motion.path 
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: isOutputVisible ? 1 : 0, opacity: isOutputVisible ? 1 : 0 }}
                transition={{ duration: 0.8, ease: "easeOut" }}
                d="M 450 200 L 555 200"
                fill="none"
                stroke="#3B82F6"
                strokeWidth="3"
                markerEnd="url(#arrowhead)"
              />
           </svg>
        </div>

        {/* Nodes Container */}
        <div className="relative w-[800px] h-[400px]">
          
          {/* 1. Gateway Node */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ y: -2, boxShadow: "0 20px 40px -10px rgba(99,102,241,0.15)" }}
            className="absolute left-[20px] top-[60px] w-[220px] h-[112px] bg-white rounded-xl shadow-lg border border-slate-200/60 flex flex-col z-10 transition-all duration-300"
          >
            {/* Header */}
            <div className="h-9 bg-indigo-50 border-b border-indigo-100 rounded-t-xl px-3 flex items-center gap-2">
              <CreditCard className="w-4 h-4 text-indigo-500" />
              <span className="text-indigo-900 font-bold text-[11px] uppercase tracking-wider">Gateway</span>
            </div>
            {/* Body */}
            <div className="flex-1 p-3 flex flex-col justify-center">
              <div className="text-slate-700 text-xl font-bold tracking-tight">
                {formatAmt(observed.amount)}
              </div>
              <div className="flex items-center gap-1.5 mt-1">
                <div className={`w-1.5 h-1.5 rounded-full ${(observed.status as string) === 'SUCCESS' || (observed.status as string) === 'AUTHORIZED' || (observed.status as string) === 'Success' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-rose-500'}`} />
                <span className="text-slate-500 text-xs font-medium">{observed.status}</span>
              </div>
            </div>
            {/* Connection Handle (Right) */}
            <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 w-3 h-3 bg-white border-2 border-indigo-400 rounded-full z-20" />
          </motion.div>

          {/* 2. Internal Ledger Node */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            whileHover={{ y: -2, boxShadow: "0 20px 40px -10px rgba(20,184,166,0.15)" }}
            className="absolute left-[20px] top-[240px] w-[220px] h-[112px] bg-white rounded-xl shadow-lg border border-slate-200/60 flex flex-col z-10 transition-all duration-300"
          >
            {/* Header */}
            <div className="h-9 bg-teal-50 border-b border-teal-100 rounded-t-xl px-3 flex items-center gap-2">
              <Database className="w-4 h-4 text-teal-500" />
              <span className="text-teal-900 font-bold text-[11px] uppercase tracking-wider">Internal Ledger</span>
            </div>
            {/* Body */}
            <div className="flex-1 p-3 flex flex-col justify-center">
              <div className="text-slate-700 text-xl font-bold tracking-tight">
                {formatAmt(expected.amount)}
              </div>
              <div className="flex items-center gap-1.5 mt-1">
                <div className={`w-1.5 h-1.5 rounded-full ${(expected.status as string) === 'CAPTURED' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]'}`} />
                <span className="text-slate-500 text-xs font-medium">{expected.status === 'UNKNOWN' ? 'Missing entry' : expected.status}</span>
              </div>
            </div>
            {/* Connection Handle (Right) */}
            <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 w-3 h-3 bg-white border-2 border-teal-400 rounded-full z-20" />
          </motion.div>

          {/* 3. Central FCE Engine Node */}
          <motion.div 
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.2, type: "spring", stiffness: 300, damping: 20 }}
            whileHover={{ scale: 1.05 }}
            className={`absolute left-[350px] top-[150px] w-[100px] h-[100px] bg-white rounded-2xl shadow-xl flex items-center justify-center z-10 transition-colors duration-300 ${isEngineActive ? 'border-2 border-blue-400 shadow-[0_0_30px_rgba(59,130,246,0.3)]' : 'border border-slate-200'}`}
          >
            {/* Custom FCE Blue Chevron Logo */}
            <svg width="44" height="44" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" className={isEngineActive ? "animate-pulse" : ""}>
              <path d="M12 30 L22 10 L28 10 L18 30 Z" fill="#2563EB" />
              <path d="M22 30 L32 10 L38 10 L28 30 Z" fill="#60A5FA" />
            </svg>

            {/* Connection Handle (Left) */}
            <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 bg-white border-2 border-blue-400 rounded-full z-20" />
            {/* Connection Handle (Right) */}
            <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 w-3 h-3 bg-white border-2 border-blue-400 rounded-full z-20" />
          </motion.div>

          {/* 4. Outcome/Reconciled Node */}
          <motion.div 
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: isOutputVisible ? 1 : 0, x: isOutputVisible ? 0 : 20 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            whileHover={{ y: -2, boxShadow: "0 20px 40px -10px rgba(16,185,129,0.15)" }}
            className="absolute left-[560px] top-[144px] w-[220px] h-[112px] bg-white rounded-xl shadow-lg border border-slate-200/60 flex flex-col z-10 transition-all duration-300"
          >
            {/* Header */}
            <div className={`h-9 border-b rounded-t-xl px-3 flex items-center gap-2 ${terminalState === 'RESOLVED' ? 'bg-emerald-50 border-emerald-100' : 'bg-amber-50 border-amber-100'}`}>
              {terminalState === 'RESOLVED' ? (
                <ShieldCheck className="w-4 h-4 text-emerald-500" />
              ) : (
                <AlertCircle className="w-4 h-4 text-amber-500" />
              )}
              <span className={`font-bold text-[11px] uppercase tracking-wider ${terminalState === 'RESOLVED' ? 'text-emerald-900' : 'text-amber-900'}`}>
                {terminalState === 'RESOLVED' ? 'Reconciled' : 'Escalated'}
              </span>
            </div>
            {/* Body */}
            <div className="flex-1 p-3 flex flex-col justify-center">
              <div className="text-slate-700 text-xl font-bold tracking-tight">
                {formatAmt(currentScenario.amount)}
              </div>
              <div className="flex items-center gap-1.5 mt-1">
                <div className={`w-1.5 h-1.5 rounded-full ${terminalState === 'RESOLVED' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]'}`} />
                <span className="text-slate-500 text-xs font-medium">
                  {terminalState === 'RESOLVED' ? 'Refund issued' : 'Flagged for review'}
                </span>
              </div>
            </div>
            {/* Connection Handle (Left) */}
            <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 bg-white border-2 border-blue-400 rounded-full z-20" />
          </motion.div>

        </div>
      </div>
    </div>
  );
};
