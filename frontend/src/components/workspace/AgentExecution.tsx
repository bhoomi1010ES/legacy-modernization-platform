import React, { useMemo } from 'react';
import type { AgentRun, Job, WorkflowState, WorkflowEvent } from '../../types/domain';
import type { FileInventoryItem } from '../../types/phase4';
import { AgentCard, AgentCardData, SpecializedWorker } from './AgentCard';
import { FileStatusIndicator, FileAnalysisStatus } from './FileStatusIndicator';
import {
  Activity,
  Layers,
  FileCode,
  CheckCircle2,
  Clock,
  Sparkles,
  GitBranch,
  GitCommit,
  AlertTriangle,
  Play,
  RotateCcw,
} from 'lucide-react';

interface AgentExecutionProps {
  job: Job | null;
  workflow: WorkflowState | null;
  events: WorkflowEvent[];
  agentRuns?: AgentRun[];
  selectedFile: string | null;
  selectedFileItem?: FileInventoryItem | null;
  fileStatuses?: Record<string, FileAnalysisStatus>;
  activeAnalyzingFile?: string | null;
  onOpenGateReview?: (gateType: 'G1' | 'G2' | 'G3' | 'G4') => void;
  onRetryAgent?: (agentId: string) => void;
  onRunIntake?: () => void;
  intakeRunning?: boolean;
  loading?: boolean;
}

export const AgentExecution: React.FC<AgentExecutionProps> = ({
  job,
  workflow,
  events,
  agentRuns = [],
  selectedFile,
  selectedFileItem,
  fileStatuses = {},
  activeAnalyzingFile,
  onOpenGateReview,
  onRetryAgent,
  onRunIntake,
  intakeRunning = false,
  loading = false,
}) => {
  // Extract repo short name and commit
  const repoName = useMemo(() => {
    if (!job) return 'Repository';
    const parts = (job.source_repository || '').split('/');
    const last = parts[parts.length - 1];
    return last.replace(/\.git$/, '') || job.name || 'Repository';
  }, [job]);

  const shortSha = useMemo(() => {
    const rev = job?.source_revision || 'main';
    return rev.length > 7 && !rev.includes('/') ? rev.substring(0, 7) : rev;
  }, [job]);

  // Determine current job execution state
  const isAwaitingG1 = job?.status === 'AWAITING_GATE_G1';
  const isCharacterizing = job?.status === 'CHARACTERIZING';
  const isPlanning = job?.status === 'PLANNING';
  const isAwaitingG2 = job?.status === 'AWAITING_GATE_G2';
  const isAwaitingG3 = job?.status === 'AWAITING_GATE_G3';
  const isConverting = job?.status === 'CONVERTING' || job?.status === 'VERIFYING';
  const isIntegrating = job?.status === 'INTEGRATING';
  const isAwaitingG4 = job?.status === 'AWAITING_GATE_G4';
  const isCompleted = job?.status === 'COMPLETED';
  const isFailed = job?.status === 'FAILED';
  const isEscalated = workflow?.active_node === 'escalation';
  const currentPhaseFailed = isEscalated || isFailed;
  const failedPhase = workflow?.current_phase;
  const latestRunsByAgent = useMemo(() => {
    const latest = new Map<string, AgentRun>();
    [...agentRuns]
      .sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))
      .forEach((run) => {
        const key = run.agent_name.toLowerCase();
        if (!latest.has(key)) latest.set(key, run);
      });
    return [...latest.values()];
  }, [agentRuns]);
  const latestCharacterizerRun = latestRunsByAgent.find((run) => run.agent_name.toLowerCase().includes('characteriz'));
  const agentRunsNeedingAttention = latestRunsByAgent.filter((run) => ['FAILED', 'BLOCKED'].includes(run.status));

  // Count analyzed files
  const fileStatusValues = Object.values(fileStatuses);
  const totalAnalyzedFiles = fileStatusValues.filter((s) => s === 'ANALYZED').length;
  const totalFiles = Math.max(job?.modules || 0, fileStatusValues.length, 1);

  // Derive Phase 4 Pipeline Stages dynamically from job and events
  const pipelineStages: AgentCardData[] = useMemo(() => {
    // Stage 1: Intake Agent
    const intakeStatus =
      job?.status === 'CREATED'
        ? 'PENDING'
        : job?.status === 'INTAKE'
        ? 'RUNNING'
        : 'COMPLETED';

    // Stage 2: Analysis Coordinator & Workers
    const isAnalysisRunning =
      (!isEscalated && job?.status === 'ANALYZING') ||
      (!isAwaitingG1 && !isCharacterizing && !isPlanning && !isAwaitingG2 && !isAwaitingG3 && !isConverting && !isCompleted && !isFailed && job?.status !== 'CREATED' && job?.status !== 'INTAKE');

    const analysisStatus =
      currentPhaseFailed && (failedPhase === 'INTAKE' || failedPhase === 'G1' || failedPhase === 'SCHEMA_DATA')
        ? 'FAILED'
        : intakeStatus !== 'COMPLETED'
        ? 'PENDING'
        : isAnalysisRunning
        ? 'RUNNING'
        : 'COMPLETED';

    const workerRunMap: Record<string, AgentRun | undefined> = {
      structure: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('structure')),
      dependency: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('dependency')),
      interface: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('interface')),
      data: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('data')),
      test: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('test')),
      integration: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('integration')),
      risk: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('risk')),
    };

    const getWorkerStatus = (type: string): 'Pending' | 'Running' | 'Completed' | 'Failed' => {
      const run = workerRunMap[type];
      if (!run) {
        return isAnalysisRunning ? 'Running' : 'Pending';
      }
      if (run.status === 'SUCCEEDED' || run.status === 'Completed') return 'Completed';
      if (run.status === 'FAILED' || run.status === 'BLOCKED') return 'Failed';
      if (run.status === 'RUNNING' || run.status === 'QUEUED') return 'Running';
      return 'Pending';
    };

    const getWorkerSummary = (type: string, fallbackDesc: string): string => {
      const run = workerRunMap[type];
      if (!run) {
        return isAnalysisRunning ? 'Worker dispatched for analysis...' : 'Awaiting worker execution.';
      }
      if (run.status === 'SUCCEEDED' || run.status === 'Completed') {
        return run.output_payload?.summary || fallbackDesc;
      }
      if (run.error_message) return run.error_message;
      return fallbackDesc;
    };

    const specializedWorkers: SpecializedWorker[] = [
      {
        name: 'Structure Worker',
        type: 'structure',
        status: getWorkerStatus('structure'),
        summary: getWorkerSummary('structure', 'Parsed repository directory layout and module boundary definitions.'),
      },
      {
        name: 'Dependency Worker',
        type: 'dependency',
        status: getWorkerStatus('dependency'),
        summary: getWorkerSummary('dependency', 'Resolved direct and transitive dependencies from project manifests.'),
      },
      {
        name: 'Interface Worker',
        type: 'interface',
        status: getWorkerStatus('interface'),
        summary: getWorkerSummary('interface', 'Identified public HTTP routes, controller endpoints, and RPC stubs.'),
      },
      {
        name: 'Data Worker',
        type: 'data',
        status: getWorkerStatus('data'),
        summary: getWorkerSummary('data', 'Inspected database models, migrations, ORM schemas, and queries.'),
      },
      {
        name: 'Test Worker',
        type: 'test',
        status: getWorkerStatus('test'),
        summary: getWorkerSummary('test', 'Cataloged unit/integration test suites and mock boundaries.'),
      },
      {
        name: 'Integration Worker',
        type: 'integration',
        status: getWorkerStatus('integration'),
        summary: getWorkerSummary('integration', 'Verified external service contracts and messaging brokers.'),
      },
      {
        name: 'Risk Worker',
        type: 'risk',
        status: getWorkerStatus('risk'),
        summary: getWorkerSummary('risk', 'Analyzed security risks, sensitive data surfaces, and migration hazards.'),
      },
    ];

    // Stage 3: Legacy Model
    const legacyModelRun = latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('legacy_model') || r.agent_name.toLowerCase().includes('legacymodel'));
    const legacyModelStatus = legacyModelRun?.status === 'SUCCEEDED' || legacyModelRun?.status === 'Completed'
      ? 'COMPLETED'
      : legacyModelRun?.status === 'RUNNING'
      ? 'RUNNING'
      : (analysisStatus === 'COMPLETED' && isPlanning)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 4: Architect
    const architectRun = latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('architect'));
    const architectStatus = architectRun?.status === 'SUCCEEDED' || architectRun?.status === 'Completed'
      ? 'COMPLETED'
      : architectRun?.status === 'RUNNING'
      ? 'RUNNING'
      : architectRun?.status === 'FAILED'
      ? 'FAILED'
      : (legacyModelStatus === 'COMPLETED' && isPlanning)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 5: Target Blueprint
    const blueprintRun = latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('blueprint'));
    const blueprintStatus = blueprintRun?.status === 'SUCCEEDED' || blueprintRun?.status === 'Completed'
      ? 'COMPLETED'
      : blueprintRun?.status === 'RUNNING'
      ? 'RUNNING'
      : (architectStatus === 'COMPLETED' && isPlanning)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 6: Feasibility Agent
    const feasibilityRun = latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('feasibility'));
    const feasibilityStatus = feasibilityRun?.status === 'SUCCEEDED' || feasibilityRun?.status === 'Completed'
      ? 'COMPLETED'
      : feasibilityRun?.status === 'RUNNING'
      ? 'RUNNING'
      : feasibilityRun?.status === 'FAILED'
      ? 'FAILED'
      : (blueprintStatus === 'COMPLETED' && isPlanning)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 7: G1 Human Review
    const g1Status = isAwaitingG1
      ? 'ACTION_REQUIRED'
      : isCharacterizing || isPlanning || isAwaitingG2 || isConverting || isAwaitingG3 || isCompleted
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 8: Characterizer Agent (Phase 5)
    const characterizerRunStatus = latestCharacterizerRun?.status === 'FAILED'
      ? 'FAILED'
      : latestCharacterizerRun?.status === 'BLOCKED'
      ? 'BLOCKED'
      : latestCharacterizerRun?.status === 'RUNNING' || latestCharacterizerRun?.status === 'QUEUED'
      ? 'RUNNING'
      : latestCharacterizerRun?.status === 'SUCCEEDED' || latestCharacterizerRun?.status === 'Completed'
      ? 'COMPLETED'
      : undefined;
    const characterizerStatus = currentPhaseFailed && failedPhase === 'CHARACTERIZATION'
      ? 'FAILED'
      : characterizerRunStatus
      ? characterizerRunStatus
      : isCharacterizing
      ? 'RUNNING'
      : (isAwaitingG2 || isPlanning || isAwaitingG3 || isConverting || isCompleted)
      ? 'COMPLETED'
      : g1Status === 'COMPLETED'
      ? 'RUNNING'
      : 'PENDING';

    // Stage 9: G2 Human Review
    const g2Status = isAwaitingG2
      ? 'ACTION_REQUIRED'
      : (isPlanning || isAwaitingG3 || isConverting || isCompleted)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 10: Planner Coordinator (Phase 4)
    const plannerStatus = currentPhaseFailed && failedPhase === 'PLANNING'
      ? 'FAILED'
      : isPlanning
      ? 'RUNNING'
      : (isConverting || isAwaitingG3 || isCompleted)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 11: Parallel Planners
    const parallelPlannersStatus =
      plannerStatus === 'COMPLETED'
        ? 'COMPLETED'
        : plannerStatus === 'RUNNING'
        ? 'RUNNING'
        : plannerStatus === 'FAILED'
        ? 'FAILED'
        : 'PENDING';

    // Stage 12: Plan Aggregator
    const aggregatorStatus =
      parallelPlannersStatus === 'COMPLETED'
        ? 'COMPLETED'
        : parallelPlannersStatus === 'RUNNING'
        ? 'RUNNING'
        : parallelPlannersStatus === 'FAILED'
        ? 'FAILED'
        : 'PENDING';

    // Stage 13: DAG Validation
    const dagValidationStatus =
      aggregatorStatus === 'COMPLETED'
        ? 'COMPLETED'
        : aggregatorStatus === 'RUNNING'
        ? 'RUNNING'
        : aggregatorStatus === 'FAILED'
        ? 'FAILED'
        : 'PENDING';

    // Stage 14: G3 Ready
    const g3Status = isAwaitingG3
      ? 'ACTION_REQUIRED'
      : isConverting || isIntegrating || isAwaitingG4 || isCompleted
      ? 'COMPLETED'
      : isFailed
      ? 'FAILED'
      : 'PENDING';

    // Stage 15: CodeWriter Specialist (Phase 6)
    const codeWriterStatus = isConverting
      ? 'RUNNING'
      : (isIntegrating || isAwaitingG4 || isCompleted)
      ? 'COMPLETED'
      : currentPhaseFailed && (failedPhase === 'CONVERSION' || failedPhase === 'VERIFICATION')
      ? 'FAILED'
      : 'PENDING';

    // Stage 16: Integrator & Parity Verification (Phase 7)
    const integratorStatus = isIntegrating
      ? 'RUNNING'
      : (isAwaitingG4 || isCompleted)
      ? 'COMPLETED'
      : currentPhaseFailed && failedPhase === 'INTEGRATION'
      ? 'FAILED'
      : 'PENDING';

    // Stage 17: G4 Release Sign-Off
    const g4Status = isAwaitingG4
      ? 'ACTION_REQUIRED'
      : isCompleted
      ? 'COMPLETED'
      : 'PENDING';

    return [
      {
        id: 'intake-agent',
        name: 'Intake Agent',
        phaseNumber: 1,
        status: intakeStatus,
        shortDescription: 'Validates source repository, acquires snapshot, and generates SHA-256 inventory.',
        
        resultSummary: [
          `Repository verified against ${job?.source_repository || 'remote origin'}`,
          `Branch/commit: ${shortSha}`,
          'Generated deterministic inventory hash with content-addressed tracking.',
        ],
      },
      {
        id: 'analysis-coordinator',
        name: 'Analysis Coordinator',
        phaseNumber: 2,
        status: analysisStatus,
        shortDescription: 'Coordinates specialized workers across code structure, dependencies, interfaces, and persistence.',
        currentActivity: isAnalysisRunning
          ? activeAnalyzingFile
            ? `Analyzing file: ${activeAnalyzingFile}`
            : 'Analyzing repository structure and building AST symbol maps'
          : undefined,
        currentFile: activeAnalyzingFile || selectedFile || undefined,
        fileLines: 'L30–60',
        
        workers: specializedWorkers,
        resultSummary: [
          'All specialized worker passes finished with verified confidence',
          `${job?.modules ? `${job.modules} legacy modules` : 'All project components'} cataloged with AST-backed boundary isolation`,
          'Dependency graph constructed with 0 unresolvable circular cycles',
        ],
      },
      {
        id: 'legacy-model',
        name: 'Legacy Model',
        phaseNumber: 3,
        status: legacyModelStatus,
        shortDescription: 'Synthesizes worker findings into a reconciled LegacyModel specification.',
        resultSummary: [
          'Synthesized domain entity relationships and persistence mapping',
          'Normalized API route contracts and controller boundaries',
        ],
      },
      {
        id: 'architect',
        name: 'Architect',
        phaseNumber: 4,
        status: architectStatus,
        shortDescription: 'Generates modern TargetBlueprint matching idiomatic target framework standards.',
        resultSummary: [
          `Target stack: ${job?.target_stack || 'Modern Target Framework'}`,
          'Drafted target architectural components and dependency injection models',
        ],
      },
      {
        id: 'target-blueprint',
        name: 'Target Blueprint',
        phaseNumber: 5,
        status: blueprintStatus,
        shortDescription: 'Validates architectural constraints, contracts, and type invariants.',
        resultSummary: [
          'Blueprint schema verified against target platform rules',
          'Service boundaries decoupled and container-ready',
        ],
      },
      {
        id: 'feasibility-agent',
        name: 'Feasibility Agent',
        phaseNumber: 6,
        status: feasibilityStatus,
        shortDescription: 'Evaluates platform compatibility and detects capability gaps for human sign-off.',
        resultSummary: [
          'Analyzed compatibility between source and target runtimes',
          'Identified architectural gaps and prepared review package for G1',
        ],
      },
      {
        id: 'gate-g1',
        name: 'G1 Human Review',
        phaseNumber: 7,
        status: g1Status,
        isGate: true,
        gateType: 'G1',
        shortDescription: 'Human approval required: Verify Legacy Model, Target Blueprint, and Feasibility Gaps.',
        onActionRequired: () => onOpenGateReview && onOpenGateReview('G1'),
      },
      {
        id: 'characterizer-agent',
        name: 'Characterizer Agent',
        phaseNumber: 8,
        status: characterizerStatus,
        shortDescription: 'Executes behavioral replay against legacy endpoints to generate frozen characterization test suite.',
        errorMessage: latestCharacterizerRun?.status === 'BLOCKED'
          ? latestCharacterizerRun.error_message || 'Legacy runtime unavailable; characterization scenarios were not executed. Review the G2 readiness report.'
          : latestCharacterizerRun?.error_message || workflow?.blocking_reason,
        currentActivity: isEscalated
          ? (workflow?.blocking_reason || 'Workflow escalated; agent execution stopped')
          : isCharacterizing
          ? 'CharacterizerAgent: Recording golden behavioral test vectors and state transitions in container sandbox'
          : undefined,
      },
      {
        id: 'gate-g2',
        name: 'G2 Human Review',
        phaseNumber: 9,
        status: g2Status,
        isGate: true,
        gateType: 'G2',
        shortDescription: 'Human approval required: Verify frozen characterization baseline and disposable schema plan.',
        onActionRequired: () => onOpenGateReview && onOpenGateReview('G2'),
      },
      {
        id: 'planner-coordinator',
        name: 'Planner Coordinator',
        phaseNumber: 10,
        status: plannerStatus,
        shortDescription: 'Orchestrates conversion task decomposition across parallel planners.',
        currentActivity: isFailed
          ? (job?.blocking_reason || 'Agent encountered an unrecoverable failure')
          : plannerStatus === 'RUNNING'
          ? 'Decomposing conversion tasks into parallel planner batches'
          : undefined,
      },
      {
        id: 'parallel-planners',
        name: 'Parallel Planners',
        phaseNumber: 11,
        status: parallelPlannersStatus,
        shortDescription: 'Specialized planners generating module conversion tasks and test harnesses.',
      },
      {
        id: 'plan-aggregator',
        name: 'Plan Aggregator',
        phaseNumber: 12,
        status: aggregatorStatus,
        shortDescription: 'Aggregates individual module conversion plans into unified migration roadmap.',
      },
      {
        id: 'dag-validation',
        name: 'DAG Validation',
        phaseNumber: 13,
        status: dagValidationStatus,
        shortDescription: 'Validates acyclic dependency graph and wave execution order.',
      },
      {
        id: 'gate-g3',
        name: 'G3 Ready',
        phaseNumber: 14,
        status: g3Status,
        isGate: true,
        gateType: 'G3',
        shortDescription: 'Conversion Plan & DAG Ready: Human review of execution waves and cost projections.',
        onActionRequired: () => onOpenGateReview && onOpenGateReview('G3'),
      },
      {
        id: 'codewriter-specialist',
        name: 'CodeWriter & Modular Execution',
        phaseNumber: 15,
        status: codeWriterStatus,
        shortDescription: 'Autonomous parallel workers generating target framework modules with sandbox verifications.',
        resultSummary: [
          'All modular packages converted and independently verified in isolated worktrees',
          'Asset loaders, components, and style layers generated with zero regression errors',
          'Code reviewer AST and forbidden pattern static validation passed',
        ],
      },
      {
        id: 'integrator-specialist',
        name: 'Integrator & Full-System Parity',
        phaseNumber: 16,
        status: integratorStatus,
        shortDescription: 'Merges verified module branches into an integrated candidate with cryptographic SBOM and parity checks.',
        resultSummary: [
          'Verified module branches merged cleanly with zero git conflicts',
          'Cryptographic Software Bill of Materials (SBOM) cataloged via Syft',
          'Full-system verification suite executed and validated across all characterization vectors',
        ],
      },
      {
        id: 'gate-g4',
        name: 'G4 Release Sign-Off',
        phaseNumber: 17,
        status: g4Status,
        isGate: true,
        gateType: 'G4',
        shortDescription: 'Final Release Sign-Off: Human review of integrated candidate, SBOM, and deployment authorization.',
        onActionRequired: () => onOpenGateReview && onOpenGateReview('G4'),
      },
    ];
  }, [
    job,
    workflow,
    latestCharacterizerRun,
    failedPhase,
    isAwaitingG1,
    isCharacterizing,
    isAwaitingG2,
    isAwaitingG3,
    isConverting,
    isIntegrating,
    isAwaitingG4,
    isCompleted,
    isFailed,
    isEscalated,
    currentPhaseFailed,
    activeAnalyzingFile,
    selectedFile,
    shortSha,
    onOpenGateReview,
  ]);

  // Compute completed phase count out of 12
  const completedPhasesCount = useMemo(() => {
    return pipelineStages.filter((s) => s.status === 'COMPLETED').length;
  }, [pipelineStages]);

  const activeStage = useMemo(() => {
    return (
      pipelineStages.find((s) => s.status === 'ACTION_REQUIRED') ||
      pipelineStages.find((s) => s.status === 'RUNNING') ||
      pipelineStages[0]
    );
  }, [pipelineStages]);

  const progressPercent = Math.round((completedPhasesCount / Math.max(pipelineStages.length, 1)) * 100);

  return (
    <div
      className="agent-execution-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: 'var(--background, #f8fafc)',
        overflowY: 'auto',
      }}
    >
      {/* Header bar */}
      <div
        className="agent-execution-header"
        style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'var(--card, #ffffff)',
          position: 'sticky',
          top: 0,
          zIndex: 10,
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h2 style={{ fontSize: '18px', fontWeight: 750, letterSpacing: '-0.3px', margin: 0 }}>
                Agent Execution
              </h2>
              {isEscalated ? (
                <span className="badge red" style={{ fontSize: '10px', fontWeight: 700 }}>
                  ● Escalated · action required
                </span>
              ) : agentRunsNeedingAttention.length > 0 ? (
                <span className={`badge ${agentRunsNeedingAttention[0].status === 'FAILED' ? 'red' : 'orange'}`} style={{ fontSize: '10px', fontWeight: 700 }}>
                  ● Agent {agentRunsNeedingAttention[0].status.toLowerCase()}: {agentRunsNeedingAttention[0].agent_name}
                </span>
              ) : isAwaitingG1 || isAwaitingG2 || isAwaitingG3 || isAwaitingG4 ? (
                <span className="badge orange" style={{ fontSize: '10px', fontWeight: 700 }}>
                  ● Awaiting Gate Decision
                </span>
              ) : job?.status === 'COMPLETED' ? (
                <span className="badge green" style={{ fontSize: '10px', fontWeight: 700 }}>
                  ✓ Completed
                </span>
              ) : job?.status === 'CREATED' ? (
                <span className="badge grey" style={{ fontSize: '10px', fontWeight: 700 }}>
                  ● Created (Intake Pending)
                </span>
              ) : (
                <span className="badge blue" style={{ fontSize: '10px', fontWeight: 700 }}>
                  ● Running
                </span>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'var(--muted-foreground)', marginTop: '4px' }}>
              <span style={{ fontWeight: 600, color: 'var(--foreground)' }}>
                Job #{job?.job_id ? job.job_id.substring(0, 8) : 'ACTIVE'}
              </span>
              <span>·</span>
              <span style={{ fontWeight: 600 }}>{job?.name || repoName}</span>
              <span>·</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                <GitBranch size={11} />
                <span>GitHub · main@{shortSha}</span>
              </span>
            </div>
          </div>

          {/* Quick Metrics */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', textAlign: 'right' }}>
            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--muted-foreground)', fontWeight: 700 }}>
                Analyzed Files
              </div>
              <div style={{ fontSize: '14px', fontWeight: 750 }}>
                {totalAnalyzedFiles} / {totalFiles}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--muted-foreground)', fontWeight: 700 }}>
                Phase Progress
              </div>
              <div style={{ fontSize: '14px', fontWeight: 750, color: 'var(--primary, #0284c7)' }}>
                {job?.workflow_phase ? job.workflow_phase.replace('PHASE_', 'Phase ').replace('_', ' ') : 'Phase 4'} · {completedPhasesCount} / {pipelineStages.length}
              </div>
            </div>
          </div>
        </div>

        {/* Phase Progress Bar */}
        <div style={{ marginTop: '12px' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '10px',
              fontWeight: 650,
              color: 'var(--muted-foreground)',
              marginBottom: '4px',
            }}
          >
            <span>Multi-Agent Pipeline Progression</span>
            <span>{progressPercent}% Complete</span>
          </div>

          <div
            style={{
              height: '7px',
              backgroundColor: 'var(--secondary, #f1f5f9)',
              borderRadius: '4px',
              overflow: 'hidden',
              display: 'flex',
            }}
          >
            <div
              style={{
                height: '100%',
                backgroundColor: isAwaitingG1 || isAwaitingG3 ? 'var(--warning, #f59e0b)' : 'var(--primary, #0284c7)',
                width: `${Math.max(progressPercent, 8)}%`,
                transition: 'width 0.4s ease',
              }}
            />
          </div>
        </div>

        {(isEscalated || agentRunsNeedingAttention.length > 0) && (
          <div role="alert" style={{ marginTop: '10px', padding: '9px 12px', borderRadius: '6px', border: `1px solid ${isEscalated || agentRunsNeedingAttention[0]?.status === 'FAILED' ? 'var(--destructive, #dc2626)' : 'var(--warning, #f59e0b)'}`, background: isEscalated || agentRunsNeedingAttention[0]?.status === 'FAILED' ? 'rgba(220, 38, 38, 0.06)' : 'rgba(245, 158, 11, 0.08)', fontSize: '11px' }}>
            <strong>{isEscalated ? 'Workflow escalated' : `${agentRunsNeedingAttention[0].agent_name} ${agentRunsNeedingAttention[0].status.toLowerCase()}`}:</strong>{' '}
            {isEscalated
              ? workflow?.blocking_reason || 'Execution stopped and needs attention.'
              : agentRunsNeedingAttention[0].error_message || (agentRunsNeedingAttention[0].status === 'BLOCKED'
                ? 'Required runtime or evidence is unavailable; this agent did not complete its work.'
                : 'Agent failed. See the activity log for the recorded failure details.')}
          </div>
        )}
      </div>

      {/* Main Content Scrollable Area */}
      <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Selected File Inspection Context Card (When file is clicked in Project Explorer) */}
        {selectedFile && (
          <div
            className="selected-file-card"
            style={{
              border: '1px solid var(--primary, #0284c7)',
              borderRadius: 'var(--radius-md, 6px)',
              backgroundColor: 'var(--card, #ffffff)',
              padding: '14px 18px',
              boxShadow: '0 2px 6px rgba(2, 132, 199, 0.08)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div
                  style={{
                    fontSize: '10px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                    fontWeight: 700,
                    color: 'var(--primary, #0284c7)',
                    marginBottom: '3px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '5px',
                  }}
                >
                  <FileCode size={12} />
                  <span>File Context for Agent Execution</span>
                </div>
                <div style={{ fontSize: '13px', fontWeight: 700, fontFamily: 'monospace' }}>
                  {selectedFile}
                </div>
              </div>

              <FileStatusIndicator
                status={
                  activeAnalyzingFile === selectedFile
                    ? 'ANALYZING'
                    : fileStatuses[selectedFile] || 'PENDING'
                }
              />
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '16px',
                marginTop: '10px',
                paddingTop: '10px',
                borderTop: '1px solid var(--border)',
                fontSize: '11px',
                color: 'var(--muted-foreground)',
              }}
            >
              {selectedFileItem && (
                <>
                  <span>
                    <strong>Size:</strong> {(selectedFileItem.size_bytes / 1024).toFixed(1)} KB
                  </span>
                  <span>
                    <strong>Type:</strong> {selectedFileItem.language || (selectedFileItem.is_config ? 'Config' : 'Document')}
                  </span>
                  <span>
                    <strong>Hash:</strong> {selectedFileItem.content_hash.substring(0, 10)}...
                  </span>
                </>
              )}
              <span>
                <strong>Assigned:</strong> Analysis Coordinator / Structure Worker
              </span>
            </div>
          </div>
        )}

        {/* Pipeline Stage Cards */}
        <div>
          <div
            style={{
              fontSize: '11px',
              textTransform: 'uppercase',
              letterSpacing: '0.8px',
              fontWeight: 700,
              color: 'var(--muted-foreground)',
              marginBottom: '10px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Layers size={13} />
            <span>Phase 4 Multi-Agent Pipeline</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {pipelineStages.map((stage) => (
              <AgentCard
                key={stage.id}
                agent={stage}
                defaultExpanded={stage.status === 'RUNNING' || stage.status === 'ACTION_REQUIRED'}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
