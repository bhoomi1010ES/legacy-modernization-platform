import React, { useState } from 'react';
import type { Job, GateDetail } from '../types/domain';
import { StatusBadge } from '../components/StatusBadge';
import { MetricCard } from '../components/MetricCard';
import { GateReviewModal } from '../components/GateReviewModal';
import {
  Layers,
  ShieldAlert,
  ArrowRight,
  TrendingUp,
  Cpu,
  CheckCircle2,
  GitBranch,
  ChevronRight,
  Sparkles,
} from 'lucide-react';

interface DashboardProps {
  jobs: Job[];
  gates: GateDetail[];
  onNavigate: (path: string) => void;
  onRefreshGates: () => void;
  onGateDecision: (gateId: string, decision: any, rationale: string, waivers?: any[]) => Promise<void>;
}

export const Dashboard: React.FC<DashboardProps> = ({
  jobs,
  gates,
  onNavigate,
  onRefreshGates,
  onGateDecision,
}) => {
  const [selectedGate, setSelectedGate] = useState<GateDetail | null>(null);

  const pendingGates = gates.filter((g) => g.status === 'PENDING');
  const activeJobs = jobs.filter((j) => j.status !== 'COMPLETED' && j.status !== 'FAILED');
  const totalSpend = jobs.reduce((acc, j) => acc + j.cost, 0);
  const totalBudget = jobs.reduce((acc, j) => acc + j.budget, 0);

  return (
    <div>
      {/* Page Heading */}
      <div className="page-heading">
        <div>
          <h1>Modernization Command Center</h1>
          <p className="subtitle">
            Autonomous Java → TypeScript vertical slice execution with non-bypassable quality gates.
          </p>
        </div>
        <div className="heading-actions">
          <button className="button button-secondary" onClick={() => onNavigate('/approvals')}>
            <ShieldAlert size={14} color="var(--warning)" />
            <span>{pendingGates.length} Pending Approvals</span>
          </button>
          <button className="button button-primary" onClick={() => onNavigate('/jobs/new')}>
            <span>+ Start Modernization</span>
          </button>
        </div>
      </div>

      {/* Hero Welcome Banner with Pipeline Visual Art */}
      <div className="welcome-banner">
        <div>
          <h2>Autonomous Migration Pipeline Ready</h2>
          <p>
            V1 Target Stack locked to <strong>TypeScript 5.x / Node.js 22 / NestJS</strong> with PostgreSQL and Jest characterization harnesses. 11 specialist agents active in sandboxed execution.
          </p>
          <a
            href="#/jobs/new"
            className="banner-link"
            onClick={(e) => { e.preventDefault(); onNavigate('/jobs/new'); }}
          >
            <span>Launch a new legacy service migration wizard</span>
            <ArrowRight size={13} />
          </a>
        </div>

        {/* Pipeline SVG illustration */}
        <div className="pipeline-art">
          <svg viewBox="0 0 280 90" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="10" y="35" width="40" height="20" rx="4" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.5" />
            <text x="30" y="49" fill="currentColor" fontSize="8" fontWeight="bold" textAnchor="middle">JAVA</text>
            
            <line x1="50" y1="45" x2="80" y2="45" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" />
            <circle cx="95" cy="45" r="14" fill="currentColor" fillOpacity="0.2" stroke="currentColor" strokeWidth="1.5" />
            <text x="95" y="48" fill="currentColor" fontSize="7" fontWeight="bold" textAnchor="middle">AGENTS</text>

            <line x1="110" y1="45" x2="140" y2="45" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" />
            <rect x="140" y="32" width="26" height="26" rx="4" fill="#b45309" fillOpacity="0.2" stroke="#b45309" strokeWidth="1.5" />
            <text x="153" y="48" fill="#b45309" fontSize="8" fontWeight="bold" textAnchor="middle">G1-4</text>

            <line x1="166" y1="45" x2="196" y2="45" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" />
            <circle cx="210" cy="45" r="14" fill="#15803d" fillOpacity="0.2" stroke="#15803d" strokeWidth="1.5" />
            <text x="210" y="48" fill="#15803d" fontSize="7" fontWeight="bold" textAnchor="middle">TESTS</text>

            <line x1="224" y1="45" x2="245" y2="45" stroke="currentColor" strokeWidth="1.5" />
            <polygon points="245,41 254,45 245,49" fill="currentColor" />
          </svg>
        </div>
      </div>

      {/* 4-Stat Metric Grid */}
      <div className="stat-grid">
        <MetricCard
          label="Active Jobs"
          value={activeJobs.length}
          note="Across 2 repositories"
          icon={<Layers size={16} color="var(--primary)" />}
        />
        <MetricCard
          label="Pending Gate Approvals"
          value={pendingGates.length}
          note="Action required by Lead Architect"
          noteType={pendingGates.length > 0 ? 'warn' : 'normal'}
          icon={<ShieldAlert size={16} color="var(--warning)" />}
        />
        <MetricCard
          label="Equivalence Rate"
          value="98.7%"
          note="4 signed difference waivers"
          noteType="success"
          icon={<TrendingUp size={16} color="var(--success)" />}
        />
        <MetricCard
          label="Budget Consumed"
          value={`$${totalSpend.toFixed(2)}`}
          note={`Cap: $${totalBudget.toFixed(2)} total`}
          icon={<Cpu size={16} color="var(--primary)" />}
        />
      </div>

      {/* Urgent Approval Gate Card (if pending) */}
      {pendingGates.length > 0 && (
        <div style={{ marginBottom: '28px' }}>
          <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '10px' }}>
            Action Required: Pending Governance Gates
          </div>
          {pendingGates.map((g) => (
            <div key={g.gate_id} className="approval-card">
              <div className="approval-icon">
                <ShieldAlert size={20} />
              </div>
              <div className="approval-copy">
                <h3>
                  <span>Gate {g.gate_type}: {g.title}</span>
                  <span className="badge amber" style={{ fontSize: '9px' }}>{g.job_name}</span>
                </h3>
                <p>{g.description} · Verified Artifact: <strong>{g.artifact}</strong></p>
              </div>
              <button
                className="button button-primary button-sm"
                onClick={() => setSelectedGate(g)}
              >
                Review Gate & Decide
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Recent Jobs Table */}
      <div style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
          <div style={{ fontSize: '13px', fontWeight: 650 }}>Active Modernization Pipeline</div>
          <button
            className="button button-secondary button-sm"
            onClick={() => onNavigate('/jobs')}
          >
            <span>View All Jobs</span>
            <ChevronRight size={13} />
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Job Identifier</th>
                <th>Source & Target Stack</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Cost / Budget</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '36px 16px', color: 'var(--muted-foreground)' }}>
                    <div style={{ marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>No Modernization Jobs Found</div>
                    <div style={{ fontSize: '12px', marginBottom: '14px' }}>
                      Start your first Java service modernization project to begin autonomous multi-agent migration.
                    </div>
                    <button
                      className="button button-primary button-sm"
                      onClick={() => onNavigate('/jobs/new')}
                      style={{ margin: '0 auto' }}
                    >
                      + Start Modernization Wizard
                    </button>
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr key={job.job_id} style={{ cursor: 'pointer' }} onClick={() => onNavigate(`/jobs/${job.job_id}`)}>
                    <td>
                      <span className="job-name">{job.name}</span>
                      <span className="job-repo">
                        <GitBranch size={11} />
                        {job.job_id.slice(0, 8)} · {job.source_repository.replace('https://github.com/', '')}
                      </span>
                    </td>
                    <td>
                      <div className="stack-cell">
                        <span className="stack-label">{job.source_stack}</span>
                        <ArrowRight size={10} color="var(--muted-foreground)" />
                        <span className="stack-label" style={{ backgroundColor: 'var(--accent)', color: 'var(--primary)' }}>
                          {job.target_stack}
                        </span>
                      </div>
                    </td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td>
                      <div className="progress-row">
                        <div className="progress-track">
                          <div
                            className={`progress-fill ${job.status.includes('AWAITING') ? 'amber' : ''}`}
                            style={{ width: `${job.progress}%` }}
                          />
                        </div>
                        <span>{job.progress}%</span>
                      </div>
                    </td>
                    <td>
                      <span style={{ fontWeight: 600 }}>${(job.cost || 0).toFixed(2)}</span>
                      <span style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}> / ${(job.budget || 0).toFixed(2)}</span>
                    </td>
                    <td>
                      <button
                        className="button button-secondary button-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          onNavigate(`/jobs/${job.job_id}`);
                        }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Review Gate Modal Dialog */}
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
