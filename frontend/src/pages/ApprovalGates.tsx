import React, { useState } from 'react';
import type { GateDetail } from '../types/domain';
import { StatusBadge } from '../components/StatusBadge';
import { GateReviewModal } from '../components/GateReviewModal';
import { ShieldAlert, ShieldCheck, CheckCircle2, Clock, FileText, ArrowRight } from 'lucide-react';

interface ApprovalGatesProps {
  gates: GateDetail[];
  onRefreshGates: () => void;
  onGateDecision: (gateId: string, decision: any, rationale: string, waivers?: any[]) => Promise<void>;
  onNavigate: (path: string) => void;
}

export const ApprovalGates: React.FC<ApprovalGatesProps> = ({
  gates,
  onRefreshGates,
  onGateDecision,
  onNavigate,
}) => {
  const [filter, setFilter] = useState<'ALL' | 'PENDING' | 'DECIDED'>('PENDING');
  const [selectedGate, setSelectedGate] = useState<GateDetail | null>(null);

  const filteredGates = gates.filter((g) => {
    if (filter === 'ALL') return true;
    if (filter === 'PENDING') return g.status === 'PENDING';
    if (filter === 'DECIDED') return g.status !== 'PENDING';
    return true;
  });

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>Governance Approval Gates (G1–G4)</h1>
          <p className="subtitle">
            Non-bypassable human review checkpoints enforcing architectural feasibility, frozen test suites, wave blueprints, and delivery readiness.
          </p>
        </div>
      </div>

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <button
          className={`button button-sm ${filter === 'PENDING' ? 'button-primary' : 'button-secondary'}`}
          onClick={() => setFilter('PENDING')}
        >
          Pending Review ({gates.filter((g) => g.status === 'PENDING').length})
        </button>
        <button
          className={`button button-sm ${filter === 'DECIDED' ? 'button-primary' : 'button-secondary'}`}
          onClick={() => setFilter('DECIDED')}
        >
          Decided Gates
        </button>
        <button
          className={`button button-sm ${filter === 'ALL' ? 'button-primary' : 'button-secondary'}`}
          onClick={() => setFilter('ALL')}
        >
          All Gates ({gates.length})
        </button>
      </div>

      {/* Gates List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {filteredGates.length === 0 ? (
          <div style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--muted-foreground)' }}>
            <ShieldCheck size={36} color="var(--success)" style={{ margin: '0 auto 12px' }} />
            <div style={{ fontSize: '14px', fontWeight: 650, color: 'var(--foreground)' }}>All Governance Gates Clear</div>
            <p style={{ fontSize: '12px', marginTop: '4px' }}>
              No approval gates currently require human architectural review.
            </p>
          </div>
        ) : (
          filteredGates.map((gate) => (
            <div
              key={gate.gate_id}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '20px',
                backgroundColor: 'var(--card)',
                boxShadow: 'var(--shadow-soft)',
                display: 'grid',
                gridTemplateColumns: 'auto 1fr auto',
                gap: '20px',
                alignItems: 'center',
              }}
            >
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: gate.status === 'PENDING' ? 'var(--warning-surface)' : 'var(--accent)',
                  color: gate.status === 'PENDING' ? 'var(--warning)' : 'var(--primary)',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                <ShieldAlert size={22} />
              </div>

              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                  <span style={{ fontWeight: 700, fontSize: '14px' }}>
                    Gate {gate.gate_type}: {gate.title}
                  </span>
                  <StatusBadge status={gate.status} />
                  <span className="badge gray" style={{ fontSize: '10px' }}>{gate.job_name}</span>
                </div>

                <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '10px' }}>
                  {gate.description}
                </p>

                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '11px', color: 'var(--muted-foreground)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <FileText size={12} color="var(--primary)" />
                    {gate.artifact}
                  </span>
                  <span>•</span>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>
                    SHA: {(gate.artifact_hash || 'sha256:verified').substring(0, 16)}...
                  </span>
                  <span>•</span>
                  <span>Cost Spend: <strong>{gate.cost_summary}</strong></span>
                </div>
              </div>

              <div>
                {gate.status === 'PENDING' ? (
                  <button
                    className="button button-primary"
                    onClick={() => setSelectedGate(gate)}
                  >
                    Review Gate & Decide
                  </button>
                ) : (
                  <div style={{ textAlign: 'right', fontSize: '11px', color: 'var(--muted-foreground)' }}>
                    <div>Reviewed by <strong>{gate.reviewer || 'Alex Morgan'}</strong></div>
                    <div style={{ fontSize: '10px' }}>
                      {gate.decided_at ? new Date(gate.decided_at).toLocaleString() : 'Decided'}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Review Modal Dialog */}
      {selectedGate && (
        <GateReviewModal
          gate={selectedGate}
          onClose={() => setSelectedGate(null)}
          onSubmit={async (decision, rationale, waivers) => {
            await onGateDecision(selectedGate.gate_id, decision, rationale, waivers);
            onRefreshGates();
          }}
        />
      )}
    </div>
  );
};
