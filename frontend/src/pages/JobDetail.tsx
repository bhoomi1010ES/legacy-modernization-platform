import React, { useState, useEffect } from 'react';
import type { Job, GateDetail, Artifact, AgentRun } from '../types/domain';
import { StatusBadge } from '../components/StatusBadge';
import { PipelineProgress } from '../components/PipelineProgress';
import { GateReviewModal } from '../components/GateReviewModal';
import { api } from '../services/api';
import {
  Layers,
  GitBranch,
  Play,
  Pause,
  XCircle,
  ShieldAlert,
  ExternalLink,
  Cpu,
  FileText,
  CheckCircle2,
  Clock,
  ArrowRight,
} from 'lucide-react';

interface JobDetailProps {
  jobId: string;
  onNavigate: (path: string) => void;
  onGateDecision: (gateId: string, decision: any, rationale: string, waivers?: any[]) => Promise<void>;
}

export const JobDetail: React.FC<JobDetailProps> = ({ jobId, onNavigate, onGateDecision }) => {
  const [job, setJob] = useState<Job | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'feasibility' | 'tests' | 'blueprint' | 'verification' | 'agents'>('overview');
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [agents, setAgents] = useState<AgentRun[]>([]);
  const [activeGate, setActiveGate] = useState<GateDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadJobData();
  }, [jobId]);

  const loadJobData = async () => {
    try {
      setLoading(true);
      const j = await api.getJob(jobId);
      setJob(j);

      const arts = await api.getArtifacts(jobId);
      setArtifacts(arts);

      const ags = await api.getAgents(jobId);
      setAgents(ags);

      const gates = await api.getAllGates();
      const jobGate = gates.find((g) => g.job_id === jobId && g.status === 'PENDING');
      setActiveGate(jobGate || null);
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    if (!job) return;
    const updated = await api.pauseJob(job.job_id);
    setJob(updated);
  };

  const handleResume = async () => {
    if (!job) return;
    const updated = await api.resumeJob(job.job_id);
    setJob(updated);
  };

  const handleCancel = async () => {
    if (!job || !confirm('Are you sure you want to cancel this modernization job?')) return;
    const updated = await api.cancelJob(job.job_id);
    setJob(updated);
  };

  if (loading || !job) {
    return <div style={{ padding: '40px', textAlign: 'center' }}>Loading job details...</div>;
  }

  return (
    <div>
      {/* Top Header */}
      <div className="page-heading">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <h1>{job.name}</h1>
            <StatusBadge status={job.status} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '11px', color: 'var(--muted-foreground)' }}>
            <span>Job ID: <strong style={{ color: 'var(--foreground)' }}>{job.job_id}</strong></span>
            <span>•</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <GitBranch size={12} />
              {job.source_repository} ({job.source_revision})
            </span>
            {job.integration_branch && (
              <>
                <span>•</span>
                <span>Branch: <strong style={{ color: 'var(--primary)' }}>{job.integration_branch}</strong></span>
              </>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="heading-actions">
          {activeGate && (
            <button
              className="button button-primary"
              onClick={() => setActiveGate(activeGate)}
            >
              <ShieldAlert size={14} />
              <span>Review Gate {activeGate.gate_type}</span>
            </button>
          )}

          {job.status === 'CONVERTING' && (
            <button className="button button-secondary" onClick={handlePause}>
              <Pause size={14} />
              <span>Pause Job</span>
            </button>
          )}

          {job.status === 'PAUSED' && (
            <button className="button button-secondary" onClick={handleResume}>
              <Play size={14} />
              <span>Resume Job</span>
            </button>
          )}

          {job.status !== 'COMPLETED' && job.status !== 'CANCELLED' && (
            <button className="button button-secondary" onClick={handleCancel}>
              <XCircle size={14} />
              <span>Cancel</span>
            </button>
          )}
        </div>
      </div>

      {/* 7-Stage Pipeline Visualizer */}
      <PipelineProgress status={job.status} />

      {/* Multi-Tab Navigation */}
      <div className="tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Job Overview
        </button>
        <button
          className={`tab ${activeTab === 'feasibility' ? 'active' : ''}`}
          onClick={() => setActiveTab('feasibility')}
        >
          Feasibility & Gaps
        </button>
        <button
          className={`tab ${activeTab === 'tests' ? 'active' : ''}`}
          onClick={() => setActiveTab('tests')}
        >
          Characterization Suite
        </button>
        <button
          className={`tab ${activeTab === 'blueprint' ? 'active' : ''}`}
          onClick={() => setActiveTab('blueprint')}
        >
          Target Blueprint & Waves
        </button>
        <button
          className={`tab ${activeTab === 'verification' ? 'active' : ''}`}
          onClick={() => setActiveTab('verification')}
        >
          Verification & Drift
        </button>
        <button
          className={`tab ${activeTab === 'agents' ? 'active' : ''}`}
          onClick={() => setActiveTab('agents')}
        >
          Active Specialist Agents ({agents.length})
        </button>
      </div>

      {/* Tab 1: Overview */}
      {activeTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
          <div>
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '20px', backgroundColor: 'var(--card)', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '15px', fontWeight: 650, marginBottom: '14px' }}>Modernization Stack Coordinates</h2>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', fontSize: '12px' }}>
                <div>
                  <span style={{ color: 'var(--muted-foreground)' }}>Source Stack:</span>
                  <div style={{ fontWeight: 600, marginTop: '4px' }}>{job.source_stack}</div>
                </div>
                <div>
                  <span style={{ color: 'var(--muted-foreground)' }}>Target Stack:</span>
                  <div style={{ fontWeight: 600, color: 'var(--primary)', marginTop: '4px' }}>{job.target_stack}</div>
                </div>
                <div>
                  <span style={{ color: 'var(--muted-foreground)' }}>Discovered Modules:</span>
                  <div style={{ fontWeight: 600, marginTop: '4px' }}>{job.modules} domain packages</div>
                </div>
                <div>
                  <span style={{ color: 'var(--muted-foreground)' }}>Max Inner-Loop Retries:</span>
                  <div style={{ fontWeight: 600, marginTop: '4px' }}>{job.max_repair_attempts} attempts / module</div>
                </div>
              </div>
            </div>

            {/* Generated Artifacts Table */}
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', backgroundColor: 'var(--secondary)', borderBottom: '1px solid var(--border)', fontWeight: 650, fontSize: '12px' }}>
                Verified Deliverable Artifacts ({artifacts.length})
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Type & Version</th>
                    <th>SHA-256 Checksum</th>
                    <th>Producing Agent</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {artifacts.map((a) => (
                    <tr key={a.artifact_id}>
                      <td>
                        <strong>{a.artifact_type}</strong> v{a.version}
                      </td>
                      <td>
                        <code style={{ fontSize: '10px', fontFamily: 'var(--font-mono)' }}>
                          {a.content_hash.substring(0, 18)}...
                        </code>
                      </td>
                      <td>{a.producing_agent}</td>
                      <td>{new Date(a.created_at).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Right Column: Spend & Guardrails */}
          <div>
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '20px', backgroundColor: 'var(--card)' }}>
              <h2 style={{ fontSize: '15px', fontWeight: 650, marginBottom: '14px' }}>Autonomous Budget</h2>
              <div style={{ fontSize: '24px', fontWeight: 700, marginBottom: '4px' }}>
                ₹{job.cost.toFixed(2)}
                <span style={{ fontSize: '13px', color: 'var(--muted-foreground)', fontWeight: 400 }}> / ₹{job.budget.toFixed(2)}</span>
              </div>
              <div className="progress-track" style={{ width: '100%', height: '8px', margin: '12px 0' }}>
                <div
                  className="progress-fill"
                  style={{ width: `${Math.min(100, (job.cost / job.budget) * 100)}%` }}
                />
              </div>
              <small style={{ color: 'var(--muted-foreground)' }}>
                {((job.cost / job.budget) * 100).toFixed(1)}% of maximum autonomous spend cap consumed.
              </small>

              <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
                <div style={{ fontSize: '11px', fontWeight: 600, marginBottom: '6px' }}>Autonomous Controls:</div>
                <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                  Container Sandboxes: <strong>Rootless gVisor</strong><br />
                  Secret Redaction: <strong>Enforced</strong><br />
                  Human Oversight: <strong>Mandatory G1–G4</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Feasibility */}
      {activeTab === 'feasibility' && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '24px', backgroundColor: 'var(--card)' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 650, marginBottom: '10px' }}>Target Stack Feasibility Assessment (Gate G1)</h2>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '20px' }}>
            Analysis conducted by the Architect specialist agent mapping Java 11 Spring Boot idioms into Node.js 22 / NestJS equivalents.
          </p>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Legacy Java Idiom</th>
                  <th>Target TypeScript Pattern</th>
                  <th>Complexity</th>
                  <th>Resolution Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><code>@RestController + @RequestMapping</code></td>
                  <td>NestJS <code>@Controller() + @Get() / @Post()</code></td>
                  <td>Low</td>
                  <td><span className="badge green"><span className="dot" />1:1 Mapping</span></td>
                </tr>
                <tr>
                  <td><code>Spring Data JPA + Hibernate</code></td>
                  <td>Prisma Client / TypeORM repository injection</td>
                  <td>Medium</td>
                  <td><span className="badge green"><span className="dot" />Resolved</span></td>
                </tr>
                <tr>
                  <td><code>Jackson ObjectMapper Polymorphism</code></td>
                  <td><code>class-transformer + class-validator</code></td>
                  <td>High</td>
                  <td><span className="badge amber"><span className="dot" />Signed in G1</span></td>
                </tr>
                <tr>
                  <td><code>Spring Security Filter Chain</code></td>
                  <td>NestJS <code>CanActivate</code> AuthGuard + Session Middleware</td>
                  <td>Medium</td>
                  <td><span className="badge green"><span className="dot" />Standardized</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Characterization Suite */}
      {activeTab === 'tests' && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '24px', backgroundColor: 'var(--card)' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 650, marginBottom: '10px' }}>Frozen Characterization Test Harness (Gate G2)</h2>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '20px' }}>
            312 black-box characterization tests recorded from legacy execution. All outputs and side effects are frozen in <code>CharacterizationSuite_v1.json</code>.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '24px' }}>
            <div style={{ padding: '14px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Total Captured Vectors</div>
              <strong style={{ fontSize: '22px' }}>312</strong>
            </div>
            <div style={{ padding: '14px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Passing Target Replay</div>
              <strong style={{ fontSize: '22px', color: 'var(--success)' }}>308 (98.7%)</strong>
            </div>
            <div style={{ padding: '14px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Cryptographic Hash</div>
              <code style={{ fontSize: '10px', fontFamily: 'var(--font-mono)' }}>sha256:4a9918231c55490a...</code>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Blueprint & Waves */}
      {activeTab === 'blueprint' && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '24px', backgroundColor: 'var(--card)' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 650, marginBottom: '10px' }}>Module Dependency DAG & Wave Conversion Plan (Gate G3)</h2>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '20px' }}>
            18 modules scheduled across 4 topological waves. Modules in the same wave run in parallel sandboxed CodeWriter workers.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '12px 16px', backgroundColor: 'var(--secondary)' }}>
              <strong>Wave 1: Common Entities & DTOs (4 modules)</strong> · Completed · 100% Equivalence
            </div>
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '12px 16px', backgroundColor: 'var(--secondary)' }}>
              <strong>Wave 2: Database Repositories & Data Access (5 modules)</strong> · Completed · 99.2% Equivalence
            </div>
            <div style={{ border: '1px solid var(--primary)', borderRadius: 'var(--radius-md)', padding: '12px 16px', backgroundColor: 'var(--accent)' }}>
              <strong>Wave 3: Domain Business Services (6 modules)</strong> · In Progress · Active CodeWriter Workers
            </div>
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '12px 16px' }}>
              <strong>Wave 4: HTTP Controllers & Route Mappings (3 modules)</strong> · Queued
            </div>
          </div>
        </div>
      )}

      {/* Tab 5: Verification & Diff */}
      {activeTab === 'verification' && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '24px', backgroundColor: 'var(--card)' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 650, marginBottom: '10px' }}>Dual-Harness Behavioral Verification (Gate G4)</h2>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '20px' }}>
            Both legacy and converted services executed against identical fixtures. Zero unintended regressions detected.
          </p>
          <button className="button button-primary" onClick={() => onNavigate('/verification')}>
            Open Full Verification Suite
            <ArrowRight size={14} />
          </button>
        </div>
      )}

      {/* Tab 6: Agents */}
      {activeTab === 'agents' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
          {agents.map((ag) => (
            <div key={ag.run_id} style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <strong style={{ fontSize: '13px' }}>{ag.agent_name}</strong>
                <StatusBadge status={ag.status} />
              </div>
              <p style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginBottom: '10px' }}>
                {ag.role_description}
              </p>
              <div style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
                Tokens: {ag.input_tokens + ag.output_tokens} · Cost: ₹{ag.cost_usd.toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Gate Review Dialog */}
      {activeGate && (
        <GateReviewModal
          gate={activeGate}
          onClose={() => setActiveGate(null)}
          onSubmit={async (decision, rationale, waivers) => {
            await onGateDecision(activeGate.gate_id, decision, rationale, waivers);
            await loadJobData();
          }}
        />
      )}
    </div>
  );
};
