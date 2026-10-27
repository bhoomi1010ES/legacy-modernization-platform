import React, { useEffect, useRef, useState } from 'react';
import type { DecisionOutcome, Job, VersionedGate } from '../types/domain';
import type { CharacterizationReport, DataMigrationPlan, SchemaAnalysis } from '../types/phase5';
import { api } from '../services/api';

const json = (value: unknown) => JSON.stringify(value, null, 2) ?? 'Not captured';
const panel: React.CSSProperties = { padding: 18, marginBottom: 16, border: '1px solid var(--border)', borderRadius: 8 };
const preview: React.CSSProperties = { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 280, overflow: 'auto', fontSize: 12 };
const captureExample = {
  scenarios: [{ name: 'Read payment', module: 'payments', interface: 'GET /payments/:id', behavior: 'Existing payment response', inputs: { id: 1 }, expected: { id: 1 }, normalization: [{ path: '/timestamp', kind: 'timestamp', justification: 'Generated response timestamp varies' }] }],
  tables: [{ name: 'payments', columns: [{ name: 'id', type: 'INTEGER', nullable: false, primary_key: true, unique: true }] }],
  target_tables: [{ name: 'payments', columns: [{ name: 'id', type: 'INTEGER', nullable: false, primary_key: true, unique: true }] }],
  environment: { notes: 'Requires an isolated legacy runtime; configuration notes do not provision it.' },
};

export function BaselineEvidence({ report }: { report: CharacterizationReport }) {
  return <section style={panel} aria-label="Baseline coverage and limitations">
    <h2>Baseline coverage: {report.coverage.percent}%</h2>
    {!report.runtime_available && <p role="alert">Legacy test environment unavailable. Discovery alone does not prove behavior equivalence.</p>}
    {!report.cases.some(item => item.evidence_status === 'OBSERVED' || item.outcome === 'PASSED') && <p role="alert">Required baseline evidence is unobserved. G2 approval is blocked.</p>}
    {report.schema_status === 'REVIEW_REQUIRED' && <p role="alert">Manual schema review required. Unsupported semantics must be resolved before G2 approval.</p>}
    {report.schema_status !== 'NOT_APPLICABLE' && report.schema_validation_status !== 'PASS' && <p role="alert">Schema/data validation is incomplete. DDL-only or empty samples do not satisfy G2.</p>}
    {report.cases.filter(item => item.limitation).map(item => <p role="alert" key={item.test_case_id}>{item.name}: {item.limitation}</p>)}
    {(report.coverage.percent < 80 || report.coverage.untested_paths.length > 0) && <p role="alert">Weak behavior coverage: review untested paths before approval.</p>}
    {(['modules', 'interfaces', 'behaviors'] as const).map(kind => <div key={kind}>
      <h3>{kind[0].toUpperCase() + kind.slice(1)}</h3>
      <ul>{report.coverage[kind].map(item => <li key={item.name}>{item.name}: {item.status || (item.covered ? 'Covered' : 'Untested')}{item.observed ? ' · OBSERVED' : ''}</li>)}</ul>
    </div>)}
    <h3>Untested paths and limitations</h3>
    {report.discovery_evidence && <><h3>Discovered tests (execution tracked separately)</h3><pre style={preview}>{json(report.discovery_evidence)}</pre></>}
    <ul>{[...report.coverage.untested_paths, ...report.coverage.limitations].map((item, i) => <li key={i}>{item}</li>)}</ul>
    <h3>Known legacy bugs</h3><pre style={preview}>{json(report.known_bugs)}</pre>
    <h3>Normalization rules</h3><pre style={preview}>{json(report.normalization)}</pre>
    <h3>Replay environment and configuration</h3><pre style={preview}>{json(report.environment)}</pre>
  </section>;
}

export function Characterization({ jobs }: { jobs: Job[] }) {
  const [jobId, setJobId] = useState(jobs[0]?.job_id || '');
  const [report, setReport] = useState<CharacterizationReport | null>(null);
  const [schema, setSchema] = useState<SchemaAnalysis | null>(null);
  const [migration, setMigration] = useState<DataMigrationPlan | null>(null);
  const [gate, setGate] = useState<VersionedGate | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('');
  const [outcome, setOutcome] = useState('ALL');
  const [selectedCase, setSelectedCase] = useState('');
  const [captureInput, setCaptureInput] = useState('{}');
  const [tableInput, setTableInput] = useState('[]');
  const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
  const [rationale, setRationale] = useState('');
  const generation = useRef(0);
  const captureRetryKey = useRef<{ payload: string; key: string } | null>(null);

  async function load(id: string, requestGeneration: number) {
    const results = await Promise.allSettled([
      api.getCharacterizationReport(id), api.getSchemaAnalysis(id), api.getDataMigrationPlan(id),
    ]);
    if (generation.current !== requestGeneration) return;
    const [baseline, schemaResult, migrationResult] = results;
    const failures = results.filter(result => result.status === 'rejected');
    if (failures.length) setError(failures.map(result => result.status === 'rejected' ? String(result.reason?.message || result.reason) : '').join('; '));
    if (schemaResult.status === 'fulfilled') setSchema(schemaResult.value);
    if (migrationResult.status === 'fulfilled') setMigration(migrationResult.value);
    if (baseline.status === 'fulfilled') {
      setReport(baseline.value);
      if (baseline.value.gate_id) {
        const currentGate = await api.getVersionedGate(baseline.value.gate_id);
        if (generation.current === requestGeneration) setGate(currentGate);
      }
    }
  }

  useEffect(() => {
    const current = ++generation.current;
    setReport(null); setGate(null); setSchema(null); setMigration(null); setValidation(null);
    setError(''); setNotice(''); setSelectedCase(''); setRationale('');
    if (!jobId) return;
    setBusy(true);
    load(jobId, current).catch(err => {
      if (generation.current === current) setError(err.message);
    }).finally(() => { if (generation.current === current) setBusy(false); });
    return () => { generation.current++; };
  }, [jobId]);

  async function act(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch (err) { setError(err instanceof Error ? err.message : 'Request failed'); }
    finally { setBusy(false); }
  }

  async function decide(decision: DecisionOutcome) {
    if (!gate || !rationale.trim()) return;
    await api.decideVersionedGate(gate, decision, rationale);
    setNotice(`G2 ${decision.toLowerCase().replace('_', ' ')} recorded.`);
    await load(jobId, generation.current);
  }

  const cases = (report?.cases || []).filter(item =>
    (outcome === 'ALL' || item.outcome === outcome) &&
    `${item.name} ${item.module} ${item.interface} ${item.behavior}`.toLowerCase().includes(filter.toLowerCase()));
  const currentCase = cases.find(item => item.test_case_id === selectedCase) || cases[0];
  const canDecide = Boolean(gate?.status === 'PENDING' && rationale.trim() && !busy);

  return <div>
    <div className="page-heading"><div><h1>Characterization &amp; schema review</h1><p className="subtitle">Capture legacy behavior, review gaps and approve a versioned baseline at G2.</p></div></div>
    <label>Modernization job <select aria-label="Modernization job" disabled={busy} value={jobId} onChange={event => setJobId(event.target.value)}>
      {!jobs.length && <option value="">No jobs available</option>}
      {jobs.map(job => <option key={job.job_id} value={job.job_id}>{job.name}</option>)}
    </select></label>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}{busy && <p role="status">Processing characterization evidence…</p>}
    <section style={panel}><h2>Capture / revise suite</h2>
      <p>Supply approved scenarios for legacy sandbox observations as JSON. A revision creates a new suite version and requires renewed G2 approval. Expected values are review assertions; actual results must come from the legacy sandbox.</p>
      <p>The backend does not provision a legacy runtime automatically. Environment fields record replay configuration notes only.</p>
      <label htmlFor="capture-input">Capture request JSON</label>
      <textarea id="capture-input" rows={5} style={{ display: 'block', width: '100%' }} value={captureInput} onChange={event => setCaptureInput(event.target.value)} />
      <details><summary>Capture request example and supported fields</summary><pre style={preview}>{json(captureExample)}</pre><p>Normalization kind: timestamp, random_id or unordered. Unordered comparisons require contract_allows: true. Every rule needs a path and justification. Scenarios may include known_bug. Columns support INTEGER, REAL, TEXT or BLOB, with nullable, primary_key, unique, max_length, references_table and references_column. An idempotency_key is generated automatically when omitted.</p></details>
      <button className="button" disabled={!jobId || busy} onClick={() => act(async () => {
        const payload: unknown = JSON.parse(captureInput);
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('Capture request must be a JSON object.');
        const requestPayload = payload as Record<string, unknown>;
        if (!Object.hasOwn(requestPayload, 'idempotency_key')) {
          const retryIdentity = `${jobId}:${captureInput}`;
          if (captureRetryKey.current?.payload !== retryIdentity) captureRetryKey.current = { payload: retryIdentity, key: crypto.randomUUID() };
          requestPayload.idempotency_key = captureRetryKey.current.key;
        }
        await api.runCharacterization(jobId, requestPayload);
        captureRetryKey.current = null;
        await load(jobId, generation.current);
      })}>Capture / replay characterization</button>
    </section>
    {report && <>
      <BaselineEvidence report={report} />
      <section style={panel}><h2>Test-case review</h2>
        <label>Filter tests <input value={filter} onChange={event => setFilter(event.target.value)} placeholder="Module, interface or behavior" /></label>
        <label> Outcome <select value={outcome} onChange={event => setOutcome(event.target.value)}><option value="ALL">All outcomes</option>{[...new Set(report.cases.map(item => item.outcome))].map(value => <option key={value}>{value}</option>)}</select></label>
        <p>{cases.length} of {report.cases.length} cases</p>
        <div className="table-wrap"><table><thead><tr><th>Case</th><th>Module / interface</th><th>Behavior</th><th>Outcome</th></tr></thead><tbody>
          {cases.map(item => <tr key={item.test_case_id}><td><button className="button" onClick={() => setSelectedCase(item.test_case_id)}>{item.name}</button></td><td>{item.module} / {item.interface}</td><td>{item.behavior}</td><td>{item.outcome}</td></tr>)}
        </tbody></table></div>
        {!cases.length && <p>No matching test cases. Untested behavior remains a gap.</p>}
        {currentCase && <div><h3>{currentCase.name}</h3><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
          <div><h4>Expected</h4><pre style={preview}>{json(currentCase.expected)}</pre></div><div><h4>Actual</h4><pre style={preview}>{json(currentCase.actual)}</pre></div>
        </div><h4>Fixtures and side effects</h4><pre style={preview}>{json({ fixtures: currentCase.fixtures, side_effects: currentCase.side_effects })}</pre><h4>Case normalization</h4><pre style={preview}>{json(currentCase.normalization)}</pre>{currentCase.known_bug && <p>Known bug: {currentCase.known_bug}</p>}</div>}
      </section>
      <section style={panel}><h2>G2 baseline approval</h2><p>Suite v{report.version} · {report.status}</p><p style={{ overflowWrap: 'anywhere' }}>Content hash: <code>{report.content_hash}</code></p>
        <button className="button" disabled={busy || report.status === 'FROZEN' || report.status === 'APPROVED' || gate?.status === 'PENDING'} onClick={() => act(async () => {
          const frozen = await api.freezeCharacterization(jobId, report.suite_id, report.content_hash);
          setGate(await api.getVersionedGate(frozen.gate_id));
          setNotice('G2 review requested. A human decision is required to freeze this suite.');
        })}>Request G2 freeze review</button>
        {gate && <p>G2 v{gate.version}: {gate.status}</p>}
        <label htmlFor="g2-rationale">Review rationale / revision feedback</label><textarea id="g2-rationale" rows={3} style={{ display: 'block', width: '100%' }} value={rationale} onChange={event => setRationale(event.target.value)} />
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>{(['APPROVED', 'REJECTED', 'NEEDS_CHANGES'] as const).map(decision => <button key={decision} className="button" disabled={!canDecide || !gate?.allowed_actions.includes({ APPROVED: 'approve', REJECTED: 'reject', NEEDS_CHANGES: 'request_changes' }[decision])} onClick={() => act(() => decide(decision))}>{({ APPROVED: 'Approve G2', REJECTED: 'Reject G2', NEEDS_CHANGES: 'Request revision' })[decision]}</button>)}</div>
      </section>
    </>}
    {schema && <section style={panel}><h2>Schema inventory &amp; differences</h2><h3>Tables, keys, constraints and relationships</h3><pre style={preview}>{json(schema.tables)}</pre><h3>Schema differences</h3><pre style={preview}>{json(schema.differences)}</pre><h3>Limitations</h3><pre style={preview}>{json(schema.limitations)}</pre></section>}
    {migration && <section style={panel}><h2>Data-mapping review</h2><p>Scope: {migration.scope}. Validation runs against a disposable database; no production migration is executed.</p><h3>Mapping rules</h3><pre style={preview}>{json(migration.mappings)}</pre><h3>Upgrade proposal</h3><pre style={preview}>{migration.upgrade_sql}</pre><h3>Rollback proposal</h3><pre style={preview}>{migration.rollback_sql}</pre><h3>Validation queries</h3><pre style={preview}>{json(migration.validation_queries)}</pre><h3>Risks</h3><pre style={preview}>{json(migration.risks)}</pre>
      <label htmlFor="validation-data">Disposable fixture tables JSON</label><textarea id="validation-data" rows={4} style={{ display: 'block', width: '100%' }} value={tableInput} onChange={event => setTableInput(event.target.value)} />
      <button className="button" disabled={busy || migration.scope !== 'disposable'} onClick={() => act(async () => {
        const tables: unknown = JSON.parse(tableInput);
        if (!Array.isArray(tables)) throw new Error('Disposable tables must be a JSON array.');
        setValidation(await api.validateDataMigrationPlan(jobId, tables));
        await load(jobId, generation.current);
      })}>Validate in disposable database</button>
      {validation && <><h3>Validation result</h3><pre style={preview}>{json(validation)}</pre></>}
    </section>}
  </div>;
}
