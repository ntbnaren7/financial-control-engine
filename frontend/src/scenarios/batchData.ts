import type { BatchRecord, BatchRunSummary } from '../types';

// Deterministic 60-record batch run mirroring scripts/batch_reconciliation.py
const generateBatchRecords = (): BatchRecord[] => {
  const records: BatchRecord[] = [];

  // 1. Direct Matches: 40 records (records 1 to 40)
  for (let i = 1; i <= 40; i++) {
    const pad = i.toString().padStart(3, '0');
    const amt = 1000 + (i * 150) % 8500;
    records.push({
      recordId: `rec_batch_${pad}`,
      paymentId: `pay_match_${pad}_${(i * 17) % 99}`,
      orderId: `ord_live_${pad}`,
      scenarioType: 'MATCH',
      amount: amt,
      expectedStatus: 'SETTLED',
      providerStatus: 'captured',
      outcome: 'MATCH',
      terminalState: 'MATCH',
      cyclesTaken: 1,
      remediated: false,
      notes: 'Direct match: internal expectation and Razorpay state both SETTLED.'
    });
  }

  // 2. Autonomous Resolutions: 11 records (records 41 to 51)
  const refundAmounts = [4500, 2800, 8900, 1250, 6400, 3200, 5100, 7800, 9400, 1800, 3600];
  for (let i = 41; i <= 51; i++) {
    const pad = i.toString().padStart(3, '0');
    const idx = i - 41;
    records.push({
      recordId: `rec_batch_${pad}`,
      paymentId: i === 41 ? 'pay_3819482701' : `pay_rfnd_${pad}_${(i * 23) % 99}`,
      orderId: i === 41 ? 'ord_5601928472' : `ord_canc_${pad}`,
      scenarioType: 'REFUND',
      amount: refundAmounts[idx],
      expectedStatus: 'SETTLED',
      providerStatus: 'captured',
      outcome: 'RESOLVED',
      terminalState: 'RESOLVED',
      cyclesTaken: 6,
      remediated: true,
      notes: 'Merchant cancelled; Razorpay captured. Autonomous refund executed & verified.'
    });
  }

  // 3. Evidence-Limited Escalations: 9 records (records 52 to 60)
  // 6 Missing (404), 3 Amount Mismatch
  const missingAmounts = [2100, 3400, 1500, 8200, 4300, 6700];
  for (let i = 52; i <= 57; i++) {
    const pad = i.toString().padStart(3, '0');
    const idx = i - 52;
    records.push({
      recordId: `rec_batch_${pad}`,
      paymentId: i === 52 ? 'pay_missing_404_99' : `pay_miss_${pad}`,
      orderId: i === 52 ? 'ord_missing_88210' : `ord_miss_${pad}`,
      scenarioType: 'MISSING',
      amount: missingAmounts[idx],
      expectedStatus: 'SETTLED',
      providerStatus: '404_NOT_FOUND',
      outcome: 'ESCALATED',
      terminalState: 'ESCALATED_MISSING_EVIDENCE',
      cyclesTaken: 3,
      remediated: false,
      notes: 'Provider returned 404. Honest escalation: required evidence not established.'
    });
  }

  const mismatchAmounts = [
    { exp: 5000, prov: 4500 },
    { exp: 12000, prov: 11000 },
    { exp: 8000, prov: 8500 }
  ];
  for (let i = 58; i <= 60; i++) {
    const pad = i.toString().padStart(3, '0');
    const idx = i - 58;
    records.push({
      recordId: `rec_batch_${pad}`,
      paymentId: `pay_amt_diff_${pad}`,
      orderId: `ord_diff_${pad}`,
      scenarioType: 'AMOUNT_MISMATCH',
      amount: mismatchAmounts[idx].exp,
      expectedStatus: 'SETTLED',
      providerStatus: `captured (₹${mismatchAmounts[idx].prov})`,
      outcome: 'ESCALATED',
      terminalState: 'ESCALATED_UNKNOWN',
      cyclesTaken: 3,
      remediated: false,
      notes: `Expected ₹${mismatchAmounts[idx].exp} but provider captured ₹${mismatchAmounts[idx].prov}. Escalated to finance ops.`
    });
  }

  return records;
};

export const BATCH_RECORDS = generateBatchRecords();

export const BATCH_RUN_SUMMARY: BatchRunSummary = {
  totalRecords: 60,
  directMatches: 40,
  autonomousResolved: 11,
  missingEvidenceEscalations: 6,
  amountMismatchEscalations: 3,
  directMatchRate: 66.7, // 40 / 60
  totalResolutionRate: 85.0, // (40 + 11) / 60 = 51 / 60 = 85.0%
  timeouts: 0,
  unsupportedResolutions: 0,
  records: BATCH_RECORDS
};
