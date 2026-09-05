import { useState } from 'react';
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 lg:p-8 bg-black/85 backdrop-blur-sm select-none font-mono text-xs">
      <div className="bg-[#090a0f] border border-[#1a1c26] w-full max-w-5xl max-h-[88vh] flex flex-col overflow-hidden shadow-2xl">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-[#1a1c26] flex items-center justify-between bg-[#090a0f]">
          <div>
            <div className="flex items-center gap-3">
              <span className="text-white font-bold text-sm tracking-wider uppercase">
                60-RECORD CONTROL RUN
              </span>
              <span className="text-slate-600">/</span>
              <span className="text-slate-400 text-xs">TRACK 04 FORENSIC BATCH EVALUATION</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Observed batch outcomes across 60 synthetic payment scenarios. 0 timeouts · 0 unsupported resolutions.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white px-2.5 py-1 border border-[#262938] hover:border-slate-500 transition-colors"
          >
            ESC ✕
          </button>
        </div>

        {/* Quiet Minimalist Metrics Summary Bar */}
        <div className="px-6 py-3 border-b border-[#1a1c26] bg-[#0c0e14] flex flex-wrap items-center justify-between text-xs gap-4">
          <div className="flex items-center gap-6">
            <div>
              <span className="text-slate-400 text-[10px] uppercase block">DIRECT MATCH</span>
              <span className="text-emerald-400 font-bold">{BATCH_RUN_SUMMARY.directMatches}/60</span>{' '}
              <span className="text-slate-400 text-[11px]">({BATCH_RUN_SUMMARY.directMatchRate}%)</span>
            </div>
            <div className="border-l border-[#1a1c26] pl-6">
              <span className="text-slate-400 text-[10px] uppercase block">REMEDIATED</span>
              <span className="text-sky-400 font-bold">{BATCH_RUN_SUMMARY.autonomousResolved} refunds</span>{' '}
              <span className="text-slate-400 text-[11px]">(18.3%)</span>
            </div>
            <div className="border-l border-[#1a1c26] pl-6">
              <span className="text-slate-400 text-[10px] uppercase block">ESCALATED</span>
              <span className="text-amber-400 font-bold">{BATCH_RUN_SUMMARY.missingEvidenceEscalations + BATCH_RUN_SUMMARY.amountMismatchEscalations} cases</span>{' '}
              <span className="text-slate-400 text-[11px]">(15.0%)</span>
            </div>
            <div className="border-l border-[#1a1c26] pl-6">
              <span className="text-slate-400 text-[10px] uppercase block">TOTAL RESOLVED</span>
              <span className="text-white font-bold">{BATCH_RUN_SUMMARY.totalResolutionRate}%</span>{' '}
              <span className="text-slate-400 text-[11px]">(51/60)</span>
            </div>
          </div>

          <span className="text-slate-400 text-[10px] italic">
            "Observed outcome rates, not an ML accuracy score"
          </span>
        </div>

        {/* Filter & Search Bar */}
        <div className="px-6 py-2.5 border-b border-[#1a1c26] flex flex-wrap items-center justify-between gap-3 bg-[#090a0f]">
          <div className="flex items-center gap-2 text-xs">
            <button
              type="button"
              onClick={() => setFilter('ALL')}
              className={`px-2.5 py-0.5 border ${
                filter === 'ALL'
                  ? 'bg-sky-500/10 text-sky-300 border-sky-500/40 font-bold'
                  : 'text-slate-400 border-transparent hover:text-slate-200'
              }`}
            >
              All (60)
            </button>
            <button
              type="button"
              onClick={() => setFilter('MATCH')}
              className={`px-2.5 py-0.5 border ${
                filter === 'MATCH'
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/40 font-bold'
                  : 'text-slate-400 border-transparent hover:text-slate-200'
              }`}
            >
              Direct Match (40)
            </button>
            <button
              type="button"
              onClick={() => setFilter('REFUND')}
              className={`px-2.5 py-0.5 border ${
                filter === 'REFUND'
                  ? 'bg-sky-500/10 text-sky-300 border-sky-500/40 font-bold'
                  : 'text-slate-400 border-transparent hover:text-slate-200'
              }`}
            >
              Autonomous Refunds (11)
            </button>
            <button
              type="button"
              onClick={() => setFilter('ESCALATED')}
              className={`px-2.5 py-0.5 border ${
                filter === 'ESCALATED'
                  ? 'bg-amber-500/10 text-amber-300 border-amber-500/40 font-bold'
                  : 'text-slate-400 border-transparent hover:text-slate-200'
              }`}
            >
              Escalated (9)
            </button>
          </div>

          <div className="w-64">
            <input
              type="text"
              placeholder="Search payment ID, order, notes..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full bg-[#12141c] border border-[#262938] px-2.5 py-1 text-slate-200 text-xs focus:outline-none focus:border-sky-400"
            />
          </div>
        </div>

        {/* Forensic Records Table */}
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead className="bg-[#0c0e14] sticky top-0 border-b border-[#1a1c26] text-[10px] text-slate-400 uppercase tracking-wider">
              <tr>
                <th className="py-2.5 px-6">Record ID</th>
                <th className="py-2.5 px-3">Payment Reference</th>
                <th className="py-2.5 px-3">Scenario Type</th>
                <th className="py-2.5 px-3">Amount</th>
                <th className="py-2.5 px-3">Provider State</th>
                <th className="py-2.5 px-3">Outcome</th>
                <th className="py-2.5 px-6 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#14161f]">
              {filteredRecords.map(rec => {
                const isEscalated = rec.outcome === 'ESCALATED';
                const isRefund = rec.scenarioType === 'REFUND';

                return (
                  <tr
                    key={rec.recordId}
                    onClick={() => onSelectRecordForTrace(rec)}
                    className="hover:bg-[#12141c] transition-colors cursor-pointer group"
                  >
                    <td className="py-2.5 px-6 text-slate-400">{rec.recordId}</td>
                    <td className="py-2.5 px-3 text-slate-200 font-bold">{rec.paymentId}</td>
                    <td className="py-2.5 px-3 text-slate-400">{rec.scenarioType}</td>
                    <td className="py-2.5 px-3 text-slate-200">₹{rec.amount.toLocaleString()}</td>
                    <td className="py-2.5 px-3 text-slate-400">{rec.providerStatus}</td>
                    <td className="py-2.5 px-3">
                      <span className={isEscalated ? 'text-amber-400' : isRefund ? 'text-sky-400' : 'text-emerald-400'}>
                        {rec.outcome}
                      </span>
                    </td>
                    <td className="py-2.5 px-6 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectRecordForTrace(rec);
                        }}
                        className="text-[11px] text-slate-400 group-hover:text-sky-300 transition-colors"
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

        {/* Footer */}
        <div className="px-6 py-3 border-t border-[#1a1c26] flex items-center justify-between text-xs text-slate-400 bg-[#0c0e14]">
          <span>Select any exception to inspect its complete progressive investigation trace.</span>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1 bg-[#12141c] hover:bg-[#1c1f2e] text-slate-300 border border-[#262938] transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
