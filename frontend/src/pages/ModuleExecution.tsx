import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { Job } from '../types/domain';
import type { ModuleAttempt, ModuleExecutionBoard } from '../types/phase6';
import { api } from '../services/api';
import { StatusBadge } from '../components/StatusBadge';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Cpu,
  FileCode2,
  FileText,
  Fingerprint,
  GitBranch,
  GitCommit,
  History,
  Layers,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';

const panelStyle: React.CSSProperties = {
  background: 'var(--card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-lg)',
  padding: '20px',
  boxShadow: 'var(--shadow-soft)',
  display: 'flex',
  flexDirection: 'column',
  gap: '12px',
};

const preStyle: React.CSSProperties = {
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
  maxHeight: 280,
  overflow: 'auto',
  fontSize: 12,
  fontFamily: 'var(--font-mono)',
  background: 'var(--secondary)',
  padding: '10px 14px',
  borderRadius: 'var(--radius-md)',
  border: '1px solid var(--border)',
};

const json = (value: unknown) => JSON.stringify(value, null, 2) ?? 'Not recorded';
const statuses = ['ALL', 'QUEUED', 'RUNNING', 'BLOCKED', 'REPAIRED', 'VERIFIED', 'REJECTED', 'FAILED', 'ESCALATED'];

export function ModuleEvidence({
  attempt,
  busy = false,
  onRepair,
  onWaiver,
}: {
  attempt: ModuleAttempt;
  busy?: boolean;
  onRepair?: (rationale: string) => void;
  onWaiver?: (findingId: string, rationale: string) => void;
}) {
  const [rationale, setRationale] = useState('');
  const evidence = attempt.evidence || {};
  const permitted = attempt.allowed_actions || [];

  return (
    <section
      style={{
        ...panelStyle,
        marginTop: 20,
        borderLeft: '4px solid var(--primary)',
      }}
      aria-label="Module evidence drawer"
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 4 }}>
            <FileCode2 size={13} /> Independent Verification & Lineage
          </div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Attempt {attempt.attempt_number} evidence</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <StatusBadge status={attempt.status} />
        </div>
      </div>

      <p style={{ margin: 0, color: 'var(--muted-foreground)', fontSize: 13 }}>
        Status: {attempt.status}
      </p>

      {attempt.failure_reason && (
        <div
          role="alert"
          style={{
            background: 'var(--danger-surface)',
            color: 'var(--destructive)',
            padding: '10px 14px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--destructive)',
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <AlertTriangle size={15} style={{ flexShrink: 0 }} />
          <span>{attempt.failure_reason}</span>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', margin: '4px 0' }}>
        <strong style={{ fontSize: 12 }}>Provider mode: </strong>
        {evidence.provider === 'openai' ||
        attempt.metadata?.model_provider === 'openai' ||
        evidence.model_provider === 'openai' ? (
          <span
            className="badge badge-success"
            style={{
              backgroundColor: '#059669',
              color: '#fff',
              padding: '2px 8px',
              borderRadius: 4,
              fontWeight: 'bold',
            }}
          >
            REAL OPENAI EXECUTION
          </span>
        ) : (
          <span
            className="badge badge-warning"
            style={{
              backgroundColor: '#d97706',
              color: '#fff',
              padding: '2px 8px',
              borderRadius: 4,
              fontWeight: 'bold',
            }}
          >
            DETERMINISTIC / FAKE PROVIDER
          </span>
        )}
      </div>

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 12,
          background: 'var(--secondary)',
          padding: 12,
          borderRadius: 'var(--radius-md)',
          margin: 0,
        }}
      >
        <div>
          <dt style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>Model</dt>
          <dd style={{ margin: 0, fontWeight: 600, fontSize: 13 }}>
            {typeof evidence.model === 'string'
              ? evidence.model
              : typeof attempt.metadata?.model_identifier === 'string'
              ? attempt.metadata.model_identifier
              : 'Not recorded'}
          </dd>
        </div>
        <div>
          <dt style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>Branch</dt>
          <dd style={{ margin: 0, fontWeight: 600, fontSize: 12, fontFamily: 'var(--font-mono)' }}>
            {attempt.git_branch || 'Not created'}
          </dd>
        </div>
        <div>
          <dt style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>Source commit</dt>
          <dd style={{ margin: 0, fontWeight: 600, fontSize: 12, fontFamily: 'var(--font-mono)' }}>
            {evidence.source_commit || 'Not recorded'}
          </dd>
        </div>
        <div>
          <dt style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>Frozen baseline hash</dt>
          <dd style={{ margin: 0, fontWeight: 600, fontSize: 12, fontFamily: 'var(--font-mono)', overflowWrap: 'anywhere' }}>
            {evidence.baseline_hash || 'Not recorded'}
          </dd>
        </div>
      </dl>

      <div style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, margin: '8px 0 4px' }}>Changed files</h3>
        {(evidence.changed_files || []).length ? (
          <ul style={{ margin: '4px 0', paddingLeft: 20, fontSize: 13 }}>
            {evidence.changed_files!.map(path => (
              <li key={path} style={{ fontFamily: 'var(--font-mono)' }}>{path}</li>
            ))}
          </ul>
        ) : (
          <p style={{ margin: '4px 0', fontSize: 12, color: 'var(--muted-foreground)' }}>No changed files recorded.</p>
        )}
      </div>

      <div style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, margin: '8px 0 4px' }}>Diff</h3>
        <pre style={preStyle}>{evidence.diff || 'No diff recorded.'}</pre>
      </div>

      <div style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, margin: '8px 0 4px' }}>Independent verification</h3>
        {!evidence.checks?.length && (
          <p role="alert" style={{ color: 'var(--warning)', fontSize: 12 }}>
            No execution evidence recorded. This attempt cannot establish verified behavior.
          </p>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {(evidence.checks || []).map((check, index) => (
            <article
              key={index}
              style={{
                background: 'var(--secondary)',
                padding: '12px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h4 style={{ margin: 0, fontSize: 13 }}>
                  {check.category}: {check.status}
                </h4>
                <StatusBadge status={check.status === 'PASS' ? 'SUCCEEDED' : 'FAILED'} />
              </div>
              <p style={{ margin: '4px 0', fontSize: 11, color: 'var(--muted-foreground)' }}>
                Exit code: {check.exit_code ?? 'Not executed'} · Duration: {check.duration_ms} ms
              </p>
              <pre style={{ ...preStyle, maxHeight: 120 }}>{json(check.command)}</pre>
              <p style={{ margin: '4px 0', fontSize: 11, color: 'var(--muted-foreground)', overflowWrap: 'anywhere' }}>
                Evidence hash: {check.artifact_hash || 'Not recorded'}
              </p>
              <details style={{ marginTop: 6, fontSize: 12 }}>
                <summary style={{ cursor: 'pointer', color: 'var(--primary)' }}>Captured stdout / stderr</summary>
                <pre style={{ ...preStyle, maxHeight: 160, marginTop: 4 }}>
                  {check.stdout || '(empty stdout)'}{'\n'}{check.stderr || '(empty stderr)'}
                </pre>
              </details>
            </article>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, margin: '8px 0 4px' }}>Frozen characterization results</h3>
        {Array.isArray(evidence.results) && evidence.results.length ? (
          <pre style={preStyle}>{json(evidence.results)}</pre>
        ) : (
          <p style={{ margin: '4px 0', fontSize: 12, color: 'var(--muted-foreground)' }}>
            No executed characterization results recorded.
          </p>
        )}
      </div>

      <div style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, margin: '8px 0 4px' }}>Reviewer findings</h3>
        <p style={{ margin: '2px 0 8px', fontSize: 12, color: 'var(--muted-foreground)' }}>
          Review status: {evidence.review?.status || 'Not recorded'}
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {(evidence.review?.findings || []).map(finding => (
            <article
              key={finding.finding_id}
              style={{
                background: 'var(--secondary)',
                padding: '12px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h4 style={{ margin: 0, fontSize: 13 }}>
                  {finding.severity} · {finding.category}
                </h4>
                <span className={`badge ${finding.severity === 'HIGH' ? 'red' : 'amber'}`}>
                  {finding.severity}
                </span>
              </div>
              <p style={{ margin: '6px 0', fontSize: 12 }}>{finding.message}</p>
              {finding.path && (
                <p style={{ margin: '2px 0', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--muted-foreground)' }}>
                  {finding.path}{finding.line ? `:${finding.line}` : ''}
                </p>
              )}
              <p style={{ margin: '2px 0', fontSize: 11, color: 'var(--muted-foreground)' }}>
                Evidence reference: {finding.evidence_ref || 'Not recorded'}
              </p>
              {permitted.includes('waiver') && onWaiver && (
                <button
                  className="button button-secondary"
                  style={{ marginTop: 6 }}
                  disabled={busy || rationale.trim().length < 10}
                  onClick={() => onWaiver(finding.finding_id, rationale.trim())}
                >
                  Request human review / waiver
                </button>
              )}
            </article>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, margin: '8px 0 4px' }}>Design notes and assumptions</h3>
        <pre style={preStyle}>
          {json({ design_notes: evidence.design_notes, assumptions: evidence.assumptions })}
        </pre>
      </div>

      <div style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, margin: '8px 0 4px' }}>Repair feedback</h3>
        <pre style={preStyle}>{json(evidence.repair_feedback)}</pre>
      </div>

      <details style={{ marginTop: 8, fontSize: 12 }}>
        <summary style={{ cursor: 'pointer', color: 'var(--primary)', fontWeight: 600 }}>
          Recorded tool trace and agent metadata
        </summary>
        <pre style={{ ...preStyle, marginTop: 4 }}>{json(attempt.metadata)}</pre>
        <pre style={preStyle}>{json(evidence)}</pre>
      </details>

      {(permitted.includes('repair') || permitted.includes('waiver')) && (
        <div
          style={{
            marginTop: 16,
            padding: 16,
            background: 'var(--secondary)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border)',
          }}
        >
          <label htmlFor="module-rationale" style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
            Repair / human review rationale
          </label>
          <textarea
            id="module-rationale"
            rows={3}
            value={rationale}
            onChange={event => setRationale(event.target.value)}
            style={{
              display: 'block',
              width: '100%',
              padding: 10,
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
              background: 'var(--card)',
              color: 'var(--foreground)',
              fontFamily: 'inherit',
              fontSize: 13,
            }}
            placeholder="Document technical repair guidance or policy waiver rationale (min 10 characters)..."
          />
          <p style={{ margin: '8px 0', fontSize: 11, color: 'var(--muted-foreground)' }}>
            Repair uses recorded failing evidence and reruns required checks. Waiver requests require backend authorization and an audit record.
          </p>
          {permitted.includes('repair') && onRepair && (
            <button
              className="button button-primary"
              disabled={busy || rationale.trim().length < 10}
              onClick={() => onRepair(rationale.trim())}
            >
              Request bounded repair
            </button>
          )}
        </div>
      )}
    </section>
  );
}

export function ModuleExecution({ jobs }: { jobs: Job[] }) {
  const getInitialJobId = () => {
    try {
      const saved = localStorage.getItem('rebase_active_job_id');
      if (saved && jobs.some(j => j.job_id === saved)) return saved;
    } catch {}
    const spendwiseJob = jobs.find(j => j.job_id === 'eb2bbaa9-90ee-4e9d-b340-5e025594126c');
    if (spendwiseJob) return spendwiseJob.job_id;
    return jobs[0]?.job_id || '';
  };

  const [jobId, setJobId] = useState(getInitialJobId);
  const [board, setBoard] = useState<ModuleExecutionBoard | null>(null);
  const [selected, setSelected] = useState<ModuleAttempt | null>(null);
  const [filter, setFilter] = useState('ALL');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const selection = useRef(0);
  const pendingKeys = useRef(new Map<string, string>());

  async function load(id: string, version: number) {
    const result = await api.getModuleAttempts(id);
    if (generation.current === version) setBoard(result);
  }

  useEffect(() => {
    if (!jobId && jobs.length) setJobId(getInitialJobId());
  }, [jobs, jobId]);

  useEffect(() => {
    const version = ++generation.current;
    selection.current++;
    setBoard(null);
    setSelected(null);
    setError('');
    setNotice('');
    if (!jobId) return;
    const refresh = () =>
      load(jobId, version).catch(err => {
        if (generation.current === version)
          setError(err instanceof Error ? err.message : 'Could not load module attempts.');
      });
    void refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      generation.current++;
      window.clearInterval(timer);
    };
  }, [jobId]);

  async function openEvidence(attemptId: string) {
    const version = generation.current;
    const selectedVersion = ++selection.current;
    setBusy(true);
    setError('');
    setSelected(null);
    try {
      const [attempt, diff, tests, review] = await Promise.all([
        api.getModuleAttempt(attemptId),
        api.getModuleAttemptDiff(attemptId),
        api.getModuleAttemptChecks(attemptId),
        api.getModuleAttemptReview(attemptId),
      ]);
      if (generation.current === version && selection.current === selectedVersion) {
        setSelected({
          ...attempt,
          evidence: { ...attempt.evidence, ...diff, checks: tests.checks, review },
        });
      }
    } catch (err) {
      if (generation.current === version)
        setError(err instanceof Error ? err.message : 'Could not retrieve module evidence.');
    } finally {
      if (generation.current === version) setBusy(false);
    }
  }

  async function act(identity: string, action: (key: string) => Promise<unknown>) {
    setBusy(true);
    setError('');
    setNotice('');
    const key = pendingKeys.current.get(identity) || crypto.randomUUID();
    pendingKeys.current.set(identity, key);
    try {
      await action(key);
      pendingKeys.current.delete(identity);
      setNotice(
        'Request recorded. Status and eligibility are determined by the Supervisor and independent checks.'
      );
      await load(jobId, generation.current);
      if (selected) await openEvidence(selected.attempt_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Module request failed.');
    } finally {
      setBusy(false);
    }
  }

  const allModules = board?.modules || [];
  const metrics = useMemo(() => {
    return {
      total: allModules.length,
      verified: allModules.filter(m => m.status === 'VERIFIED').length,
      inProgress: allModules.filter(m => ['LEASED', 'RUNNING', 'QUEUED', 'GENERATED', 'VERIFYING'].includes(m.status)).length,
      blocked: allModules.filter(m => ['BLOCKED', 'REPAIR_REQUIRED', 'REJECTED', 'FAILED', 'ESCALATED'].includes(m.status)).length,
    };
  }, [allModules]);

  const availableStatuses = useMemo(() => {
    return [...new Set([...statuses, ...allModules.map(m => m.status)])];
  }, [allModules]);

  const modules = useMemo(() => {
    return allModules.filter(
      module =>
        filter === 'ALL' ||
        module.status === filter ||
        (filter === 'REPAIRED' &&
          module.status === 'VERIFIED' &&
          module.attempts.some(attempt => attempt.attempt_number > 1 && attempt.status === 'VERIFIED'))
    );
  }, [allModules, filter]);

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', paddingBottom: 40 }}>
      {/* Page Heading aligned with platform standard */}
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <Cpu size={13} /> Phase 6 · Multi-Agent Module Execution & Bounded Repair
          </div>
          <h1>Module execution board</h1>
          <p className="subtitle">
            CodeWriter attempts, independent verification, reviewer findings and bounded repair.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <button
            className="button button-secondary"
            disabled={!jobId || busy}
            onClick={() => void act(`refresh:${jobId}`, () => load(jobId, generation.current))}
          >
            Refresh evidence
          </button>
        </div>
      </div>

      {/* Modern Control Bar: Job Selector */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 16,
          background: 'var(--card)',
          padding: '12px 18px',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border)',
          marginBottom: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 13 }}>
            <span>Modernization job</span>
            <select
              aria-label="Modernization job"
              disabled={busy}
              value={jobId}
              onChange={event => {
                setJobId(event.target.value);
                try {
                  localStorage.setItem('rebase_active_job_id', event.target.value);
                } catch {}
              }}
              style={{
                padding: '6px 12px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)',
                background: 'var(--secondary)',
                color: 'var(--foreground)',
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              {!jobs.length && <option value="">No jobs available</option>}
              {jobs.map(job => (
                <option key={job.job_id} value={job.job_id}>
                  {job.name}
                  {job.job_id ? ` · ${job.job_id.slice(0, 8)}` : ''}
                  {job.status ? ` · ${job.status}` : ''}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--muted-foreground)' }}>
          <ShieldCheck size={14} style={{ color: 'var(--success)' }} />
          <span>PostgreSQL Lease Fencing & LangGraph Durable Execution</span>
        </div>
      </div>

      {/* Alert Notices */}
      {error && (
        <div
          role="alert"
          style={{
            background: 'var(--danger-surface)',
            color: 'var(--destructive)',
            padding: '12px 16px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--destructive)',
            marginBottom: 16,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            fontSize: 13,
          }}
        >
          <AlertTriangle size={18} style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div
          role="status"
          style={{
            background: 'var(--accent)',
            color: 'var(--success)',
            padding: '12px 16px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--success)',
            marginBottom: 16,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            fontSize: 13,
          }}
        >
          <CheckCircle2 size={18} style={{ flexShrink: 0 }} />
          <span>{notice}</span>
        </div>
      )}
      {busy && (
        <div role="status" style={{ fontSize: 12, color: 'var(--muted-foreground)', marginBottom: 12 }}>
          Loading module evidence…
        </div>
      )}

      {/* Sandbox Warning */}
      {board && !board.runtime_available && (
        <div
          role="alert"
          style={{
            background: 'var(--warning-surface)',
            color: 'var(--warning)',
            padding: '12px 16px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--warning)',
            marginBottom: 16,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            fontSize: 13,
          }}
        >
          <AlertTriangle size={18} style={{ flexShrink: 0 }} />
          <div>
            <strong>Conversion sandbox unavailable.</strong> Modules remain blocked until a real isolated runtime is available; no execution success is inferred.
          </div>
        </div>
      )}

      {/* Policy and Invariant Banner */}
      <div
        style={{
          background: 'var(--secondary)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '10px 16px',
          marginBottom: 16,
          fontSize: 12,
          color: 'var(--muted-foreground)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        <ShieldCheck size={16} style={{ color: 'var(--primary)', flexShrink: 0 }} />
        <p style={{ margin: 0 }}>
          G1 constraints, the frozen G2 baseline and approved G3 plan govern execution. Only dependency-ready modules may run. Each attempt retains its own branch and evidence.
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="gate-metrics" style={{ marginBottom: 20 }}>
        <div>
          <Layers size={17} />
          <span>Total Modules</span>
          <strong>{metrics.total}</strong>
        </div>
        <div>
          <CheckCircle2 size={17} style={{ color: 'var(--success)' }} />
          <span>Verified Modules</span>
          <strong>{metrics.verified}</strong>
        </div>
        <div>
          <Clock3 size={17} style={{ color: 'var(--info)' }} />
          <span>In Progress / Leased</span>
          <strong>{metrics.inProgress}</strong>
        </div>
        <div>
          <ShieldAlert size={17} style={{ color: 'var(--destructive)' }} />
          <span>Needs Attention / Blocked</span>
          <strong>{metrics.blocked}</strong>
        </div>
      </div>

      {/* Status Filter */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600 }}>
          <span>Module status</span>
          <select
            aria-label="Module status"
            value={filter}
            onChange={event => setFilter(event.target.value)}
            style={{
              padding: '6px 12px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
              background: 'var(--secondary)',
              color: 'var(--foreground)',
              fontSize: 13,
            }}
          >
            {availableStatuses.map(status => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
      </div>

      {board && !modules.length && (
        <div className="empty-state" style={{ margin: '30px 0' }}>
          <Layers size={36} />
          <h3>No modules match this status</h3>
          <p>No modules match this status. A current approved plan is required to queue conversion.</p>
        </div>
      )}

      {/* Modules Cards Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
          gap: 18,
          marginTop: 16,
        }}
      >
        {modules.map(module => {
          const isRepaired =
            module.status === 'VERIFIED' &&
            module.attempts.some(attempt => attempt.attempt_number > 1 && attempt.status === 'VERIFIED');

          return (
            <section
              key={module.module_id}
              style={{
                ...panelStyle,
                borderLeft: `4px solid ${
                  module.status === 'VERIFIED'
                    ? 'var(--success)'
                    : module.status === 'LEASED' || module.status === 'RUNNING'
                    ? 'var(--info)'
                    : module.status === 'BLOCKED' || module.status === 'FAILED'
                    ? 'var(--destructive)'
                    : 'var(--border)'
                }`,
              }}
            >
              {/* Card Header */}
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <FileCode2 size={15} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                    <h2
                      style={{
                        margin: 0,
                        fontSize: 16,
                        fontWeight: 700,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {module.name}
                    </h2>
                  </div>
                  {module.target_path && (
                    <small
                      style={{
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--muted-foreground)',
                        fontSize: 11,
                        display: 'block',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {module.target_path}
                    </small>
                  )}
                </div>
                <StatusBadge status={module.status} />
              </div>

              {/* Status Text (Preserved for test assertions) */}
              <p style={{ margin: '2px 0', fontSize: 12, color: 'var(--muted-foreground)' }}>
                Status: {module.status}
                {isRepaired ? ' · repaired and independently reverified' : ''}
              </p>

              {/* Dependency Blockers */}
              {module.dependency_blockers.length > 0 && (
                <div
                  style={{
                    background: 'var(--warning-surface)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 12px',
                    margin: '4px 0',
                  }}
                >
                  <h3
                    style={{
                      margin: '0 0 4px',
                      fontSize: 12,
                      fontWeight: 650,
                      color: 'var(--warning)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                    }}
                  >
                    <AlertTriangle size={13} /> Dependency blockers
                  </h3>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11, color: 'var(--foreground)' }}>
                    {module.dependency_blockers.map(blocker => (
                      <li key={blocker}>{blocker}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Queue Conversion Action */}
              {board?.allowed_actions?.includes('queue') && (
                <div style={{ margin: '6px 0' }}>
                  <button
                    className="button button-primary"
                    style={{ width: '100%', fontSize: 12, padding: '7px 12px' }}
                    disabled={
                      busy ||
                      module.attempts.length > 0 ||
                      module.dependency_blockers.length > 0 ||
                      ['LEASED', 'RUNNING', 'QUEUED', 'GENERATED', 'VERIFYING', 'VERIFIED'].includes(module.status)
                    }
                    onClick={() =>
                      void act(`queue:${jobId}:${module.module_id}`, key =>
                        api.queueModuleConversion(jobId, module.module_id, key)
                      )
                    }
                  >
                    Queue conversion
                  </button>
                </div>
              )}

              {/* Attempt History */}
              <div style={{ marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 10 }}>
                <h3
                  style={{
                    fontSize: 12,
                    fontWeight: 650,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    color: 'var(--muted-foreground)',
                    margin: '0 0 8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <History size={13} /> Attempt history
                </h3>

                {!module.attempts.length && (
                  <p style={{ margin: 0, fontSize: 12, color: 'var(--muted-foreground)' }}>
                    No attempts recorded.
                  </p>
                )}

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {module.attempts.map(attempt => (
                    <div
                      key={attempt.attempt_id}
                      style={{
                        background: 'var(--secondary)',
                        padding: '10px 12px',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                        <button
                          className="button button-secondary"
                          style={{ fontSize: 12, padding: '4px 8px', height: 'auto' }}
                          disabled={busy}
                          onClick={() => void openEvidence(attempt.attempt_id)}
                        >
                          Attempt {attempt.attempt_number}: {attempt.status}
                        </button>
                        <StatusBadge status={attempt.status} />
                      </div>

                      {attempt.git_branch && (
                        <div style={{ marginTop: 6 }}>
                          <span
                            style={{
                              fontFamily: 'var(--font-mono)',
                              fontSize: 10,
                              color: 'var(--muted-foreground)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 4,
                            }}
                          >
                            <GitBranch size={11} /> <code>{attempt.git_branch}</code>
                          </span>
                        </div>
                      )}

                      {attempt.failure_reason && (
                        <div
                          style={{
                            marginTop: 6,
                            color: 'var(--destructive)',
                            fontSize: 11,
                            background: 'var(--danger-surface)',
                            padding: '6px 8px',
                            borderRadius: 'var(--radius-sm)',
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: 6,
                          }}
                        >
                          <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                          <p style={{ margin: 0 }}>{attempt.failure_reason}</p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </section>
          );
        })}
      </div>

      {/* Selected Evidence Drawer / Modal */}
      {selected && (
        <div style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <button
              className="button button-secondary"
              onClick={() => {
                selection.current++;
                setSelected(null);
              }}
            >
              <X size={14} /> Close evidence
            </button>
          </div>
          <ModuleEvidence
            key={selected.attempt_id}
            attempt={selected}
            busy={busy}
            onRepair={rationale =>
              void act(`repair:${selected.attempt_id}:${rationale}`, key =>
                api.requestModuleRepair(selected.attempt_id, key, rationale)
              )
            }
            onWaiver={(findingId, rationale) =>
              void act(`waiver:${selected.attempt_id}:${findingId}:${rationale}`, () =>
                api.requestModuleWaiver(selected.attempt_id, findingId, rationale)
              )
            }
          />
        </div>
      )}
    </div>
  );
}
