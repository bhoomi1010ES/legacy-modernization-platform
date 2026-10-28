import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { BaselineEvidence, Characterization } from '../pages/Characterization';
import type { CharacterizationReport } from '../types/phase5';
import { api } from '../services/api';

const report: CharacterizationReport = {
  suite_id: 'suite-1', version: 2, content_hash: 'sha256:baseline', status: 'DRAFT',
  runtime_available: false, cases: [],
  coverage: { percent: 0, modules: [{ name: 'Payments', covered: false }], interfaces: [], behaviors: [], untested_paths: ['refund failure'], limitations: ['Runtime unavailable'] },
  known_bugs: ['Legacy rounds tax incorrectly'], normalization: [{ field: 'timestamp', reason: 'Clock varies' }],
  environment: { runtime: 'java' },
};

afterEach(() => vi.unstubAllGlobals());

describe('Phase 5 characterization review', () => {
  it('displays unavailable runtime, uncovered behavior, known bugs and normalization without implying equivalence', () => {
    const markup = renderToStaticMarkup(<BaselineEvidence report={report} />);
    expect(markup).toContain('Legacy test environment unavailable');
    expect(markup).toContain('Weak behavior coverage');
    expect(markup).toContain('Payments: Untested');
    expect(markup).toContain('refund failure');
    expect(markup).toContain('Legacy rounds tax incorrectly');
    expect(markup).toContain('Clock varies');
  });

  it('offers job selection and explicit revision capture instead of automatically starting capture', () => {
    const markup = renderToStaticMarkup(<Characterization jobs={[]} />);
    expect(markup).toContain('No jobs available');
    expect(markup).toContain('Capture request JSON');
    expect(markup).toContain('requires renewed G2 approval');
  });

  it('warns about unobserved evidence, manual schema review and incomplete data validation', () => {
    const markup = renderToStaticMarkup(<BaselineEvidence report={{ ...report, schema_status: 'REVIEW_REQUIRED', schema_validation_status: 'DDL_ONLY' }} />);
    expect(markup).toContain('baseline evidence is unobserved');
    expect(markup).toContain('Manual schema review required');
    expect(markup).toContain('Schema/data validation is incomplete');
  });

  it('preserves observed failures and non-reproducibility instead of showing them as untested passes', () => {
    const markup = renderToStaticMarkup(<BaselineEvidence report={{ ...report, runtime_available: true, cases: [{ test_case_id: 'case', name: 'unstable', module: 'm', interface: 'i', behavior: 'b', expected: 1, actual: 2, normalization: [], outcome: 'NON_REPRODUCIBLE', evidence_status: 'OBSERVED', limitation: 'Side effects changed' }], coverage: { ...report.coverage, behaviors: [{ name: 'b', covered: false, observed: true, status: 'NON_REPRODUCIBLE' }] } }} />);
    expect(markup).toContain('NON_REPRODUCIBLE');
    expect(markup).toContain('OBSERVED');
    expect(markup).toContain('Side effects changed');
  });

  it('binds a freeze request to the reviewed suite hash', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ gate_id: 'g2' }) });
    vi.stubGlobal('fetch', fetchMock);
    await api.freezeCharacterization('job-1', 'suite-1', 'sha256:baseline');
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/jobs/job-1/g2/freeze', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ suite_id: 'suite-1', content_hash: 'sha256:baseline' }),
    }));
  });

  it('sends only supplied disposable fixtures to migration validation', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ passed: true }) });
    vi.stubGlobal('fetch', fetchMock);
    await api.validateDataMigrationPlan('job-1', []);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/jobs/job-1/data-migration-plan/validate', expect.objectContaining({
      method: 'POST', body: '{"tables":[]}',
    }));
  });

  it('clearly distinguishes real Docker execution from simulated execution in the UI', () => {
    const realMarkup = renderToStaticMarkup(<BaselineEvidence report={{ ...report, execution_mode: 'REAL_CONTAINER' }} />);
    expect(realMarkup).toContain('REAL EXECUTION (DOCKER)');

    const simMarkup = renderToStaticMarkup(<BaselineEvidence report={{ ...report, execution_mode: 'IN_MEMORY_DOUBLE' }} />);
    expect(simMarkup).toContain('SIMULATED / IN-MEMORY EXECUTION');

    const unavailMarkup = renderToStaticMarkup(<BaselineEvidence report={{ ...report, execution_mode: 'UNAVAILABLE' }} />);
    expect(unavailMarkup).toContain('EXECUTION UNAVAILABLE');
  });

  it('renders structured schema findings for complex and proprietary SQL constructs', () => {
    const markup = renderToStaticMarkup(
      <BaselineEvidence
        report={{
          ...report,
          schema_findings: [
            {
              construct: 'trigger',
              name: 'sync_audit_trigger',
              status: 'REVIEW_REQUIRED',
              reason: 'Dialect-specific trigger requires manual validation',
            },
            {
              construct: 'table',
              name: 'accounts',
              status: 'SUPPORTED',
              reason: 'Standard table parsed',
            },
          ],
        }}
      />
    );
    expect(markup).toContain('Schema &amp; SQL Findings (2)');
    expect(markup).toContain('sync_audit_trigger');
    expect(markup).toContain('REVIEW_REQUIRED');
    expect(markup).toContain('Dialect-specific trigger requires manual validation');
    expect(markup).toContain('accounts');
    expect(markup).toContain('SUPPORTED');
  });
});
