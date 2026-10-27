import React, { useEffect, useMemo, useState } from 'react';
import type { AgentRun, Job } from '../types/domain';
import { StatusBadge } from '../components/StatusBadge';
import { AgentTraceModal } from '../components/AgentTraceModal';
import {
  AlertTriangle, Bot, Clock3, Cpu, DollarSign, FileJson, Filter,
  RefreshCw, ShieldCheck, Terminal, Wrench, XCircle,
} from 'lucide-react';
import { api } from '../services/api';

interface AgentWorkspaceProps { jobs: Job[] }
const statuses = ['ALL', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'CANCELLED'] as const;

const elapsed = (run: AgentRun) => {
  if (run.duration_seconds != null) return run.duration_seconds;
  const start = Date.parse(run.started_at);
  const end = run.completed_at ? Date.parse(run.completed_at) : Date.now();
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, (end - start) / 1000) : 0;
};

const formatDuration = (seconds: number) => {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
};

export const AgentWorkspace: React.FC<AgentWorkspaceProps> = ({ jobs }) => {
  const [jobId, setJobId] = useState(jobs[0]?.job_id || '');
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [statusFilter, setStatusFilter] = useState<(typeof statuses)[number]>('ALL');
  const [selectedAgent, setSelectedAgent] = useState<AgentRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!jobs.some((job) => job.job_id === jobId)) setJobId(jobs[0]?.job_id || '');
  }, [jobs, jobId]);

  const loadRuns = async (quiet = false) => {
    if (!jobId) { setRuns([]); return; }
    if (!quiet) setLoading(true);
    try {
      setError('');
      setRuns(await api.getAgents(jobId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load agent runs.');
    } finally {
      if (!quiet) setLoading(false);
    }
  };

  useEffect(() => { void loadRuns(); }, [jobId]);

  useEffect(() => {
    if (!runs.some((run) => run.status === 'QUEUED' || run.status === 'RUNNING')) return;
    const timer = window.setInterval(() => void loadRuns(true), 5000);
    return () => window.clearInterval(timer);
  }, [jobId, runs]);

  const filtered = useMemo(
    () => [...runs].filter((run) => statusFilter === 'ALL' || run.status === statusFilter)
      .sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at)),
    [runs, statusFilter],
  );
  const totalTokens = runs.reduce((sum, run) => sum + run.input_tokens + run.output_tokens, 0);
  const totalCost = runs.reduce((sum, run) => sum + run.cost_usd, 0);
  const totalDuration = runs.reduce((sum, run) => sum + elapsed(run), 0);

  const cancelRun = async (run: AgentRun) => {
    if (!window.confirm(`Request cancellation for ${run.agent_name}?`)) return;
    try {
      await api.cancelAgentRun(run.run_id);
      await loadRuns(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Cancellation request failed.');
    }
  };

  return (
    <div>
      <div className="page-heading">
        <div>
          <div className="eyebrow"><ShieldCheck size={13} /> Phase 2 · shared runtime</div>
          <h1>Agent execution timeline</h1>
          <p className="subtitle">Inspect redacted traces, scoped tool calls, evidence, budgets, and safe failure classifications.</p>
        </div>
        <div className="heading-actions agent-toolbar">
          <label className="compact-select"><span>Job</span>
            <select value={jobId} onChange={(event) => setJobId(event.target.value)} disabled={!jobs.length}>
              {!jobs.length && <option value="">No jobs available</option>}
              {jobs.map((job) => <option key={job.job_id} value={job.job_id}>{job.name}</option>)}
            </select>
          </label>
          <button className="button button-secondary" onClick={() => void loadRuns()} disabled={loading || !jobId}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      <div className="runtime-metrics">
        <div className="runtime-metric"><Bot size={18} /><div><span>Persisted runs</span><strong>{runs.length}</strong></div></div>
        <div className="runtime-metric"><Cpu size={18} /><div><span>Token usage</span><strong>{totalTokens.toLocaleString()}</strong></div></div>
        <div className="runtime-metric"><DollarSign size={18} /><div><span>Model cost</span><strong>${totalCost.toFixed(4)}</strong></div></div>
        <div className="runtime-metric"><Clock3 size={18} /><div><span>Runtime</span><strong>{formatDuration(totalDuration)}</strong></div></div>
      </div>

      <div className="runtime-filterbar">
        <div className="runtime-filter-label"><Filter size={13} /> Status</div>
        <div className="runtime-filter-list">
          {statuses.map((status) => <button key={status} className={`filter-chip ${statusFilter === status ? 'active' : ''}`} onClick={() => setStatusFilter(status)}>
            {status === 'ALL' ? 'All' : status.replace('_', ' ')}
            <span>{status === 'ALL' ? runs.length : runs.filter((run) => run.status === status).length}</span>
          </button>)}
        </div>
      </div>

      {error && <div className="safe-error"><AlertTriangle size={16} /><div><strong>Safe runtime error</strong><span>{error}</span></div></div>}

      {!jobId ? <div className="empty-state"><Terminal size={34} /><h3>Create a job to inspect agent activity</h3><p>Runtime traces are scoped to an authorized modernization job.</p></div>
        : loading && !runs.length ? <div className="empty-state"><RefreshCw size={28} className="spin" /><h3>Loading persisted runs</h3></div>
        : !filtered.length ? <div className="empty-state"><Terminal size={34} /><h3>No matching agent runs</h3><p>Authorized launches will appear here with persisted traces and evidence references.</p></div>
        : <div className="agent-timeline">{filtered.map((run) => {
          const isActive = run.status === 'QUEUED' || run.status === 'RUNNING';
          return <article key={run.run_id} className={`agent-run-card ${isActive ? 'is-active' : ''}`}>
            <div className="timeline-rail"><span className={`timeline-node status-${run.status.toLowerCase()}`} /></div>
            <div className="agent-run-main">
              <div className="agent-run-heading"><div className="agent-identity"><div className="agent-icon"><Bot size={18} /></div><div><h2>{run.agent_name}</h2><code>{run.run_id}</code></div></div><StatusBadge status={run.status} /></div>
              <div className="agent-run-meta"><span><Cpu size={12} /> {run.model_identifier || 'Model unavailable'}</span><span><Clock3 size={12} /> {formatDuration(elapsed(run))}</span><span>{new Date(run.started_at).toLocaleString()}</span></div>
              {run.error_message && <div className="inline-safe-error"><AlertTriangle size={13} /><span><strong>{run.failure_classification || 'FAILED'}:</strong> {run.error_message}</span></div>}
              <div className="agent-run-foot"><div className="run-facts"><span><Cpu size={12} /> {(run.input_tokens + run.output_tokens).toLocaleString()} tokens</span><span><DollarSign size={12} /> ${run.cost_usd.toFixed(4)}</span><span><Wrench size={12} /> Scoped tools</span><span><FileJson size={12} /> {run.evidence_artifact_ids?.length || 0} artifacts</span></div>
                <div className="run-actions">{isActive && <button className="button button-danger button-sm" onClick={() => void cancelRun(run)}><XCircle size={12} /> Cancel</button>}<button className="button button-secondary button-sm" onClick={() => setSelectedAgent(run)}><Terminal size={12} /> Inspect trace</button></div>
              </div>
            </div>
          </article>;
        })}</div>}
      {selectedAgent && <AgentTraceModal agent={selectedAgent} onClose={() => setSelectedAgent(null)} />}
    </div>
  );
};
