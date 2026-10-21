import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api } from '../services/api';
import { INITIAL_JOBS, INITIAL_GATES } from '../mocks/fixtures';

describe('Frontend API Client and Contracts Validation', () => {
  let jobs = [...INITIAL_JOBS];
  let gates = [...INITIAL_GATES];

  beforeEach(() => {
    jobs = JSON.parse(JSON.stringify(INITIAL_JOBS));
    gates = JSON.parse(JSON.stringify(INITIAL_GATES));

    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      const urlStr = url.toString();
      const method = init?.method || 'GET';

      if (urlStr.includes('/api/v1/jobs') && method === 'GET') {
        const match = urlStr.match(/\/jobs\/([^?]+)/);
        if (match) {
          const id = match[1];
          if (id.includes('/reports/verification')) {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                job_id: id.split('/')[0],
                behavioral_equivalence_pct: 98.7,
                regressions_count: 0,
                total_tests: 312,
                differences: ['Minor precision difference in ISO timestamps'],
              }),
            };
          }
          if (id.includes('/reports/delivery')) {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                job_id: id.split('/')[0],
                integration_branch: 'job/JOB-0248/integration',
                pull_request_url: 'https://github.com/acme/commerce-api/pull/189',
                production_cutover_included: true,
                included_artifacts: ['art_01', 'art_02'],
              }),
            };
          }
          const job = jobs.find((j) => j.job_id === id);
          return {
            ok: !!job,
            status: job ? 200 : 404,
            json: async () => job || { error: 'Not found' },
          };
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: jobs, total: jobs.length, limit: 50, offset: 0 }),
        };
      }

      if (urlStr.includes('/decisions') && method === 'POST') {
        const body = JSON.parse((init?.body as string) || '{}');
        const g1 = gates.find((g) => g.gate_type === 'G1') || gates[0];
        const job = jobs.find((j) => j.job_id === g1.job_id);
        if (job) {
          job.status = 'CHARACTERIZING';
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            gate_id: g1.gate_id,
            decision: body.decision,
            reviewer: 'Alex Morgan',
            timestamp: new Date().toISOString(),
          }),
        };
      }

      if (urlStr.includes('/detect-stack') && method === 'POST') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            source_repository: 'https://github.com/acme/payment-gateway',
            source_revision: 'main',
            primary_language: 'Java',
            language_version: 'Java 11 (LTS)',
            framework: 'Spring Boot',
            framework_version: '2.7.14',
            build_tool: 'Maven (pom.xml)',
            build_file: 'pom.xml',
            test_framework: 'JUnit 5 & Mockito',
            architecture_style: 'RESTful Microservice',
            confidence_score: 0.98,
            summary_stack: 'Java 11 / Spring Boot 2.7 (Maven)',
            detection_method: 'Repository Coordinates & Manifest Analysis (pom.xml)',
            scan_status: 'COMPLETED',
            is_fallback: false,
            warnings: [],
            components: [],
            resolved_commit: '1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9012',
            tiers: {
              frontend: {
                primary: undefined,
                components: [],
              },
              backend: {
                primary: {
                  name: 'Root Service',
                  relative_path: '',
                  technology: 'Spring Boot',
                  framework: 'Spring Boot',
                  version: '2.7.14',
                  primary_language: 'Java',
                  build_tool_or_driver: 'Maven (pom.xml)',
                  evidence: [{ file: 'pom.xml', reason: 'Spring Boot declaration' }],
                },
                components: [],
              },
              database: {
                primary: {
                  name: 'MySQL Layer',
                  relative_path: 'database/schema.sql',
                  engine: 'MySQL',
                  version: 'N/A',
                  orm_or_driver: 'Hibernate',
                  inferred_from: 'ddl_syntax',
                  confidence: 0.98,
                  evidence: [],
                },
                components: [],
              },
            },
          }),
        };
      }

      if (urlStr.includes('/api/v1/jobs') && method === 'POST') {
        const body = JSON.parse((init?.body as string) || '{}');
        const createdJob = {
          job_id: `JOB-0${jobs.length + 245}`,
          name: body.name,
          source_repository: body.source_repository,
          source_revision: body.source_revision,
          source_stack: body.source_stack,
          target_stack: body.target_stack,
          status: 'INTAKE' as const,
          progress: 0,
          modules: 0,
          cost: 0,
          budget: body.budget || 100,
          owner: 'Alex Morgan',
          max_repair_attempts: body.max_repair_attempts || 3,
          stack_metadata: {
            pinned_commit: body.pinned_commit,
            overrides: body.user_overrides,
          },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        jobs.push(createdJob as any);
        return {
          ok: true,
          status: 201,
          json: async () => createdJob,
        };
      }

      if (urlStr.includes('/api/v1/gates/pending')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: gates, total: gates.length }),
        };
      }
    }));
  });
  it('should fetch the initial list of modernization jobs', async () => {
    const res = await api.getJobs();
    expect(res).toBeDefined();
    expect(res.items.length).toBeGreaterThanOrEqual(4);
    expect(res.total).toBeGreaterThanOrEqual(4);

    const commerceApi = res.items.find((j) => j.job_id === 'JOB-0248');
    expect(commerceApi).toBeDefined();
    expect(commerceApi?.name).toBe('Commerce API');
    expect(commerceApi?.source_stack).toBe('Java 11 / Spring Boot');
    expect(commerceApi?.target_stack).toBe('TypeScript / Node.js 22 / NestJS');
  });

  it('should retrieve a single job by id', async () => {
    const job = await api.getJob('JOB-0248');
    expect(job).toBeDefined();
    expect(job.job_id).toBe('JOB-0248');
    expect(job.max_repair_attempts).toBe(3);
  });

  it('should create a new modernization job with valid defaults and guardrails', async () => {
    const newJob = await api.createJob({
      name: 'Authentication Microservice',
      source_repository: 'https://github.com/acme/auth-service',
      source_revision: 'main',
      source_stack: 'Java 8 / Spring Boot',
      target_stack: 'TypeScript / Node.js 22 / NestJS',
      budget: 120.0,
      max_repair_attempts: 3,
      constraints: 'Preserve all OAuth2 endpoints',
    });

    expect(newJob).toBeDefined();
    expect(newJob.name).toBe('Authentication Microservice');
    expect(newJob.status).toBe('INTAKE');
    expect(newJob.budget).toBe(120.0);
    expect(newJob.max_repair_attempts).toBe(3);

    // Verify it is present in subsequent list
    const res = await api.getJobs();
    const found = res.items.find((j) => j.name === 'Authentication Microservice');
    expect(found).toBeDefined();
  });

  it('should list pending approval gates requiring human review', async () => {
    const res = await api.getPendingGates();
    expect(res).toBeDefined();
    expect(res.items.length).toBeGreaterThanOrEqual(1);

    const gate = res.items[0];
    expect(gate.status).toBe('PENDING');
    expect(['G1', 'G2', 'G3', 'G4']).toContain(gate.gate_type);
    expect(gate.artifact_hash).toContain('sha256:');
  });

  it('should submit an approved gate decision and update status and job progression', async () => {
    const pending = await api.getPendingGates();
    const gateToApprove = pending.items.find((g) => g.gate_type === 'G1') || pending.items[0];

    const decisionRes = await api.submitGateDecision(gateToApprove.gate_id, {
      decision: 'APPROVED',
      rationale: 'Architectural gap analysis reviewed and approved. Viable NestJS equivalents validated.',
    });

    expect(decisionRes.decision).toBe('APPROVED');
    expect(decisionRes.gate_id).toBe(gateToApprove.gate_id);
    expect(decisionRes.reviewer).toBeDefined();

    // Verify job status progression
    const job = await api.getJob(gateToApprove.job_id);
    if (gateToApprove.gate_type === 'G1') {
      expect(job.status).toBe('CHARACTERIZING');
    }
  });

  it('should return 98.7% equivalence and 0 regressions in verification report', async () => {
    const report = await api.getVerificationReport('JOB-0248');
    expect(report).toBeDefined();
    expect(report.behavioral_equivalence_pct).toBe(98.7);
    expect(report.regressions_count).toBe(0);
    expect(report.total_tests).toBe(312);
    expect(report.differences.length).toBeGreaterThan(0);
  });

  it('should return certified delivery package coordinates', async () => {
    const delivery = await api.getDeliveryReport('JOB-0248');
    expect(delivery).toBeDefined();
    expect(delivery.integration_branch).toContain('integration');
    expect(delivery.pull_request_url).toContain('pull');
    expect(delivery.production_cutover_included).toBe(true);
    expect(delivery.included_artifacts.length).toBeGreaterThan(0);
  });

  it('should detect tech stack from git repository manifests and return structured card metadata', async () => {
    const detected = await api.detectSourceStack('https://github.com/acme/payment-gateway', 'main');
    expect(detected).toBeDefined();
    expect(detected.primary_language).toBe('Java');
    expect(detected.framework).toBe('Spring Boot');
    expect(detected.confidence_score).toBeGreaterThanOrEqual(0.9);
    expect(detected.summary_stack).toContain('Java 11');
  });

  it('should support three-tier architecture breakdown and pinned commit', async () => {
    const detected = await api.detectSourceStack('https://github.com/acme/payment-gateway', 'main');
    expect(detected.tiers).toBeDefined();
    expect(detected.tiers?.backend?.primary?.framework).toBe('Spring Boot');
    expect(detected.tiers?.database?.primary?.engine).toBe('MySQL');
    expect(detected.resolved_commit).toBe('1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9012');
  });

  it('should pass pinned_commit and user_overrides to createJob API', async () => {
    const created = await api.createJob({
      name: 'Tier Override Job',
      source_repository: 'https://github.com/acme/payment-gateway',
      source_revision: 'main',
      target_stack: 'TypeScript / Node.js 22 / NestJS',
      budget: 150.0,
      pinned_commit: '1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9012',
      user_overrides: {
        database: { engine: 'PostgreSQL' },
      },
    });
    expect(created).toBeDefined();
    expect(created.name).toBe('Tier Override Job');
  });
});


