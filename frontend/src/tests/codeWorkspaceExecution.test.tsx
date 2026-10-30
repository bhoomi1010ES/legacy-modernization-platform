import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { ProjectExplorer } from '../components/workspace/ProjectExplorer';
import { AgentExecution } from '../components/workspace/AgentExecution';
import { ActivityLog } from '../components/workspace/ActivityLog';
import { AgentCard } from '../components/workspace/AgentCard';
import { FileStatusIndicator } from '../components/workspace/FileStatusIndicator';
import { CodeWorkspace } from '../pages/CodeWorkspace';
import { Layout } from '../components/Layout';
import type { Job, WorkflowState, WorkflowEvent } from '../types/domain';
import type { FileInventoryItem, DetectedTechnologyProfile } from '../types/phase4';

const mockJob: Job = {
  job_id: '7645e6f2-e52d-4dee-b91c-7d3a0bec0827',
  name: 'Spendwise Modernization',
  source_repository: 'https://github.com/parthptl0911/spendwise',
  source_revision: '9a27078f28ac842cf4cd0e002d7a9a863331f390',
  source_stack: 'Python / FastAPI',
  target_stack: 'TypeScript / NestJS',
  status: 'ANALYZING',
  progress: 25,
  modules: 164,
  cost: 158,
  budget: 15000,
  owner: 'Alex Morgan',
  max_repair_attempts: 3,
  created_at: '2026-10-22T10:00:00Z',
  updated_at: '2026-10-22T11:00:00Z',
};

const mockFiles: FileInventoryItem[] = [
  {
    path: 'app/services/auth_service.py',
    size_bytes: 4200,
    content_hash: 'hash_auth_123',
    language: 'Python',
    is_manifest: false,
    is_test: false,
    is_config: false,
    is_documentation: false,
  },
  {
    path: 'app/models/user.py',
    size_bytes: 3100,
    content_hash: 'hash_user_456',
    language: 'Python',
    is_manifest: false,
    is_test: false,
    is_config: false,
    is_documentation: false,
  },
  {
    path: 'app/api/routes.py',
    size_bytes: 5800,
    content_hash: 'hash_routes_789',
    language: 'Python',
    is_manifest: false,
    is_test: false,
    is_config: false,
    is_documentation: false,
  },
  {
    path: 'requirements.txt',
    size_bytes: 850,
    content_hash: 'hash_req_001',
    language: null,
    is_manifest: true,
    is_test: false,
    is_config: true,
    is_documentation: false,
  },
  {
    path: 'README.md',
    size_bytes: 1200,
    content_hash: 'hash_readme_002',
    language: null,
    is_manifest: false,
    is_test: false,
    is_config: false,
    is_documentation: true,
  },
];

const mockTechProfile: DetectedTechnologyProfile = {
  primary_language: 'Python',
  languages: { Python: 67.5, JavaScript: 32.0 },
  frameworks: ['FastAPI'],
  build_systems: ['pip'],
  package_managers: ['pip'],
  manifest_files: ['requirements.txt'],
  config_files: ['.env.example'],
  test_frameworks: ['pytest'],
  database_dialects: ['PostgreSQL'],
  confidence: 0.98,
};

const mockWorkflow: WorkflowState = {
  job_id: mockJob.job_id,
  status: 'ANALYZING',
  active_node: 'analysis',
  blocking_reason: undefined,
  checkpoint_sequence: 3,
  workflow_version: 1,
  budget_used: 158,
  budget_limit: 15000,
  budget_warning: false,
  allowed_actions: ['pause', 'cancel'],
  updated_at: '2026-10-22T11:00:00Z',
  phases: [
    { node: 'intake', label: 'Repository Intake', status: 'SUCCEEDED' },
    { node: 'analysis', label: 'Multi-Agent Analysis', status: 'RUNNING' },
    { node: 'gate_g1', label: 'G1 Feasibility Decision', status: 'PENDING' },
  ],
};

const mockEvents: WorkflowEvent[] = [
  {
    event_id: 'evt-1',
    event_type: 'phase4.started',
    actor_type: 'system',
    actor_id: 'rebase-engine',
    correlation_id: 'corr-1',
    payload: { description: 'Phase 4 execution initiated for job JOB-0248' },
    created_at: '2026-10-22T11:00:00Z',
  },
  {
    event_id: 'evt-2',
    event_type: 'intake.completed',
    actor_type: 'agent',
    actor_id: 'intake-agent',
    correlation_id: 'corr-1',
    payload: { summary: 'Repository validated · 164 files · SHA-256 inventory sealed' },
    created_at: '2026-10-22T11:02:00Z',
  },
  {
    event_id: 'evt-3',
    event_type: 'analysis.started',
    actor_type: 'agent',
    actor_id: 'analysis-coordinator',
    correlation_id: 'corr-1',
    payload: { agent_name: 'Analysis Coordinator with 7 specialized workers' },
    created_at: '2026-10-22T11:03:00Z',
  },
  {
    event_id: 'evt-4',
    event_type: 'analysis.worker.started',
    actor_type: 'worker',
    actor_id: 'structure-worker',
    correlation_id: 'corr-1',
    payload: { worker: 'structure-worker · Analyzing project layout and symbols' },
    created_at: '2026-10-22T11:04:00Z',
  },
  {
    event_id: 'evt-5',
    event_type: 'file.analysis',
    actor_type: 'worker',
    actor_id: 'structure-worker',
    correlation_id: 'corr-1',
    payload: { path: 'app/services/auth_service.py', action: 'AST inspection L30–60' },
    created_at: '2026-10-22T11:05:00Z',
  },
];

describe('Multi-Agent Execution Workspace (Redesigned Code Workspace)', () => {
  it('renders the complete four-panel layout architecture without code editor components', () => {
    const markup = renderToStaticMarkup(
      <Layout
        currentPath="/code"
        onNavigate={vi.fn()}
        user={{
          user_id: 'user-1',
          email: 'alex.morgan@acme.corp',
          full_name: 'Alex Morgan',
          role: 'ADMIN',
          status: 'ACTIVE',
          permissions: ['job:read'],
          created_at: '2026-10-22T10:00:00Z',
        }}
        pendingGatesCount={1}
      >
        <div className="code-workspace-container">
          <ProjectExplorer
            jobs={[mockJob]}
            selectedJob={mockJob}
            onSelectJob={vi.fn()}
            files={mockFiles}
            directories={['app', 'app/services', 'app/models', 'app/api']}
            techProfile={mockTechProfile}
            selectedFile="app/services/auth_service.py"
            onSelectFile={vi.fn()}
            fileStatuses={{ 'app/services/auth_service.py': 'ANALYZING' }}
            activeAnalyzingFile="app/services/auth_service.py"
          />
          <AgentExecution
            job={mockJob}
            workflow={mockWorkflow}
            events={mockEvents}
            selectedFile="app/services/auth_service.py"
            selectedFileItem={mockFiles[0]}
            fileStatuses={{ 'app/services/auth_service.py': 'ANALYZING' }}
            activeAnalyzingFile="app/services/auth_service.py"
          />
          <ActivityLog
            events={mockEvents}
            activeAnalyzingFile="app/services/auth_service.py"
          />
        </div>
      </Layout>
    );

    // Panel 1: Rebase Sidebar
    expect(markup).toContain('Rebase');
    expect(markup).toContain('Modernization Jobs');
    expect(markup).toContain('Code Workspace');

    // Panel 2: Project Explorer
    expect(markup).toContain('Project Explorer');
    expect(markup).toContain('Spendwise Modernization');
    expect(markup).toContain('5 Files');
    expect(markup).toContain('auth_service.py');

    // Panel 3: Agent Execution
    expect(markup).toContain('Agent Execution');
    expect(markup).toContain('Multi-Agent Pipeline Progression');
    expect(markup).toContain('Analysis Coordinator');
    expect(markup).toContain('Structure Worker');

    // Panel 4: Real-time Activity Log
    expect(markup).toContain('Real-time Activity Log');
    expect(markup).toContain('Live');
    expect(markup).toContain('phase4.started');
    expect(markup).toContain('file.analysis');

    // VERIFY STRICT PROHIBITIONS: No code editors, no converted code panes, no Agent Copilot!
    expect(markup).not.toContain('OrderController.java');
    expect(markup).not.toContain('Side-by-side legacy Java inspection');
    expect(markup).not.toContain('Converted: order.controller.ts');
    expect(markup).not.toContain('Agent Copilot');
    expect(markup).not.toContain('Ask CodeWriter to refine');
  });

  it('renders Project Explorer with repository inventory, commit SHA, file count, and status indicators', () => {
    const markup = renderToStaticMarkup(
      <ProjectExplorer
        jobs={[mockJob]}
        selectedJob={mockJob}
        onSelectJob={vi.fn()}
        files={mockFiles}
        directories={['app', 'app/services', 'app/models']}
        techProfile={mockTechProfile}
        selectedFile="app/services/auth_service.py"
        onSelectFile={vi.fn()}
        fileStatuses={{
          'app/services/auth_service.py': 'ANALYZING',
          'app/models/user.py': 'ANALYZED',
          'app/api/routes.py': 'PENDING',
        }}
        activeAnalyzingFile="app/services/auth_service.py"
      />
    );

    expect(markup).toContain('Project Explorer');
    expect(markup).toContain('spendwise');
    expect(markup).toContain('5 Files');
    expect(markup).toContain('Python 68%');
    expect(markup).toContain('FastAPI');
    expect(markup).toContain('main@9a27078');
    expect(markup).toContain('auth_service.py');
    expect(markup).toContain('user.py');
    expect(markup).toContain('Analyzing');
    expect(markup).toContain('Analyzed');
  });

  it('renders Agent Execution pipeline with specialized workers, current activity, and file context', () => {
    const markup = renderToStaticMarkup(
      <AgentExecution
        job={mockJob}
        workflow={mockWorkflow}
        events={mockEvents}
        selectedFile="app/services/auth_service.py"
        selectedFileItem={mockFiles[0]}
        fileStatuses={{ 'app/services/auth_service.py': 'ANALYZING' }}
        activeAnalyzingFile="app/services/auth_service.py"
      />
    );

    expect(markup).toContain('Agent Execution');
    expect(markup).toContain('Running');
    expect(markup).toContain('Phase 4 ·');
    expect(markup).toContain('File Context for Agent Execution');
    expect(markup).toContain('app/services/auth_service.py');
    expect(markup).toContain('Analysis Coordinator');
    expect(markup).toContain('Current Activity');
    expect(markup).toContain('Analyzing file: app/services/auth_service.py');
    expect(markup).toContain('Structure Worker');
    expect(markup).toContain('Dependency Worker');
    expect(markup).toContain('Interface Worker');
    expect(markup).toContain('Data Worker');
    expect(markup).toContain('Test Worker');
    expect(markup).toContain('Integration Worker');
    expect(markup).toContain('Risk Worker');
  });

  it('renders Action Required state when workflow reaches Approval Gate G1', () => {
    const g1Job: Job = { ...mockJob, status: 'AWAITING_GATE_G1' };
    const markup = renderToStaticMarkup(
      <AgentExecution
        job={g1Job}
        workflow={{ ...mockWorkflow, status: 'AWAITING_GATE_G1', active_node: 'gate_g1' }}
        events={mockEvents}
        selectedFile={null}
        onOpenGateReview={vi.fn()}
      />
    );

    expect(markup).toContain('G1 Human Review');
    expect(markup).toContain('ACTION REQUIRED');
    expect(markup).toContain('Human Review &amp; Approval Required');
    expect(markup).toContain('Review &amp; Decide');
  });

  it('renders Real-time Activity Log with live stream events chronologically', () => {
    const markup = renderToStaticMarkup(
      <ActivityLog
        events={mockEvents}
        activeAnalyzingFile="app/services/auth_service.py"
        onRefresh={vi.fn()}
      />
    );

    expect(markup).toContain('Real-time Activity Log');
    expect(markup).toContain('Live');
    expect(markup).toContain('phase4.started');
    expect(markup).toContain('intake.completed');
    expect(markup).toContain('analysis.started');
    expect(markup).toContain('analysis.worker.started');
    expect(markup).toContain('file.analysis');
    expect(markup).toContain('Analyzing: app/services/auth_service.py');
  });

  it('renders Cake Shop Modernization file structure accurately with HTML and CSS items', () => {
    const cakeJob: Job = {
      job_id: 'd9c9947f-5071-43ce-ac73-c2b26402f614',
      name: 'Cake Shop Modernization',
      source_repository: 'https://github.com/parthptl0911/Cake-shop',
      source_revision: '2ef1860da3717018f4752157b52b3f3916bb2cfc',
      source_stack: 'HTML / CSS',
      target_stack: 'React / TypeScript',
      status: 'CHARACTERIZING',
      progress: 30,
      modules: 3,
      cost: 158,
      budget: 15000,
      owner: 'Alex Morgan',
      max_repair_attempts: 3,
      created_at: '2026-10-22T10:00:00Z',
      updated_at: '2026-10-22T11:00:00Z',
    };

    const cakeFiles: FileInventoryItem[] = [
      { path: 'index.html', size_bytes: 24197, content_hash: 'hash1', language: 'HTML', is_manifest: false, is_test: false, is_config: false, is_documentation: false },
      { path: 'style.css', size_bytes: 21970, content_hash: 'hash2', language: 'CSS', is_manifest: false, is_test: false, is_config: false, is_documentation: false },
      { path: 'README.md', size_bytes: 824, content_hash: 'hash3', language: null, is_manifest: false, is_test: false, is_config: false, is_documentation: true },
    ];

    const markup = renderToStaticMarkup(
      <ProjectExplorer
        jobs={[cakeJob, mockJob]}
        selectedJob={cakeJob}
        onSelectJob={vi.fn()}
        files={cakeFiles}
        directories={[]}
        selectedFile="index.html"
        onSelectFile={vi.fn()}
        fileStatuses={{
          'index.html': 'ANALYZING',
          'style.css': 'ANALYZED',
          'README.md': 'ANALYZED',
        }}
        activeAnalyzingFile="index.html"
      />
    );

    expect(markup).toContain('Cake Shop Modernization');
    expect(markup).toContain('Cake-shop');
    expect(markup).toContain('3 Files');
    expect(markup).toContain('index.html');
    expect(markup).toContain('style.css');
    expect(markup).toContain('README.md');
    expect(markup).toContain('main@2ef1860');
    expect(markup).toContain('Analyzing');
    expect(markup).toContain('Analyzed');
  });
});

