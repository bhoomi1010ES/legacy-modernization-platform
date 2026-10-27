export interface ModuleCheck {
  category: string;
  command: string[];
  exit_code: number | null;
  duration_ms: number;
  status: string;
  stdout?: string;
  stderr?: string;
  artifact_hash?: string;
}

export interface ModuleFinding {
  finding_id: string;
  severity: string;
  category: string;
  message: string;
  path?: string;
  line?: number;
  evidence_ref?: string;
}

export interface ModuleReview {
  status: string;
  findings: ModuleFinding[];
}

export interface ModuleAttempt {
  attempt_id: string;
  module_id: string;
  attempt_number: number;
  status: string;
  git_branch?: string;
  failure_reason?: string | null;
  allowed_actions?: string[];
  completed_at?: string | null;
  metadata?: Record<string, unknown>;
  evidence?: {
    changed_files?: string[];
    diff?: string;
    checks?: ModuleCheck[];
    review?: ModuleReview;
    design_notes?: unknown;
    assumptions?: unknown;
    repair_feedback?: unknown;
    baseline_hash?: string;
    source_commit?: string;
    workspace?: string;
    [key: string]: unknown;
  };
}

export interface ExecutionModule {
  module_id: string;
  name: string;
  status: string;
  dependency_blockers: string[];
  attempts: ModuleAttempt[];
}

export interface ModuleExecutionBoard {
  modules: ExecutionModule[];
  items: ModuleAttempt[];
  runtime_available: boolean;
  allowed_actions?: string[];
}
