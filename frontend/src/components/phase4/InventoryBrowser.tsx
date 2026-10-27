import React, { useState } from 'react';
import type { RepositorySnapshot, RepositoryInventory, LegacyModel, LegacyModule, EvidenceRef } from '../../types/phase4';
import { EvidenceDrawer } from './EvidenceDrawer';
import {
  FolderTree,
  FileCode,
  Layers,
  Search,
  ExternalLink,
  ShieldAlert,
  CheckCircle2,
  Cpu,
  Package,
  FileText,
  Boxes,
} from 'lucide-react';

interface InventoryBrowserProps {
  snapshot: RepositorySnapshot | null;
  inventory: RepositoryInventory | null;
  legacyModel: LegacyModel | null;
}

export const InventoryBrowser: React.FC<InventoryBrowserProps> = ({
  snapshot,
  inventory,
  legacyModel,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'files' | 'modules'>('files');
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'ALL' | 'MANIFEST' | 'CONFIG' | 'TEST' | 'DOC'>('ALL');
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceRef | null>(null);

  if (!snapshot || !inventory) {
    return (
      <div style={{ padding: '32px', textAlign: 'center', color: 'var(--muted-foreground)' }}>
        <p>No repository inventory data available for this job yet.</p>
        <small>Execute intake or wait for repository snapshot ingestion to complete.</small>
      </div>
    );
  }

  const files = inventory.files || [];
  const filteredFiles = files.filter((f) => {
    const matchesSearch = f.path.toLowerCase().includes(searchQuery.toLowerCase());
    if (!matchesSearch) return false;
    if (typeFilter === 'MANIFEST') return f.is_manifest;
    if (typeFilter === 'CONFIG') return f.is_config;
    if (typeFilter === 'TEST') return f.is_test;
    if (typeFilter === 'DOC') return f.is_documentation;
    return true;
  });

  const modules = legacyModel?.modules || [];
  const filteredModules = modules.filter(
    (m) =>
      m.module_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.path.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.responsibility.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleShowEvidence = (evidenceId: string) => {
    if (legacyModel?.evidence_index && legacyModel.evidence_index[evidenceId]) {
      setSelectedEvidence(legacyModel.evidence_index[evidenceId]);
    } else {
      // Fallback synthetic evidence for drill-down
      setSelectedEvidence({
        evidence_id: evidenceId,
        source_artifact: snapshot.snapshot_id,
        source_path: snapshot.metadata.source_ref,
        evidence_type: 'FILE_PATH',
        confidence: 'CONFIRMED',
        agent_name: 'intake_agent',
        artifact_version: 1,
        observed_at: new Date().toISOString(),
      });
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Technology Profile Card */}
      <div
        style={{
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '20px',
          backgroundColor: 'var(--card)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Cpu size={20} color="var(--primary)" />
            <h3 style={{ fontSize: '15px', fontWeight: 650, margin: 0 }}>
              Detected Technology Profile & Ingestion Metadata
            </h3>
          </div>
          <span className="badge green">Deterministic Hash: {inventory.inventory_hash.substring(0, 12)}...</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', fontSize: '12px' }}>
          <div>
            <span style={{ color: 'var(--muted-foreground)' }}>Primary Language</span>
            <div style={{ fontWeight: 650, marginTop: '4px', fontSize: '14px' }}>
              {snapshot.tech_profile.primary_language || 'N/A'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
              Confidence: {(snapshot.tech_profile.confidence * 100).toFixed(0)}%
            </div>
          </div>
          <div>
            <span style={{ color: 'var(--muted-foreground)' }}>Frameworks Detected</span>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '4px' }}>
              {snapshot.tech_profile.frameworks.length > 0 ? (
                snapshot.tech_profile.frameworks.map((fw) => (
                  <span key={fw} className="badge blue" style={{ fontSize: '10px' }}>
                    {fw}
                  </span>
                ))
              ) : (
                <span style={{ color: 'var(--muted-foreground)' }}>None</span>
              )}
            </div>
          </div>
          <div>
            <span style={{ color: 'var(--muted-foreground)' }}>Build Systems & Tools</span>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '4px' }}>
              {snapshot.tech_profile.build_systems.length > 0 ? (
                snapshot.tech_profile.build_systems.map((bs) => (
                  <span key={bs} className="badge purple" style={{ fontSize: '10px' }}>
                    {bs}
                  </span>
                ))
              ) : (
                <span style={{ color: 'var(--muted-foreground)' }}>Standard</span>
              )}
            </div>
          </div>
          <div>
            <span style={{ color: 'var(--muted-foreground)' }}>Total Files & Size</span>
            <div style={{ fontWeight: 650, marginTop: '4px', fontSize: '14px' }}>
              {inventory.total_files} files
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
              {(inventory.total_bytes / 1024).toFixed(1)} KB inventory
            </div>
          </div>
        </div>
      </div>

      {/* Sub-Tab Navigation & Search Filter */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className={`button ${activeSubTab === 'files' ? 'button-primary' : 'button-secondary'}`}
            onClick={() => setActiveSubTab('files')}
            style={{ fontSize: '12px', padding: '6px 12px' }}
          >
            <FolderTree size={14} />
            <span>Repository Files ({inventory.total_files})</span>
          </button>
          <button
            className={`button ${activeSubTab === 'modules' ? 'button-primary' : 'button-secondary'}`}
            onClick={() => setActiveSubTab('modules')}
            style={{ fontSize: '12px', padding: '6px 12px' }}
          >
            <Boxes size={14} />
            <span>Discovered Modules ({modules.length})</span>
          </button>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div style={{ position: 'relative' }}>
            <Search
              size={14}
              style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--muted-foreground)' }}
            />
            <input
              type="text"
              placeholder={activeSubTab === 'files' ? 'Filter files...' : 'Filter modules...'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                padding: '6px 10px 6px 30px',
                fontSize: '12px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border)',
                background: 'var(--background)',
                color: 'var(--foreground)',
                width: '220px',
              }}
            />
          </div>

          {activeSubTab === 'files' && (
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as any)}
              style={{
                padding: '6px 10px',
                fontSize: '12px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border)',
                background: 'var(--background)',
                color: 'var(--foreground)',
              }}
            >
              <option value="ALL">All File Types</option>
              <option value="MANIFEST">Manifests Only</option>
              <option value="CONFIG">Configs Only</option>
              <option value="TEST">Tests Only</option>
              <option value="DOC">Docs Only</option>
            </select>
          )}
        </div>
      </div>

      {/* View 1: Files Table */}
      {activeSubTab === 'files' && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--secondary)', textAlign: 'left' }}>
                <th style={{ padding: '10px 14px' }}>Path</th>
                <th style={{ padding: '10px 14px' }}>Category</th>
                <th style={{ padding: '10px 14px' }}>Language</th>
                <th style={{ padding: '10px 14px' }}>Size</th>
                <th style={{ padding: '10px 14px' }}>SHA-256 Hash</th>
              </tr>
            </thead>
            <tbody>
              {filteredFiles.length > 0 ? (
                filteredFiles.map((file) => (
                  <tr key={file.path} style={{ borderTop: '1px solid var(--border)' }}>
                    <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <FileCode size={14} color="var(--primary)" />
                        <span>{file.path}</span>
                      </div>
                    </td>
                    <td style={{ padding: '8px 14px' }}>
                      <div style={{ display: 'flex', gap: '4px' }}>
                        {file.is_manifest && <span className="badge blue" style={{ fontSize: '9px' }}>MANIFEST</span>}
                        {file.is_config && <span className="badge amber" style={{ fontSize: '9px' }}>CONFIG</span>}
                        {file.is_test && <span className="badge green" style={{ fontSize: '9px' }}>TEST</span>}
                        {file.is_documentation && <span className="badge purple" style={{ fontSize: '9px' }}>DOC</span>}
                        {!file.is_manifest && !file.is_config && !file.is_test && !file.is_documentation && (
                          <span style={{ color: 'var(--muted-foreground)', fontSize: '11px' }}>Source</span>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '8px 14px' }}>{file.language || '—'}</td>
                    <td style={{ padding: '8px 14px' }}>{(file.size_bytes / 1024).toFixed(1)} KB</td>
                    <td style={{ padding: '8px 14px' }}>
                      <code style={{ fontSize: '10px', fontFamily: 'var(--font-mono)' }}>
                        {file.content_hash.substring(0, 16)}...
                      </code>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: 'var(--muted-foreground)' }}>
                    No files matching filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* View 2: Discovered Modules Table */}
      {activeSubTab === 'modules' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {filteredModules.length > 0 ? (
            filteredModules.map((mod) => (
              <div
                key={mod.module_id}
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '16px',
                  backgroundColor: 'var(--card)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <strong style={{ fontSize: '14px' }}>{mod.module_id}</strong>
                      <span className={`badge ${mod.risk === 'CRITICAL' || mod.risk === 'HIGH' ? 'red' : mod.risk === 'MEDIUM' ? 'amber' : 'green'}`}>
                        {mod.risk} Risk
                      </span>
                      <span className="badge blue">{mod.confidence}</span>
                    </div>
                    <code style={{ fontSize: '11px', color: 'var(--muted-foreground)', display: 'block', marginTop: '2px' }}>
                      {mod.path}
                    </code>
                  </div>
                  <span style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
                    Language: <strong>{mod.language}</strong> {mod.framework ? `(${mod.framework})` : ''}
                  </span>
                </div>

                <p style={{ fontSize: '12px', margin: '8px 0', color: 'var(--foreground)' }}>
                  {mod.responsibility}
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', fontSize: '11px', marginTop: '10px', borderTop: '1px solid var(--border)', paddingTop: '10px' }}>
                  <div>
                    <span style={{ color: 'var(--muted-foreground)', display: 'block' }}>Entry Points ({mod.entry_points.length})</span>
                    <div style={{ marginTop: '2px' }}>
                      {mod.entry_points.length > 0 ? mod.entry_points.join(', ') : 'None'}
                    </div>
                  </div>
                  <div>
                    <span style={{ color: 'var(--muted-foreground)', display: 'block' }}>Public Interfaces ({mod.public_interfaces.length})</span>
                    <div style={{ marginTop: '2px' }}>
                      {mod.public_interfaces.length > 0 ? mod.public_interfaces.join(', ') : 'None'}
                    </div>
                  </div>
                  <div>
                    <span style={{ color: 'var(--muted-foreground)', display: 'block' }}>Dependencies ({mod.dependencies.length})</span>
                    <div style={{ marginTop: '2px' }}>
                      {mod.dependencies.length > 0 ? mod.dependencies.join(', ') : 'None (Independent)'}
                    </div>
                  </div>
                </div>

                {mod.evidence_refs.length > 0 && (
                  <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Evidence Records:</span>
                    {mod.evidence_refs.map((refId) => (
                      <button
                        key={refId}
                        onClick={() => handleShowEvidence(refId)}
                        className="button button-secondary"
                        style={{ fontSize: '10px', padding: '2px 6px' }}
                      >
                        <ExternalLink size={10} />
                        <span>{refId}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))
          ) : (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--muted-foreground)' }}>
              No modules discovered or matching search query.
            </div>
          )}
        </div>
      )}

      {/* Evidence Drill-down Drawer */}
      <EvidenceDrawer evidence={selectedEvidence} onClose={() => setSelectedEvidence(null)} />
    </div>
  );
};
