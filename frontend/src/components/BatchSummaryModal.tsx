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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm select-none">
      <div className="bg-slate-900 border border-slate-700 w-full max-w-5xl max-h-[90vh] rounded-sm shadow-2xl flex flex-col overflow-hidden font-mono">
        {/* Modal Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold bg-sky-500/20 text-sky-400 border border-sky-500/40 px-2 py-0.5 rounded-xs uppercase">
                Track 04 • AI Finance Controller Proof
              </span>
              <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
                60-RECORD FINANCIAL CONTROL RUN
              </h2>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Demonstrating full closed-loop control across synthetic payment batches with honest exceptions and zero unsupported resolutions.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 p-1.5 rounded-sm hover:bg-slate-800 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* KPI Top Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 bg-slate-950/60 border-b border-slate-800 shrink-0">
          <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm">
            <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Direct Matches</div>
            <div className="text-xl font-bold text-emerald-400">
              {BATCH_RUN_SUMMARY.directMatches} <span className="text-xs font-normal text-slate-400">/ 60</span>
            </div>
            <div className="text-[10px] text-emerald-400/80 mt-0.5">
              {BATCH_RUN_SUMMARY.directMatchRate}% observed direct match
            </div>
          </div>

          <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm">
            <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Autonomous Resolutions</div>
            <div className="text-xl font-bold text-sky-400">
              {BATCH_RUN_SUMMARY.autonomousResolved} <span className="text-xs font-normal text-slate-400">refunds</span>
            </div>
            <div className="text-[10px] text-sky-400/80 mt-0.5">
              Closed without human intervention
            </div>
          </div>

          <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm">
            <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Honest Escalations</div>
            <div className="text-xl font-bold text-amber-400">
              {BATCH_RUN_SUMMARY.missingEvidenceEscalations + BATCH_RUN_SUMMARY.amountMismatchEscalations} <span className="text-xs font-normal text-slate-400">cases</span>
            </div>
            <div className="text-[10px] text-amber-400/80 mt-0.5">
              Missing evidence & amount mismatches
            </div>
          </div>

          <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-sm">
            <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Total Resolution Rate</div>
            <div className="text-xl font-bold text-emerald-400">
              {BATCH_RUN_SUMMARY.totalResolutionRate}%
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              0 timeouts • 0 unsupported
            </div>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="p-3 bg-slate-900 border-b border-slate-800 flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-1.5 text-xs">
            <button
              type="button"
              onClick={() => setFilter('ALL')}
              className={`px-2.5 py-1 rounded-xs border ${
                filter === 'ALL'
                  ? 'bg-sky-500/20 text-sky-300 border-sky-500/50 font-bold'
                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-300'
              }`}
            >
              All Records ({BATCH_RECORDS.length})
            </button>
            <button
              type="button"
              onClick={() => setFilter('MATCH')}
              className={`px-2.5 py-1 rounded-xs border ${
                filter === 'MATCH'
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 font-bold'
                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-300'
              }`}
            >
              Direct Match ({BATCH_RUN_SUMMARY.directMatches})
            </button>
            <button
              type="button"
              onClick={() => setFilter('REFUND')}
              className={`px-2.5 py-1 rounded-xs border ${
                filter === 'REFUND'
                  ? 'bg-sky-500/20 text-sky-300 border-sky-500/50 font-bold'
                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-300'
              }`}
            >
              Autonomous Refunds ({BATCH_RUN_SUMMARY.autonomousResolved})
            </button>
            <button
              type="button"
              onClick={() => setFilter('ESCALATED')}
              className={`px-2.5 py-1 rounded-xs border ${
                filter === 'ESCALATED'
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/50 font-bold'
                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-300'
              }`}
            >
              Escalated ({BATCH_RUN_SUMMARY.missingEvidenceEscalations + BATCH_RUN_SUMMARY.amountMismatchEscalations})
            </button>
          </div>

          <div className="w-64">
            <input
              type="text"
              placeholder="Search payment, order or note..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 px-2.5 py-1 text-xs text-slate-200 rounded-xs focus:outline-none focus:border-sky-500"
            />
          </div>
        </div>

        {/* Records Table */}
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead className="bg-slate-950/80 sticky top-0 border-b border-slate-800 text-[10px] text-slate-400 uppercase tracking-wider">
              <tr>
                <th className="p-2.5">Record ID</th>
                <th className="p-2.5">Payment Reference</th>
                <th className="p-2.5">Scenario Type</th>
                <th className="p-2.5">Amount</th>
                <th className="p-2.5">Provider Status</th>
                <th className="p-2.5">Outcome</th>
                <th className="p-2.5">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredRecords.map(rec => {
                let badgeStyle = 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
                if (rec.outcome === 'ESCALATED') {
                  badgeStyle = 'bg-amber-500/15 text-amber-400 border-amber-500/30';
                } else if (rec.scenarioType === 'REFUND') {
                  badgeStyle = 'bg-sky-500/15 text-sky-400 border-sky-500/30';
                }

                return (
                  <tr
                    key={rec.recordId}
                    className="hover:bg-slate-800/40 transition-colors group cursor-pointer"
                    onClick={() => onSelectRecordForTrace(rec)}
                  >
                    <td className="p-2.5 text-slate-400 font-semibold">{rec.recordId}</td>
                    <td className="p-2.5 text-slate-200 font-bold">{rec.paymentId}</td>
                    <td className="p-2.5 text-slate-300">
                      <span className="px-1.5 py-0.5 rounded-xs bg-slate-800 border border-slate-700 text-[10px]">
                        {rec.scenarioType}
                      </span>
                    </td>
                    <td className="p-2.5 text-slate-200">₹{rec.amount.toLocaleString()}</td>
                    <td className="p-2.5 text-slate-400">{rec.providerStatus}</td>
                    <td className="p-2.5">
                      <span className={`px-2 py-0.5 rounded-xs border text-[10px] font-bold ${badgeStyle}`}>
                        {rec.outcome}
                      </span>
                    </td>
                    <td className="p-2.5">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectRecordForTrace(rec);
                        }}
                        className="text-[10px] bg-sky-600/20 hover:bg-sky-600/40 text-sky-300 border border-sky-500/40 px-2 py-0.5 rounded-xs uppercase tracking-wider transition-colors"
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
        <div className="p-3 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>Click any transaction to load its complete control trace into the live engine.</span>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1 bg-slate-800 hover:bg-slate-750 text-slate-200 border border-slate-700 rounded-sm uppercase tracking-wider text-[11px]"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
