const API_BASE_URL = 'http://localhost:8000';

export interface IncidentSummary {
  active: number;
  resolved: number;
  escalated: number;
  total: number;
  by_state: Record<string, number>;
}

export interface IncidentItem {
  incident_id: string;
  state: string;
  discrepancy_reason: string;
  created_at: string;
  updated_at: string;
  is_terminal: boolean;
  is_escalated: boolean;
}

export interface PaginatedIncidents {
  total: number;
  offset: number;
  limit: number;
  items: IncidentItem[];
}

export interface AuditTrace {
  incident_id: string;
  discrepancy_reason: string;
  current_state: string;
  is_terminal: boolean;
  created_at: string;
  retry_count: number;
  hypothesis_available: boolean;
  timeline: Array<{
    step: string;
    at: string;
    detail: string;
  }>;
  recovery_intent: Record<string, unknown> | null;
  actuation: Record<string, unknown> | null;
  evidence_count: number;
  operator_actions: Array<Record<string, unknown>>;
  discrepancy: Record<string, unknown> | null;
}

export const api = {
  getSummary: async (): Promise<IncidentSummary> => {
    const res = await fetch(`${API_BASE_URL}/incidents/summary`);
    if (!res.ok) throw new Error('Failed to fetch summary');
    return res.json();
  },

  getIncidents: async (state?: string, limit = 50, offset = 0): Promise<PaginatedIncidents> => {
    const params = new URLSearchParams({ limit: limit.toString(), offset: offset.toString() });
    if (state) params.append('state', state);
    
    const res = await fetch(`${API_BASE_URL}/incidents?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch incidents');
    return res.json();
  },

  getIncident: async (incidentId: string): Promise<Record<string, unknown>> => {
    const res = await fetch(`${API_BASE_URL}/incidents/${incidentId}`);
    if (!res.ok) throw new Error('Failed to fetch incident');
    return res.json();
  },

  getIncidentAudit: async (incidentId: string): Promise<AuditTrace> => {
    const res = await fetch(`${API_BASE_URL}/incidents/${incidentId}/audit`);
    if (!res.ok) throw new Error('Failed to fetch incident audit');
    return res.json();
  },

  triggerWebhook: async (payload: Record<string, unknown>): Promise<Record<string, unknown>> => {
    const res = await fetch(`${API_BASE_URL}/webhooks/razorpay`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-razorpay-signature': 'test-signature'
      },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Failed to trigger webhook');
    return res.json();
  },

  operatorAction: async (incidentId: string, action: 'retry' | 'resolve' | 'escalate', reason: string): Promise<Record<string, unknown>> => {
    const res = await fetch(`${API_BASE_URL}/incidents/${incidentId}/${action}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ reason, operator_id: 'operator' })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to ${action} incident`);
    }
    return res.json();
  }
};
