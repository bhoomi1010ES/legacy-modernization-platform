import React, { useMemo, useState } from 'react';
import type { GateDetail } from '../types/domain';
import { StatusBadge } from '../components/StatusBadge';
import { GateReviewModal } from '../components/GateReviewModal';
import {
  ArrowRight, CheckCircle2, Clock3, FileCheck2, FileText,
  Fingerprint, History, RefreshCw, ShieldAlert, ShieldCheck, UserRoundCheck,
} from 'lucide-react';

interface ApprovalGatesProps {
  gates: GateDetail[];
  onRefreshGates: () => Promise<void> | void;
  onGateDecision: (gateId: string, decision: any, rationale: string, waivers?: any[], options?: Record<string, string>) => Promise<void>;
  onNavigate: (path: string) => void;
}

type Filter = 'ALL' | 'PENDING' | 'APPROVED' | 'CHANGES';

const hashPreview = (gate: GateDetail) => gate.artifact_hash || Object.values(gate.artifact_hashes || {})[0] || 'No artifact hash';

export const ApprovalGates: React.FC<ApprovalGatesProps> = ({ gates, onRefreshGates, onGateDecision, onNavigate }) => {
  const [filter, setFilter] = useState<Filter>('PENDING');
  const [selectedGate, setSelectedGate] = useState<GateDetail | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const counts = {
    PENDING: gates.filter((gate) => gate.status === 'PENDING').length,
    APPROVED: gates.filter((gate) => gate.status === 'APPROVED').length,
    CHANGES: gates.filter((gate) => ['REJECTED', 'NEEDS_CHANGES', 'INVALIDATED', 'TIMED_OUT'].includes(gate.status)).length,
  };
  const filtered = useMemo(() => gates.filter((gate) => {
    if (filter === 'ALL') return true;
    if (filter === 'CHANGES') return ['REJECTED', 'NEEDS_CHANGES', 'INVALIDATED', 'TIMED_OUT'].includes(gate.status);
    return gate.status === filter;
  }), [filter, gates]);

  const refresh = async () => {
    setRefreshing(true);
    try { await onRefreshGates(); } finally { setRefreshing(false); }
  };

  return <div>
    <div className="page-heading">
      <div><div className="eyebrow"><ShieldCheck size={13} /> Phase 3 · human governance</div><h1>Gate decision inbox</h1><p className="subtitle">Review version-bound evidence for G1–G4. Every decision is attributable, immutable, and tied to artifact hashes.</p></div>
      <button className="button button-secondary" onClick={() => void refresh()} disabled={refreshing}><RefreshCw size={14} className={refreshing ? 'spin' : ''} /> Refresh</button>
    </div>

    <div className="gate-metrics">
      <div><Clock3 size={17} /><span>Pending review</span><strong>{counts.PENDING}</strong></div>
      <div><CheckCircle2 size={17} /><span>Approved</span><strong>{counts.APPROVED}</strong></div>
      <div><History size={17} /><span>Needs attention</span><strong>{counts.CHANGES}</strong></div>
      <div><FileCheck2 size={17} /><span>Total decisions</span><strong>{gates.length}</strong></div>
    </div>

    <div className="gate-filterbar">
      {(['PENDING', 'APPROVED', 'CHANGES', 'ALL'] as Filter[]).map((value) => <button key={value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{value === 'CHANGES' ? 'Needs attention' : value[0] + value.slice(1).toLowerCase()} <span>{value === 'ALL' ? gates.length : counts[value as keyof typeof counts]}</span></button>)}
    </div>

    {!filtered.length ? <div className="empty-state"><ShieldCheck size={36} /><h3>{filter === 'PENDING' ? 'No gates are waiting' : 'No gates match this view'}</h3><p>Gate decisions and artifact revisions will appear here as the workflow advances.</p></div>
      : <div className="gate-inbox">{filtered.map((gate) => {
        const canReview = gate.status === 'PENDING' && (gate.allowed_actions === undefined || gate.allowed_actions.some((action) => ['approve', 'reject', 'request_changes'].includes(action)));
        return <article key={gate.gate_id} className={`gate-card gate-${gate.status.toLowerCase()}`}>
          <div className="gate-card-icon"><ShieldAlert size={21} /></div>
          <div className="gate-card-body">
            <div className="gate-card-title"><div><span className="gate-code">{gate.gate_type}</span><h2>{gate.title}</h2><StatusBadge status={gate.status} /></div><button className="job-link" onClick={() => onNavigate(`/jobs/${gate.job_id}`)}>{gate.job_name}<ArrowRight size={12} /></button></div>
            <p>{gate.description}</p>
            <div className="gate-evidence-grid">
              <div><FileText size={13} /><span><small>Evidence package</small><strong>{gate.artifact}</strong></span></div>
              <div><Fingerprint size={13} /><span><small>Artifact binding</small><code>{hashPreview(gate).slice(0, 24)}{hashPreview(gate).length > 24 ? '…' : ''}</code></span></div>
              <div><History size={13} /><span><small>Version</small><strong>v{gate.version || 1}</strong></span></div>
              <div><Clock3 size={13} /><span><small>{gate.decided_at ? 'Decided' : 'Requested'}</small><strong>{new Date(gate.decided_at || gate.requested_at).toLocaleString()}</strong></span></div>
            </div>
            {gate.rationale && <div className="gate-rationale"><strong>Reviewer rationale</strong><p>{gate.rationale}</p></div>}
          </div>
          <div className="gate-card-actions">
            {canReview ? (
              <button className="button button-primary" onClick={() => setSelectedGate(gate)}>
                Review evidence
              </button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'flex-end' }}>
                <div className="reviewer-stamp">
                  <UserRoundCheck size={16} />
                  <div>
                    <small>Reviewed by</small>
                    <strong>{gate.reviewer || 'Recorded reviewer'}</strong>
                  </div>
                </div>
                <button
                  className="button button-secondary"
                  style={{ fontSize: '11px', height: '26px', padding: '3px 8px' }}
                  onClick={() => setSelectedGate(gate)}
                >
                  View Assessment
                </button>
              </div>
            )}
            <small>{gate.cost_summary}</small>
          </div>
        </article>;
      })}</div>}

    {selectedGate && <GateReviewModal gate={selectedGate} onClose={() => setSelectedGate(null)} onSubmit={async (decision, rationale, waivers, options) => { await onGateDecision(selectedGate.gate_id, decision, rationale, waivers, options); setSelectedGate(null); await refresh(); }} />}
  </div>;
};
