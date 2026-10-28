import React, { useEffect, useRef, useState } from 'react';
import type { Job } from '../types/domain';
import type { ModuleAttempt, ModuleExecutionBoard } from '../types/phase6';
import { api } from '../services/api';

const panel: React.CSSProperties = { padding: 18, border: '1px solid var(--border)', borderRadius: 8, marginBottom: 16 };
const preview: React.CSSProperties = { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 320, overflow: 'auto', fontSize: 12 };
const json = (value: unknown) => JSON.stringify(value, null, 2) ?? 'Not recorded';
const statuses = ['ALL', 'QUEUED', 'RUNNING', 'BLOCKED', 'REPAIRED', 'VERIFIED', 'REJECTED', 'FAILED', 'ESCALATED'];

export function ModuleEvidence({ attempt, busy = false, onRepair, onWaiver }: {
  attempt: ModuleAttempt;
  busy?: boolean;
  onRepair?: (rationale: string) => void;
  onWaiver?: (findingId: string, rationale: string) => void;
}) {
  const [rationale, setRationale] = useState('');
  const evidence = attempt.evidence || {};
  const permitted = attempt.allowed_actions || [];
  return <section style={panel} aria-label="Module evidence drawer">
    <h2>Attempt {attempt.attempt_number} evidence</h2>
    <p>Status: {attempt.status}</p>
    {attempt.failure_reason && <p role="alert">{attempt.failure_reason}</p>}
    <div style={{ marginBottom: 12 }}>
      <strong>Provider mode: </strong>
      {(evidence.provider === 'openai' || attempt.metadata?.model_provider === 'openai' || evidence.model_provider === 'openai') ? (
        <span className="badge badge-success" style={{ backgroundColor: '#059669', color: '#fff', padding: '2px 8px', borderRadius: 4, fontWeight: 'bold' }}>REAL OPENAI EXECUTION</span>
      ) : (
        <span className="badge badge-warning" style={{ backgroundColor: '#d97706', color: '#fff', padding: '2px 8px', borderRadius: 4, fontWeight: 'bold' }}>DETERMINISTIC / FAKE PROVIDER</span>
      )}
    </div>
    <dl>
      <dt>Model</dt><dd>{
        typeof evidence.model === 'string'
          ? evidence.model
          : typeof attempt.metadata?.model_identifier === 'string'
            ? attempt.metadata.model_identifier
            : 'Not recorded'
      }</dd>
      <dt>Branch</dt><dd>{attempt.git_branch || 'Not created'}</dd>
      <dt>Source commit</dt><dd>{evidence.source_commit || 'Not recorded'}</dd>
      <dt>Frozen baseline hash</dt><dd style={{ overflowWrap: 'anywhere' }}>{evidence.baseline_hash || 'Not recorded'}</dd>
    </dl>
    <h3>Changed files</h3>
    {(evidence.changed_files || []).length ? <ul>{evidence.changed_files!.map(path => <li key={path}>{path}</li>)}</ul> : <p>No changed files recorded.</p>}
    <h3>Diff</h3><pre style={preview}>{evidence.diff || 'No diff recorded.'}</pre>
    <h3>Independent verification</h3>
    {!evidence.checks?.length && <p role="alert">No execution evidence recorded. This attempt cannot establish verified behavior.</p>}
    {(evidence.checks || []).map((check, index) => <article key={index} style={panel}>
      <h4>{check.category}: {check.status}</h4>
      <p>Exit code: {check.exit_code ?? 'Not executed'} · Duration: {check.duration_ms} ms</p>
      <pre style={preview}>{json(check.command)}</pre>
      <p style={{ overflowWrap: 'anywhere' }}>Evidence hash: {check.artifact_hash || 'Not recorded'}</p>
      <details><summary>Captured stdout / stderr</summary><pre style={preview}>{check.stdout || '(empty stdout)'}{'\n'}{check.stderr || '(empty stderr)'}</pre></details>
    </article>)}
    <h3>Frozen characterization results</h3>
    {Array.isArray(evidence.results) && evidence.results.length ? <pre style={preview}>{json(evidence.results)}</pre> : <p>No executed characterization results recorded.</p>}
    <h3>Reviewer findings</h3><p>Review status: {evidence.review?.status || 'Not recorded'}</p>
    {(evidence.review?.findings || []).map(finding => <article style={panel} key={finding.finding_id}>
      <h4>{finding.severity} · {finding.category}</h4><p>{finding.message}</p>
      {finding.path && <p>{finding.path}{finding.line ? `:${finding.line}` : ''}</p>}
      <p>Evidence reference: {finding.evidence_ref || 'Not recorded'}</p>
      {permitted.includes('waiver') && onWaiver && <button className="button" disabled={busy || rationale.trim().length < 10} onClick={() => onWaiver(finding.finding_id, rationale.trim())}>Request human review / waiver</button>}
    </article>)}
    <h3>Design notes and assumptions</h3><pre style={preview}>{json({ design_notes: evidence.design_notes, assumptions: evidence.assumptions })}</pre>
    <h3>Repair feedback</h3><pre style={preview}>{json(evidence.repair_feedback)}</pre>
    <details><summary>Recorded tool trace and agent metadata</summary><pre style={preview}>{json(attempt.metadata)}</pre><pre style={preview}>{json(evidence)}</pre></details>
    {(permitted.includes('repair') || permitted.includes('waiver')) && <>
      <label htmlFor="module-rationale">Repair / human review rationale</label>
      <textarea id="module-rationale" rows={3} value={rationale} onChange={event => setRationale(event.target.value)} style={{ display: 'block', width: '100%' }} />
      <p>Repair uses recorded failing evidence and reruns required checks. Waiver requests require backend authorization and an audit record.</p>
      {permitted.includes('repair') && onRepair && <button className="button" disabled={busy || rationale.trim().length < 10} onClick={() => onRepair(rationale.trim())}>Request bounded repair</button>}
    </>}
  </section>;
}

export function ModuleExecution({ jobs }: { jobs: Job[] }) {
  const [jobId, setJobId] = useState(jobs[0]?.job_id || '');
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
    if (!jobId && jobs.length) setJobId(jobs[0].job_id);
  }, [jobs, jobId]);

  useEffect(() => {
    const version = ++generation.current;
    selection.current++;
    setBoard(null); setSelected(null); setError(''); setNotice('');
    if (!jobId) return;
    const refresh = () => load(jobId, version).catch(err => {
      if (generation.current === version) setError(err instanceof Error ? err.message : 'Could not load module attempts.');
    });
    void refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => { generation.current++; window.clearInterval(timer); };
  }, [jobId]);

  async function openEvidence(attemptId: string) {
    const version = generation.current;
    const selectedVersion = ++selection.current;
    setBusy(true); setError(''); setSelected(null);
    try {
      const [attempt, diff, tests, review] = await Promise.all([
        api.getModuleAttempt(attemptId), api.getModuleAttemptDiff(attemptId),
        api.getModuleAttemptChecks(attemptId), api.getModuleAttemptReview(attemptId),
      ]);
      if (generation.current === version && selection.current === selectedVersion) setSelected({
        ...attempt, evidence: { ...attempt.evidence, ...diff, checks: tests.checks, review },
      });
    } catch (err) {
      if (generation.current === version) setError(err instanceof Error ? err.message : 'Could not retrieve module evidence.');
    } finally { if (generation.current === version) setBusy(false); }
  }

  async function act(identity: string, action: (key: string) => Promise<unknown>) {
    setBusy(true); setError(''); setNotice('');
    const key = pendingKeys.current.get(identity) || crypto.randomUUID();
    pendingKeys.current.set(identity, key);
    try {
      await action(key);
      pendingKeys.current.delete(identity);
      setNotice('Request recorded. Status and eligibility are determined by the Supervisor and independent checks.');
      await load(jobId, generation.current);
      if (selected) await openEvidence(selected.attempt_id);
    } catch (err) { setError(err instanceof Error ? err.message : 'Module request failed.'); }
    finally { setBusy(false); }
  }

  const modules = (board?.modules || []).filter(module => filter === 'ALL' || module.status === filter || (filter === 'REPAIRED' && module.status === 'VERIFIED' && module.attempts.some(attempt => attempt.attempt_number > 1 && attempt.status === 'VERIFIED')));
  return <div>
    <div className="page-heading"><div><h1>Module execution board</h1><p className="subtitle">CodeWriter attempts, independent verification, reviewer findings and bounded repair.</p></div></div>
    <label>Modernization job <select aria-label="Modernization job" disabled={busy} value={jobId} onChange={event => setJobId(event.target.value)}>
      {!jobs.length && <option value="">No jobs available</option>}
      {jobs.map(job => <option key={job.job_id} value={job.job_id}>{job.name}</option>)}
    </select></label>
    <button className="button" disabled={!jobId || busy} onClick={() => void act(`refresh:${jobId}`, () => load(jobId, generation.current))}>Refresh evidence</button>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}{busy && <p role="status">Loading module evidence…</p>}
    {board && !board.runtime_available && <p role="alert">Conversion sandbox unavailable. Modules remain blocked until a real isolated runtime is available; no execution success is inferred.</p>}
    <p>G1 constraints, the frozen G2 baseline and approved G3 plan govern execution. Only dependency-ready modules may run. Each attempt retains its own branch and evidence.</p>
    <label>Module status <select aria-label="Module status" value={filter} onChange={event => setFilter(event.target.value)}>{[...new Set([...statuses, ...(board?.modules || []).map(module => module.status)])].map(status => <option key={status}>{status}</option>)}</select></label>
    {board && !modules.length && <p>No modules match this status. A current approved plan is required to queue conversion.</p>}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginTop: 16 }}>
      {modules.map(module => <section key={module.module_id} style={panel}>
        <h2>{module.name}</h2><p>Status: {module.status}{module.status === 'VERIFIED' && module.attempts.some(attempt => attempt.attempt_number > 1 && attempt.status === 'VERIFIED') ? ' · repaired and independently reverified' : ''}</p>
        {module.dependency_blockers.length > 0 && <><h3>Dependency blockers</h3><ul>{module.dependency_blockers.map(blocker => <li key={blocker}>{blocker}</li>)}</ul></>}
        {board?.allowed_actions?.includes('queue') && <button className="button" disabled={busy || module.attempts.length > 0 || module.dependency_blockers.length > 0 || ['LEASED', 'RUNNING', 'QUEUED', 'GENERATED', 'VERIFYING', 'VERIFIED'].includes(module.status)} onClick={() => void act(`queue:${jobId}:${module.module_id}`, key => api.queueModuleConversion(jobId, module.module_id, key))}>Queue conversion</button>}
        <h3>Attempt history</h3>
        {!module.attempts.length && <p>No attempts recorded.</p>}
        {module.attempts.map(attempt => <div key={attempt.attempt_id} style={{ marginBottom: 8 }}>
          <button className="button" disabled={busy} onClick={() => void openEvidence(attempt.attempt_id)}>Attempt {attempt.attempt_number}: {attempt.status}</button>
          {attempt.git_branch && <div><code>{attempt.git_branch}</code></div>}
          {attempt.failure_reason && <p>{attempt.failure_reason}</p>}
        </div>)}
      </section>)}
    </div>
    {selected && <><button className="button" onClick={() => { selection.current++; setSelected(null); }}>Close evidence</button><ModuleEvidence key={selected.attempt_id} attempt={selected} busy={busy}
      onRepair={rationale => void act(`repair:${selected.attempt_id}:${rationale}`, key => api.requestModuleRepair(selected.attempt_id, key, rationale))}
      onWaiver={(findingId, rationale) => void act(`waiver:${selected.attempt_id}:${findingId}:${rationale}`, () => api.requestModuleWaiver(selected.attempt_id, findingId, rationale))} /></>}
  </div>;
}
