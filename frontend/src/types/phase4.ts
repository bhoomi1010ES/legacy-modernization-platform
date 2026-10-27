/**
 * TypeScript types for Phase 4: Intake, Legacy Analyzer, Architect, Feasibility, and Planner.
 */

export type ConfidenceLevel = 'CONFIRMED' | 'INFERRED' | 'UNCERTAIN' | 'UNKNOWN';

export type EvidenceType =
  | 'FILE_PATH'
  | 'MANIFEST_ENTRY'
  | 'AST_SYMBOL'
  | 'CODE_EXCERPT'
  | 'CONFIG_KEY'
  | 'TEST_CASE'
  | 'DATABASE_SCHEMA'
  | 'NETWORK_INTERFACE'
  | 'DEPENDENCY_EDGE'
  | 'STATIC_HEURISTIC';

export interface EvidenceRef {
  evidence_id: string;
  source_artifact: string;
  source_path: string;
  source_location?: string | null;
  evidence_type: EvidenceType;
  evidence_excerpt?: string | null;
  content_hash?: string | null;
  confidence: ConfidenceLevel;
  agent_name: string;
  model_version?: string | null;
  artifact_version: number;
  observed_at: string;
}

export interface SourceMetadata {
  repository_id: string;
  source_type: 'git' | 'github' | 'local' | 'archive';
  source_ref: string;
  commit_sha?: string | null;
  content_hash: string;
  archive_size_bytes: number;
  file_count: number;
  acquired_at: string;
  analyzer_version: string;
}

export interface FileInventoryItem {
  path: string;
  size_bytes: number;
  content_hash: string;
  language?: string | null;
  is_manifest: boolean;
  is_test: boolean;
  is_config: boolean;
  is_documentation: boolean;
}

export interface DetectedTechnologyProfile {
  primary_language: string;
  languages: Record<string, number>;
  frameworks: string[];
  build_systems: string[];
  package_managers: string[];
  manifest_files: string[];
  config_files: string[];
  test_frameworks: string[];
  database_dialects: string[];
  confidence: number;
}

export interface RepositorySnapshot {
  snapshot_id: string;
  job_id: string;
  version: number;
  metadata: SourceMetadata;
  tech_profile: DetectedTechnologyProfile;
  inventory_hash: string;
  created_at: string;
  content_hash: string;
}

export interface RepositoryInventory {
  inventory_id: string;
  snapshot_id: string;
  job_id: string;
  total_files: number;
  total_bytes: number;
  files: FileInventoryItem[];
  directories: string[];
  inventory_hash: string;
  created_at: string;
}

export interface AnalysisConflict {
  conflict_id: string;
  subject: string;
  claim_a: string;
  claim_b: string;
  evidence_a: string[];
  evidence_b: string[];
  confidence_a: ConfidenceLevel;
  confidence_b: ConfidenceLevel;
  resolution_status: 'UNRESOLVED' | 'RESOLVED_A' | 'RESOLVED_B' | 'RESOLVED_MERGED' | 'HUMAN_OVERRIDE';
  resolution_notes?: string | null;
  created_at: string;
}

export interface LegacyModule {
  module_id: string;
  path: string;
  responsibility: string;
  language: string;
  framework?: string | null;
  entry_points: string[];
  public_interfaces: string[];
  dependencies: string[];
  dependents: string[];
  configuration_dependencies: string[];
  risk: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  confidence: ConfidenceLevel;
  evidence_refs: string[];
}

export interface DependencyEdge {
  source: string;
  target: string;
  dependency_type: 'CODE_IMPORT' | 'RUNTIME_SERVICE' | 'DATA_STORE' | 'EVENT_QUEUE' | 'EXTERNAL_API';
  evidence: string[];
  confidence: ConfidenceLevel;
}

export interface PublicInterface {
  interface_id: string;
  interface_type:
    | 'REST_ENDPOINT'
    | 'CLI'
    | 'PUBLIC_CLASS'
    | 'FUNCTION'
    | 'EVENT'
    | 'QUEUE'
    | 'SERVICE_CONTRACT'
    | 'EXTERNAL_INTERFACE';
  name: string;
  signature?: string | null;
  location_path: string;
  line_number?: number | null;
  consumer_modules: string[];
  evidence_refs: string[];
}

export interface PersistenceEntity {
  entity_id: string;
  name: string;
  entity_type: 'TABLE' | 'DOCUMENT_COLLECTION' | 'ORM_MODEL' | 'DAO' | 'REPOSITORY' | 'CACHE_KEY' | 'MIGRATION_SCRIPT';
  database_engine?: string | null;
  schema_definition?: string | null;
  source_path: string;
  evidence_refs: string[];
}

export interface ConfigurationItem {
  config_key: string;
  config_type: 'ENV_VAR' | 'FILE_PROPERTY' | 'FEATURE_FLAG' | 'SERVICE_ENDPOINT' | 'SECRET_REFERENCE';
  source_file: string;
  default_value?: string | null;
  secret_reference_detected: boolean;
  evidence_refs: string[];
}

export interface LegacyTestSuite {
  suite_id: string;
  framework: string;
  test_location: string;
  test_count: number;
  test_type: 'UNIT' | 'INTEGRATION' | 'CHARACTERIZATION' | 'E2E';
  covered_modules: string[];
  evidence_refs: string[];
}

export interface ArchitecturalRisk {
  risk_id: string;
  category: 'ARCHITECTURAL' | 'DEPENDENCY' | 'DATA' | 'SECURITY' | 'INTEGRATION' | 'TEST' | 'MIGRATION' | 'OPERATIONAL';
  title: string;
  description: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  inferred: boolean;
  evidence_refs: string[];
  mitigation_suggestion?: string | null;
}

export interface LegacyModel {
  model_id: string;
  job_id: string;
  snapshot_id: string;
  version: number;
  modules: LegacyModule[];
  dependency_graph: DependencyEdge[];
  public_interfaces: PublicInterface[];
  persistence_entities: PersistenceEntity[];
  configurations: ConfigurationItem[];
  test_suites: LegacyTestSuite[];
  risks: ArchitecturalRisk[];
  conflicts: AnalysisConflict[];
  evidence_index: Record<string, EvidenceRef>;
  content_hash: string;
  created_at: string;
}

export type BlueprintStatus = 'DRAFT' | 'UNDER_REVIEW' | 'G1_PENDING' | 'APPROVED' | 'REVISED' | 'LOCKED';

export interface TargetComponent {
  component_id: string;
  name: string;
  target_path: string;
  mapped_legacy_modules: string[];
  responsibilities: string[];
  technologies: string[];
  dependencies: string[];
  interfaces: string[];
}

export interface TargetInterfaceContract {
  contract_id: string;
  component_id: string;
  interface_type: 'REST_API' | 'GRAPHQL' | 'GRPC' | 'MESSAGE_CONSUMER' | 'MESSAGE_PRODUCER' | 'INTERNAL_SERVICE';
  name: string;
  specification: Record<string, any>;
  preserved_legacy_interface_id?: string | null;
}

export interface TargetDataModel {
  model_id: string;
  name: string;
  orm_strategy: string;
  target_engine: string;
  schema_definition: Record<string, any>;
  migration_strategy: string;
  mapped_legacy_entities: string[];
}

export interface TargetBlueprint {
  blueprint_id: string;
  job_id: string;
  version: number;
  status: BlueprintStatus;
  target_stack: string;
  target_architecture: string;
  components: TargetComponent[];
  interfaces: TargetInterfaceContract[];
  data_model: TargetDataModel[];
  integration_contracts: Record<string, any>[];
  deployment_constraints: string[];
  security_constraints: string[];
  compatibility_constraints: string[];
  migration_constraints: string[];
  accepted_decisions: Record<string, any>[];
  open_constraints: string[];
  evidence_refs: string[];
  created_by: string;
  created_at: string;
  content_hash: string;
}

export type CapabilityClassification = 'SUPPORTED' | 'SUBSTITUTE' | 'CUSTOM_BUILD' | 'UNSUPPORTED' | 'UNKNOWN';

export interface FeasibilityCapability {
  capability_id: string;
  category: 'TECHNOLOGY' | 'DATA' | 'INTERFACES' | 'OPERATIONAL' | 'TESTING' | 'SECURITY';
  legacy_requirement: string;
  target_requirement: string;
  classification: CapabilityClassification;
  confidence: number;
  evidence: string[];
  tool_dependency?: string | null;
  effort: 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH';
  risk: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  verification_impact: string;
  recommendation: string;
}

export interface ToolReadiness {
  tool: string;
  availability: boolean;
  version?: string | null;
  compatibility: 'COMPATIBLE' | 'PARTIAL' | 'INCOMPATIBLE' | 'UNKNOWN';
  configuration_status: 'CONFIGURED' | 'NEEDS_SETUP' | 'MISSING';
  readiness: 'READY' | 'BLOCKED' | 'OPTIONAL';
  evidence: string[];
}

export interface FeasibilityReport {
  report_id: string;
  job_id: string;
  version: number;
  blueprint_version: number;
  legacy_model_version: number;
  capabilities: FeasibilityCapability[];
  tool_readiness: ToolReadiness[];
  overall_feasibility_score: number;
  unsupported_count: number;
  custom_build_count: number;
  substitute_count: number;
  unknown_count: number;
  summary: string;
  created_at: string;
  content_hash: string;
}

export type G1DecisionType =
  | 'ACCEPT_SUBSTITUTE'
  | 'ADD_TOOL'
  | 'CUSTOM_BUILD'
  | 'DESCOPE'
  | 'REVISE_BLUEPRINT'
  | 'REQUEST_MORE_ANALYSIS'
  | 'CANCEL'
  | 'REJECT';

export interface G1DecisionRecord {
  decision_id: string;
  job_id: string;
  capability_id?: string | null;
  decision: G1DecisionType;
  reason: string;
  actor: string;
  timestamp: string;
  previous_feasibility_version: number;
  resulting_blueprint_version?: number | null;
}

export interface G1DecisionBatchRequest {
  decisions: G1DecisionRecord[];
  global_decision?: G1DecisionType | null;
  global_rationale?: string | null;
}

export interface PlanningTask {
  task_id: string;
  module_id: string;
  title: string;
  description: string;
  dependencies: string[];
  interfaces: string[];
  migration_steps: string[];
  required_tests: string[];
  acceptance_criteria: string[];
  estimate_hours: number;
  risk: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  required_tools: string[];
  environment_requirements: string[];
  data_considerations?: string | null;
  integration_points: string[];
  evidence_refs: string[];
}

export interface ModulePlanningUnit {
  module_id: string;
  responsibility: string;
  source_scope: string[];
  target_scope: string[];
  dependencies: string[];
  interfaces: string[];
  migration_steps: string[];
  implementation_tasks: PlanningTask[];
  required_tests: string[];
  acceptance_criteria: string[];
  estimate_hours: number;
  risk: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  required_tools: string[];
  environment_requirements: string[];
  data_considerations?: string | null;
  integration_points: string[];
  evidence_refs: string[];
}

export interface ConversionPlanWave {
  wave_number: number;
  name: string;
  module_ids: string[];
  task_ids: string[];
  rationale: string;
}

export interface ConversionPlanValidation {
  is_valid_dag: boolean;
  has_cycles: boolean;
  cycle_nodes: string[][];
  missing_dependencies: string[];
  duplicate_ids: string[];
  invalid_references: string[];
  interface_conflicts: string[];
  scope_overlaps: string[];
  missing_acceptance_criteria_tasks: string[];
  validation_messages: string[];
}

export interface ConversionPlan {
  plan_id: string;
  job_id: string;
  version: number;
  blueprint_version: number;
  modules: ModulePlanningUnit[];
  tasks: PlanningTask[];
  dependencies: DependencyEdge[];
  waves: ConversionPlanWave[];
  interfaces: Record<string, any>[];
  estimates: {
    total_hours: number;
    tasks_count: number;
    modules_count: number;
    risk_distribution: Record<string, number>;
  };
  risks: ArchitecturalRisk[];
  required_tests: string[];
  acceptance_criteria: string[];
  tool_requirements: string[];
  environment_requirements: string[];
  evidence_refs: string[];
  conflicts: string[];
  validation_status: ConversionPlanValidation;
  content_hash: string;
  created_at: string;
}
