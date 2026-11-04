"""Workflow projection schemas for truthful UI state representation."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StageProjection(BaseModel):
    stage_id: str = Field(..., description="Unique identifier for the pipeline stage")
    name: str = Field(..., description="Display name of the stage")
    status: str = Field(
        ...,
        description="One of: NOT_STARTED, QUEUED, RUNNING, WAITING_FOR_HUMAN, FAILED, BLOCKED, VERIFIED, NOT_RUN, STALE, SUCCEEDED",
    )
    agent_name: Optional[str] = Field(None, description="Name of specialist agent if applicable")
    agent_run_id: Optional[str] = Field(None, description="Persisted AgentRun UUID")
    worker_id: Optional[str] = Field(None, description="Worker or container identity")
    artifact_id: Optional[str] = Field(None, description="Primary produced artifact ID")
    artifact_hash: Optional[str] = Field(None, description="SHA-256 content hash of artifact")
    tool_name: Optional[str] = Field(None, description="Execution tool name")
    tool_version: Optional[str] = Field(None, description="Tool version")
    commit_sha: Optional[str] = Field(None, description="Target or candidate commit SHA")
    evidence_url: Optional[str] = Field(None, description="API URL to fetch authoritative evidence")
    evidence_available: bool = Field(False, description="True if verified artifact exists on disk")
    error_message: Optional[str] = Field(None, description="Failure or rejection reason")
    started_at: Optional[datetime] = Field(None, description="Stage start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Stage completion timestamp")


class ModuleItemProjection(BaseModel):
    module_id: str = Field(..., description="Module UUID")
    name: str = Field(..., description="Module name")
    legacy_path: str = Field(..., description="Legacy source path")
    target_path: str = Field(..., description="Target modernized path")
    status: str = Field(..., description="Current module lifecycle status")
    risk_level: str = Field("MEDIUM", description="Risk classification")
    wave_number: int = Field(1, description="Assigned execution wave")
    attempt_count: int = Field(0, description="Number of attempted conversions")
    latest_attempt_id: Optional[str] = Field(None, description="Latest attempt UUID")
    verification_status: str = Field(
        "NOT_RUN",
        description="One of: NOT_RUN, QUEUED, RUNNING, PASS, FAIL, BLOCKED",
    )
    verification_run_id: Optional[str] = Field(None, description="Latest VerificationRun UUID")
    candidate_hash: Optional[str] = Field(None, description="Candidate worktree tree hash")
    error_message: Optional[str] = Field(None, description="Latest failure or error message")


class GateProjection(BaseModel):
    gate_id: Optional[str] = Field(None, description="WorkflowGate UUID")
    gate_type: str = Field(..., description="G1, G2, G3, or G4")
    version: int = Field(1, description="Gate version sequence")
    status: str = Field(
        ...,
        description="One of: NOT_REACHED, PENDING, APPROVED, REJECTED, NEEDS_CHANGES, INVALIDATED, STALE",
    )
    artifact_hashes: Dict[str, str] = Field(default_factory=dict, description="Locked artifact hashes")
    is_stale: bool = Field(False, description="True if upstream dependencies have drifted")
    blocking_reason: Optional[str] = Field(None, description="Reason if blocked or invalidated")
    reviewer_user_id: Optional[str] = Field(None, description="User UUID who decided gate")
    reviewer_name: Optional[str] = Field(None, description="Full name of deciding reviewer")
    decided_at: Optional[datetime] = Field(None, description="Timestamp of decision")
    waivers: List[Any] = Field(default_factory=list, description="Approved waiver details")
    selected_options: Dict[str, str] = Field(default_factory=dict, description="Chosen gate options")


class VerificationSummaryProjection(BaseModel):
    total_cases: int = Field(0, description="Total planned test scenarios")
    executed_cases: int = Field(0, description="Scenarios actually executed")
    passed_cases: int = Field(0, description="Scenarios matching baseline")
    failed_cases: int = Field(0, description="Scenarios with regressions")
    unobserved_cases: int = Field(0, description="Scenarios marked UNAVAILABLE or NOT_RUN")
    parity_verified: bool = Field(False, description="True if dual-harness replay succeeded")
    has_unwaived_regressions: bool = Field(False, description="True if any regressions lack approved waivers")
    unintended_regressions_count: int = Field(0, description="Unapproved behavioral differences")
    approved_waivers_count: int = Field(0, description="Formally waived intentional differences")
    latest_verification_run_id: Optional[str] = Field(None, description="Latest run ID")


class AuditEventProjection(BaseModel):
    event_id: str = Field(..., description="Audit event UUID")
    sequence: int = Field(..., description="Monotonic sequence number")
    event_type: str = Field(..., description="Event type identifier")
    actor_type: str = Field(..., description="USER, SYSTEM, or AGENT")
    actor_id: str = Field(..., description="Actor identity")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Redacted event payload")
    created_at: datetime = Field(..., description="Event timestamp")


class CostSummaryProjection(BaseModel):
    budget_limit_usd: float = Field(0.0, description="Job budget ceiling")
    budget_used_usd: float = Field(0.0, description="Actual recorded token/infrastructure spend")
    input_tokens: int = Field(0, description="Observed input tokens")
    output_tokens: int = Field(0, description="Observed output tokens")
    pricing_version: Optional[str] = Field(None, description="Active pricing table version")


class WorkflowProjectionResponse(BaseModel):
    projection_version: str = Field("v1", description="Schema version of this projection")
    job_id: str = Field(..., description="Job UUID")
    job_name: str = Field(..., description="Project name")
    status: str = Field(..., description="Coarse job state")
    progress: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Weighted progress percentage based on verified work items. Null if indeterminate.",
    )
    is_progress_indeterminate: bool = Field(
        True,
        description="True if modules or total work items have not been topologically planned yet.",
    )
    total_modules: int = Field(0, description="Actual persisted module count")
    stages: List[StageProjection] = Field(default_factory=list, description="Truthful pipeline stage projections")
    modules: List[ModuleItemProjection] = Field(default_factory=list, description="Persisted module items")
    gates: List[GateProjection] = Field(default_factory=list, description="Gate status projections")
    verification_summary: VerificationSummaryProjection = Field(
        default_factory=VerificationSummaryProjection,
        description="Aggregated verification metrics",
    )
    cost: CostSummaryProjection = Field(default_factory=CostSummaryProjection, description="Spend details")
    events: List[AuditEventProjection] = Field(default_factory=list, description="Audit timeline events")
    latest_sequence: int = Field(0, description="Highest monotonic sequence number in this response")

