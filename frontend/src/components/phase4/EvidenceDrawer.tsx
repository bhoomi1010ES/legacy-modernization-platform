import React from 'react';
import type { EvidenceRef } from '../../types/phase4';
import { X, ShieldCheck, FileCode, Hash, Terminal } from 'lucide-react';

interface EvidenceDrawerProps {
  evidence: EvidenceRef | null;
  onClose: () => void;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({ evidence, onClose }) => {
  if (!evidence) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        justifyContent: 'flex-end',
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '560px',
          maxWidth: '90vw',
          height: '100%',
          backgroundColor: 'var(--card, #1e293b)',
          borderLeft: '1px solid var(--border, #334155)',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          overflowY: 'auto',
          boxShadow: '-4px 0 24px rgba(0,0,0,0.3)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldCheck size={20} color="var(--primary, #3b82f6)" />
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>Verified Evidence Record</h2>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--muted-foreground, #94a3b8)',
            }}
          >
            <X size={20} />
          </button>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <span className="badge blue">{evidence.evidence_type}</span>
          <span className={`badge ${evidence.confidence === 'CONFIRMED' ? 'green' : 'amber'}`}>
            {evidence.confidence}
          </span>
          <span className="badge purple">v{evidence.artifact_version}</span>
        </div>

        <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div>
            <span style={{ color: 'var(--muted-foreground)', display: 'block', marginBottom: '4px' }}>
              Evidence ID
            </span>
            <code style={{ fontFamily: 'var(--font-mono)', padding: '2px 6px', background: 'var(--secondary)', borderRadius: '4px' }}>
              {evidence.evidence_id}
            </code>
          </div>

          <div>
            <span style={{ color: 'var(--muted-foreground)', display: 'block', marginBottom: '4px' }}>
              Source File & Location
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
              <FileCode size={14} />
              <span>{evidence.source_path}</span>
              {evidence.source_location && (
                <span style={{ color: 'var(--primary)' }}>({evidence.source_location})</span>
              )}
            </div>
          </div>

          <div>
            <span style={{ color: 'var(--muted-foreground)', display: 'block', marginBottom: '4px' }}>
              Source Artifact / Snapshot
            </span>
            <code style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
              {evidence.source_artifact}
            </code>
          </div>

          {evidence.content_hash && (
            <div>
              <span style={{ color: 'var(--muted-foreground)', display: 'block', marginBottom: '4px' }}>
                Content Hash (SHA-256)
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Hash size={14} />
                <code style={{ fontFamily: 'var(--font-mono)', fontSize: '10px' }}>
                  {evidence.content_hash}
                </code>
              </div>
            </div>
          )}

          <div>
            <span style={{ color: 'var(--muted-foreground)', display: 'block', marginBottom: '4px' }}>
              Capturing Agent & Model
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Terminal size={14} />
              <span>{evidence.agent_name} ({evidence.model_version || 'standard'})</span>
            </div>
          </div>

          {evidence.evidence_excerpt && (
            <div style={{ marginTop: '8px' }}>
              <span style={{ color: 'var(--muted-foreground)', display: 'block', marginBottom: '6px' }}>
                Sanitized Code / Config Excerpt
              </span>
              <pre
                style={{
                  background: 'var(--background, #0f172a)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  padding: '12px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  whiteSpace: 'pre-wrap',
                  overflowX: 'auto',
                  maxHeight: '220px',
                }}
              >
                {evidence.evidence_excerpt}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
