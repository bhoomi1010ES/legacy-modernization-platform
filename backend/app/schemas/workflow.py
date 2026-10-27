"""Typed API and graph payloads for the durable modernization supervisor."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

from app.schemas.gates import GateType
from app.schemas.jobs import JobStatus


class WorkflowNode(str, Enum):
    CREATED = "created"
    INTAKE = "intake"
    ANALYSIS = "analysis"
    GATE_G1 = "gate_g1"
    CHARACTERIZATION = "characterization"
    SCHEMA_DATA = "schema_data"
    GATE_G2 = "gate_g2"
    PLANNING = "planning"
    GATE_G3 = "gate_g3"
    CONVERSION = "conversion"
    VERIFICATION = "verification"
    INTEGRATION = "integration"
    GATE_G4 = "gate_g4"
    PAUSED = "paused"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowPhase(str, Enum):
    """Canonical product phases, independent from coarse execution statuses."""

    INTAKE = "INTAKE"
    G1 = "G1"
    CHARACTERIZATION = "CHARACTERIZATION"
    SCHEMA_DATA = "SCHEMA_DATA"
    G2 = "G2"
    PLANNING = "PLANNING"
    G3 = "G3"
    CONVERSION = "CONVERSION"
    VERIFICATION = "VERIFICATION"
    INTEGRATION = "INTEGRATION"
    G4 = "G4"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowEvent(str, Enum):
    """Commands accepted by the one authoritative transition boundary."""

    INTAKE_STARTED = "INTAKE_STARTED"
    ANALYSIS_STARTED = "ANALYSIS_STARTED"
    INTAKE_READY = "INTAKE_READY"
    G1_APPROVED = "G1_APPROVED"
    G1_REJECTED = "G1_REJECTED"
    CHARACTERIZATION_COMPLETE = "CHARACTERIZATION_COMPLETE"
    SCHEMA_DATA_COMPLETE = "SCHEMA_DATA_COMPLETE"
    G2_APPROVED = "G2_APPROVED"
    G2_REJECTED = "G2_REJECTED"
    PLAN_COMPLETE = "PLAN_COMPLETE"
    G3_APPROVED = "G3_APPROVED"
    G3_REJECTED = "G3_REJECTED"
    CONVERSION_COMPLETE = "CONVERSION_COMPLETE"
    VERIFICATION_PASSED = "VERIFICATION_PASSED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    INTEGRATION_COMPLETE = "INTEGRATION_COMPLETE"
    G4_APPROVED = "G4_APPROVED"
    G4_REJECTED = "G4_REJECTED"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    RESUME_REQUESTED = "RESUME_REQUESTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    RECOVERY_RECONCILED = "RECOVERY_RECONCILED"
    BASELINE_INVALIDATED = "BASELINE_INVALIDATED"


class TaskType(str, Enum):
    ANALYZE = "ANALYZE"
    ARCHITECT = "ARCHITECT"
    FEASIBILITY = "FEASIBILITY"
    PLAN = "PLAN"
    CHARACTERIZE = "CHARACTERIZE"
    SCHEMA_DATA = "SCHEMA_DATA"
    CODE_GENERATE = "CODE_GENERATE"
    VERIFY = "VERIFY"
    REPAIR = "REPAIR"
    INTEGRATE = "INTEGRATE"
    SYSTEM_VERIFY = "SYSTEM_VERIFY"
    GATE_PREPARE = "GATE_PREPARE"


class SupervisorTask(BaseModel):
    task_id: str
    job_id: str
    task_type: str
    agent_id: str
    status: str = "PENDING"
    priority: int = 1
    dependencies: list[str] = Field(default_factory=list)
    required_gate: Optional[str] = None
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    retry_count: int = 0
    repair_count: int = 0
    budget_estimate: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupervisorState(TypedDict, total=False):
    """LangGraph state. Values are JSON-safe for PostgreSQL checkpoints."""

    job_id: str
    workflow_id: str
    current_phase: str
    status: str
    active_node: str
    target_node: str
    checkpoint_sequence: int
    retry_count: int
    budget_used: float
    budget_limit: float
    blocking_reason: Optional[str]
    correlation_id: Optional[str]
    events: Annotated[list[dict[str, Any]], lambda left, right: left + right]
    active_task_ids: list[str]
    completed_task_ids: list[str]
    blocked_task_ids: list[str]
    failed_task_ids: list[str]
    pending_gate_id: Optional[str]
    approved_artifact_versions: dict[str, int]
    artifact_hashes: dict[str, str]
    retry_counts: dict[str, int]
    budget_state: dict[str, Any]
    dependency_state: dict[str, Any]
    last_checkpoint: Optional[dict[str, Any]]
    last_transition: Optional[str]
    failure_reason: Optional[str]
    terminal_reason: Optional[str]


class PhaseProgress(BaseModel):
    node: WorkflowNode
    label: str
    status: Literal["PENDING", "RUNNING", "BLOCKED", "SUCCEEDED", "FAILED", "CANCELLED"]


class WorkflowStateResponse(BaseModel):
    job_id: str
    workflow_id: str
    current_phase: WorkflowPhase
    status: JobStatus
    active_node: WorkflowNode
    blocking_reason: Optional[str] = None
    checkpoint_sequence: int
    workflow_version: int
    budget_used: float
    budget_limit: float
    budget_warning: bool
    allowed_actions: list[Literal["cancel", "pause", "resume"]]
    phases: list[PhaseProgress]
    active_task_ids: list[str] = Field(default_factory=list)
    completed_task_ids: list[str] = Field(default_factory=list)
    blocked_task_ids: list[str] = Field(default_factory=list)
    failed_task_ids: list[str] = Field(default_factory=list)
    pending_gate_id: Optional[str] = None
    approved_artifact_versions: dict[str, int] = Field(default_factory=dict)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    retry_counts: dict[str, int] = Field(default_factory=dict)
    dependency_state: dict[str, Any] = Field(default_factory=dict)
    last_transition: Optional[str] = None
    failure_reason: Optional[str] = None
    terminal_reason: Optional[str] = None
    updated_at: str


class WorkflowEventResponse(BaseModel):
    event_id: str
    event_type: str
    actor_type: str
    actor_id: str
    correlation_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class WorkflowEventsResponse(BaseModel):
    items: list[WorkflowEventResponse]
    next_cursor: Optional[str] = None


class WorkflowGateResponse(BaseModel):
    gate_id: str
    job_id: str
    gate_type: GateType
    version: int
    status: str
    artifact_ids: list[str]
    artifact_hashes: dict[str, str]
    blocking_reason: Optional[str] = None
    requested_at: str
    decided_at: Optional[str] = None
    allowed_actions: list[str] = Field(default_factory=list)


class GateDecisionResult(BaseModel):
    decision_id: str
    gate: WorkflowGateResponse
    job_status: JobStatus
    idempotent_replay: bool = False


class ResumeRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)


class PauseRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)
