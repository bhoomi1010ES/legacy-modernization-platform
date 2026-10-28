// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ModuleEvidence, ModuleExecution } from '../pages/ModuleExecution';
import { api } from '../services/api';
import type { ModuleAttempt, ModuleExecutionBoard } from '../types/phase6';
import type { Job } from '../types/domain';

const attempt: ModuleAttempt = {
  attempt_id: 'attempt-1', module_id: 'module-1', attempt_number: 2, status: 'REJECTED',
  git_branch: 'job/job-1/module-1/attempt-2', failure_reason: 'Frozen characterization mismatch',
  allowed_actions: ['repair', 'waiver'],
  evidence: {
    source_commit: 'source-sha', baseline_hash: 'baseline-sha', changed_files: ['target/payments.py'],
    diff: '-return 1\n+return 2\n<script>unsafe()</script>',
    checks: [{ category: 'characterization', command: ['python', '/verify.py'], exit_code: 1, duration_ms: 37, status: 'FAIL', stdout: 'Expected: 1; actual: 2', artifact_hash: 'check-sha' }],
    review: { status: 'REJECTED', findings: [{ finding_id: 'finding-1', severity: 'HIGH', category: 'security', message: 'Unsafe SQL construction', path: 'target/payments.py', line: 12, evidence_ref: 'review-sha:12' }] },
    repair_feedback: { failing_check: 'characterization' },
  },
};
const job = { job_id: 'job-1', name: 'Payments modernization' } as Job;
const board: ModuleExecutionBoard = { runtime_available: false, allowed_actions: ['queue'], items: [attempt], modules: [
  { module_id: 'module-1', name: 'Payments', status: 'REJECTED', dependency_blockers: ['Accounts is not verified'], attempts: [attempt] },
  { module_id: 'module-2', name: 'Accounts', status: 'QUEUED', dependency_blockers: [], attempts: [] },
] };
let root: Root | null = null;
let container: HTMLDivElement;

async function mount(component: React.ReactNode) {
  container = document.createElement('div'); document.body.append(container);
  root = createRoot(container);
  await act(async () => { root!.render(component); });
}

function button(label: string) {
  return [...container.querySelectorAll('button')].find(item => item.textContent === label)!;
}

async function rationale(value: string) {
  const input = container.querySelector('textarea')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

beforeEach(() => { vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); });

afterEach(async () => {
  if (root) await act(async () => root!.unmount());
  root = null; document.body.innerHTML = '';
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

describe('Phase 6 execution evidence', () => {
  it('shows immutable lineage, differences, failing checks and reviewer severity without rendering code as HTML', () => {
    const markup = renderToStaticMarkup(<ModuleEvidence attempt={attempt} />);
    for (const value of ['source-sha', 'baseline-sha', 'check-sha', 'target/payments.py', 'Exit code: 1', '37 ms', 'HIGH', 'review-sha:12', 'Frozen characterization mismatch']) expect(markup).toContain(value);
    expect(markup).toContain('&lt;script&gt;');
    expect(markup).not.toContain('<script>');
  });

  it('distinguishes real OpenAI execution from deterministic/fake provider mode', () => {
    const fakeMarkup = renderToStaticMarkup(<ModuleEvidence attempt={attempt} />);
    expect(fakeMarkup).toContain('DETERMINISTIC / FAKE PROVIDER');

    const realAttempt = {
      ...attempt,
      evidence: { ...attempt.evidence, provider: 'openai', model: 'gpt-4o-mini' },
    };
    const realMarkup = renderToStaticMarkup(<ModuleEvidence attempt={realAttempt} />);
    expect(realMarkup).toContain('REAL OPENAI EXECUTION');
    expect(realMarkup).toContain('gpt-4o-mini');
  });

  it('warns when execution evidence does not exist and hides unauthorized controls', () => {
    const markup = renderToStaticMarkup(<ModuleEvidence attempt={{ ...attempt, evidence: {}, allowed_actions: [] }} />);
    expect(markup).toContain('No execution evidence recorded');
    expect(markup).not.toContain('Request bounded repair');
    expect(markup).not.toContain('Request human review / waiver');
  });

  it('requires a rationale for a bounded repair and passes it to the authorized action', async () => {
    const repair = vi.fn();
    await mount(<ModuleEvidence attempt={attempt} onRepair={repair} />);
    expect(button('Request bounded repair').disabled).toBe(true);
    await rationale('Fix the recorded baseline mismatch');
    await act(async () => button('Request bounded repair').click());
    expect(repair).toHaveBeenCalledWith('Fix the recorded baseline mismatch');
  });

  it('binds human review to the recorded finding with a written rationale', async () => {
    const waiver = vi.fn();
    await mount(<ModuleEvidence attempt={attempt} onWaiver={waiver} />);
    expect(button('Request human review / waiver').disabled).toBe(true);
    await rationale('Request approver review of the security finding');
    await act(async () => button('Request human review / waiver').click());
    expect(waiver).toHaveBeenCalledWith('finding-1', 'Request approver review of the security finding');
  });

  it('loads job-scoped attempts, shows runtime/dependency blockers and filters modules', async () => {
    vi.spyOn(api, 'getModuleAttempts').mockResolvedValue(board);
    await mount(<ModuleExecution jobs={[job]} />);
    expect(api.getModuleAttempts).toHaveBeenCalledWith('job-1');
    expect(container.textContent).toContain('Conversion sandbox unavailable');
    expect(container.textContent).toContain('Accounts is not verified');
    expect(button('Queue conversion').disabled).toBe(true);
    const status = container.querySelector('select[aria-label="Module status"]') as HTMLSelectElement;
    await act(async () => { status.value = 'QUEUED'; status.dispatchEvent(new Event('change', { bubbles: true })); });
    expect(container.querySelectorAll('h2')).toHaveLength(1);
    expect(container.querySelector('h2')!.textContent).toBe('Accounts');
  });

  it('fetches independent detail endpoints for the evidence drawer', async () => {
    vi.spyOn(api, 'getModuleAttempts').mockResolvedValue(board);
    vi.spyOn(api, 'getModuleAttempt').mockResolvedValue(attempt);
    vi.spyOn(api, 'getModuleAttemptDiff').mockResolvedValue({ diff: attempt.evidence!.diff!, changed_files: ['target/payments.py'] });
    vi.spyOn(api, 'getModuleAttemptChecks').mockResolvedValue({ checks: attempt.evidence!.checks!, results: [] });
    vi.spyOn(api, 'getModuleAttemptReview').mockResolvedValue(attempt.evidence!.review!);
    await mount(<ModuleExecution jobs={[job]} />);
    await act(async () => button('Attempt 2: REJECTED').click());
    for (const method of [api.getModuleAttempt, api.getModuleAttemptDiff, api.getModuleAttemptChecks, api.getModuleAttemptReview]) expect(method).toHaveBeenCalledWith('attempt-1');
    expect(container.textContent).toContain('Attempt 2 evidence');
    expect(container.textContent).toContain('Unsafe SQL construction');
  });

  it('reports failed API requests rather than claiming successful execution', async () => {
    vi.spyOn(api, 'getModuleAttempts').mockRejectedValue(new Error('Job access denied'));
    await mount(<ModuleExecution jobs={[job]} />);
    expect(container.querySelector('[role="alert"]')!.textContent).toBe('Job access denied');
    expect(container.textContent).not.toContain('Status: VERIFIED');
  });

  it('queues only an idempotent conversion request without command or patch inputs', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => attempt });
    vi.stubGlobal('fetch', fetchMock);
    await api.queueModuleConversion('job/1', 'module/1', 'stable-key');
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/jobs/job%2F1/modules/module%2F1/conversion-runs', expect.objectContaining({ credentials: 'include', method: 'POST', body: '{"idempotency_key":"stable-key"}' }));
  });

  it('sends repair and waiver requests with exact recorded identity and rationale', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => attempt });
    vi.stubGlobal('fetch', fetchMock);
    await api.requestModuleRepair('attempt-1', 'repair-key', 'Fix failing evidence');
    await api.requestModuleWaiver('attempt-1', 'finding-1', 'Approve intended difference');
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/module-attempts/attempt-1/repair', expect.objectContaining({ body: '{"idempotency_key":"repair-key","rationale":"Fix failing evidence"}' }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/module-attempts/attempt-1/waivers', expect.objectContaining({ body: '{"finding_id":"finding-1","rationale":"Approve intended difference"}' }));
  });
});
