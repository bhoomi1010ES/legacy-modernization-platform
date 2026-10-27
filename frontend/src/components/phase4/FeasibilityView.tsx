import React, { useState } from 'react';
import type {
  FeasibilityReport,
  FeasibilityCapability,
  ToolReadiness,
  G1DecisionType,
  G1DecisionRecord,
  EvidenceRef,
} from '../../types/phase4';
import { api } from '../../services/api';
import { EvidenceDrawer } from './EvidenceDrawer';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  Wrench,
  ShieldAlert,
  Send,
  ExternalLink,
  Filter,
} from 'lucide-react';

interface FeasibilityViewProps {
  jobId: string;
  feasibilityReport: FeasibilityReport | null;
  gapsRequiringG1?: FeasibilityCapability[];
  onDecisionSubmitted?: () => Promise<void>;
}

export const FeasibilityView: React.FC<FeasibilityViewProps> = ({
  jobId,
  feasibilityReport,
  gapsRequiringG1 = [],
  onDecisionSubmitted,
}) => {
  const [filterClass, setFilterClass] = useState<string>('ALL');
  const [selectedCapability, setSelectedCapability] = useState<FeasibilityCapability | null>(null);
  const [decisionModalOpen, setDecisionModalOpen] = useState(false);
  const [decisionType, setDecisionType] = useState<G1DecisionType>('ACCEPT_SUBSTITUTE');
  const [rationale, setRationale] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceRef | null>(null);

  if (!feasibilityReport) {
    return (
      <div style={{ padding: '32px', textAlign: 'center', color: 'var(--muted-foreground)' }}>
        <p>No feasibility assessment report available for this job yet.</p>
        <small>The Feasibility Agent evaluates compatibility between the LegacyModel and TargetBlueprint.</small>
      </div>
    );
  }

  const capabilities = feasibilityReport.capabilities || [];
  const toolReadiness = feasibilityReport.tool_readiness || [];

  const filteredCapabilities = capabilities.filter((c) => {
    if (filterClass === 'ALL') return true;
    return c.classification === filterClass;
  });

  const handleOpenDecision = (cap: FeasibilityCapability) => {
    setSelectedCapability(cap);
    setDecisionType(
      cap.classification === 'SUBSTITUTE'
        ? 'ACCEPT_SUBSTITUTE'
        : cap.classification === 'UNSUPPORTED'
        ? 'CUSTOM_BUILD'
        : 'ACCEPT_SUBSTITUTE'
    );
    setRationale(`Decision applied to resolve capability ${cap.capability_id} with recommendation: ${cap.recommendation}`);
    setStatusMessage(null);
    setDecisionModalOpen(true);
  };

  const handleOpenGlobalDecision = (type: G1DecisionType) => {
    setSelectedCapability(null);
    setDecisionType(type);
    setRationale(`Global G1 decision ${type} applied to Blueprint v${feasibilityReport.blueprint_version}`);
    setStatusMessage(null);
    setDecisionModalOpen(true);
  };

  const handleSubmitDecision = async () => {
    if (!rationale.trim() || rationale.trim().length < 10) {
      setStatusMessage({ type: 'error', text: 'Please provide a clear rationale (minimum 10 characters).' });
      return;
    }

    try {
      setSubmitting(true);
      setStatusMessage(null);

      const decisionRecord: G1DecisionRecord = {
        decision_id: `g1_${Date.now().toString(36)}`,
        job_id: jobId,
        capability_id: selectedCapability ? selectedCapability.capability_id : null,
        decision: decisionType,
        reason: rationale.trim(),
        actor: 'reviewer@platform.local',
        timestamp: new Date().toISOString(),
        previous_feasibility_version: feasibilityReport.version,
      };

      await api.submitFeasibilityDecisions(jobId, {
        decisions: [decisionRecord],
        global_decision: selectedCapability ? null : decisionType,
        global_rationale: selectedCapability ? null : rationale.trim(),
      });

      setStatusMessage({ type: 'success', text: `G1 decision ${decisionType} submitted successfully!` });
      setTimeout(() => {
        setDecisionModalOpen(false);
        if (onDecisionSubmitted) {
          onDecisionSubmitted();
        }
      }, 1200);
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to submit feasibility decision.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const getClassificationBadge = (classification: string) => {
    switch (classification) {
      case 'SUPPORTED':
        return <span className="badge green"><CheckCircle2 size={10} style={{ marginRight: 4 }} />SUPPORTED</span>;
      case 'SUBSTITUTE':
        return <span className="badge blue"><Wrench size={10} style={{ marginRight: 4 }} />SUBSTITUTE</span>;
      case 'CUSTOM_BUILD':
        return <span className="badge amber"><AlertTriangle size={10} style={{ marginRight: 4 }} />CUSTOM_BUILD</span>;
      case 'UNSUPPORTED':
        return <span className="badge red"><XCircle size={10} style={{ marginRight: 4 }} />UNSUPPORTED</span>;
      default:
        return <span className="badge purple"><HelpCircle size={10} style={{ marginRight: 4 }} />UNKNOWN</span>;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Feasibility Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '14px' }}>
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
          <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Overall Feasibility Score</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px', color: feasibilityReport.overall_feasibility_score >= 0.7 ? 'var(--success, #22c55e)' : 'var(--warning, #f59e0b)' }}>
            {(feasibilityReport.overall_feasibility_score * 100).toFixed(0)}%
          </div>
          <small style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}>
            Report v{feasibilityReport.version} (Blueprint v{feasibilityReport.blueprint_version})
          </small>
        </div>

        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
          <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Fully Supported</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px', color: 'var(--success, #22c55e)' }}>
            {capabilities.filter((c) => c.classification === 'SUPPORTED').length}
          </div>
          <small style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}>Direct target equivalent</small>
        </div>

        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
          <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Substitutions</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px', color: 'var(--primary, #3b82f6)' }}>
            {feasibilityReport.substitute_count}
          </div>
          <small style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}>Target stack alternative</small>
        </div>

        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
          <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Custom Build</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px', color: 'var(--warning, #f59e0b)' }}>
            {feasibilityReport.custom_build_count}
          </div>
          <small style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}>Requires custom adapter</small>
        </div>

        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
          <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Unsupported / Unknown</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px', color: 'var(--destructive, #ef4444)' }}>
            {feasibilityReport.unsupported_count + feasibilityReport.unknown_count}
          </div>
          <small style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}>Requires human decision</small>
        </div>
      </div>

      {/* Global G1 Action Bar */}
      <div
        style={{
          border: '1px solid var(--primary)',
          borderRadius: 'var(--radius-md)',
          padding: '16px 20px',
          backgroundColor: 'var(--secondary, #1e293b)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldAlert size={18} color="var(--primary)" />
            <strong style={{ fontSize: '13px' }}>Gate G1 Human Gap Decision Authority</strong>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
            Decide on feasibility gaps before planning. All decisions are immutably audited.
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            className="button button-primary"
            style={{ fontSize: '11px', padding: '6px 12px' }}
            onClick={() => handleOpenGlobalDecision('ACCEPT_SUBSTITUTE')}
          >
            Accept Substitutions
          </button>
          <button
            className="button button-secondary"
            style={{ fontSize: '11px', padding: '6px 12px' }}
            onClick={() => handleOpenGlobalDecision('ADD_TOOL')}
          >
            Add Tool
          </button>
          <button
            className="button button-secondary"
            style={{ fontSize: '11px', padding: '6px 12px' }}
            onClick={() => handleOpenGlobalDecision('CUSTOM_BUILD')}
          >
            Approve Custom Build
          </button>
          <button
            className="button button-secondary"
            style={{ fontSize: '11px', padding: '6px 12px' }}
            onClick={() => handleOpenGlobalDecision('REVISE_BLUEPRINT')}
          >
            Revise Blueprint
          </button>
          <button
            className="button button-secondary"
            style={{ fontSize: '11px', padding: '6px 12px', color: 'var(--destructive, #ef4444)' }}
            onClick={() => handleOpenGlobalDecision('REJECT')}
          >
            Reject Gate G1
          </button>
        </div>
      </div>

      {/* Tool Readiness Grid */}
      <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '20px', backgroundColor: 'var(--card)' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 650, marginBottom: '12px' }}>Platform Tool Readiness & Availability</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
          {toolReadiness.map((tr) => (
            <div
              key={tr.tool}
              style={{
                border: '1px solid var(--border)',
                borderRadius: '6px',
                padding: '12px',
                backgroundColor: 'var(--background)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong style={{ fontSize: '12px' }}>{tr.tool}</strong>
                <span className={`badge ${tr.readiness === 'READY' ? 'green' : 'amber'}`}>
                  {tr.readiness}
                </span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginTop: '4px' }}>
                Status: {tr.configuration_status} · Version: {tr.version || 'installed'}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Capabilities Table */}
      <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'var(--secondary)',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <strong style={{ fontSize: '13px' }}>Capability Assessment Matrix ({capabilities.length})</strong>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <Filter size={14} color="var(--muted-foreground)" />
            <select
              value={filterClass}
              onChange={(e) => setFilterClass(e.target.value)}
              style={{
                padding: '4px 8px',
                fontSize: '11px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border)',
                background: 'var(--background)',
                color: 'var(--foreground)',
              }}
            >
              <option value="ALL">All Classifications</option>
              <option value="SUPPORTED">Supported</option>
              <option value="SUBSTITUTE">Substitute</option>
              <option value="CUSTOM_BUILD">Custom Build</option>
              <option value="UNSUPPORTED">Unsupported</option>
              <option value="UNKNOWN">Unknown</option>
            </select>
          </div>
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--background)', textAlign: 'left' }}>
              <th style={{ padding: '10px 14px' }}>Category</th>
              <th style={{ padding: '10px 14px' }}>Legacy Requirement</th>
              <th style={{ padding: '10px 14px' }}>Target Requirement</th>
              <th style={{ padding: '10px 14px' }}>Classification</th>
              <th style={{ padding: '10px 14px' }}>Effort & Risk</th>
              <th style={{ padding: '10px 14px' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredCapabilities.map((cap) => (
              <tr key={cap.capability_id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '10px 14px' }}>
                  <span className="badge blue" style={{ fontSize: '9px' }}>{cap.category}</span>
                </td>
                <td style={{ padding: '10px 14px', maxWidth: '240px' }}>
                  <strong>{cap.legacy_requirement}</strong>
                </td>
                <td style={{ padding: '10px 14px', maxWidth: '260px' }}>
                  <span>{cap.target_requirement}</span>
                  <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
                    Rec: {cap.recommendation}
                  </div>
                </td>
                <td style={{ padding: '10px 14px' }}>
                  {getClassificationBadge(cap.classification)}
                  <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
                    Confidence: {(cap.confidence * 100).toFixed(0)}%
                  </div>
                </td>
                <td style={{ padding: '10px 14px' }}>
                  <div style={{ fontSize: '11px' }}>
                    Effort: <strong>{cap.effort}</strong>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
                    Risk: <strong>{cap.risk}</strong>
                  </div>
                </td>
                <td style={{ padding: '10px 14px' }}>
                  <button
                    className="button button-secondary"
                    style={{ fontSize: '11px', padding: '4px 8px' }}
                    onClick={() => handleOpenDecision(cap)}
                  >
                    <span>G1 Decide</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* G1 Decision Modal */}
      {decisionModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
          }}
          onClick={() => setDecisionModalOpen(false)}
        >
          <div
            style={{
              width: '540px',
              maxWidth: '90vw',
              backgroundColor: 'var(--card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldAlert size={20} color="var(--primary)" />
                <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>
                  {selectedCapability ? `G1 Decision: ${selectedCapability.capability_id}` : 'Global G1 Gate Decision'}
                </h3>
              </div>
              <button
                onClick={() => setDecisionModalOpen(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--muted-foreground)' }}
              >
                ✕
              </button>
            </div>

            {selectedCapability && (
              <div style={{ fontSize: '12px', background: 'var(--background)', padding: '12px', borderRadius: '6px' }}>
                <div><strong>Legacy:</strong> {selectedCapability.legacy_requirement}</div>
                <div><strong>Target:</strong> {selectedCapability.target_requirement}</div>
                <div style={{ marginTop: '4px', color: 'var(--muted-foreground)' }}>
                  Recommendation: {selectedCapability.recommendation}
                </div>
              </div>
            )}

            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                G1 Decision Outcome:
              </label>
              <select
                value={decisionType}
                onChange={(e) => setDecisionType(e.target.value as G1DecisionType)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border)',
                  background: 'var(--background)',
                  color: 'var(--foreground)',
                  fontSize: '13px',
                }}
              >
                <option value="ACCEPT_SUBSTITUTE">ACCEPT_SUBSTITUTE — Accept target library or idiom</option>
                <option value="ADD_TOOL">ADD_TOOL — Configure or provision required migration tool</option>
                <option value="CUSTOM_BUILD">CUSTOM_BUILD — Author bespoke bridge / adapter</option>
                <option value="DESCOPE">DESCOPE — Descope capability from target blueprint</option>
                <option value="REVISE_BLUEPRINT">REVISE_BLUEPRINT — Send blueprint back to Architect</option>
                <option value="REQUEST_MORE_ANALYSIS">REQUEST_MORE_ANALYSIS — Request deep scan rerun</option>
                <option value="CANCEL">CANCEL — Cancel modernization job progression</option>
                <option value="REJECT">REJECT — Reject Gate G1</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                Architectural Rationale & Audited Justification (Mandatory):
              </label>
              <textarea
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                placeholder="Detail technical grounds, constraints, or approval considerations..."
                rows={4}
                style={{
                  width: '100%',
                  padding: '10px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border)',
                  background: 'var(--background)',
                  color: 'var(--foreground)',
                  fontSize: '12px',
                  fontFamily: 'inherit',
                }}
              />
            </div>

            {statusMessage && (
              <div
                style={{
                  padding: '10px 14px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  backgroundColor: statusMessage.type === 'success' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                  color: statusMessage.type === 'success' ? 'var(--success)' : 'var(--destructive)',
                  border: `1px solid ${statusMessage.type === 'success' ? 'var(--success)' : 'var(--destructive)'}`,
                }}
              >
                {statusMessage.text}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                className="button button-secondary"
                onClick={() => setDecisionModalOpen(false)}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                className="button button-primary"
                onClick={handleSubmitDecision}
                disabled={submitting}
              >
                <Send size={14} />
                <span>{submitting ? 'Applying...' : 'Submit Decision'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Evidence Drawer */}
      <EvidenceDrawer evidence={selectedEvidence} onClose={() => setSelectedEvidence(null)} />
    </div>
  );
};
