import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronLeft, ChevronRight, CheckCircle2, AlertTriangle, ShieldAlert, Zap, Search, Cpu, RotateCcw, Flag } from 'lucide-react';
import type { PipelineStageId, ScenarioPresetId, StageExecutionPayload, AuthorityDomain } from '../types';
import { DEMO_SCENARIOS } from '../scenarios/demoScenarios';

interface StageInspectorModalProps {
  stageId: PipelineStageId | 'READY';
  onClose: () => void;
  onNext: () => void;
  onPrev: () => void;
}

const STAGE_ICONS: Record<string, React.ElementType> = {
  DETECT: Search,
  INVESTIGATE: Cpu,
  VERIFY: ShieldAlert,
  DECIDE: Zap,
  ACT: CheckCircle2,
  REOBSERVE: RotateCcw,
  TERMINAL: Flag
};

const STAGE_INDEX: Record<string, string> = {
  DETECT: '01',
  INVESTIGATE: '02',
  VERIFY: '03',
  DECIDE: '04',
  ACT: '05',
  REOBSERVE: '06',
  TERMINAL: '07'
};

const AUTHORITY_COLORS: Record<AuthorityDomain, string> = {
  DETERMINISTIC: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  UNTRUSTED_AI: 'text-amber-400 bg-amber-500/10 border-amber-500/30'
};

export const INVARIANTS: Record<string, { role: string; invariant: string }> = {
  DETECT: {
    role: 'Parallel ingestion and strict deterministic equality checking between internal ledgers and external gateways.',
    invariant: 'State equality requires 1:1 match across all monetary values and canonical status mappings.'
  },
  INVESTIGATE: {
    role: 'A3 Reasoner (Untrusted LLM). Formulates causal hypotheses and proposes verification intents based on bounded evidence context.',
    invariant: 'Untrusted AI reasoning can propose hypotheses but cannot mutate financial state or contact external gateways directly. (Authority: NONE)'
  },
  VERIFY: {
    role: 'D4 Gate and Deterministic Verifier. Intercepts LLM intents, validates payload containment, and queries ground-truth APIs.',
    invariant: 'All AI intents must pass strict deterministic schema and containment validation before any external execution is permitted.'
  },
  DECIDE: {
    role: 'Policy & Governance Engine. Evaluates kill-switches, budgetary limits, and mutation authority against the proven ground truth.',
    invariant: 'Mutations are strictly prohibited unless explicit cryptographically verifiable ground-truth evidence justifies the action.'
  },
  ACT: {
    role: 'OCC Actuator. Executes side-effecting financial mutations (refunds, voids, captures) with Optimistic Concurrency Control.',
    invariant: 'Duplicate intents must never result in duplicate financial effects. Mutations must be idempotent and strictly version-locked.'
  },
  REOBSERVE: {
    role: 'Verification loop. Re-polls the provider state post-mutation to confirm convergence.',
    invariant: 'A dispatched mutation does not equal a verified outcome. The system must re-observe to prove convergence.'
  },
  TERMINAL: {
    role: 'Final Incident Outcome. Either successfully converged and remediated, or safely halted and escalated for human review.',
    invariant: 'Contradictory evidence, unresolved state, or policy violations must immediately escalate and quarantine the transaction.'
  }
};

const SCENARIO_TABS: { id: ScenarioPresetId; label: string; badge: string; color: string }[] = [
  { id: 'SCENARIO_A', label: 'Case A: Auto-Repair', badge: 'RESOLVED', color: 'bg-emerald-500' },
  { id: 'SCENARIO_B', label: 'Case B: Missing Evidence', badge: 'HONEST ESCALATION', color: 'bg-amber-500' },
  { id: 'SCENARIO_C', label: 'Case C: Adversarial Guard', badge: 'HALLUCINATION BLOCKED', color: 'bg-rose-500' }
];

export const StageInspectorModal: React.FC<StageInspectorModalProps> = ({ stageId, onClose, onNext, onPrev }) => {
  const [activeTab, setActiveTab] = useState<ScenarioPresetId>('SCENARIO_A');

  if (stageId === 'READY') return null; // Should not happen in UI, but just in case

  const Icon = STAGE_ICONS[stageId] || CheckCircle2;
  const stageInfo = INVARIANTS[stageId];
  
  // Get payload for current tab
  const scenario = DEMO_SCENARIOS[activeTab];
  const payload = scenario.stages[stageId as PipelineStageId];

  // Helper to render JSON block
  const renderDataBlock = (title: string, data: any) => {
    if (!data) return null;
    return (
      <div className="mt-4">
        <h4 className="text-[10px] font-mono text-zinc-500 mb-2 tracking-widest uppercase">{title}</h4>
        <div className="bg-[#0c0c0e] border border-white/5 rounded-lg p-4 overflow-x-auto">
          <pre className="text-[11px] font-mono text-zinc-300 leading-relaxed">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      </div>
    );
  };

  const renderPayloadDetails = (stagePayload: StageExecutionPayload) => {
    switch (stageId) {
      case 'DETECT':
        return renderDataBlock('Detection Payload', stagePayload.detectData);
      case 'INVESTIGATE':
        return renderDataBlock('Bounded Evidence & LLM Output', stagePayload.investigateData);
      case 'VERIFY':
        return renderDataBlock('D4 Gate & Provider Verification', stagePayload.verifyData);
      case 'DECIDE':
        return renderDataBlock('Governance Check', stagePayload.decideData);
      case 'ACT':
        return renderDataBlock('OCC Actuation Details', stagePayload.actData);
      case 'REOBSERVE':
        return renderDataBlock('Re-Observation Loop', stagePayload.reobserveData);
      case 'TERMINAL':
        return renderDataBlock('Terminal Resolution Summary', stagePayload.terminalData);
      default:
        return null;
    }
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
        {/* Backdrop */}
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="absolute inset-0 bg-black/80 backdrop-blur-md"
        />

        {/* Modal Container */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          transition={{ type: "spring", damping: 25, stiffness: 300 }}
          className="relative w-full max-w-4xl max-h-[90vh] bg-[#050505] border border-white/10 rounded-2xl shadow-2xl flex flex-col overflow-hidden"
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-zinc-950">
            <div className="flex items-center gap-3">
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-1.5">
                <Icon className="w-5 h-5 text-zinc-300" strokeWidth={2} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-zinc-500 uppercase tracking-widest">STAGE {STAGE_INDEX[stageId]}</span>
                  {payload?.authorityBadge && (
                    <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded border ${AUTHORITY_COLORS[payload.authorityBadge.domain]}`}>
                      {payload.authorityBadge.text}
                    </span>
                  )}
                </div>
                <h2 className="text-lg font-semibold text-white tracking-tight leading-tight mt-0.5">
                  {payload?.title || stageId}
                </h2>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center bg-zinc-900 rounded-md border border-zinc-800 p-0.5 mr-2">
                <button onClick={onPrev} className="p-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded transition-colors" title="Previous Stage">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <div className="w-px h-4 bg-zinc-800 mx-0.5" />
                <button onClick={onNext} className="p-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded transition-colors" title="Next Stage">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
              <button onClick={onClose} className="p-2 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-lg transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Architectural Context */}
          <div className="px-6 py-4 bg-zinc-950/50 border-b border-white/5">
            <p className="text-sm text-zinc-300 mb-2 leading-relaxed">
              <span className="font-semibold text-white">Role: </span>{stageInfo?.role}
            </p>
            <div className="flex gap-2 p-3 bg-blue-500/5 border border-blue-500/20 rounded-lg">
              <ShieldAlert className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-blue-200/80 leading-relaxed font-medium">
                {stageInfo?.invariant}
              </p>
            </div>
          </div>

          {/* 3-Case Tabs */}
          <div className="flex items-center gap-2 px-6 py-3 border-b border-white/5 bg-[#0a0a0a] overflow-x-auto custom-scrollbar">
            {SCENARIO_TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-full text-xs font-medium transition-all whitespace-nowrap ${
                  activeTab === tab.id 
                    ? 'bg-zinc-800 text-white border border-white/10' 
                    : 'text-zinc-500 hover:text-zinc-300 border border-transparent'
                }`}
              >
                <div className={`w-1.5 h-1.5 rounded-full ${tab.color} ${activeTab === tab.id ? 'opacity-100' : 'opacity-50'}`} />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Body Content */}
          <div className="flex-1 overflow-y-auto custom-scrollbar p-6 bg-[#050505]">
            {payload ? (
              <motion.div
                key={`${stageId}-${activeTab}`}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex items-start gap-3 mb-6">
                  {activeTab === 'SCENARIO_C' && stageId === 'VERIFY' ? (
                    <AlertTriangle className="w-5 h-5 text-rose-500 flex-shrink-0 mt-0.5" />
                  ) : activeTab === 'SCENARIO_B' && stageId === 'DECIDE' ? (
                    <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
                  ) : (
                    <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0 mt-0.5" />
                  )}
                  <div>
                    <h3 className="text-lg font-medium text-white mb-1 leading-tight">{payload.headline}</h3>
                    <p className="text-sm text-zinc-400 leading-relaxed">{payload.whyThisHappened}</p>
                  </div>
                </div>

                {renderPayloadDetails(payload)}
              </motion.div>
            ) : (
              <div className="flex flex-col items-center justify-center h-48 text-zinc-500">
                <p>No execution data for this stage in this scenario.</p>
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
