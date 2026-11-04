import React, { useEffect, useRef, useState } from 'react';
import type { Job } from '../types/domain';
import type { FinalDelivery } from '../types/phase7';
import { api } from '../services/api';
import { fetchVerifiedZip } from '../services/verifiedDownload';

const box: React.CSSProperties = { border: '1px solid var(--border)', borderRadius: 8, padding: 18, marginBottom: 16 };
const preview: React.CSSProperties = { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 350, overflow: 'auto', fontSize: 12 };
const json = (value: unknown) => JSON.stringify(value, null, 2);

export function FinalEvidence({ delivery }: { delivery: FinalDelivery }) {
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  async function downloadZip() {
    const zip = delivery.delivery_zip;
    if (!delivery.delivery_ready || !zip) return;
    setDownloadBusy(true); setDownloadError('');
    try {
      const blob = await fetchVerifiedZip(delivery.job_id, zip.artifact_id, zip.sha256);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `modernized-project-${zip.artifact_id}.zip`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'ZIP download failed.');
    } finally { setDownloadBusy(false); }
  }
  const artifact = delivery.report;
  const report = artifact?.content;
  const downloadable = delivery.allowed_actions.includes('download');
  return <>
    <section style={box} aria-label="Delivery readiness">
      <h2>{delivery.delivery_ready ? 'Delivery ready — human G4 approved' : 'Not delivery ready'}</h2>
      <p>Backend workflow: {delivery.job_status}</p>
      <p>Production deployment / cutover is not included. No automatic merge to the default branch.</p>
      {delivery.limitations.map((message, index) => <p role="alert" key={index}>{message}</p>)}
      {delivery.report && !delivery.package_current && <p role="alert">Evidence is blocked, rejected or stale. An existing artifact is not proof of current verification.</p>}
      {delivery.delivery_record && <p>Delivery timestamp: {delivery.delivery_record.content.delivered_at}</p>}
    </section>
    {!report || !artifact ? <p role="alert">No final integration report. Verified module artifacts alone cannot establish delivery readiness.</p> : <>
      <section style={box} aria-label="Exact G4 evidence">
        <h2>Exact candidate for G4 review</h2>
        <p>Report version {artifact.version} · {report.status}</p>
        <p>Candidate tree SHA-256: <code>{report.candidate_hash}</code></p>
        <p>Report SHA-256: <code>{artifact.content_hash}</code></p>
        <p>Source commit: {report.source_commit}</p>
        <p>{report.source_stack} → {report.target_stack}</p>
        <p>Frozen baseline: <code>{report.baseline_hash}</code></p>
        <p>Approved plan: <code>{report.plan_hash}</code></p>
        {downloadable && artifact.download_url && <a className="button" href={artifact.download_url}>Download exact JobReport JSON</a>}
        {downloadable && delivery.delivery_ready && delivery.package_current && delivery.delivery_zip?.download_url && <button className="button" disabled={downloadBusy} onClick={() => void downloadZip()}>{downloadBusy ? 'Verifying ZIP download…' : 'Download modernized project ZIP'}</button>}
        {downloadError && <p role="alert">{downloadError}</p>}
        {delivery.delivery_zip?.packaging_timestamp && <p>Packaged: {delivery.delivery_zip.packaging_timestamp}</p>}
        {delivery.delivery_zip && <p>Project ZIP SHA-256: <code>{delivery.delivery_zip.sha256}</code>; manifest SHA-256: <code>{delivery.delivery_zip.manifest_hash}</code></p>}
      </section>
      <section style={box} aria-label="Module matrix">
        <h2>Module matrix and source lineage</h2>
        <table><thead><tr><th>Module</th><th>Status</th><th>Attempt</th><th>Base SHA / ChangeSet diff SHA-256</th></tr></thead><tbody>{report.modules.map(module => <tr key={module.module_id}><td>{module.name}</td><td>{module.status}</td><td>{module.attempt_id}</td><td>{module.base_sha}<br />{module.diff_hash}</td></tr>)}</tbody></table>
        {report.modules.map(module => <details key={module.module_id}><summary>Changed files and diff: {module.name}</summary><ul>{module.changed_files.map(path => <li key={path}>{path}</li>)}</ul><pre style={preview}>{module.diff}</pre></details>)}
        {!!report.evidence.integration.conflicts?.length && <p role="alert">Unresolved merge conflicts: {report.evidence.integration.conflicts.join(', ')}</p>}
        <details><summary>Integrated diff / merge history</summary><pre style={preview}>{report.evidence.integration.diff}</pre><pre style={preview}>{json(report.evidence.integration.merge_history)}</pre></details>
      </section>
      <section style={box} aria-label="System verification">
        <h2>Full-system verification</h2>
        <p>{report.counts.passed} / {report.counts.total} frozen cases matched; {report.counts.executed} executed; {report.counts.failed} failed; {report.counts.unobserved} unobserved.</p>
        {(!report.counts.executed || report.counts.unobserved > 0) && <p role="alert">Required execution evidence is missing. Unobserved cases are not PASS.</p>}
        {report.evidence.verification.reason && <p role="alert">{report.evidence.verification.reason}</p>}
        {(report.evidence.verification.checks || []).map((check, index) => <details key={index}><summary>{check.category}: {check.status} · exit {check.exit_code ?? 'not executed'} · {check.duration_ms} ms</summary><pre style={preview}>{json(check.command)}{'\n'}{check.stdout}{'\n'}{check.stderr}</pre></details>)}
        <p>Image: {report.evidence.verification.image_id || 'Not executed'}; container: {report.evidence.verification.container_name || 'Not recorded'}</p>
      </section>
      <section style={box} aria-label="Coverage findings and waivers">
        <h2>Coverage, findings, waivers and limitations</h2>
        <p>Scenario/interface coverage only — no branch or line coverage claim.</p>
        <p>Uncovered behavior: {report.coverage.untested_paths?.join(', ') || 'No additional paths listed; review limitations'}</p>
        {!!report.coverage.untested_paths?.length && <p role="alert">Untested paths remain outside proven equivalence.</p>}
        <h3>Known legacy bugs</h3><pre style={preview}>{json(report.coverage.known_legacy_bugs || [])}</pre>
        <h3>Normalization rules</h3><pre style={preview}>{json(report.coverage.normalization || [])}</pre>
        <h3>Reviewer findings</h3>{report.findings.map(finding => <p key={finding.finding_id}>{finding.severity}: {finding.message} · evidence {finding.evidence_ref}</p>)}
        <h3>Recorded waivers</h3><pre style={preview}>{json(report.waivers)}</pre>
        {report.limitations.map((message, index) => <p key={index}>{message}</p>)}
        <details><summary>Decisions, costs and durations</summary><pre style={preview}>{json({ decisions: report.decisions, costs: report.costs, duration_ms: report.duration_ms })}</pre></details>
      </section>
      <section style={box} aria-label="SBOM evidence">
        <h2>SBOM: {report.evidence.sbom.status}</h2>
        <p>Tool: {report.evidence.sbom.tool || 'Not selected'} · version: {report.evidence.sbom.tool_version || 'Not executed'} · format: {report.evidence.sbom.format || 'Not generated'}</p>
        <p>SHA-256: {report.evidence.sbom.hash}</p>
        {report.evidence.sbom.status !== 'GENERATED' ? <p role="alert">SBOM unavailable, invalid or unsupported. No standard or successful generation is claimed; G4 remains blocked.</p> : downloadable && <a className="button" href={`/api/v1/jobs/${delivery.job_id}/artifacts/${report.evidence.sbom.artifact_id}/download`}>Download exact SBOM evidence JSON</a>}
      </section>
    </>}
    <section style={box} aria-label="ZIP delivery"><h2>ZIP delivery</h2><p>Conversion does not create Git commits or publish a branch. Download the verified project ZIP above.</p></section>
  </>;
}

export const Reports = ({ jobs }: { jobs: Job[] }) => {
  const [jobId, setJobId] = useState(jobs[0]?.job_id || '');
  const [delivery, setDelivery] = useState<FinalDelivery | null>(null);
  const [rationale, setRationale] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const keys = useRef(new Map<string, string>());
  useEffect(() => { if (!jobId && jobs.length) setJobId(jobs[0].job_id); }, [jobId, jobs]);
  useEffect(() => {
    const version = ++generation.current;
    setDelivery(null); setError(''); setRationale('');
    if (!jobId) return;
    const refresh = () => api.getFinalDelivery(jobId).then(value => { if (generation.current === version) setDelivery(value); }).catch(reason => { if (generation.current === version) setError(reason instanceof Error ? reason.message : 'Failed to load final package'); });
    void refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => { generation.current++; window.clearInterval(timer); };
  }, [jobId]);
  const action = async (name: 'integrate' | 'submit' | 'pr' | 'APPROVED' | 'REJECTED') => {
    if (!delivery) return;
    const version = generation.current;
    const hash = delivery.report?.content_hash;
    const identity = `${jobId}:${name}:${hash || 'no-report'}:${delivery.gate?.gate_id || ''}`;
    if (!keys.current.has(identity)) keys.current.set(identity, crypto.randomUUID());
    const key = keys.current.get(identity)!;
    setBusy(true); setError('');
    try {
      if (name === 'integrate') await api.startIntegration(jobId, key);
      else if (name === 'submit' && hash) await api.submitFinalReview(jobId, hash, key);
      else if (name === 'pr' && hash) await api.createPullRequest(jobId, hash, key);
      else if ((name === 'APPROVED' || name === 'REJECTED') && delivery.gate && rationale.trim().length >= 10) {
        await api.decideFinalGate(delivery.gate.gate_id, delivery.gate.artifact_hashes, name, rationale.trim(), key);
      } else throw new Error('A current report, gate and explanatory rationale are required');
      const fresh = await api.getFinalDelivery(jobId);
      if (generation.current === version) setDelivery(fresh);
      keys.current.delete(identity);
    } catch (reason) { if (generation.current === version) setError(reason instanceof Error ? reason.message : 'Backend rejected the request'); }
    finally { if (generation.current === version) setBusy(false); }
  };
  const allowed = delivery?.allowed_actions || [];
  return <main>
    <h1>Integration & final human review</h1>
    <label>Modernization job <select aria-label="Final review job" value={jobId} onChange={event => setJobId(event.target.value)}>{jobs.map(job => <option key={job.job_id} value={job.job_id}>{job.name}</option>)}</select></label>
    {error && <p role="alert">{error}</p>}
    {!delivery ? <p>Select a job and load its backend evidence.</p> : <>
      <FinalEvidence delivery={delivery} />
      {allowed.includes('integrate') && <button className="button" disabled={busy || !['CONVERTING', 'VERIFYING', 'INTEGRATING'].includes(delivery.job_status)} onClick={() => void action('integrate')}>Start fresh integration verification</button>}
      {allowed.includes('submit_g4') && <button className="button" disabled={busy || !delivery.package_current || delivery.gate?.status === 'PENDING' || delivery.delivery_ready} onClick={() => void action('submit')}>Submit exact package for G4</button>}
      {delivery.gate && <p>G4: {delivery.gate.status} · version {delivery.gate.version}</p>}
      {allowed.includes('decide_g4') && delivery.gate?.status === 'PENDING' && <section style={box}>
        <h2>Human decision on displayed ZIP/report</h2>
        <label htmlFor="final-review-rationale">Approval / rejection rationale</label><textarea id="final-review-rationale" value={rationale} onChange={event => setRationale(event.target.value)} />
        <p>Approval is recorded by the backend GateService. Mandatory failing execution is not silently waived.</p>
        <button className="button" disabled={busy || !delivery.package_current || rationale.trim().length < 10} onClick={() => void action('APPROVED')}>Approve exact G4 evidence</button>
        <button className="button" disabled={busy || rationale.trim().length < 10} onClick={() => void action('REJECTED')}>Reject for revision</button>
      </section>}
    </>}
  </main>;
};
