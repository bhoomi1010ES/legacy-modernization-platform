import React, { useState, useEffect } from 'react';
import type { Artifact, Job } from '../types/domain';
import { api } from '../services/api';
import { FileText, Download, Check, Copy, Eye, RefreshCw, AlertCircle, Filter } from 'lucide-react';

interface ArtifactsProps {
  artifacts: Artifact[];
  jobs?: Job[];
}

export const Artifacts: React.FC<ArtifactsProps> = ({ artifacts, jobs = [] }) => {
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [copiedPayload, setCopiedPayload] = useState<boolean>(false);
  const [selectedJobId, setSelectedJobId] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Real artifact JSON payload state
  const [payload, setPayload] = useState<any | null>(null);
  const [loadingPayload, setLoadingPayload] = useState<boolean>(false);
  const [payloadError, setPayloadError] = useState<string | null>(null);

  // Fetch real artifact content from backend when selectedArtifact changes
  useEffect(() => {
    if (!selectedArtifact) {
      setPayload(null);
      setPayloadError(null);
      setLoadingPayload(false);
      return;
    }

    let cancelled = false;
    setLoadingPayload(true);
    setPayloadError(null);

    api
      .getArtifactContent(selectedArtifact.job_id, selectedArtifact.artifact_id)
      .then((res) => {
        if (!cancelled) {
          // If response has a content field, display content, else display whole response
          const content = res?.content !== undefined ? res.content : res;
          setPayload(content);
          setLoadingPayload(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setPayloadError(err?.message || 'Failed to fetch artifact JSON from storage.');
          setLoadingPayload(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedArtifact?.artifact_id, selectedArtifact?.job_id]);

  const handleCopy = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const handleCopyPayload = () => {
    if (!payload) return;
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopiedPayload(true);
    setTimeout(() => setCopiedPayload(false), 2000);
  };

  const handleDownloadPayload = () => {
    if (!payload || !selectedArtifact) return;
    const filename = `${selectedArtifact.artifact_type}_v${selectedArtifact.version}.json`;
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const filteredArtifacts = artifacts.filter((a) => {
    const matchesJob =
      selectedJobId === 'ALL' ||
      a.job_id === selectedJobId ||
      a.job_id.toLowerCase().startsWith(selectedJobId.toLowerCase());
    const matchesQuery =
      !searchQuery.trim() ||
      a.artifact_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.content_hash.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.job_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.producing_agent.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesJob && matchesQuery;
  });

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>Artifact Repository & Lineage</h1>
          <p className="subtitle">
            Cryptographically hashed, versioned deliverable artifacts tracking full multi-agent provenance.
          </p>
        </div>
      </div>

      {/* Filters bar: Job Selector + Search */}
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap' }}>
        {jobs.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px', color: 'var(--muted-foreground)', fontWeight: 500 }}>
              <Filter size={13} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />
              Filter Job:
            </span>
            <select
              className="select"
              style={{ fontSize: '12px', padding: '6px 12px', minWidth: '220px' }}
              value={selectedJobId}
              onChange={(e) => {
                setSelectedJobId(e.target.value);
                setSelectedArtifact(null);
              }}
            >
              <option value="ALL">All Jobs ({jobs.length})</option>
              {jobs.map((j) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.name || j.source_repository || 'Job'} ({j.job_id.slice(0, 8)}) {j.source_stack ? `— ${j.source_stack}` : ''}
                </option>
              ))}
            </select>
          </div>
        )}

        <div style={{ flex: 1, minWidth: '240px' }}>
          <input
            type="text"
            className="input"
            style={{ width: '100%', fontSize: '12px', padding: '6px 12px' }}
            placeholder="Search artifacts by type, agent, or hash..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: selectedArtifact ? '1fr 1fr' : '1fr', gap: '24px' }}>
        {/* Artifacts Table */}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Artifact</th>
                <th>Version</th>
                <th>Job</th>
                <th>SHA-256 Checksum</th>
                <th>Producing Agent</th>
                <th>Size</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredArtifacts.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '40px', color: 'var(--muted-foreground)' }}>
                    No versioned artifacts found for the current selection. Deliverables appear here as modernization jobs progress.
                  </td>
                </tr>
              ) : (
                filteredArtifacts.map((a) => (
                  <tr
                    key={a.artifact_id}
                    style={{
                      cursor: 'pointer',
                      backgroundColor: selectedArtifact?.artifact_id === a.artifact_id ? 'var(--secondary)' : undefined,
                    }}
                    onClick={() => setSelectedArtifact(a)}
                  >
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <FileText size={15} color="var(--primary)" />
                        <strong>{a.artifact_type}</strong>
                      </div>
                    </td>
                    <td>
                      <span className="badge blue">v{a.version}</span>
                    </td>
                    <td>
                      <span style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>{a.job_id.slice(0, 8)}</span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <code style={{ fontSize: '10px', fontFamily: 'var(--font-mono)' }}>
                          {(a.content_hash || 'sha256:verified').substring(0, 16)}...
                        </code>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(a.content_hash);
                          }}
                          title="Copy SHA-256 Hash"
                          style={{ padding: '2px' }}
                        >
                          {copiedHash === a.content_hash ? <Check size={11} color="var(--success)" /> : <span style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>Copy</span>}
                        </button>
                      </div>
                    </td>
                    <td>{a.producing_agent}</td>
                    <td>{((a.size_bytes || 0) / 1024).toFixed(1)} KB</td>
                    <td>
                      <button
                        className="button button-secondary button-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedArtifact(a);
                        }}
                      >
                        <Eye size={12} />
                        <span>Inspect</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Selected Artifact Inspector Drawer */}
        {selectedArtifact && (
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '20px',
              backgroundColor: 'var(--card)',
              boxShadow: 'var(--shadow-soft)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h2 style={{ fontSize: '15px', fontWeight: 650 }}>{selectedArtifact.artifact_type} (v{selectedArtifact.version})</h2>
                <small style={{ color: 'var(--muted-foreground)' }}>Artifact ID: {selectedArtifact.artifact_id}</small>
              </div>
              <button className="button button-secondary button-sm" onClick={() => setSelectedArtifact(null)}>
                Close
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '11px', marginBottom: '16px' }}>
              <div>
                <span style={{ color: 'var(--muted-foreground)' }}>Job ID: </span>
                <code style={{ fontFamily: 'var(--font-mono)' }}>{selectedArtifact.job_id}</code>
              </div>
              <div>
                <span style={{ color: 'var(--muted-foreground)' }}>Storage Path: </span>
                <code style={{ fontFamily: 'var(--font-mono)' }}>{selectedArtifact.storage_path}</code>
              </div>
              <div>
                <span style={{ color: 'var(--muted-foreground)' }}>Cryptographic Hash: </span>
                <code style={{ fontFamily: 'var(--font-mono)' }}>{selectedArtifact.content_hash}</code>
              </div>
              <div>
                <span style={{ color: 'var(--muted-foreground)' }}>Producing Agent: </span>
                <span>{selectedArtifact.producing_agent}</span>
              </div>
              <div>
                <span style={{ color: 'var(--muted-foreground)' }}>Derived From: </span>
                <span>{selectedArtifact.derived_from.length > 0 ? selectedArtifact.derived_from.join(', ') : 'Root Source Intake'}</span>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ fontSize: '11px', fontWeight: 650 }}>
                Artifact Payload (JSON):
              </div>
              {payload && !loadingPayload && (
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    className="button button-secondary button-sm"
                    style={{ fontSize: '10px', padding: '2px 8px' }}
                    onClick={handleCopyPayload}
                    title="Copy JSON Payload"
                  >
                    {copiedPayload ? <Check size={11} color="var(--success)" /> : <Copy size={11} />}
                    <span>{copiedPayload ? 'Copied' : 'Copy JSON'}</span>
                  </button>
                  <button
                    className="button button-secondary button-sm"
                    style={{ fontSize: '10px', padding: '2px 8px' }}
                    onClick={handleDownloadPayload}
                    title="Download JSON File"
                  >
                    <Download size={11} />
                    <span>Download</span>
                  </button>
                </div>
              )}
            </div>

            <div className="code-panel" style={{ maxHeight: '350px', overflowY: 'auto' }}>
              {loadingPayload ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '40px', color: 'var(--muted-foreground)' }}>
                  <RefreshCw size={14} className="spin" />
                  <span>Loading artifact JSON from storage...</span>
                </div>
              ) : payloadError ? (
                <div style={{ padding: '16px', color: 'var(--destructive)', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                  <AlertCircle size={16} />
                  <div>
                    <strong>Failed to load artifact content:</strong>
                    <p style={{ marginTop: '4px', fontSize: '11px' }}>{payloadError}</p>
                  </div>
                </div>
              ) : (
                <pre style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '11px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {JSON.stringify(payload, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
