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
}

export interface CharacterizationReport {
  suite_id: string;
  version: number;
  content_hash: string;
  status: string;
  runtime_available: boolean;
  schema_status?: string;
  schema_validation_status?: string;
  discovery_evidence?: { path: string; status: string; execution_status: string }[];
  cases: CharacterizationCase[];
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
}
