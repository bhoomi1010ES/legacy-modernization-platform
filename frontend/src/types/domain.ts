export type JobStatus =
  | 'CREATED'
  | 'INTAKE'
  | 'ANALYZING'
  | 'AWAITING_GATE_G1'
  | 'CHARACTERIZING'
  | 'AWAITING_GATE_G2'
  | 'PLANNING'
  | 'AWAITING_GATE_G3'
  | 'CONVERTING'
  | 'VERIFYING'
  | 'INTEGRATING'
  | 'AWAITING_GATE_G4'
  | 'PAUSED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface User {
  user_id: string;
  email: string;
  full_name: string;
  role: 'SUPER_ADMIN' | 'ADMIN' | 'REVIEWER' | 'DEVELOPER' | 'VIEWER';
  status: string;
  permissions?: string[];
  created_at: string;
}

export interface Job {
  job_id: string;
  name: string;
  source_repository: string;
  source_revision: string;
  source_stack: string;
  target_stack: string;
  status: JobStatus;
  progress: number;
  modules: number;
  cost: number;
  budget: number;
  owner: string;
  max_repair_attempts: number;
  integration_branch?: string;
  pull_request_url?: string;
  current_gate?: string;
  blocking_reason?: string;
  workflow_phase?: string;
  active_node?: string;
  created_at: string;
  updated_at: string;
}

export interface Artifact {
  artifact_id: string;
  job_id: string;
  artifact_type: string;
  version: number;
  content_hash: string;
  producing_agent: string;
  derived_from: string[];
  size_bytes: number;
  created_at: string;
}

export type GateType = 'G1' | 'G2' | 'G3' | 'G4';
export type DecisionOutcome = 'APPROVED' | 'REJECTED' | 'NEEDS_CHANGES';

export interface GateVerificationItem {
  id: string;
  title: string;
  description: string;
  mandatory?: boolean;
}

export interface GateMetricItem {
  label: string;
  value: string;
  subtext?: string;
  badge?: string;
}

export interface GateVerificationGuide {
  producing_agent: string;
  producing_agent_role: string;
  work_summary: string;
  key_deliverables: string[];
  metrics: GateMetricItem[];
  checklist: GateVerificationItem[];
  next_agent: string;
  next_agent_role: string;
  next_agent_preview: string;
}

export interface GateDetail {
  gate_id: string;
  job_id: string;
  job_name: string;
  gate_type: GateType;
  title: string;
  description: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'NEEDS_CHANGES' | 'INVALIDATED' | 'TIMED_OUT';
  artifact: string;
  artifact_hash: string;
  cost_summary: string;
  requested_at: string;
  decided_at?: string;
  reviewer?: string;
  version?: number;
  rationale?: string;
  artifact_hashes?: Record<string, string>;
  allowed_actions?: string[];
  verification_guide?: GateVerificationGuide;
  blocking_reason?: string;
}

export interface WorkflowPhase {
  node: string;
  label: string;
  status: 'PENDING' | 'RUNNING' | 'BLOCKED' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED';
}

export interface WorkflowState {
  job_id: string;
    workflow_id?: string;
    current_phase?: 'INTAKE' | 'G1' | 'CHARACTERIZATION' | 'SCHEMA_DATA' | 'G2' | 'PLANNING' | 'G3' | 'CONVERSION' | 'VERIFICATION' | 'INTEGRATION' | 'G4' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  status: JobStatus;
  active_node: string;
  blocking_reason?: string;
  checkpoint_sequence: number;
  workflow_version: number;
  budget_used: number;
  budget_limit: number;
  budget_warning: boolean;
  allowed_actions: Array<'cancel' | 'pause' | 'resume'>;
  phases: WorkflowPhase[];
    workspace?: {
      status: 'RECEIVED' | 'UNAVAILABLE' | 'RECOVERING' | 'RECOVERY_FAILED' | 'READY';
      received: boolean;
      staged: boolean;
      validated: boolean;
      ready: boolean;
      workspace_name?: string;
      commit_sha?: string;
      error_code?: string;
      message?: string;
    };
    active_task_ids?: string[];
    completed_task_ids?: string[];
    blocked_task_ids?: string[];
    failed_task_ids?: string[];
    pending_gate_id?: string;
    approved_artifact_versions?: Record<string, number>;
    artifact_hashes?: Record<string, string>;
    retry_counts?: Record<string, number>;
    dependency_state?: Record<string, unknown>;
    last_transition?: string;
    failure_reason?: string;
    terminal_reason?: string;
  updated_at: string;
}

export interface WorkflowEvent {
  event_id: string;
  event_type: string;
  actor_type: string;
  actor_id: string;
  correlation_id?: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface VersionedGate {
  gate_id: string;
  job_id: string;
  gate_type: GateType;
  version: number;
  status: GateDetail['status'];
  artifact_ids: string[];
  artifact_hashes: Record<string, string>;
  blocking_reason?: string;
  requested_at: string;
  decided_at?: string;
  allowed_actions: string[];
}

export interface AgentRun {
  run_id: string;
  job_id: string;
  agent_name: string;
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'BLOCKED' | 'CANCELLED' | 'Active' | 'Idle' | 'Completed' | 'Failed';
  role_description?: string;
  tooling?: string;
  model_identifier?: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  failure_classification?: string;
  error_message?: string;
  evidence_artifact_ids?: string[];
  output_payload?: any;
}

export interface AgentTraceStep {
  step_number: number;
  step_type: string;
  content: unknown;
  duration_ms: number;
  timestamp: string;
}

export interface AgentToolCallSummary {
  call_id: string;
  tool_name: string;
  is_read_only: boolean;
  ok: boolean;
  duration_ms: number;
  error?: string;
  arguments_summary: Record<string, unknown>;
  output_summary?: string;
  timestamp: string;
}

export interface AgentTrace {
  run_id: string;
  job_id: string;
  agent_name: string;
  status: AgentRun['status'];
  model_identifier: string;
  duration_seconds: number;
  total_tokens: number;
  cost_usd: number;
  started_at: string;
  completed_at?: string;
  failure_classification?: string;
  error_message?: string;
  steps: AgentTraceStep[];
  tool_calls: AgentToolCallSummary[];
  output_evidence?: Record<string, unknown>;
  evidence_artifacts: string[];
}

export interface AuditEvent {
  event_id: string;
  job_id: string;
  event_type: string;
  actor_type: 'USER' | 'AGENT' | 'SYSTEM' | 'HUMAN' | string;
  actor_id: string;
  action: string;
  correlation_id?: string;
  payload?: Record<string, any>;
  created_at: string;
}
