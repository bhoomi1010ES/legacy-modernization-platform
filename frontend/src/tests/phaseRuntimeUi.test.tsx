import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { WorkflowProgress } from '../components/WorkflowProgress';
import { AgentWorkspace } from '../pages/AgentWorkspace';
import { ApprovalGates } from '../pages/ApprovalGates';
import { CreateJob } from '../pages/CreateJob';
import { GateReviewModal } from '../components/GateReviewModal';
import type { GateDetail, Job, WorkflowState } from '../types/domain';

const job: Job = {
  job_id: '1d12db40-3692-414f-b1cc-274a08fe5196', name: 'Payments modernization',
  source_repository: 'https://github.com/acme/payments', source_revision: 'main',
  source_stack: 'Java 11 / Spring Boot', target_stack: 'TypeScript / NestJS',
  status: 'AWAITING_GATE_G2', progress: 30, modules: 8, cost: 42, budget: 100,
  owner: 'Alex Morgan', max_repair_attempts: 3,
  created_at: '2026-10-22T10:00:00Z', updated_at: '2026-10-22T11:00:00Z',
};

const workflow: WorkflowState = {
  job_id: job.job_id, status: 'AWAITING_GATE_G2', active_node: 'gate_g2',
  blocking_reason: 'Human decision required for G2.', checkpoint_sequence: 8,
  workflow_version: 1, budget_used: 42, budget_limit: 100, budget_warning: false,
  allowed_actions: ['pause', 'cancel'], updated_at: '2026-10-22T11:00:00Z',
  phases: [
    { node: 'analysis', label: 'Feasibility analysis', status: 'SUCCEEDED' },
    { node: 'gate_g2', label: 'G2 characterization freeze', status: 'BLOCKED' },
    { node: 'conversion', label: 'Dependency-aware conversion', status: 'PENDING' },
  ],
};

const gate: GateDetail = {
  gate_id: '05f31b9f-3427-43aa-a594-a536706b02c8', job_id: job.job_id,
  job_name: job.name, gate_type: 'G2', title: 'Characterization test suite',
  description: 'Confirm the frozen behavioral suite.', status: 'PENDING',
  artifact: 'Gate G2 artifact package v2', artifact_hash: 'sha256:abc123',
  cost_summary: '42 / 100', requested_at: '2026-10-22T11:00:00Z', version: 2,
  artifact_hashes: { artifact_1: 'sha256:abc123' },
  allowed_actions: ['approve', 'reject', 'request_changes'],
};

describe('Phase 2 and Phase 3 operational UI', () => {
  it('renders a job-scoped Phase 2 runtime workspace with status filtering', () => {
    const markup = renderToStaticMarkup(<AgentWorkspace jobs={[job]} />);
    expect(markup).toContain('Agent execution timeline');
    expect(markup).toContain('Payments modernization');
    expect(markup).toContain('Token usage');
    expect(markup).toContain('BLOCKED');
  });

  it('renders durable workflow checkpoints, budget and blocking reason', () => {
    const markup = renderToStaticMarkup(<WorkflowProgress workflow={workflow} events={[]} />);
    expect(markup).toContain('Workflow checkpoint timeline');
    expect(markup).toContain('Sequence 8');
    expect(markup).toContain('Human decision required for G2.');
    expect(markup).toContain('G2 characterization freeze');
  });

  it('renders a version-bound gate with an authorized review action', () => {
    const markup = renderToStaticMarkup(<ApprovalGates gates={[gate]} onRefreshGates={vi.fn()} onGateDecision={vi.fn()} onNavigate={vi.fn()} />);
    expect(markup).toContain('Gate decision inbox');
    expect(markup).toContain('sha256:abc123');
    expect(markup).toContain('v2');
    expect(markup).toContain('Review evidence');
  });

  it('renders CreateJob wizard with dynamic Project Name field and no hardcoded default', () => {
    const markup = renderToStaticMarkup(<CreateJob onSubmit={vi.fn()} onNavigate={vi.fn()} />);
    expect(markup).toContain('Project Name');
    expect(markup).toContain('id="project-name"');
    expect(markup).toContain('placeholder="e.g., Cake Shop Modernization, SpendWise API"');
    expect(markup).not.toContain('Payment Gateway Modernization');
  });

  it('renders GateReviewModal with previous agent deliverables, verification checklist, and next stage preview', () => {
    const markup = renderToStaticMarkup(
      <GateReviewModal
        gate={gate}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
      />
    );
    expect(markup).toContain('Completed by Previous Agent');
    expect(markup).toContain('CharacterizerAgent');
    expect(markup).toContain('What You Need to Verify Before Advancing');
    expect(markup).toContain('Next Stage:');
    expect(markup).toContain('PlannerCoordinator &amp; ModulePlanner');
    expect(markup).toContain('Verified Evidence Package');
  });
});
