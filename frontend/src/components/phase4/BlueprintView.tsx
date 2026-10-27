import React, { useState } from 'react';
import type { TargetBlueprint } from '../../types/phase4';
import {
  Layers,
  FileCode,
  Database,
  Lock,
  ShieldCheck,
  Cpu,
  Share2,
  CheckCircle,
} from 'lucide-react';

interface BlueprintViewProps {
  blueprint: TargetBlueprint | null;
}

export const BlueprintView: React.FC<BlueprintViewProps> = ({ blueprint }) => {
  const [activeTab, setActiveTab] = useState<'components' | 'interfaces' | 'data' | 'constraints'>('components');

  if (!blueprint) {
    return (
      <div style={{ padding: '32px', textAlign: 'center', color: 'var(--muted-foreground)' }}>
        <p>No Target Blueprint generated yet for this job.</p>
        <small>The Architect agent produces the TargetBlueprint based on the LegacyModel and target stack profile.</small>
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'APPROVED':
      case 'LOCKED':
        return <span className="badge green"><Lock size={10} style={{ marginRight: 4 }} />{status}</span>;
      case 'G1_PENDING':
        return <span className="badge amber"><ShieldCheck size={10} style={{ marginRight: 4 }} />G1 PENDING</span>;
      default:
        return <span className="badge blue">{status}</span>;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Blueprint Header */}
      <div
        style={{
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '20px',
          backgroundColor: 'var(--card)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Layers size={20} color="var(--primary)" />
              <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>
                Target Blueprint v{blueprint.version}
              </h3>
              {getStatusBadge(blueprint.status)}
            </div>
            <code style={{ fontSize: '11px', color: 'var(--muted-foreground)', display: 'block', marginTop: '4px' }}>
              ID: {blueprint.blueprint_id} · SHA-256: {blueprint.content_hash.substring(0, 16)}...
            </code>
          </div>

          <div style={{ textAlign: 'right', fontSize: '11px', color: 'var(--muted-foreground)' }}>
            <div>Authored by: <strong>{blueprint.created_by}</strong></div>
            <div>Generated: {new Date(blueprint.created_at).toLocaleString()}</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', fontSize: '12px', borderTop: '1px solid var(--border)', paddingTop: '12px' }}>
          <div>
            <span style={{ color: 'var(--muted-foreground)' }}>Target Stack Specification:</span>
            <div style={{ fontWeight: 600, color: 'var(--primary)', marginTop: '2px' }}>{blueprint.target_stack}</div>
          </div>
          <div>
            <span style={{ color: 'var(--muted-foreground)' }}>Architectural Style:</span>
            <div style={{ fontWeight: 600, marginTop: '2px' }}>{blueprint.target_architecture}</div>
          </div>
        </div>
      </div>

      {/* Blueprint Tabs */}
      <div className="tabs" style={{ marginBottom: 0 }}>
        <button
          className={`tab ${activeTab === 'components' ? 'active' : ''}`}
          onClick={() => setActiveTab('components')}
        >
          Target Components ({blueprint.components.length})
        </button>
        <button
          className={`tab ${activeTab === 'interfaces' ? 'active' : ''}`}
          onClick={() => setActiveTab('interfaces')}
        >
          Interface Contracts ({blueprint.interfaces.length})
        </button>
        <button
          className={`tab ${activeTab === 'data' ? 'active' : ''}`}
          onClick={() => setActiveTab('data')}
        >
          Data Models ({blueprint.data_model.length})
        </button>
        <button
          className={`tab ${activeTab === 'constraints' ? 'active' : ''}`}
          onClick={() => setActiveTab('constraints')}
        >
          Constraints & Policies
        </button>
      </div>

      {/* View 1: Components */}
      {activeTab === 'components' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '14px' }}>
          {blueprint.components.map((comp) => (
            <div
              key={comp.component_id}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '16px',
                backgroundColor: 'var(--card)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <strong style={{ fontSize: '13px' }}>{comp.name}</strong>
                <span className="badge blue" style={{ fontSize: '10px' }}>{comp.component_id}</span>
              </div>
              <code style={{ fontSize: '11px', color: 'var(--muted-foreground)', display: 'block', marginBottom: '10px' }}>
                {comp.target_path}
              </code>

              <div style={{ fontSize: '11px', marginBottom: '10px' }}>
                <span style={{ color: 'var(--muted-foreground)' }}>Mapped Legacy Modules: </span>
                <span>{comp.mapped_legacy_modules.join(', ') || 'Direct addition'}</span>
              </div>

              <div style={{ fontSize: '11px', marginBottom: '8px' }}>
                <span style={{ color: 'var(--muted-foreground)' }}>Technologies: </span>
                <span style={{ fontWeight: 600 }}>{comp.technologies.join(', ')}</span>
              </div>

              <div style={{ fontSize: '11px', borderTop: '1px solid var(--border)', paddingTop: '8px', marginTop: '8px' }}>
                <span style={{ color: 'var(--muted-foreground)' }}>Dependencies: </span>
                <span>{comp.dependencies.length > 0 ? comp.dependencies.join(', ') : 'None (Base)'}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* View 2: Interfaces */}
      {activeTab === 'interfaces' && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--secondary)', textAlign: 'left' }}>
                <th style={{ padding: '10px 14px' }}>Interface Name</th>
                <th style={{ padding: '10px 14px' }}>Type</th>
                <th style={{ padding: '10px 14px' }}>Owner Component</th>
                <th style={{ padding: '10px 14px' }}>Preserved Legacy Interface</th>
              </tr>
            </thead>
            <tbody>
              {blueprint.interfaces.map((iface) => (
                <tr key={iface.contract_id} style={{ borderTop: '1px solid var(--border)' }}>
                  <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)' }}>
                    <strong>{iface.name}</strong>
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    <span className="badge purple" style={{ fontSize: '9px' }}>{iface.interface_type}</span>
                  </td>
                  <td style={{ padding: '10px 14px' }}>{iface.component_id}</td>
                  <td style={{ padding: '10px 14px' }}>
                    {iface.preserved_legacy_interface_id ? (
                      <span className="badge green" style={{ fontSize: '10px' }}>
                        Preserved ({iface.preserved_legacy_interface_id})
                      </span>
                    ) : (
                      <span style={{ color: 'var(--muted-foreground)' }}>Target native</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* View 3: Data Models */}
      {activeTab === 'data' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '14px' }}>
          {blueprint.data_model.map((dm) => (
            <div
              key={dm.model_id}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '16px',
                backgroundColor: 'var(--card)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Database size={16} color="var(--primary)" />
                  <strong style={{ fontSize: '13px' }}>{dm.name}</strong>
                </div>
                <span className="badge blue">{dm.target_engine}</span>
              </div>

              <div style={{ fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '10px' }}>
                <div><span style={{ color: 'var(--muted-foreground)' }}>ORM Strategy: </span><strong>{dm.orm_strategy}</strong></div>
                <div><span style={{ color: 'var(--muted-foreground)' }}>Migration: </span><span>{dm.migration_strategy}</span></div>
                <div><span style={{ color: 'var(--muted-foreground)' }}>Mapped Entities: </span><span>{dm.mapped_legacy_entities.join(', ') || 'N/A'}</span></div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* View 4: Constraints */}
      {activeTab === 'constraints' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px' }}>
          <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
            <strong style={{ fontSize: '13px', display: 'block', marginBottom: '8px' }}>Deployment Constraints</strong>
            <ul style={{ fontSize: '11px', paddingLeft: '16px', margin: 0, lineHeight: 1.6 }}>
              {blueprint.deployment_constraints.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>

          <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
            <strong style={{ fontSize: '13px', display: 'block', marginBottom: '8px' }}>Security Constraints</strong>
            <ul style={{ fontSize: '11px', paddingLeft: '16px', margin: 0, lineHeight: 1.6 }}>
              {blueprint.security_constraints.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>

          <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
            <strong style={{ fontSize: '13px', display: 'block', marginBottom: '8px' }}>Migration & Compatibility</strong>
            <ul style={{ fontSize: '11px', paddingLeft: '16px', margin: 0, lineHeight: 1.6 }}>
              {blueprint.migration_constraints.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};
