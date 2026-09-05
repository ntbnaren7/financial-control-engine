import React, { useState } from 'react';
import { BATCH_RUN_SUMMARY, BATCH_RECORDS } from '../scenarios/batchData';
import type { BatchRecord } from '../types';

interface BatchSummaryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectRecordForTrace: (record: BatchRecord) => void;
}

export const BatchSummaryModal: React.FC<BatchSummaryModalProps> = ({
  isOpen,
  onClose,
  onSelectRecordForTrace
}) => {
  const [filter, setFilter] = useState<'ALL' | 'MATCH' | 'REFUND' | 'ESCALATED'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  if (!isOpen) return null;

  const filteredRecords = BATCH_RECORDS.filter(rec => {
    if (filter === 'MATCH' && rec.outcome !== 'MATCH') return false;
    if (filter === 'REFUND' && rec.scenarioType !== 'REFUND') return false;
    if (filter === 'ESCALATED' && rec.outcome !== 'ESCALATED') return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        rec.recordId.toLowerCase().includes(q) ||
        rec.paymentId.toLowerCase().includes(q) ||
        rec.scenarioType.toLowerCase().includes(q) ||
        rec.notes.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 lg:p-8 bg-slate-900/40 backdrop-blur-xs select-none font-sans text-xs">
      <div className="bg-white border border-[#D8E2EE] rounded-md w-full max-w-5xl max-h-[88vh] flex flex-col overflow-hidden shadow-lg">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-[#E2E8F0] flex items-center justify-between bg-[#FAFCFE]">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="text-[#0C1A30] font-bold text-xs tracking-wider uppercase font-sans">
                60-RECORD CONTROL RUN
              </span>
              <span className="text-slate-300">/</span>
              <span className="text-slate-500 text-[11px] font-medium font-sans">TRACK 04 FORENSIC BATCH EVALUATION</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5 font-sans">
              Observed batch outcomes across 60 synthetic payment scenarios. 0 timeouts · 0 unsupported resolutions.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="text-slate-500 hover:text-[#0C1A30] px-2.5 py-1 border border-[#D8E2EE] rounded hover:bg-slate-50 transition-colors text-xs font-semibold cursor-pointer font-sans"
          >
            ESC ✕
          </button>
        </div>

        {/* Minimalist Single-Line Metrics Summary Bar (No Card Grids) */}
        <div className="px-6 py-3 border-b border-[#E2E8F0] bg-white flex flex-wrap items-center justify-between text-xs gap-4 font-sans">
          <div className="flex items-center gap-5 flex-wrap">
            <div>
              <span className="text-slate-400 text-[10px] uppercase font-semibold">DIRECT MATCH:</span>{' '}
              <span className="text-[#00B37E] font-bold font-mono">{BATCH_RUN_SUMMARY.directMatches}/60</span>{' '}
              <span className="text-slate-500 text-[11px] font-mono">({BATCH_RUN_SUMMARY.directMatchRate}%)</span>
            </div>
            <div className="border-l border-[#E2E8F0] pl-5">
              <span className="text-slate-400 text-[10px] uppercase font-semibold">REMEDIATED:</span>{' '}
              <span className="text-[#0C6BF5] font-bold font-mono">{BATCH_RUN_SUMMARY.autonomousResolved} refunds</span>{' '}
              <span className="text-slate-500 text-[11px] font-mono">(18.3%)</span>
            </div>
            <div className="border-l border-[#E2E8F0] pl-5">
              <span className="text-slate-400 text-[10px] uppercase font-semibold">ESCALATED:</span>{' '}
              <span className="text-amber-700 font-bold font-mono">{BATCH_RUN_SUMMARY.missingEvidenceEscalations + BATCH_RUN_SUMMARY.amountMismatchEscalations} cases</span>{' '}
              <span className="text-slate-500 text-[11px] font-mono">(15.0%)</span>
            </div>
            <div className="border-l border-[#E2E8F0] pl-5">
              <span className="text-slate-400 text-[10px] uppercase font-semibold">TOTAL RESOLVED:</span>{' '}
              <span className="text-[#0C1A30] font-bold font-mono">{BATCH_RUN_SUMMARY.totalResolutionRate}%</span>{' '}
              <span className="text-slate-500 text-[11px] font-mono">(51/60)</span>
            </div>
          </div>

          <span className="text-slate-400 text-[10px] italic font-sans">
            "Observed outcome rates, not an ML accuracy score"
          </span>
        </div>

        {/* Filter & Search Bar */}
        <div className="px-6 py-2.5 border-b border-[#E2E8F0] flex flex-wrap items-center justify-between gap-3 bg-[#F8FAFC]">
          <div className="flex items-center gap-1.5 text-xs font-sans">
            <button
              type="button"
              onClick={() => setFilter('ALL')}
              className={`px-3 py-1 rounded border transition-colors cursor-pointer ${
                filter === 'ALL'
                  ? 'bg-[#EDF5FF] text-[#0C6BF5] border-[#D0E4FF] font-semibold'
                  : 'bg-white text-slate-600 border-[#D8E2EE] hover:text-[#0C1A30] hover:border-slate-300'
              }`}
            >
              All (60)
            </button>
            <button
              type="button"
              onClick={() => setFilter('MATCH')}
              className={`px-3 py-1 rounded border transition-colors cursor-pointer ${
                filter === 'MATCH'
                  ? 'bg-emerald-50 text-[#00B37E] border-emerald-300 font-semibold'
                  : 'bg-white text-slate-600 border-[#D8E2EE] hover:text-[#0C1A30] hover:border-slate-300'
              }`}
            >
              Direct Match (40)
            </button>
            <button
              type="button"
              onClick={() => setFilter('REFUND')}
              className={`px-3 py-1 rounded border transition-colors cursor-pointer ${
                filter === 'REFUND'
                  ? 'bg-[#EDF5FF] text-[#0C6BF5] border-[#D0E4FF] font-semibold'
                  : 'bg-white text-slate-600 border-[#D8E2EE] hover:text-[#0C1A30] hover:border-slate-300'
              }`}
            >
              Autonomous Refunds (11)
            </button>
            <button
              type="button"
              onClick={() => setFilter('ESCALATED')}
              className={`px-3 py-1 rounded border transition-colors cursor-pointer ${
                filter === 'ESCALATED'
                  ? 'bg-amber-50 text-amber-800 border-amber-300 font-semibold'
                  : 'bg-white text-slate-600 border-[#D8E2EE] hover:text-[#0C1A30] hover:border-slate-300'
              }`}
            >
              Escalated (9)
            </button>
          </div>

          <div className="w-64">
            <input
              type="text"
              placeholder="Search payment, order, notes..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full bg-white border border-[#D8E2EE] rounded px-3 py-1 text-[#0C1A30] text-xs focus:outline-none focus:border-[#0C6BF5] font-sans transition-colors"
            />
          </div>
        </div>

        {/* Dense Forensic Ledger Table: RECORD | PAYMENT | AMOUNT | EXPECTED | OBSERVED | OUTCOME | REASON */}
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead className="bg-[#FAFCFE] sticky top-0 border-b border-[#E2E8F0] text-[10px] text-slate-500 uppercase tracking-wider font-semibold font-sans">
              <tr>
                <th className="py-2.5 px-4">RECORD</th>
                <th className="py-2.5 px-3">PAYMENT</th>
                <th className="py-2.5 px-3">AMOUNT</th>
                <th className="py-2.5 px-3">EXPECTED</th>
                <th className="py-2.5 px-3">OBSERVED</th>
                <th className="py-2.5 px-3">OUTCOME</th>
                <th className="py-2.5 px-4">REASON</th>
                <th className="py-2.5 px-4 text-right">ACTION</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EBF0F7]">
              {filteredRecords.map(rec => {
                const isEscalated = rec.outcome === 'ESCALATED';
                const isRefund = rec.scenarioType === 'REFUND';

                return (
                  <tr
                    key={rec.recordId}
                    onClick={() => onSelectRecordForTrace(rec)}
                    className="hover:bg-[#EDF5FF]/50 transition-colors cursor-pointer group"
                  >
                    <td className="py-2.5 px-4 text-slate-400 font-medium">{rec.recordId}</td>
                    <td className="py-2.5 px-3 text-[#0C1A30] font-bold">{rec.paymentId}</td>
                    <td className="py-2.5 px-3 text-[#0C1A30] font-mono font-semibold">₹{rec.amount.toLocaleString()}</td>
                    <td className="py-2.5 px-3 text-[#00B37E] font-bold">{rec.expectedStatus}</td>
                    <td className="py-2.5 px-3 text-slate-700">{rec.providerStatus}</td>
                    <td className="py-2.5 px-3">
                      <span className={`font-semibold ${
                        isEscalated ? 'text-amber-700' : isRefund ? 'text-[#0C6BF5]' : 'text-[#00B37E]'
                      }`}>
                        {rec.outcome}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-slate-500 text-[11px] truncate max-w-xs">{rec.notes}</td>
                    <td className="py-2.5 px-4 text-right whitespace-nowrap">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectRecordForTrace(rec);
                        }}
                        className="text-[11px] text-[#0C6BF5] hover:text-[#0957C7] font-semibold group-hover:underline cursor-pointer"
                      >
                        Inspect Trace →
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-[#E2E8F0] flex items-center justify-between text-xs text-slate-500 bg-[#FAFCFE]">
          <span>Select any exception to inspect its complete progressive investigation trace in the forensic console.</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 bg-white hover:bg-slate-50 text-[#0C1A30] border border-[#D8E2EE] rounded-lg transition-colors font-semibold shadow-2xs cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
