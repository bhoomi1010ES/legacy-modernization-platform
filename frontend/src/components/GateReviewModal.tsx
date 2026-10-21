import React, { useState } from 'react';
import type { GateDetail, DecisionOutcome } from '../types/domain';
import { ShieldCheck, X, AlertTriangle, FileText, CheckCircle2 } from 'lucide-react';

interface GateReviewModalProps {
  gate: GateDetail;
  onClose: () => void;
  onSubmit: (decision: DecisionOutcome, rationale: string, waivers?: any[]) => Promise<void>;
}

export const GateReviewModal: React.FC<GateReviewModalProps> = ({ gate, onClose, onSubmit }) => {
  const [rationale, setRationale] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Waiver checkbox for G4
  const [waiverAccepted, setWaiverAccepted] = useState(false);

  const handleDecision = async (decision: DecisionOutcome) => {
    if (!rationale.trim() || rationale.trim().length < 10) {
      setError('A comprehensive technical rationale of at least 10 characters is mandatory for audit compliance.');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const waivers = waiverAccepted && gate.gate_type === 'G4' ? [
        {
          test_id: 'test_timestamp_formatting_iso8601',
          difference_type: 'INTENDED_DIFFERENCE',
          waiver_rationale: rationale,
        }
      ] : undefined;

      await onSubmit(decision, rationale, waivers);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to submit decision.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-box" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--accent)',
                color: 'var(--primary)',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <ShieldCheck size={18} />
            </div>
            <div>
              <h2>Human Approval: Gate {gate.gate_type}</h2>
              <small style={{ color: 'var(--muted-foreground)' }}>
                {gate.job_name} ({gate.job_id}) · {gate.gate_id}
              </small>
            </div>
          </div>
          <button onClick={onClose} style={{ padding: '6px' }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ marginBottom: '20px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 650, marginBottom: '6px' }}>{gate.title}</h3>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
            {gate.description}
          </p>
        </div>

        {/* Artifact Evidence Card */}
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '12px 14px',
            backgroundColor: 'var(--secondary)',
            marginBottom: '20px',
            fontSize: '11px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <FileText size={14} color="var(--primary)" />
            <strong>Verified Artifact Evidence:</strong>
            <span>{gate.artifact}</span>
          </div>
          <div style={{ color: 'var(--muted-foreground)', fontFamily: 'var(--font-mono)' }}>
            SHA-256: {gate.artifact_hash}
          </div>
          <div style={{ marginTop: '6px', color: 'var(--muted-foreground)' }}>
            Cost Spend: <strong>{gate.cost_summary}</strong>
          </div>
        </div>

        {/* Gate-specific requirement guidance */}
        {gate.gate_type === 'G1' && (
          <div className="callout" style={{ padding: '12px 16px', marginBottom: '16px' }}>
            <AlertTriangle size={18} />
            <div className="grow">
              <strong>Feasibility & Capability Sign-Off</strong>
              <p>Verify that all detected legacy patterns have viable equivalents in TypeScript / Node.js 22 / NestJS.</p>
            </div>
          </div>
        )}

        {gate.gate_type === 'G4' && (
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', cursor: 'pointer', fontSize: '11px' }}>
              <input
                type="checkbox"
                checked={waiverAccepted}
                onChange={(e) => setWaiverAccepted(e.target.checked)}
                style={{ marginTop: '2px' }}
              />
              <span>
                <strong>Sign Intended Difference Waivers (4 approved differences):</strong> Confirm that behavioral changes (e.g. ISO-8601 formatting, empty array return) are acceptable and do not violate external API contracts.
              </span>
            </label>
          </div>
        )}

        {/* Mandatory Rationale */}
        <div className="form-field" style={{ marginBottom: '20px' }}>
          <label>Reviewer Decision Rationale (Mandatory for Audit Trail):</label>
          <textarea
            className="field"
            rows={4}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="Document technical review findings, architecture rationale, or reason for rejection..."
          />
          <small>Minimum 10 characters. Signed with your corporate identity Alex Morgan (Lead Architect).</small>
        </div>

        {error && (
          <div style={{ color: 'var(--destructive)', fontSize: '11px', marginBottom: '16px' }}>
            {error}
          </div>
        )}

        {/* Action Buttons */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button className="button button-secondary" onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button
            className="button button-danger"
            onClick={() => handleDecision('REJECTED')}
            disabled={loading}
          >
            Reject Gate
          </button>
          <button
            className="button button-primary"
            onClick={() => handleDecision('APPROVED')}
            disabled={loading}
          >
            <CheckCircle2 size={14} />
            {loading ? 'Submitting...' : 'Approve Gate & Continue'}
          </button>
        </div>
      </div>
    </div>
  );
};
