from pathlib import Path

target_file = Path("frontend/src/components/workspace/AgentExecution.tsx")
content = target_file.read_text(encoding="utf-8")

old_stage_logic = """    // Stage 7: G1 Human Review
    const g1Status = isAwaitingG1
      ? 'ACTION_REQUIRED'
      : isCharacterizing || isPlanning || isAwaitingG2 || isConverting || isAwaitingG3 || isCompleted
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 8: Planner Coordinator
    const plannerStatus = isFailed
      ? 'FAILED'
      : isPlanning || isCharacterizing
      ? 'RUNNING'
      : (isConverting || isAwaitingG3 || isCompleted)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 9: Parallel Planners
    const parallelPlannersStatus =
      plannerStatus === 'COMPLETED'
        ? 'COMPLETED'
        : plannerStatus === 'RUNNING'
        ? 'RUNNING'
        : plannerStatus === 'FAILED'
        ? 'FAILED'
        : 'PENDING';

    // Stage 10: Plan Aggregator
    const aggregatorStatus =
      parallelPlannersStatus === 'COMPLETED'
        ? 'COMPLETED'
        : parallelPlannersStatus === 'RUNNING'
        ? 'RUNNING'
        : parallelPlannersStatus === 'FAILED'
        ? 'FAILED'
        : 'PENDING';

    // Stage 11: DAG Validation
    const dagValidationStatus =
      aggregatorStatus === 'COMPLETED'
        ? 'COMPLETED'
        : aggregatorStatus === 'RUNNING'
        ? 'RUNNING'
        : aggregatorStatus === 'FAILED'
        ? 'FAILED'
        : 'PENDING';

    // Stage 12: G3 Ready
    const g3Status = isAwaitingG3
      ? 'ACTION_REQUIRED'
      : isConverting || isCompleted
      ? 'COMPLETED'
      : isFailed
      ? 'FAILED'
      : 'PENDING';"""

new_stage_logic = """    // Stage 7: G1 Human Review
    const g1Status = isAwaitingG1
      ? 'ACTION_REQUIRED'
      : isCharacterizing || isPlanning || isAwaitingG2 || isConverting || isAwaitingG3 || isCompleted
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 8: Characterizer Agent (Phase 5)
    const characterizerStatus = isCharacterizing
      ? 'RUNNING'
      : (isAwaitingG2 || isPlanning || isAwaitingG3 || isConverting || isCompleted)
      ? 'COMPLETED'
      : isFailed
      ? 'FAILED'
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
    const plannerStatus = isFailed
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
      : isConverting || isCompleted
      ? 'COMPLETED'
      : isFailed
      ? 'FAILED'
      : 'PENDING';"""

if old_stage_logic in content:
    content = content.replace(old_stage_logic, new_stage_logic)
    print("Replaced stage status logic in AgentExecution.tsx")
else:
    print("Warning: old_stage_logic not found")

old_stage_definitions = """      {
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
        id: 'planner-coordinator',
        name: 'Planner Coordinator',
        phaseNumber: 8,
        status: plannerStatus,
        shortDescription: 'Orchestrates conversion task decomposition across parallel planners.',
        currentActivity: isFailed
          ? (job?.blocking_reason || 'Agent encountered an unrecoverable failure')
          : isCharacterizing
          ? 'CharacterizerAgent: Recording golden HTTP test vectors and state transitions in container sandbox'
          : plannerStatus === 'RUNNING'
          ? 'Decomposing conversion tasks into parallel planner batches'
          : undefined,
      },
      {
        id: 'parallel-planners',
        name: 'Parallel Planners',
        phaseNumber: 9,
        status: parallelPlannersStatus,
        shortDescription: 'Specialized planners generating module conversion tasks and test harnesses.',
      },
      {
        id: 'plan-aggregator',
        name: 'Plan Aggregator',
        phaseNumber: 10,
        status: aggregatorStatus,
        shortDescription: 'Aggregates individual module conversion plans into unified migration roadmap.',
      },
      {
        id: 'dag-validation',
        name: 'DAG Validation',
        phaseNumber: 11,
        status: dagValidationStatus,
        shortDescription: 'Validates acyclic dependency graph and wave execution order.',
      },
      {
        id: 'gate-g3',
        name: 'G3 Ready',
        phaseNumber: 12,
        status: g3Status,
        isGate: true,
        gateType: 'G3',
        shortDescription: 'Conversion Plan & DAG Ready: Human review of execution waves and cost projections.',
        onActionRequired: () => onOpenGateReview && onOpenGateReview('G3'),
      },"""

new_stage_definitions = """      {
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
        currentActivity: isCharacterizing
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
      },"""

if old_stage_definitions in content:
    content = content.replace(old_stage_definitions, new_stage_definitions)
    print("Replaced stage definitions in AgentExecution.tsx")
else:
    print("Warning: old_stage_definitions not found")

content = content.replace(
    "Math.round((completedPhasesCount / 12) * 100)",
    "Math.round((completedPhasesCount / Math.max(pipelineStages.length, 1)) * 100)"
)

content = content.replace(
    "Phase 4 · {completedPhasesCount} / 12",
    "{job?.workflow_phase ? job.workflow_phase.replace('PHASE_', 'Phase ').replace('_', ' ') : 'Multi-Agent'} · {completedPhasesCount} / {pipelineStages.length}"
)

content = content.replace(
    "{isAwaitingG1 || isAwaitingG3 ?",
    "{isAwaitingG1 || isAwaitingG2 || isAwaitingG3 ?"
)

content = content.replace(
    "Job #{job?.job_id ? job.job_id.substring(0, 8) : 'JOB-0248'}",
    "Job #{job?.job_id ? job.job_id.substring(0, 8) : 'ACTIVE'}"
)

content = content.replace(
    "'37 legacy modules cataloged with AST-backed boundary isolation'",
    "'{job?.modules ? `${job.modules} legacy modules` : 'All project components'} cataloged with AST-backed boundary isolation'"
)

content = content.replace(
    "elapsedTime: '1.2s',",
    ""
)

content = content.replace(
    "elapsedTime: '4.8s',",
    ""
)

target_file.write_text(content, encoding="utf-8")
print("Saved AgentExecution.tsx successfully.")

