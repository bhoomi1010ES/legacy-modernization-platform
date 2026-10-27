"""Typed schemas and contracts for Phase 2 Shared Agent Runtime and Tool Registry."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FailureClassification(str, Enum):
    """Categorizes runtime and verification failures for automated repair and triage."""

    REGRESSION = "REGRESSION"
    INTENDED_DIFFERENCE = "INTENDED_DIFFERENCE"
    NONDETERMINISTIC = "NONDETERMINISTIC"
    TEST_DEFECT = "TEST_DEFECT"
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"
    TIMEOUT = "TIMEOUT"
    TOOL_ERROR = "TOOL_ERROR"
    RETRY_EXHAUSTION = "RETRY_EXHAUSTION"
    BUDGET_EXHAUSTION = "BUDGET_EXHAUSTION"
    ITERATION_EXHAUSTION = "ITERATION_EXHAUSTION"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNSUPPORTED_OUTPUT = "UNSUPPORTED_OUTPUT"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AgentRunStatus(str, Enum):
    """Standard lifecycle states for agent runs in the execution timeline."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class ToolCategory(str, Enum):
    """Enforces strict isolation between read-only inspection and write/execute capabilities."""

    READ_ONLY = "read_only"
    WRITE_EXECUTE = "write_execute"


class ToolSpec(BaseModel):
    """Declarative specification for a registered agent tool."""

    name: str = Field(..., description="Unique tool identifier, e.g. repo_read_file.")
    description: str = Field(
        ..., description="Description of the tool purpose and behavior."
    )
    category: ToolCategory = Field(
        ..., description="Tool capability category: read_only or write_execute."
    )
    is_read_only: bool = Field(
        default=True, description="True if tool performs zero side-effects."
    )
    parameters_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON schema describing the required and optional arguments.",
    )
    required_permission: Optional[str] = Field(
        default=None,
        description="Platform permission required to execute this tool, e.g. job:write.",
    )
    timeout_seconds: float = Field(
        default=30.0, ge=0.5, le=300.0, description="Max execution time in seconds."
    )
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def category_matches_mutability(self) -> "ToolSpec":
        if self.category == ToolCategory.READ_ONLY and not self.is_read_only:
            raise ValueError("read_only tools must set is_read_only=true")
        if self.category == ToolCategory.WRITE_EXECUTE and self.is_read_only:
            raise ValueError("write_execute tools must set is_read_only=false")
        return self


class ToolCall(BaseModel):
    """Structured request by an agent to invoke a specific tool."""

    call_id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")
    tool_name: str = Field(..., description="Name of the tool to invoke.")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Parsed arguments for the tool."
    )
    timestamp: datetime = Field(default_factory=utc_now)
    model_config = ConfigDict(extra="forbid")


class ToolResult(BaseModel):
    """Deterministic result observed from a tool execution."""

    call_id: str = Field(..., description="Matching call_id from ToolCall.")
    tool_name: str = Field(..., description="Tool invoked.")
    ok: bool = Field(..., description="True if tool executed successfully.")
    output: Any = Field(default=None, description="Output payload or return value.")
    error: Optional[str] = Field(
        default=None, description="Sanitized error description on failure."
    )
    duration_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Elapsed execution wall-clock time in milliseconds.",
    )
    timestamp: datetime = Field(default_factory=utc_now)
    truncated: bool = False
    model_config = ConfigDict(extra="forbid")


class AgentContext(BaseModel):
    """Immutable or scoped execution context passed to an agent step."""

    job_id: str = Field(..., description="Job identifier.")
    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    agent_name: str = Field(
        ..., description="Specialist agent name (e.g. Intake, CodeWriter)."
    )
    session_id: Optional[str] = Field(default=None, description="Parent session ID.")
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}")
    workspace_path: Optional[str] = Field(
        default=None, description="Absolute root of the isolated workspace."
    )
    environment_variables: Dict[str, str] = Field(
        default_factory=dict,
        description="Redacted environment configuration for the run.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Custom metadata tags."
    )
    iteration: int = Field(
        default=0, ge=0, description="Current inner-loop step index."
    )
    tokens_used: int = Field(
        default=0, ge=0, description="Cumulative tokens consumed so far."
    )
    cost_spent_usd: float = Field(
        default=0.0, ge=0.0, description="Cumulative dollar spend so far."
    )
    permissions: List[str] = Field(
        default_factory=list,
        description="Runtime permission scopes granted to the agent.",
    )
    model_config = ConfigDict(extra="forbid")


class AgentTask(BaseModel):
    """Typed unit of work scheduled for execution by an agent."""

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    job_id: str = Field(..., description="Target job UUID.")
    agent_name: str = Field(..., description="Specialist agent to execute this task.")
    task_type: str = Field(
        ..., description="Task classification, e.g. 'code_analysis', 'synthesize_diff'."
    )
    instruction: str = Field(
        ..., description="Top-level prompt instruction provided to the agent."
    )
    input_artifacts: List[str] = Field(
        default_factory=list, description="IDs of input artifacts consumed."
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Domain parameters for the task."
    )
    allowed_tools: List[str] = Field(
        default_factory=list,
        description="Strict allowlist of tool names this agent is permitted to execute.",
    )
    max_iterations: int = Field(
        default=8, ge=1, le=50, description="Bounded reason-act-observe loops."
    )
    timeout_seconds: float = Field(
        default=60.0, ge=1.0, le=600.0, description="Total wall-clock deadline."
    )
    token_budget: int = Field(
        default=50000, ge=100, description="Hard cap on token consumption."
    )
    cost_budget_usd: float = Field(
        default=5.0, ge=0.01, description="Hard cap on spend in USD."
    )
    max_output_bytes: int = Field(default=262144, ge=256, le=10_485_760)
    model_provider: str = Field(default="fake")
    model_identifier: str = Field(default="fake-model-v1")
    model_retries: int = Field(default=2, ge=0, le=5)
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional JSON schema against which final structured agent output must validate.",
    )
    output_schema_name: Optional[str] = Field(
        default=None, description="Name of the expected output artifact schema."
    )
    model_config = ConfigDict(extra="forbid")


class AgentTraceStep(BaseModel):
    """Atomic step in the agent reason-act-observe trace timeline."""

    step_number: int = Field(..., ge=1)
    step_type: str = Field(
        ..., description="THOUGHT, TOOL_CALL, TOOL_RESULT, OBSERVATION, OUTPUT, ERROR"
    )
    content: Any = Field(..., description="Redacted payload for this trace step.")
    duration_ms: float = Field(default=0.0, ge=0.0)
    timestamp: datetime = Field(default_factory=utc_now)
    tokens_consumed: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)


class AgentTrace(BaseModel):
    """Complete, append-only, redactable audit trace of an agent execution."""

    run_id: str = Field(...)
    job_id: str = Field(...)
    agent_name: str = Field(...)
    correlation_id: str = Field(...)
    status: AgentRunStatus = Field(default=AgentRunStatus.QUEUED)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    steps: List[AgentTraceStep] = Field(default_factory=list)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    tool_results: List[ToolResult] = Field(default_factory=list)
    total_input_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    failure_classification: Optional[FailureClassification] = None
    error_message: Optional[str] = None
    model_identifier: str = Field(default="fake-model-v1")


class AgentResult(BaseModel):
    """Final validated result emitted upon completion or termination of an agent run."""

    run_id: str = Field(...)
    job_id: str = Field(...)
    agent_name: str = Field(...)
    status: AgentRunStatus = Field(...)
    output_data: Optional[Dict[str, Any]] = None
    output_artifacts: List[str] = Field(default_factory=list)
    failure_classification: Optional[FailureClassification] = None
    error_message: Optional[str] = None
    trace: AgentTrace = Field(...)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    completed_at: Optional[datetime] = None
    model_config = ConfigDict(extra="forbid")


class ModelUsage(BaseModel):
    """Normalized provider usage returned for every completion."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)


class ModelResponse(BaseModel):
    """Provider-neutral model decision consumed by the runtime loop."""

    action: Literal["tool_call", "final"]
    tool_call: Optional[ToolCall] = None
    output: Optional[Dict[str, Any]] = None
    usage: ModelUsage = Field(default_factory=ModelUsage)
    provider_request_id: Optional[str] = None
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def action_payload_matches(self) -> "ModelResponse":
        if self.action == "tool_call" and self.tool_call is None:
            raise ValueError("tool_call action requires tool_call")
        if self.action == "final" and self.output is None:
            raise ValueError("final action requires output")
        return self


# REST API Request/Response Models
class LaunchAgentRunRequest(BaseModel):
    """Request payload to launch an agent run for a job."""

    agent_name: str = Field(..., description="Name of the specialist agent to launch.")
    task_type: str = Field(
        default="custom_task", description="Type of task to execute."
    )
    instruction: str = Field(..., description="Prompt instructions for the agent.")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Domain parameters."
    )
    input_artifacts: List[str] = Field(
        default_factory=list, description="IDs of consumed artifacts."
    )
    allowed_tools: Optional[List[str]] = Field(
        default=None, description="Scoped tool allowlist override."
    )
    max_iterations: Optional[int] = Field(default=8, ge=1, le=50)
    timeout_seconds: Optional[float] = Field(default=60.0, ge=1.0, le=600.0)
    token_budget: Optional[int] = Field(default=50000, ge=100)
    cost_budget_usd: Optional[float] = Field(default=5.0, ge=0.01)
    output_schema: Optional[Dict[str, Any]] = None
    max_output_bytes: Optional[int] = Field(default=262144, ge=256, le=10_485_760)
    model_provider: str = "fake"
    model_identifier: str = "fake-model-v1"
    model_config = ConfigDict(extra="forbid")


class AgentRunSummaryResponse(BaseModel):
    """Safe, high-level summary of an agent run."""

    run_id: str
    job_id: str
    agent_name: str
    status: AgentRunStatus
    model_identifier: str
    role_description: Optional[str] = None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    failure_classification: Optional[FailureClassification] = None
    error_message: Optional[str] = None
    evidence_artifact_ids: List[str] = Field(default_factory=list)


class AgentRunListResponse(BaseModel):
    items: List[AgentRunSummaryResponse]
    total: int
    offset: int = 0
    limit: int = 50


class ToolCallSummaryItem(BaseModel):
    """Safe summary of a single tool execution."""

    call_id: str
    tool_name: str
    is_read_only: bool
    ok: bool
    duration_ms: float
    error: Optional[str] = None
    arguments_summary: Dict[str, Any] = Field(default_factory=dict)
    output_summary: Optional[str] = None
    timestamp: str


class AgentTraceResponse(BaseModel):
    """Authorized, redacted trace and tool-call summary for UI timeline and evidence inspection."""

    run_id: str
    job_id: str
    agent_name: str
    status: AgentRunStatus
    model_identifier: str
    duration_seconds: float
    total_tokens: int
    cost_usd: float
    started_at: str
    completed_at: Optional[str] = None
    failure_classification: Optional[FailureClassification] = None
    error_message: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    tool_calls: List[ToolCallSummaryItem] = Field(default_factory=list)
    output_evidence: Optional[Dict[str, Any]] = None
    evidence_artifacts: List[str] = Field(default_factory=list)


class CancelAgentRunResponse(BaseModel):
    """Response returned upon requesting cancellation of an agent run."""

    run_id: str
    status: AgentRunStatus
    message: str
    cancelled_at: str
