"""Modernization job request, response, and status schemas."""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, HttpUrl


class JobStatus(str, Enum):
    CREATED = "CREATED"
    INTAKE = "INTAKE"
    ANALYZING = "ANALYZING"
    AWAITING_GATE_G1 = "AWAITING_GATE_G1"
    CHARACTERIZING = "CHARACTERIZING"
    AWAITING_GATE_G2 = "AWAITING_GATE_G2"
    PLANNING = "PLANNING"
    AWAITING_GATE_G3 = "AWAITING_GATE_G3"
    CONVERTING = "CONVERTING"
    VERIFYING = "VERIFYING"
    INTEGRATING = "INTEGRATING"
    AWAITING_GATE_G4 = "AWAITING_GATE_G4"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120, description="Project name.")
    source_repository: str = Field(..., description="Git repository URL or configured reference.")
    source_revision: str = Field("main", description="Git branch or commit revision.")
    source_stack: Optional[str] = Field("Auto-detect", description="Legacy language and framework.")
    target_stack: str = Field("TypeScript / Node.js 22 / NestJS", description="Target modern stack.")
    budget: float = Field(15000.0, ge=50.0, description="Job budget ceiling in INR (Rupees, minimum ₹50.00).")
    max_repair_attempts: int = Field(3, ge=1, le=5, description="Maximum automated repair attempts per module.")
    constraints: Optional[str] = Field(None, description="Architecture constraints or preserved behaviors.")
    stack_metadata: Optional[dict[str, Any]] = Field(None, description="Detailed stack detection metadata.")
    pinned_commit: Optional[str] = Field(None, description="Pinned Git commit hash verified during preview.")
    user_overrides: Optional[dict[str, Any]] = Field(None, description="Explicit user customizations overriding automated detection.")
    git_token: Optional[str] = Field(None, description="Optional GitHub Personal Access Token for private repository intake.")
    source_type: Optional[str] = Field("git", description="Source provider type: 'git' or 'local'.")
    preview_snapshot_id: Optional[str] = Field(None, description="UUID of staged preview snapshot for local folder intake.")
    snapshot_fingerprint: Optional[str] = Field(None, description="Authoritative SHA-256 fingerprint of the local source snapshot.")


class JobIntakeRequest(BaseModel):
    git_token: Optional[str] = Field(None, description="Optional GitHub Personal Access Token for private repository intake.")
    preview_snapshot_id: Optional[str] = Field(None, description="UUID of staged preview snapshot to promote to permanent workspace.")
    snapshot_fingerprint: Optional[str] = Field(None, description="Authoritative SHA-256 fingerprint to verify against staged snapshot.")


class JobSummaryResponse(BaseModel):
    job_id: str = Field(..., description="Unique job identifier.")
    name: str = Field(..., description="Project name.")
    source_repository: str = Field(..., description="Source repository.")
    source_revision: str = Field(..., description="Source branch / revision.")
    source_stack: str = Field(..., description="Source stack.")
    target_stack: str = Field(..., description="Target stack.")
    status: JobStatus = Field(..., description="Current lifecycle state.")
    progress: int = Field(0, ge=0, le=100, description="Overall completion percentage.")
    modules: int = Field(0, description="Total identified modules.")
    cost: float = Field(0.0, description="Current token and infrastructure spend in INR (Rupees).")
    budget: float = Field(..., description="Budget ceiling in INR (Rupees).")
    owner: str = Field(..., description="Job owner full name.")
    created_at: str = Field(..., description="ISO 8601 creation timestamp.")
    updated_at: str = Field(..., description="ISO 8601 last updated timestamp.")


class JobDetailResponse(JobSummaryResponse):
    max_repair_attempts: int = Field(3, description="Maximum allowed repair attempts per module.")
    integration_branch: Optional[str] = Field(None, description="Target integration Git branch.")
    pull_request_url: Optional[str] = Field(None, description="Delivery pull request URL.")
    current_gate: Optional[str] = Field(None, description="Active pending gate if awaiting human review.")
    stack_metadata: Optional[dict[str, Any]] = Field(None, description="Detailed stack detection metadata.")


class JobListResponse(BaseModel):
    items: list[JobSummaryResponse]
    total: int
    offset: int
    limit: int


class TierComponent(BaseModel):
    name: str = Field(..., description="Component identifier or service name")
    relative_path: str = Field("", description="Repository-relative root path")
    technology: str = Field(..., description="Identified framework or runtime")
    framework: str
    version: Optional[str] = "N/A"
    primary_language: Optional[str] = None
    build_tool_or_driver: Optional[str] = "None"
    evidence: list[dict[str, str]] = Field(default_factory=list)


class DatabaseComponent(BaseModel):
    name: str = Field(..., description="Database identifier or component name")
    relative_path: str = Field("", description="Directory containing schema or configs")
    engine: str = Field(..., description="MySQL | PostgreSQL | SQLite | MongoDB | Relational SQL (Dialect Unconfirmed)")
    version: Optional[str] = "N/A"
    orm_or_driver: Optional[str] = "None declared"
    schema_artifacts: list[str] = Field(default_factory=list)
    migration_tool: Optional[str] = None
    inferred_from: str = Field(..., description="ddl_syntax | driver_dependency | config_template | generic_sql")
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: list[dict[str, str]] = Field(default_factory=list)


class TierGroup(BaseModel):
    primary: Optional[TierComponent] = Field(None, description="Primary detected component for this tier")
    components: list[TierComponent] = Field(default_factory=list, description="All components detected in this tier")


class DatabaseTierGroup(BaseModel):
    primary: Optional[DatabaseComponent] = Field(None, description="Primary detected database engine/layer")
    components: list[DatabaseComponent] = Field(default_factory=list, description="All database layers detected")


class TieredStackBreakdown(BaseModel):
    frontend: TierGroup = Field(default_factory=TierGroup, description="Client-side / presentation tier")
    backend: TierGroup = Field(default_factory=TierGroup, description="Server-side application logic tier")
    database: DatabaseTierGroup = Field(default_factory=DatabaseTierGroup, description="Persistence and database tier")


class StackDetectionRequest(BaseModel):
    source_repository: str = Field(..., description="Git repository URL or configured reference.")
    source_revision: Optional[str] = Field("main", description="Git branch or commit revision.")
    job_id: Optional[str] = Field(None, description="Optional job ID to associate and persist detection results.")
    access_token: Optional[str] = Field(None, description="Optional GitHub Personal Access Token for private repository access.")
    source_type: Optional[str] = Field("git", description="Source provider type: 'git' or 'local'.")


class DetectedStackResponse(BaseModel):
    source_repository: str
    source_revision: str
    requested_revision: Optional[str] = None
    source_type: str = Field("git", description="Source provider: 'git' or 'local'.")
    preview_snapshot_id: Optional[str] = Field(None, description="Temporary staging snapshot ID for local source reuse.")
    snapshot_fingerprint: Optional[str] = Field(None, description="Authoritative canonical SHA-256 snapshot fingerprint.")
    primary_language: str
    language_version: str
    framework: str
    framework_version: str
    build_tool: str
    build_file: str
    test_framework: str
    architecture_style: str
    confidence_score: float
    summary_stack: str
    detection_method: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    scan_status: str = Field("COMPLETED", description="Status of the scan: COMPLETED, PARTIAL, INCONCLUSIVE, FAILED")
    is_fallback: bool = Field(False, description="True if no empirical evidence was found")
    warnings: list[str] = Field(default_factory=list, description="Diagnostic warnings and unparseable manifests")
    components: list[dict[str, Any]] = Field(default_factory=list, description="Detected monorepo sub-components or services")
    tiers: TieredStackBreakdown = Field(default_factory=TieredStackBreakdown, description="Three-Tier Architecture breakdown")
    languages: dict[str, Any] = Field(default_factory=dict, description="Detailed language breakdown by byte count and file count")
    frameworks: list[dict[str, Any]] = Field(default_factory=list, description="All detected frameworks and libraries with categories")
    evidence: list[dict[str, str]] = Field(default_factory=list, description="Audit evidence linking findings to relative file paths")
    resolved_commit: Optional[str] = Field(None, description="Resolved Git commit hash of scanned snapshot")
    detector_version: str = "2.2.0"
    scanned_at: Optional[str] = None


