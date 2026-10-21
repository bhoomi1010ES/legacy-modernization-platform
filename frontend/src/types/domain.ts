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
  created_at: string;
  updated_at: string;
}

export interface Artifact {
  artifact_id: string;
  job_id: string;
  artifact_type: string;
  version: number;
  content_hash: string;
  storage_path: string;
  producing_agent: string;
  derived_from: string[];
  size_bytes: number;
  created_at: string;
}

export type GateType = 'G1' | 'G2' | 'G3' | 'G4';
export type DecisionOutcome = 'APPROVED' | 'REJECTED';

export interface GateDetail {
  gate_id: string;
  job_id: string;
  job_name: string;
  gate_type: GateType;
  title: string;
  description: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  artifact: string;
  artifact_hash: string;
  cost_summary: string;
  requested_at: string;
  decided_at?: string;
  reviewer?: string;
}

export interface AgentRun {
  run_id: string;
  job_id: string;
  agent_name: string;
  status: 'Active' | 'Idle' | 'Completed' | 'Failed';
  role_description: string;
  tooling: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  started_at: string;
  completed_at?: string;
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
