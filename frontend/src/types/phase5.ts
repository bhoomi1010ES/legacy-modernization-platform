export interface CharacterizationCase {
  test_case_id: string;
  name: string;
  module: string;
  interface: string;
  behavior: string;
  expected: unknown;
  actual: unknown;
  outcome: string;
  normalization: unknown[];
  known_bug?: string;
  side_effects?: unknown;
  fixtures?: unknown;
  limitation?: string;
  evidence_status?: string;
  observed_candidate?: boolean;
  execution_mode?: 'REAL_CONTAINER' | 'IN_MEMORY_DOUBLE' | 'UNAVAILABLE';
  reproducibility?: 'DETERMINISTIC' | 'NON_DETERMINISTIC' | 'FAILED' | 'UNAVAILABLE';
  duration_ms?: number;
  exit_status?: number;
  stdout_sample?: string;
  stderr_sample?: string;
  captured_at?: string;
  provenance?: Record<string, unknown>;
  execution_metadata?: Record<string, unknown>;
}

export interface SchemaFinding {
  construct: string;
  name: string;
  status: 'SUPPORTED' | 'REVIEW_REQUIRED' | 'UNSUPPORTED' | 'BLOCKED';
  reason: string;
  file?: string;
  raw_sql?: string;
}

export interface CharacterizationReport {
  suite_id: string;
  version: number;
  content_hash: string;
  status: string;
  runtime_available: boolean;
  execution_mode?: string;
  schema_status?: string;
  schema_validation_status?: string;
  discovery_evidence?: { path: string; status: string; execution_status: string }[];
  cases: CharacterizationCase[];
  schema_findings?: SchemaFinding[];
  g2_readiness?: {
    scenario_count: number;
    approved_count: number;
    executed_count: number;
    golden_count: number;
    untested_count: number;
    non_reproducible_count: number;
    blocking_reasons: string[];
    ready_for_g2: boolean;
  };
  coverage: {
    modules: { name: string; covered: boolean; status?: string; observed?: boolean }[];
    interfaces: { name: string; covered: boolean; status?: string; observed?: boolean }[];
    behaviors: { name: string; covered: boolean; status?: string; observed?: boolean }[];
    untested_paths: string[];
    limitations: string[];
    percent: number;
  };
  known_bugs: unknown[];
  normalization: unknown[];
  environment: Record<string, unknown>;
  gate_id?: string;
}

export interface SchemaAnalysis {
  status?: string;
  tables: unknown[];
  differences: unknown[];
  limitations: string[];
  findings?: SchemaFinding[];
}

export interface DataMigrationPlan {
  status?: string;
  validation_status?: string;
  mappings: unknown[];
  upgrade_sql: string;
  rollback_sql: string;
  validation_queries: unknown[];
  risks: string[];
  scope: string;
  schema_findings?: SchemaFinding[];
}

