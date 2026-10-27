import type { Job, Artifact, GateDetail, AgentRun, AuditEvent, User, DecisionOutcome, GateType } from './domain';

export interface ApiResponse<T> {
  data?: T;
  error?: {
    code: string;
    message: string;
    request_id: string;
    details?: Array<{ field?: string; issue: string }>;
  };
}

export interface JobListResponse {
  items: Job[];
  total: number;
  offset: number;
  limit: number;
}

export interface JobCreateRequest {
  name: string;
  source_repository: string;
  source_revision?: string;
  source_stack?: string;
  target_stack: string;
  budget: number;
  max_repair_attempts?: number;
  constraints?: string;
  stack_metadata?: Record<string, any>;
  pinned_commit?: string;
  user_overrides?: Record<string, any>;
  git_token?: string;
  source_type?: 'git' | 'local';
  preview_snapshot_id?: string;
  snapshot_fingerprint?: string;
}

export interface JobIntakeRequest {
  git_token?: string;
  preview_snapshot_id?: string;
  snapshot_fingerprint?: string;
}

export interface GateDecisionRequest {
  decision: DecisionOutcome;
  rationale: string;
  waivers?: Array<{ test_id: string; difference_type: string; waiver_rationale: string }>;
  options?: Record<string, string>;
}

export interface GateDecisionResponse {
  decision_id: string;
  job_id: string;
  gate_id: string;
  gate_type: GateType;
  decision: DecisionOutcome;
  rationale: string;
  reviewer: string;
  decided_at: string;
}

export interface PendingGatesResponse {
  items: GateDetail[];
  total: number;
}

export interface VerificationReportResponse {
  job_id: string;
  total_tests: number;
  passing_tests: number;
  behavioral_equivalence_pct: number;
  regressions_count: number;
  intended_differences_count: number;
    uncovered_code_pct: number | null;
  differences: Array<{
    test_name: string;
    module: string;
    classification: string;
    legacy_behavior: string;
    converted_behavior: string;
    resolution: string;
  }>;
}

export interface DeliveryReportResponse {
  job_id: string;
  project_name: string;
  integration_branch: string;
  pull_request_url: string;
  equivalence_pct: number;
  signed_waivers_count: number;
  production_cutover_included: boolean;
  included_artifacts: string[];
    delivered_at: string | null;
}

export interface TierComponent {
  name: string;
  relative_path: string;
  technology: string;
  framework: string;
  version?: string;
  primary_language?: string;
  build_tool_or_driver?: string;
  evidence?: Array<{ file: string; reason: string }>;
}

export interface DatabaseComponent {
  name: string;
  relative_path: string;
  engine: string;
  version?: string;
  orm_or_driver?: string;
  schema_artifacts?: string[];
  migration_tool?: string;
  inferred_from: string;
  confidence: number;
  evidence?: Array<{ file: string; reason: string }>;
}

export interface TierGroup {
  primary?: TierComponent;
  components?: TierComponent[];
}

export interface DatabaseTierGroup {
  primary?: DatabaseComponent;
  components?: DatabaseComponent[];
}

export interface TieredStackBreakdown {
  frontend?: TierGroup;
  backend?: TierGroup;
  database?: DatabaseTierGroup;
}

export interface DetectedStackResponse {
  source_repository: string;
  source_revision: string;
  requested_revision?: string;
  source_type?: 'git' | 'local' | string;
  preview_snapshot_id?: string;
  snapshot_fingerprint?: string;
  primary_language: string;
  language_version: string;
  framework: string;
  framework_version: string;
  build_tool: string;
  build_file: string;
  test_framework: string;
  architecture_style: string;
  confidence_score: number;
  summary_stack: string;
  detection_method: string;
  metadata?: Record<string, any>;
  scan_status?: 'COMPLETED' | 'PARTIAL' | 'INCONCLUSIVE' | 'FAILED' | string;
  is_fallback?: boolean;
  warnings?: string[];
  tiers?: TieredStackBreakdown;
  components?: Array<{
    component_id: string;
    name: string;
    relative_path: string;
    component_type: string;
    primary_language: string;
    framework: string;
    build_tool: string;
    manifest_files: string[];
    evidence?: Array<{ file: string; reason: string }>;
  }>;
  languages?: Record<string, { file_count: number; byte_count: number; percentage: number }>;
  frameworks?: Array<{ name: string; version: string; category: string; manifest: string }>;
  evidence?: Array<{ file: string; reason: string }>;
  resolved_commit?: string;
  detector_version?: string;
  scanned_at?: string;
}


