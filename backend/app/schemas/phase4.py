"""Typed schemas and contracts for Phase 4: Intake, Analysis, Architect, Feasibility, and Planning."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Set
import uuid
from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ==============================================================================
# EVIDENCE & INTEGRITY CONTRACTS
# ==============================================================================

class EvidenceType(str, Enum):
    FILE_PATH = "FILE_PATH"
    MANIFEST_ENTRY = "MANIFEST_ENTRY"
    AST_SYMBOL = "AST_SYMBOL"
    CODE_EXCERPT = "CODE_EXCERPT"
    CONFIG_KEY = "CONFIG_KEY"
    TEST_CASE = "TEST_CASE"
    DATABASE_SCHEMA = "DATABASE_SCHEMA"
    NETWORK_INTERFACE = "NETWORK_INTERFACE"
    DEPENDENCY_EDGE = "DEPENDENCY_EDGE"
    STATIC_HEURISTIC = "STATIC_HEURISTIC"


class ConfidenceLevel(str, Enum):
    CONFIRMED = "CONFIRMED"
    INFERRED = "INFERRED"
    UNCERTAIN = "UNCERTAIN"
    UNKNOWN = "UNKNOWN"


class EvidenceRef(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:12]}")
    source_artifact: str = Field(..., description="Artifact or snapshot ID containing the source evidence")
    source_path: str = Field(..., description="Repository-relative POSIX path")
    source_location: Optional[str] = Field(None, description="Line number range, symbol name, or JSON pointer")
    evidence_type: EvidenceType = Field(..., description="Category of evidence observed")
    evidence_excerpt: Optional[str] = Field(None, description="Sanitized excerpt or summary (never raw secrets)")
    content_hash: Optional[str] = Field(None, description="SHA-256 hash of the evidence snippet or file")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.CONFIRMED)
    agent_name: str = Field("analyzer", description="Agent that captured this evidence")
    model_version: Optional[str] = Field(None, description="Model provider/identifier used")
    artifact_version: int = Field(1, ge=1)
    observed_at: datetime = Field(default_factory=utc_now)
    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# INTAKE & REPOSITORY INVENTORY CONTRACTS
# ==============================================================================

class SourceMetadata(BaseModel):
    repository_id: str
    source_type: Literal["git", "github", "local", "archive"] = "git"
    source_ref: str
    commit_sha: Optional[str] = None
    content_hash: str
    archive_size_bytes: int = 0
    file_count: int = 0
    acquired_at: datetime = Field(default_factory=utc_now)
    analyzer_version: str = "4.0.0"
    model_config = ConfigDict(extra="forbid")


class FileInventoryItem(BaseModel):
    path: str
    size_bytes: int
    content_hash: str
    language: Optional[str] = None
    is_manifest: bool = False
    is_test: bool = False
    is_config: bool = False
    is_documentation: bool = False
    model_config = ConfigDict(extra="forbid")


class DetectedTechnologyProfile(BaseModel):
    primary_language: str
    languages: Dict[str, float] = Field(default_factory=dict, description="Language percentage distribution")
    frameworks: List[str] = Field(default_factory=list)
    build_systems: List[str] = Field(default_factory=list)
    package_managers: List[str] = Field(default_factory=list)
    manifest_files: List[str] = Field(default_factory=list)
    config_files: List[str] = Field(default_factory=list)
    test_frameworks: List[str] = Field(default_factory=list)
    database_dialects: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_config = ConfigDict(extra="forbid")


class RepositorySnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: f"snap_{uuid.uuid4().hex[:12]}")
    job_id: str
    version: int = 1
    metadata: SourceMetadata
    tech_profile: DetectedTechnologyProfile
    inventory_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    content_hash: str
    model_config = ConfigDict(extra="forbid")


class RepositoryInventory(BaseModel):
    inventory_id: str = Field(default_factory=lambda: f"inv_{uuid.uuid4().hex[:12]}")
    snapshot_id: str
    job_id: str
    total_files: int
    total_bytes: int
    files: List[FileInventoryItem] = Field(default_factory=list)
    directories: List[str] = Field(default_factory=list)
    inventory_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# LEGACY ANALYZER & WORKER CONTRACTS
# ==============================================================================

class AnalysisType(str, Enum):
    STRUCTURE_MODULES = "STRUCTURE_MODULES"
    DEPENDENCIES = "DEPENDENCIES"
    PUBLIC_INTERFACES = "PUBLIC_INTERFACES"
    PERSISTENCE_DATA = "PERSISTENCE_DATA"
    CONFIGURATION = "CONFIGURATION"
    TESTS = "TESTS"
    INTEGRATION_EXTERNAL = "INTEGRATION_EXTERNAL"
    RISK_SECURITY = "RISK_SECURITY"


class WorkerLifecycleStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    OBSERVING = "OBSERVING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class AnalyzerWorkerResult(BaseModel):
    worker_id: str = Field(default_factory=lambda: f"worker_{uuid.uuid4().hex[:12]}")
    analysis_type: AnalysisType
    input_scope: List[str] = Field(default_factory=list)
    status: WorkerLifecycleStatus = WorkerLifecycleStatus.COMPLETED
    findings: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[EvidenceRef] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    model_version: str = "deterministic-scanner"
    prompt_version: str = "v4.0"
    artifact_hash: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class AnalysisConflict(BaseModel):
    conflict_id: str = Field(default_factory=lambda: f"conf_{uuid.uuid4().hex[:12]}")
    subject: str = Field(..., description="Subject or entity under dispute (e.g. module_boundary, database_engine)")
    claim_a: str
    claim_b: str
    evidence_a: List[str] = Field(default_factory=list, description="EvidenceRef IDs supporting claim A")
    evidence_b: List[str] = Field(default_factory=list, description="EvidenceRef IDs supporting claim B")
    confidence_a: ConfidenceLevel = ConfidenceLevel.CONFIRMED
    confidence_b: ConfidenceLevel = ConfidenceLevel.CONFIRMED
    resolution_status: Literal["UNRESOLVED", "RESOLVED_A", "RESOLVED_B", "RESOLVED_MERGED", "HUMAN_OVERRIDE"] = "UNRESOLVED"
    resolution_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# CANONICAL LEGACY MODEL
# ==============================================================================

class LegacyModule(BaseModel):
    module_id: str
    path: str
    responsibility: str
    language: str
    framework: Optional[str] = None
    entry_points: List[str] = Field(default_factory=list)
    public_interfaces: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list, description="Module IDs this module depends on")
    dependents: List[str] = Field(default_factory=list, description="Module IDs that depend on this module")
    configuration_dependencies: List[str] = Field(default_factory=list)
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED
    evidence_refs: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class DependencyEdge(BaseModel):
    source: str
    target: str
    dependency_type: Literal["CODE_IMPORT", "RUNTIME_SERVICE", "DATA_STORE", "EVENT_QUEUE", "EXTERNAL_API"] = "CODE_IMPORT"
    evidence: List[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED
    model_config = ConfigDict(extra="forbid")


class PublicInterface(BaseModel):
    interface_id: str = Field(default_factory=lambda: f"iface_{uuid.uuid4().hex[:10]}")
    interface_type: Literal["REST_ENDPOINT", "CLI", "PUBLIC_CLASS", "FUNCTION", "EVENT", "QUEUE", "SERVICE_CONTRACT", "EXTERNAL_INTERFACE"]
    name: str
    signature: Optional[str] = None
    location_path: str
    line_number: Optional[int] = None
    consumer_modules: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class PersistenceEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: f"entity_{uuid.uuid4().hex[:10]}")
    name: str
    entity_type: Literal["TABLE", "DOCUMENT_COLLECTION", "ORM_MODEL", "DAO", "REPOSITORY", "CACHE_KEY", "MIGRATION_SCRIPT"]
    database_engine: Optional[str] = None
    schema_definition: Optional[str] = None
    source_path: str
    evidence_refs: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class ConfigurationItem(BaseModel):
    config_key: str
    config_type: Literal["ENV_VAR", "FILE_PROPERTY", "FEATURE_FLAG", "SERVICE_ENDPOINT", "SECRET_REFERENCE"]
    source_file: str
    default_value: Optional[str] = None
    secret_reference_detected: bool = False
    evidence_refs: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class LegacyTestSuite(BaseModel):
    suite_id: str = Field(default_factory=lambda: f"suite_{uuid.uuid4().hex[:10]}")
    framework: str
    test_location: str
    test_count: int = 0
    test_type: Literal["UNIT", "INTEGRATION", "CHARACTERIZATION", "E2E"] = "UNIT"
    covered_modules: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class ArchitecturalRisk(BaseModel):
    risk_id: str = Field(default_factory=lambda: f"risk_{uuid.uuid4().hex[:10]}")
    category: Literal["ARCHITECTURAL", "DEPENDENCY", "DATA", "SECURITY", "INTEGRATION", "TEST", "MIGRATION", "OPERATIONAL"]
    title: str
    description: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    inferred: bool = False
    evidence_refs: List[str] = Field(default_factory=list)
    mitigation_suggestion: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class LegacyModel(BaseModel):
    model_id: str = Field(default_factory=lambda: f"legacy_{uuid.uuid4().hex[:12]}")
    job_id: str
    snapshot_id: str
    version: int = 1
    modules: List[LegacyModule] = Field(default_factory=list)
    dependency_graph: List[DependencyEdge] = Field(default_factory=list)
    public_interfaces: List[PublicInterface] = Field(default_factory=list)
    persistence_entities: List[PersistenceEntity] = Field(default_factory=list)
    configurations: List[ConfigurationItem] = Field(default_factory=list)
    test_suites: List[LegacyTestSuite] = Field(default_factory=list)
    risks: List[ArchitecturalRisk] = Field(default_factory=list)
    conflicts: List[AnalysisConflict] = Field(default_factory=list)
    evidence_index: Dict[str, EvidenceRef] = Field(default_factory=dict)
    content_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# TARGET BLUEPRINT CONTRACTS (ARCHITECT AGENT)
# ==============================================================================

class BlueprintStatus(str, Enum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    G1_PENDING = "G1_PENDING"
    APPROVED = "APPROVED"
    REVISED = "REVISED"
    LOCKED = "LOCKED"


class TargetComponent(BaseModel):
    component_id: str
    name: str
    target_path: str
    mapped_legacy_modules: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list, description="Target component IDs")
    interfaces: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class TargetInterfaceContract(BaseModel):
    contract_id: str
    component_id: str
    interface_type: Literal["REST_API", "GRAPHQL", "GRPC", "MESSAGE_CONSUMER", "MESSAGE_PRODUCER", "INTERNAL_SERVICE"]
    name: str
    specification: Dict[str, Any] = Field(default_factory=dict)
    preserved_legacy_interface_id: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class TargetDataModel(BaseModel):
    model_id: str
    name: str
    orm_strategy: str
    target_engine: str
    schema_definition: Dict[str, Any] = Field(default_factory=dict)
    migration_strategy: str
    mapped_legacy_entities: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class TargetBlueprint(BaseModel):
    blueprint_id: str = Field(default_factory=lambda: f"bp_{uuid.uuid4().hex[:12]}")
    job_id: str
    version: int = 1
    status: BlueprintStatus = BlueprintStatus.DRAFT
    target_stack: str
    target_architecture: str
    components: List[TargetComponent] = Field(default_factory=list)
    interfaces: List[TargetInterfaceContract] = Field(default_factory=list)
    data_model: List[TargetDataModel] = Field(default_factory=list)
    integration_contracts: List[Dict[str, Any]] = Field(default_factory=list)
    deployment_constraints: List[str] = Field(default_factory=list)
    security_constraints: List[str] = Field(default_factory=list)
    compatibility_constraints: List[str] = Field(default_factory=list)
    migration_constraints: List[str] = Field(default_factory=list)
    accepted_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    open_constraints: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    created_by: str = "architect-agent"
    created_at: datetime = Field(default_factory=utc_now)
    content_hash: str
    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# FEASIBILITY & G1 HUMAN GAP DECISION CONTRACTS
# ==============================================================================

class CapabilityClassification(str, Enum):
    SUPPORTED = "SUPPORTED"
    SUBSTITUTE = "SUBSTITUTE"
    CUSTOM_BUILD = "CUSTOM_BUILD"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class FeasibilityCapability(BaseModel):
    capability_id: str
    category: Literal["TECHNOLOGY", "DATA", "INTERFACES", "OPERATIONAL", "TESTING", "SECURITY"]
    legacy_requirement: str
    target_requirement: str
    classification: CapabilityClassification
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    tool_dependency: Optional[str] = None
    effort: Literal["LOW", "MEDIUM", "HIGH", "VERY_HIGH"] = "MEDIUM"
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    verification_impact: str
    recommendation: str
    model_config = ConfigDict(extra="forbid")


class ToolReadiness(BaseModel):
    tool: str
    availability: bool
    version: Optional[str] = None
    compatibility: Literal["COMPATIBLE", "PARTIAL", "INCOMPATIBLE", "UNKNOWN"] = "COMPATIBLE"
    configuration_status: Literal["CONFIGURED", "NEEDS_SETUP", "MISSING"] = "CONFIGURED"
    readiness: Literal["READY", "BLOCKED", "OPTIONAL"] = "READY"
    evidence: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class FeasibilityReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"feas_{uuid.uuid4().hex[:12]}")
    job_id: str
    version: int = 1
    blueprint_version: int
    legacy_model_version: int
    capabilities: List[FeasibilityCapability] = Field(default_factory=list)
    tool_readiness: List[ToolReadiness] = Field(default_factory=list)
    overall_feasibility_score: float = Field(..., ge=0.0, le=1.0)
    unsupported_count: int = 0
    custom_build_count: int = 0
    substitute_count: int = 0
    unknown_count: int = 0
    summary: str
    created_at: datetime = Field(default_factory=utc_now)
    content_hash: str
    model_config = ConfigDict(extra="forbid")


class G1DecisionType(str, Enum):
    ACCEPT_SUBSTITUTE = "ACCEPT_SUBSTITUTE"
    ADD_TOOL = "ADD_TOOL"
    CUSTOM_BUILD = "CUSTOM_BUILD"
    DESCOPE = "DESCOPE"
    REVISE_BLUEPRINT = "REVISE_BLUEPRINT"
    REQUEST_MORE_ANALYSIS = "REQUEST_MORE_ANALYSIS"
    CANCEL = "CANCEL"
    REJECT = "REJECT"


class G1DecisionRecord(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"g1_{uuid.uuid4().hex[:12]}")
    job_id: str
    capability_id: Optional[str] = None
    decision: G1DecisionType
    reason: str = Field(..., min_length=10)
    actor: str
    timestamp: datetime = Field(default_factory=utc_now)
    previous_feasibility_version: int
    resulting_blueprint_version: Optional[int] = None
    model_config = ConfigDict(extra="forbid")


class G1DecisionBatchRequest(BaseModel):
    decisions: List[G1DecisionRecord]
    global_decision: Optional[G1DecisionType] = None
    global_rationale: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# PLANNER & CONVERSION PLAN CONTRACTS
# ==============================================================================

class PlanningTask(BaseModel):
    task_id: str
    module_id: str
    title: str
    description: str
    dependencies: List[str] = Field(default_factory=list, description="Task IDs this task depends on")
    interfaces: List[str] = Field(default_factory=list)
    migration_steps: List[str] = Field(default_factory=list)
    required_tests: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    estimate_hours: float = Field(default=1.0, ge=0.1)
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    required_tools: List[str] = Field(default_factory=list)
    environment_requirements: List[str] = Field(default_factory=list)
    data_considerations: Optional[str] = None
    integration_points: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class ModulePlanningUnit(BaseModel):
    module_id: str
    responsibility: str
    source_scope: List[str] = Field(default_factory=list)
    target_scope: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list, description="Module IDs depended upon")
    interfaces: List[str] = Field(default_factory=list)
    migration_steps: List[str] = Field(default_factory=list)
    implementation_tasks: List[PlanningTask] = Field(default_factory=list)
    required_tests: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    estimate_hours: float = Field(default=1.0, ge=0.1)
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    required_tools: List[str] = Field(default_factory=list)
    environment_requirements: List[str] = Field(default_factory=list)
    data_considerations: Optional[str] = None
    integration_points: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class ConversionPlanWave(BaseModel):
    wave_number: int
    name: str
    module_ids: List[str] = Field(default_factory=list)
    task_ids: List[str] = Field(default_factory=list)
    rationale: str
    model_config = ConfigDict(extra="forbid")


class ConversionPlanValidation(BaseModel):
    is_valid_dag: bool
    has_cycles: bool = False
    cycle_nodes: List[List[str]] = Field(default_factory=list)
    missing_dependencies: List[str] = Field(default_factory=list)
    duplicate_ids: List[str] = Field(default_factory=list)
    invalid_references: List[str] = Field(default_factory=list)
    interface_conflicts: List[str] = Field(default_factory=list)
    scope_overlaps: List[str] = Field(default_factory=list)
    missing_acceptance_criteria_tasks: List[str] = Field(default_factory=list)
    validation_messages: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class PlanEstimates(BaseModel):
    total_hours: float = 0.0
    model_config = ConfigDict(extra="forbid")


class ConversionPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    job_id: str
    version: int = 1
    blueprint_version: int
    modules: List[ModulePlanningUnit] = Field(default_factory=list)
    tasks: List[PlanningTask] = Field(default_factory=list)
    dependencies: List[DependencyEdge] = Field(default_factory=list)
    waves: List[ConversionPlanWave] = Field(default_factory=list)
    interfaces: List[Dict[str, Any]] = Field(default_factory=list)
    total_estimate_hours: float = 0.0
    estimates: Optional[PlanEstimates] = None
    risk_summary: Dict[str, int] = Field(default_factory=dict)
    risks: Optional[Dict[str, int]] = None
    required_tests_count: int = 0
    acceptance_criteria_completeness_pct: float = 100.0
    tool_requirements: List[str] = Field(default_factory=list)
    environment_requirements: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    validation: ConversionPlanValidation
    validation_status: Optional[ConversionPlanValidation] = None
    content_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    # Complete provenance fields
    provenance: Dict[str, Any] = Field(default_factory=dict)
    repo_inventory_hash: Optional[str] = None
    legacy_model_hash: Optional[str] = None
    target_blueprint_hash: Optional[str] = None
    feasibility_report_hash: Optional[str] = None
    g1_decision_hash: Optional[str] = None
    characterization_suite_hash: Optional[str] = None
    characterization_coverage_hash: Optional[str] = None
    schema_data_plan_hash: Optional[str] = None
    planner_version: str = "v4.5"
    model_config = ConfigDict(extra="forbid")

    def model_post_init(self, __context: Any) -> None:
        if self.validation_status is None and self.validation is not None:
            object.__setattr__(self, "validation_status", self.validation)
        elif self.validation is None and self.validation_status is not None:
            object.__setattr__(self, "validation", self.validation_status)
        if self.estimates is None:
            object.__setattr__(self, "estimates", PlanEstimates(total_hours=self.total_estimate_hours))
        if self.risks is None:
            object.__setattr__(self, "risks", self.risk_summary)


class PlanningContext(BaseModel):
    """Authoritative input context feeding ModulePlanner and PlanAggregator."""
    job_id: str
    legacy_model: LegacyModel
    target_blueprint: TargetBlueprint
    feasibility_report: Optional[FeasibilityReport] = None
    g1_decisions: List[G1DecisionRecord] = Field(default_factory=list)
    characterization_suite: Optional[Dict[str, Any]] = None
    characterization_coverage: Optional[Dict[str, Any]] = None
    schema_data_plan: Optional[Dict[str, Any]] = None
    provenance_hashes: Dict[str, str] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# G3 READINESS PACKAGE CONTRACT
# ==============================================================================

class G3ReadinessPackage(BaseModel):
    job_id: str
    blueprint_version: int
    planner_versions: List[str] = Field(default_factory=list)
    conversion_plan_version: int
    module_list: List[Dict[str, Any]] = Field(default_factory=list)
    dependency_dag: Dict[str, List[str]] = Field(default_factory=dict)
    waves: List[ConversionPlanWave] = Field(default_factory=list)
    risk_summary: Dict[str, Any] = Field(default_factory=dict)
    estimate_summary: Dict[str, Any] = Field(default_factory=dict)
    unresolved_conflicts: List[AnalysisConflict] = Field(default_factory=list)
    missing_dependencies: List[str] = Field(default_factory=list)
    acceptance_criteria_completeness: float
    evidence_coverage_pct: float
    feasibility_assumptions: List[Dict[str, Any]] = Field(default_factory=list)
    g1_decisions: List[G1DecisionRecord] = Field(default_factory=list)
    ready_for_g3_decision: bool = True
    g3_ready: bool = True
    dag_valid: bool = True
    acceptance_criteria_summary: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    prepared_at: datetime = Field(default_factory=utc_now)
    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# API REQUEST & RESPONSE SCHEMAS
# ==============================================================================

class AnalysisRetryRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)
    optional_constraints: Optional[Dict[str, Any]] = None
    slices_to_retry: Optional[List[AnalysisType]] = None
    model_config = ConfigDict(extra="forbid")


class PlanRevisionRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)
    module_overrides: Optional[Dict[str, Any]] = None
    dependency_adjustments: Optional[List[Dict[str, str]]] = None
    model_config = ConfigDict(extra="forbid")


class AnalysisDetailResponse(BaseModel):
    legacy_model: LegacyModel
    evidence_index: Dict[str, EvidenceRef] = Field(default_factory=dict)
    conflicts: List[AnalysisConflict] = Field(default_factory=list)
    analysis_version: int = 1
    content_hash: str
    model_config = ConfigDict(extra="forbid")


class FeasibilityDetailResponse(BaseModel):
    feasibility_report: FeasibilityReport
    capabilities: List[FeasibilityCapability] = Field(default_factory=list)
    tool_readiness: List[ToolReadiness] = Field(default_factory=list)
    decisions_history: List[G1DecisionRecord] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class BlueprintDetailResponse(BaseModel):
    blueprint: TargetBlueprint
    version: int
    status: BlueprintStatus
    content_hash: str
    model_config = ConfigDict(extra="forbid")


class ConversionPlanDetailResponse(BaseModel):
    conversion_plan: ConversionPlan
    version: int
    validation: ConversionPlanValidation
    waves: List[ConversionPlanWave]
    content_hash: str
    model_config = ConfigDict(extra="forbid")
