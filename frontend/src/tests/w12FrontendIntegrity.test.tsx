import React from 'react';
import { describe, it, expect } from 'vitest';
import { renderToString } from 'react-dom/server';
import { AgentExecution } from '../components/workspace/AgentExecution';
import { ActivityLog } from '../components/workspace/ActivityLog';
import { GateDetailExplanationView } from '../components/GateDetailExplanationView';
import { GateReviewModal } from '../components/GateReviewModal';
import type { Job, GateDetail } from '../types/domain';

const mockCreatedJob: Job = {
  job_id: 'job-w12-test-01',
  name: 'W12 Test Project',
  source_repository: 'https://github.com/acme/modernize.git',
  source_revision: 'main',
  source_stack: 'Java',
  target_stack: 'NodeJS',
  status: 'CREATED',
  progress: 0,
  modules: 0,
  cost: 0,
  budget: 15000,
  owner: 'Alex Morgan',
  created_at: '2026-11-03T10:00:00Z',
  updated_at: '2026-11-03T10:00:00Z',
  max_repair_attempts: 3,
};

describe('W12 Frontend State and Approval Evidence Integrity', () => {
  it('UI-01: AgentExecution shows Running/Pending workers when no AgentRun exists (never fabricates Completed)', () => {
    const mockAnalyzingJob: Job = {
      ...mockCreatedJob,
      status: 'ANALYZING',
    };

    const markup = renderToString(
      <AgentExecution
        job={mockAnalyzingJob}
        workflow={null}
        events={[]}
        agentRuns={[]}
        selectedFile={null}
      />
    );

    // Structure Worker and Dependency Worker should be rendered with Running status
    expect(markup).toContain('Structure Worker');
    expect(markup).toContain('Dependency Worker');
    expect(markup).toContain('Specialized Workers');
    expect(markup).not.toContain('Parsed repository directory layout and module boundary definitions.');
    expect(markup).not.toContain('Resolved direct and transitive dependencies from project manifests.');
  });

  it('UI-02: ActivityLog does not fabricate synthetic seed events and shows explicit polling label', () => {
    const markup = renderToString(
      <ActivityLog events={[]} />
    );

    // Explicit polling label
    expect(markup).toContain('Polling active (5s)');

    // Honest empty state
    expect(markup).toContain('No activity recorded yet for this job.');

    // Strict prohibition: seed-1..seed-7 synthetic events must be completely absent
    expect(markup).not.toContain('seed-1');
    expect(markup).not.toContain('seed-7');
    expect(markup).not.toContain('Specialized analysis passes advancing in parallel');
    expect(markup).not.toContain('Repository validated · SHA-256 inventory sealed');
  });

  it('UI-04: GateDetailExplanationView displays EVIDENCE_UNAVAILABLE when conversion plan or equivalence report missing', () => {
    const g3Gate: GateDetail = {
      gate_id: 'gate-g3-01',
      job_id: mockCreatedJob.job_id,
      job_name: mockCreatedJob.name,
      gate_type: 'G3',
      title: 'Modular Wave Plan Approval',
      description: 'Review modular wave decomposition',
      version: 1,
      status: 'PENDING',
      artifact: '',
      artifact_hash: '',
      cost_summary: '$0.00',
      artifact_hashes: {},
      requested_at: '2026-11-03T10:00:00Z',
    };

    const g3Markup = renderToString(
      <GateDetailExplanationView
        gateType="G3"
        job={mockCreatedJob}
        gate={g3Gate}
        conversionPlan={null}
      />
    );

    // Should indicate evidence is unavailable, NOT claim 14 modules or 42 tasks
    expect(g3Markup).toContain('EVIDENCE_UNAVAILABLE');
    expect(g3Markup).toContain('Awaiting Plan Generation');
    expect(g3Markup).not.toContain('14 Modules');
    expect(g3Markup).not.toContain('42 conversion tasks');

    const g4Gate: GateDetail = {
      gate_id: 'gate-g4-01',
      job_id: mockCreatedJob.job_id,
      job_name: mockCreatedJob.name,
      gate_type: 'G4',
      title: 'Final Release Sign-Off',
      description: 'Review final release candidate',
      version: 1,
      status: 'PENDING',
      artifact: '',
      artifact_hash: '',
      cost_summary: '$0.00',
      artifact_hashes: {},
      requested_at: '2026-11-03T10:00:00Z',
    };

    const g4Markup = renderToString(
      <GateDetailExplanationView
        gateType="G4"
        job={mockCreatedJob}
        gate={g4Gate}
      />
    );

    // Should indicate evidence is unavailable for G4 when not completed
    expect(g4Markup).toContain('EVIDENCE_UNAVAILABLE');
    expect(g4Markup).toContain('Awaiting Verification');
    expect(g4Markup).not.toContain('42 / 42 Fixtures Matched');
  });

  it('UI-04: GateReviewModal disables approval and displays alert when evidence is missing or stale', () => {
    const stalePendingGate: GateDetail = {
      gate_id: 'gate-stale-01',
      job_id: mockCreatedJob.job_id,
      job_name: mockCreatedJob.name,
      gate_type: 'G3',
      title: 'Modular Wave Plan Approval',
      description: 'Review modular wave decomposition',
      version: 1,
      status: 'PENDING',
      artifact: '',
      artifact_hash: '',
      cost_summary: '$0.00',
      artifact_hashes: {},
      blocking_reason: 'Upstream CharacterizationSuite modified; plan is stale',
      requested_at: '2026-11-03T10:00:00Z',
    };

    const markup = renderToString(
      <GateReviewModal
        gate={stalePendingGate}
        job={mockCreatedJob}
        onClose={() => {}}
        onSubmit={async () => {}}
      />
    );

    // Approval must be disabled and display STALE or EVIDENCE_UNAVAILABLE alert
    expect(markup).toContain('Approval Blocked');
    expect(markup).toContain('STALE');
    expect(markup).toContain('disabled');
  });
});
