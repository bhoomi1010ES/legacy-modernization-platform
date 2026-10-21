import React, { useState, useEffect } from 'react';
import type { DeliveryReportResponse } from '../types/api';
import { api } from '../services/api';
import { FileSpreadsheet, ExternalLink, CheckCircle2, GitPullRequest, Download, ShieldCheck } from 'lucide-react';

export const Reports: React.FC = () => {
  const [report, setReport] = useState<DeliveryReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloaded, setDownloaded] = useState(false);

  useEffect(() => {
    loadReport();
  }, []);

  const loadReport = async () => {
    try {
      setLoading(true);
      const data = await api.getDeliveryReport('JOB-0248');
      setReport(data);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    setDownloaded(true);
    setTimeout(() => setDownloaded(false), 3000);
  };

  if (loading || !report) {
    return <div style={{ padding: '40px', textAlign: 'center' }}>Loading delivery report...</div>;
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>Delivery Readiness & Cutover Package</h1>
          <p className="subtitle">
            Gate G4 certified modernization bundle with verified equivalence, pull request coordinates, and rollback playbooks.
          </p>
        </div>
        <div className="heading-actions">
          <button className="button button-primary" onClick={handleDownload}>
            <Download size={14} />
            <span>{downloaded ? 'Package Downloaded!' : 'Export Audit Certificate'}</span>
          </button>
        </div>
      </div>

      {/* Main Delivery Card */}
      <div
        style={{
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          padding: '28px',
          backgroundColor: 'var(--card)',
          boxShadow: 'var(--shadow-soft)',
          marginBottom: '28px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <span className="badge green">G4 Certified</span>
              <span style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Delivered {new Date(report.delivered_at).toLocaleDateString()}</span>
            </div>
            <h2 style={{ fontSize: '20px', fontWeight: 700 }}>{report.project_name}</h2>
          </div>

          <a
            href={report.pull_request_url}
            target="_blank"
            rel="noreferrer"
            className="button button-secondary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}
          >
            <GitPullRequest size={14} color="var(--primary)" />
            <span>Open Pull Request #189</span>
            <ExternalLink size={12} />
          </a>
        </div>

        {/* 3 Metric Summary Boxes */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '28px' }}>
          <div style={{ padding: '16px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--secondary)' }}>
            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Behavioral Equivalence Score</div>
            <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--success)', marginTop: '4px' }}>
              {report.equivalence_pct}%
            </div>
            <small style={{ color: 'var(--muted-foreground)' }}>Passed 308 / 312 tests</small>
          </div>

          <div style={{ padding: '16px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--secondary)' }}>
            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Integration Git Branch</div>
            <div style={{ fontSize: '14px', fontWeight: 650, fontFamily: 'var(--font-mono)', color: 'var(--primary)', marginTop: '8px' }}>
              {report.integration_branch}
            </div>
            <small style={{ color: 'var(--muted-foreground)' }}>Verified rebased cleanly</small>
          </div>

          <div style={{ padding: '16px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--secondary)' }}>
            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Architectural Waivers</div>
            <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px' }}>
              {report.signed_waivers_count} signed
            </div>
            <small style={{ color: 'var(--muted-foreground)' }}>Signed by Alex Morgan</small>
          </div>
        </div>

        {/* Included Deliverable Artifacts */}
        <div style={{ marginBottom: '24px' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 650, marginBottom: '10px' }}>Verified Artifact Manifest:</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {report.included_artifacts.map((art, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '11px',
                  padding: '8px 12px',
                  backgroundColor: 'var(--secondary)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <CheckCircle2 size={13} color="var(--success)" />
                <code style={{ fontFamily: 'var(--font-mono)' }}>{art}</code>
              </div>
            ))}
          </div>
        </div>

        {/* Production Cutover Checklist */}
        <div>
          <h3 style={{ fontSize: '13px', fontWeight: 650, marginBottom: '10px' }}>Zero-Downtime Cutover Checklist:</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <CheckCircle2 size={15} color="var(--primary)" />
              <span>Database schema forward-compatible migration applied via Prisma Migrate.</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <CheckCircle2 size={15} color="var(--primary)" />
              <span>Canary reverse-proxy weighting configured (10% traffic to NestJS cluster).</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <CheckCircle2 size={15} color="var(--primary)" />
              <span>Automated rollback triggers primed on 5xx error rate &gt; 0.05%.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
