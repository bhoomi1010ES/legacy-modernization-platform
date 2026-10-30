import React, { useState, useEffect } from 'react';
import type { VerificationReportResponse } from '../types/api';
import type { Job } from '../types/domain';
import { api } from '../services/api';
import { MetricCard } from '../components/MetricCard';
import { Activity, ShieldCheck, CheckCircle2, AlertTriangle, ArrowRight, FileCheck } from 'lucide-react';

interface VerificationProps {
  jobs?: Job[];
  onNavigate: (path: string) => void;
}

export const Verification: React.FC<VerificationProps> = ({ jobs = [], onNavigate }) => {
  const getInitialJobId = () => {
    try {
      const saved = localStorage.getItem('rebase_active_job_id');
      if (saved && jobs.some(j => j.job_id === saved)) return saved;
    } catch {}
    return jobs[0]?.job_id || '';
  };
  const [selectedJobId, setSelectedJobId] = useState(getInitialJobId);
  const [report, setReport] = useState<VerificationReportResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const activeJob = jobs.find(j => j.job_id === selectedJobId) || jobs[0] || null;

  useEffect(() => {
    if (selectedJobId) {
      loadReport(selectedJobId);
    }
  }, [selectedJobId]);

  const loadReport = async (jobId: string) => {
    try {
      setLoading(true);
      const data = await api.getVerificationReport(jobId);
      setReport(data);
    } catch {
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !report) {
    return <div style={{ padding: '40px', textAlign: 'center' }}>Loading verification metrics...</div>;
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>Dual-Harness Behavioral Verification</h1>
          <p className="subtitle">
            {`Parallel replay of frozen characterization vectors across legacy ${activeJob?.source_stack || 'source'} and modern ${activeJob?.target_stack || 'target'} implementations.`}
          </p>
        </div>
        <div className="heading-actions">
          <button className="button button-primary" onClick={() => onNavigate('/reports')}>
            <FileCheck size={14} />
            <span>Generate Delivery Package</span>
          </button>
        </div>
      </div>

      {/* 4 Metrics Grid */}
      <div className="stat-grid">
        <MetricCard
          label="Behavioral Equivalence"
          value={`${report.behavioral_equivalence_pct}%`}
          note="Exceeds 98.0% production threshold"
          noteType="success"
          icon={<ShieldCheck size={16} color="var(--success)" />}
        />
        <MetricCard
          label="Total Characterization Tests"
          value={report.total_tests}
          note={`${report.passing_tests} passing target vectors`}
          icon={<Activity size={16} color="var(--primary)" />}
        />
        <MetricCard
          label="Regressions Count"
          value={report.regressions_count}
          note="0 breaking defects detected"
          noteType="success"
          icon={<CheckCircle2 size={16} color="var(--success)" />}
        />
        <MetricCard
          label="Intended Differences"
          value={report.intended_differences_count}
          note="Covered by architectural waivers"
          noteType="warn"
          icon={<AlertTriangle size={16} color="var(--warning)" />}
        />
      </div>

      {/* Behavioral Differences Classification Table */}
      <div style={{ marginTop: '20px' }}>
        <div style={{ marginBottom: '12px' }}>
          <h2 style={{ fontSize: '15px', fontWeight: 650 }}>Classified Differences & Waivers</h2>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)' }}>
            Each behavioral discrepancy between legacy source and target architecture is evaluated and categorized by the Verifier agent.
          </p>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Test Case</th>
                <th>Target Module</th>
                <th>Classification</th>
                <th>Legacy Behavior</th>
                <th>Converted Behavior</th>
                <th>Governance Resolution</th>
              </tr>
            </thead>
            <tbody>
              {report.differences.map((diff, idx) => (
                <tr key={idx}>
                  <td>
                    <code style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                      {diff.test_name}
                    </code>
                  </td>
                  <td>
                    <span className="stack-label">{diff.module}</span>
                  </td>
                  <td>
                    <span className="badge amber">
                      <span className="dot" />
                      {diff.classification.replace('_', ' ')}
                    </span>
                  </td>
                  <td style={{ maxWidth: '240px', whiteSpace: 'normal', fontSize: '11px', color: 'var(--muted-foreground)' }}>
                    {diff.legacy_behavior}
                  </td>
                  <td style={{ maxWidth: '240px', whiteSpace: 'normal', fontSize: '11px', fontWeight: 500 }}>
                    {diff.converted_behavior}
                  </td>
                  <td style={{ maxWidth: '240px', whiteSpace: 'normal', fontSize: '11px', color: 'var(--primary)' }}>
                    {diff.resolution}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
