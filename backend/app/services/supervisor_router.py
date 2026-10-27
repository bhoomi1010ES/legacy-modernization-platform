"""Supervisor Routing & Decision Engine: Deterministic policy evaluation, multi-agent scheduling, and deadlock detection."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.state_machine import JobStateMachine
from app.models.artifact import Artifact
from app.models.base import utc_now
from app.models.job import Job
from app.models.module import Module
from app.models.workflow import WorkflowGate
from app.core.errors import ConflictException
from app.schemas.jobs import JobStatus
from app.schemas.workflow import SupervisorTask, TaskType
from app.services.budget_manager import budget_manager

logger = logging.getLogger(__name__)


def _artifact_key(value: str) -> str:
    """Compare historical snake-case and canonical CamelCase artifact names."""
    return "".join(ch for ch in value.upper() if ch.isalnum())


class SupervisorAction(str, Enum):
    EXECUTE = "EXECUTE"
    WAIT = "WAIT"
    RETRY = "RETRY"
    REPAIR = "REPAIR"
    ESCALATE = "ESCALATE"
    ADVANCE_GATE = "ADVANCE_GATE"
    COMPLETE = "COMPLETE"


class AgentCapability(BaseModel):
    agent_id: str
    name: str
    capabilities: List[str]
    supported_task_types: List[str] = Field(default_factory=list)
    required_inputs: List[str] = Field(default_factory=list)
    input_artifacts: List[str] = Field(default_factory=list)
    produced_artifacts: List[str] = Field(default_factory=list)
    output_artifacts: List[str] = Field(default_factory=list)
    required_gate: Optional[str] = None
    allowed_states: List[str]
    required_permissions: List[str]
    resource_profile: Dict[str, Any] = Field(default_factory=dict)
    retry_policy: Dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 3


# ---------------------------------------------------------------------------
# Canonical Agent Capability Registry
# ---------------------------------------------------------------------------
AGENT_CAPABILITY_REGISTRY: Dict[str, AgentCapability] = {
    # 1. Intake Agent
    "IntakeAgent": AgentCapability(
        agent_id="intake_agent",
        name="IntakeAgent",
        capabilities=["repository_intake", "ast_scanning", "manifest_profiling", "archive_safety_check"],
        supported_task_types=["INTAKE", "ANALYZE"],
        required_inputs=["source_ref", "workspace_path"],
        input_artifacts=["GIT_REPOSITORY", "LOCAL_REPOSITORY"],
        produced_artifacts=["REPOSITORY_SNAPSHOT", "REPOSITORY_INVENTORY"],
        output_artifacts=["REPOSITORY_SNAPSHOT", "REPOSITORY_INVENTORY"],
        allowed_states=["CREATED", "INTAKE"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "standard", "max_cost_usd": 100.0, "max_tokens": 50000},
        retry_policy={"max_retries": 2, "backoff_seconds": 2},
    ),
    # 2. Analyzer
    "ANALYZER": AgentCapability(
        agent_id="analyzer",
        name="Analyzer",
        capabilities=["ast_parsing", "entity_extraction", "route_mapping", "dependency_graphing"],
        supported_task_types=["ANALYZE"],
        required_inputs=["REPOSITORY_SNAPSHOT", "REPOSITORY_INVENTORY"],
        input_artifacts=["REPOSITORY_SNAPSHOT", "REPOSITORY_INVENTORY"],
        produced_artifacts=["LEGACY_MODEL"],
        output_artifacts=["LEGACY_MODEL"],
        allowed_states=["ANALYZING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 500.0, "max_tokens": 200000},
        retry_policy={"max_retries": 3, "backoff_seconds": 5},
    ),
    "AnalyzerCoordinator": AgentCapability(
        agent_id="analyzer_coordinator",
        name="AnalyzerCoordinator",
        capabilities=["ast_parsing", "entity_extraction", "route_mapping", "feasibility_scoring"],
        supported_task_types=["ANALYZE", "ARCHITECT", "FEASIBILITY"],
        required_inputs=["REPOSITORY_SNAPSHOT", "REPOSITORY_INVENTORY"],
        input_artifacts=["REPOSITORY_SNAPSHOT", "REPOSITORY_INVENTORY"],
        produced_artifacts=["LEGACY_MODEL", "TARGET_BLUEPRINT", "FEASIBILITY_REPORT"],
        output_artifacts=["LEGACY_MODEL", "TARGET_BLUEPRINT", "FEASIBILITY_REPORT"],
        allowed_states=["ANALYZING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 1000.0, "max_tokens": 500000},
        retry_policy={"max_retries": 3, "backoff_seconds": 5},
    ),
    # 3. Architect
    "ARCHITECT": AgentCapability(
        agent_id="architect",
        name="Architect",
        capabilities=["target_blueprint_synthesis", "clean_architecture_mapping", "interface_specification"],
        supported_task_types=["ARCHITECT"],
        required_inputs=["LEGACY_MODEL"],
        input_artifacts=["LEGACY_MODEL"],
        produced_artifacts=["TARGET_BLUEPRINT"],
        output_artifacts=["TARGET_BLUEPRINT"],
        allowed_states=["ANALYZING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 500.0, "max_tokens": 200000},
        retry_policy={"max_retries": 2, "backoff_seconds": 5},
    ),
    # 4. Feasibility
    "FEASIBILITY": AgentCapability(
        agent_id="feasibility",
        name="Feasibility",
        capabilities=["gap_analysis", "complexity_scoring", "toolchain_validation", "risk_profiling"],
        supported_task_types=["FEASIBILITY"],
        required_inputs=["LEGACY_MODEL", "TARGET_BLUEPRINT"],
        input_artifacts=["LEGACY_MODEL", "TARGET_BLUEPRINT"],
        produced_artifacts=["FEASIBILITY_REPORT"],
        output_artifacts=["FEASIBILITY_REPORT"],
        allowed_states=["ANALYZING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "standard", "max_cost_usd": 250.0, "max_tokens": 100000},
        retry_policy={"max_retries": 2, "backoff_seconds": 3},
    ),
    # 5. Characterizer
    "CHARACTERIZER": AgentCapability(
        agent_id="characterizer",
        name="Characterizer",
        capabilities=["test_vector_recording", "fixture_synthesis", "baseline_fingerprinting", "golden_record_lock"],
        supported_task_types=["CHARACTERIZE"],
        required_inputs=["TARGET_BLUEPRINT", "LEGACY_MODEL"],
        input_artifacts=["TARGET_BLUEPRINT", "LEGACY_MODEL"],
        produced_artifacts=["CHARACTERIZATION_SUITE"],
        output_artifacts=["CHARACTERIZATION_SUITE"],
        required_gate="G1",
        allowed_states=["CHARACTERIZING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 750.0, "max_tokens": 300000},
        retry_policy={"max_retries": 3, "backoff_seconds": 5},
    ),
    "CharacterizerAgent": AgentCapability(
        agent_id="characterizer_agent",
        name="CharacterizerAgent",
        capabilities=["test_vector_recording", "fixture_synthesis", "baseline_fingerprinting"],
        supported_task_types=["CHARACTERIZE"],
        required_inputs=["TARGET_BLUEPRINT", "LEGACY_MODEL"],
        input_artifacts=["TARGET_BLUEPRINT", "LEGACY_MODEL"],
        produced_artifacts=["CHARACTERIZATION_SUITE"],
        output_artifacts=["CHARACTERIZATION_SUITE"],
        required_gate="G1",
        allowed_states=["CHARACTERIZING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 750.0, "max_tokens": 300000},
        retry_policy={"max_retries": 3, "backoff_seconds": 5},
    ),
    # 6. Schema/Data (First-class Agent)
    "SCHEMA_DATA": AgentCapability(
        agent_id="schema_data",
        name="SchemaData",
        capabilities=["sql_ast_parsing", "dialect_detection", "orm_mapping", "migration_plan_synthesis", "data_validation_rules"],
        supported_task_types=["SCHEMA_DATA"],
        required_inputs=["CHARACTERIZATION_SUITE", "TARGET_BLUEPRINT", "REPOSITORY_INVENTORY"],
        input_artifacts=["CHARACTERIZATION_SUITE", "TARGET_BLUEPRINT", "REPOSITORY_INVENTORY"],
        produced_artifacts=["SCHEMA_MIGRATION_PLAN"],
        output_artifacts=["SCHEMA_MIGRATION_PLAN"],
        required_gate="G1",
        allowed_states=["CHARACTERIZING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "standard", "max_cost_usd": 300.0, "max_tokens": 150000},
        retry_policy={"max_retries": 2, "backoff_seconds": 3},
    ),
    "SchemaDataAgent": AgentCapability(
        agent_id="schema_data_agent",
        name="SchemaDataAgent",
        capabilities=["sql_ast_parsing", "dialect_detection", "orm_mapping", "migration_plan_synthesis"],
        supported_task_types=["SCHEMA_DATA"],
        required_inputs=["CHARACTERIZATION_SUITE", "TARGET_BLUEPRINT", "REPOSITORY_INVENTORY"],
        input_artifacts=["CHARACTERIZATION_SUITE", "TARGET_BLUEPRINT", "REPOSITORY_INVENTORY"],
        produced_artifacts=["SCHEMA_MIGRATION_PLAN"],
        output_artifacts=["SCHEMA_MIGRATION_PLAN"],
        required_gate="G1",
        allowed_states=["CHARACTERIZING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "standard", "max_cost_usd": 300.0, "max_tokens": 150000},
        retry_policy={"max_retries": 2, "backoff_seconds": 3},
    ),
    # 7. Planner
    "PLANNER": AgentCapability(
        agent_id="planner",
        name="Planner",
        capabilities=["module_decomposition", "dependency_dag", "wave_scheduling", "acyclic_validation", "parallel_feature_planning"],
        supported_task_types=["PLAN"],
        required_inputs=["TARGET_BLUEPRINT", "CHARACTERIZATION_SUITE", "SCHEMA_MIGRATION_PLAN"],
        input_artifacts=["TARGET_BLUEPRINT", "CHARACTERIZATION_SUITE", "SCHEMA_MIGRATION_PLAN"],
        produced_artifacts=["CONVERSION_PLAN"],
        output_artifacts=["CONVERSION_PLAN"],
        required_gate="G2",
        allowed_states=["PLANNING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 600.0, "max_tokens": 250000},
        retry_policy={"max_retries": 3, "backoff_seconds": 5},
    ),
    "PlannerCoordinator": AgentCapability(
        agent_id="planner_coordinator",
        name="PlannerCoordinator",
        capabilities=["module_decomposition", "dependency_dag", "wave_scheduling", "acyclic_validation"],
        supported_task_types=["PLAN"],
        required_inputs=["TARGET_BLUEPRINT", "CHARACTERIZATION_SUITE"],
        input_artifacts=["TARGET_BLUEPRINT", "CHARACTERIZATION_SUITE"],
        produced_artifacts=["CONVERSION_PLAN"],
        output_artifacts=["CONVERSION_PLAN"],
        required_gate="G2",
        allowed_states=["PLANNING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 600.0, "max_tokens": 250000},
        retry_policy={"max_retries": 3, "backoff_seconds": 5},
    ),
    # 8. CodeWriter Pool
    "CODE_WRITER": AgentCapability(
        agent_id="code_writer",
        name="CodeWriter",
        capabilities=["modular_code_generation", "sandbox_compilation", "targeted_repair", "contract_synthesis"],
        supported_task_types=["CODE_GENERATE", "REPAIR"],
        required_inputs=["CONVERSION_PLAN", "TARGET_BLUEPRINT", "SCHEMA_MIGRATION_PLAN"],
        input_artifacts=["CONVERSION_PLAN", "TARGET_BLUEPRINT"],
        produced_artifacts=["CONVERTED_MODULE"],
        output_artifacts=["CONVERTED_MODULE"],
        required_gate="G3",
        allowed_states=["CONVERTING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "gpu", "max_cost_usd": 5000.0, "max_tokens": 1500000},
        retry_policy={"max_retries": 3, "backoff_seconds": 5},
    ),
    "CodeWriter": AgentCapability(
        agent_id="code_writer",
        name="CodeWriter",
        capabilities=["modular_code_generation", "sandbox_compilation", "targeted_repair"],
        supported_task_types=["CODE_GENERATE", "REPAIR"],
        required_inputs=["CONVERSION_PLAN", "TARGET_BLUEPRINT"],
        input_artifacts=["CONVERSION_PLAN", "TARGET_BLUEPRINT"],
        produced_artifacts=["CONVERTED_MODULE"],
        output_artifacts=["CONVERTED_MODULE"],
        required_gate="G3",
        allowed_states=["CONVERTING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "gpu", "max_cost_usd": 5000.0, "max_tokens": 1500000},
        retry_policy={"max_retries": 3, "backoff_seconds": 5},
    ),
    # 9. Verifier
    "VERIFIER": AgentCapability(
        agent_id="verifier",
        name="Verifier",
        capabilities=["independent_syntax_verification", "type_checking", "contract_validation", "characterization_testing"],
        supported_task_types=["VERIFY"],
        required_inputs=["CONVERTED_MODULE", "CHARACTERIZATION_SUITE"],
        input_artifacts=["CONVERTED_MODULE", "CHARACTERIZATION_SUITE"],
        produced_artifacts=["VERIFICATION_REPORT"],
        output_artifacts=["VERIFICATION_REPORT"],
        required_gate="G3",
        allowed_states=["CONVERTING", "VERIFYING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 2000.0, "max_tokens": 600000},
        retry_policy={"max_retries": 2, "backoff_seconds": 3},
    ),
    "Verifier": AgentCapability(
        agent_id="verifier",
        name="Verifier",
        capabilities=["independent_syntax_verification", "type_checking", "contract_validation", "characterization_testing"],
        supported_task_types=["VERIFY"],
        required_inputs=["CONVERTED_MODULE", "CHARACTERIZATION_SUITE"],
        input_artifacts=["CONVERTED_MODULE", "CHARACTERIZATION_SUITE"],
        produced_artifacts=["VERIFICATION_REPORT"],
        output_artifacts=["VERIFICATION_REPORT"],
        required_gate="G3",
        allowed_states=["CONVERTING", "VERIFYING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 2000.0, "max_tokens": 600000},
        retry_policy={"max_retries": 2, "backoff_seconds": 3},
    ),
    "REVIEWER": AgentCapability(
        agent_id="reviewer", name="Reviewer",
        capabilities=["security_review", "contract_review", "maintainability_review", "evidence_references"],
        supported_task_types=["REVIEW"], required_inputs=["CONVERTED_MODULE", "VERIFICATION_REPORT"],
        input_artifacts=["CONVERTED_MODULE", "VERIFICATION_REPORT"], produced_artifacts=["REVIEW_REPORT"],
        output_artifacts=["REVIEW_REPORT"], required_gate="G3", allowed_states=["CONVERTING", "VERIFYING"],
        required_permissions=["job:read"], resource_profile={"cpu": "bounded", "max_cost_usd": 0.0},
        retry_policy={"max_retries": 0},
    ),
    # 10. Integrator
    "INTEGRATOR": AgentCapability(
        agent_id="integrator",
        name="Integrator",
        capabilities=["workspace_merging", "cross_module_contracts", "system_level_verification", "end_to_end_replay"],
        supported_task_types=["INTEGRATE", "SYSTEM_VERIFY"],
        required_inputs=["CONVERTED_MODULE", "VERIFICATION_REPORT", "CHARACTERIZATION_SUITE"],
        input_artifacts=["CONVERTED_MODULE", "VERIFICATION_REPORT"],
        produced_artifacts=["INTEGRATED_WORKSPACE", "SYSTEM_VERIFICATION_REPORT"],
        output_artifacts=["INTEGRATED_WORKSPACE", "SYSTEM_VERIFICATION_REPORT"],
        required_gate="G3",
        allowed_states=["INTEGRATING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 1500.0, "max_tokens": 400000},
        retry_policy={"max_retries": 2, "backoff_seconds": 5},
    ),
    "Integrator": AgentCapability(
        agent_id="integrator",
        name="Integrator",
        capabilities=["workspace_merging", "cross_module_contracts", "system_level_verification"],
        supported_task_types=["INTEGRATE", "SYSTEM_VERIFY"],
        required_inputs=["CONVERTED_MODULE", "VERIFICATION_REPORT"],
        input_artifacts=["CONVERTED_MODULE", "VERIFICATION_REPORT"],
        produced_artifacts=["INTEGRATED_WORKSPACE", "SYSTEM_VERIFICATION_REPORT"],
        output_artifacts=["INTEGRATED_WORKSPACE", "SYSTEM_VERIFICATION_REPORT"],
        required_gate="G3",
        allowed_states=["INTEGRATING"],
        required_permissions=["job:read", "job:write"],
        resource_profile={"cpu": "high", "max_cost_usd": 1500.0, "max_tokens": 400000},
        retry_policy={"max_retries": 2, "backoff_seconds": 5},
    ),
}


class SupervisorDecision(BaseModel):
    action: SupervisorAction
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    target_node: Optional[str] = None
    target_status: Optional[str] = None
    reason: str
    budget_state: Dict[str, Any] = Field(default_factory=dict)
    gate_state: Dict[str, Any] = Field(default_factory=dict)
    dependency_state: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SupervisorRouter:
    """Deterministic routing and decision engine for the modernization supervisor."""

    def __init__(self):
        pass

    async def evaluate_next_action(
        self,
        db: AsyncSession,
        job: Job,
    ) -> SupervisorDecision:
        """Determines the next authoritative, deterministic action for the complete agent team."""
        current_status = JobStatus(job.status)

        # 1. Terminal State Check
        if current_status in JobStateMachine.TERMINAL_STATES:
            if current_status == JobStatus.COMPLETED:
                return SupervisorDecision(
                    action=SupervisorAction.COMPLETE,
                    reason="Project reached terminal completion state.",
                    target_status=JobStatus.COMPLETED.value,
                    gate_state={"status": "APPROVED", "gate": "G4"},
                )
            return SupervisorDecision(
                action=SupervisorAction.ESCALATE,
                reason=f"Job is in terminal state '{current_status.value}' ({job.blocking_reason or 'No reason'}).",
                target_status=current_status.value,
            )

        # 2. Multi-Dimensional Budget Enforcement Check (USD, Tokens, Time, Concurrency, Agent/Task Caps)
        b_res = await budget_manager.evaluate_budget(db, job)
        if b_res.is_exceeded:
            if b_res.exceeded_dimension == "CONCURRENCY":
                return SupervisorDecision(
                    action=SupervisorAction.WAIT,
                    reason=b_res.blocking_reason or "Worker concurrency limit reached; waiting for capacity.",
                    budget_state=b_res.state,
                )
            return SupervisorDecision(
                action=SupervisorAction.ESCALATE,
                reason=b_res.blocking_reason or "Job budget exhausted; reviewer escalation required.",
                target_status=JobStatus.PAUSED.value,
                budget_state=b_res.state,
                metadata={"budget_used": float(job.budget_used_usd), "budget_limit": float(job.budget_limit_usd)},
            )

        # 3. Gate Status & Human Approval Enforcement
        gate_waiting_map = {
            JobStatus.AWAITING_GATE_G1: "G1",
            JobStatus.AWAITING_GATE_G2: "G2",
            JobStatus.AWAITING_GATE_G3: "G3",
            JobStatus.AWAITING_GATE_G4: "G4",
        }
        if current_status in gate_waiting_map:
            gate_type = gate_waiting_map[current_status]
            gate = (
                await db.execute(
                    select(WorkflowGate)
                    .where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == gate_type)
                    .order_by(WorkflowGate.version.desc())
                )
            ).scalars().first()

            gate_info = {"gate_type": gate_type, "gate_id": str(gate.gate_id) if gate else None, "status": gate.status if gate else "NONE"}

            if not gate or gate.status == "PENDING":
                return SupervisorDecision(
                    action=SupervisorAction.WAIT,
                    reason=f"Human approval pending at Gate {gate_type}.",
                    target_node=f"gate_{gate_type.lower()}",
                    gate_state=gate_info,
                    metadata={"gate_type": gate_type, "gate_id": str(gate.gate_id) if gate else None},
                )
            elif gate and gate.status == "REJECTED":
                return SupervisorDecision(
                    action=SupervisorAction.ESCALATE,
                    reason=f"Gate {gate_type} was rejected by human reviewer.",
                    target_status=JobStatus.FAILED.value,
                    gate_state=gate_info,
                    metadata={"gate_type": gate_type, "gate_id": str(gate.gate_id)},
                )
            elif gate and gate.status == "APPROVED":
                # Advance to next canonical phase
                next_status_map = {
                    "G1": JobStatus.CHARACTERIZING,
                    "G2": JobStatus.PLANNING,
                    "G3": JobStatus.CONVERTING,
                    "G4": JobStatus.COMPLETED,
                }
                return SupervisorDecision(
                    action=SupervisorAction.ADVANCE_GATE,
                    reason=f"Gate {gate_type} approved; advancing to {next_status_map[gate_type].value}.",
                    target_status=next_status_map[gate_type].value,
                    gate_state=gate_info,
                    metadata={"gate_type": gate_type},
                )

        # 4. Fetch Existing Artifacts for Artifact-Driven Routing
        artifacts = list(
            (
                await db.execute(
                    select(Artifact).where(Artifact.job_id == job.job_id)
                )
            ).scalars().all()
        )
        artifact_types: Set[str] = {_artifact_key(a.artifact_type) for a in artifacts}

        # -------------------------------------------------------------------
        # Phase 1: Intake & Analysis
        # -------------------------------------------------------------------
        if current_status == JobStatus.CREATED:
            return SupervisorDecision(
                action=SupervisorAction.EXECUTE,
                task_id=f"intake-{job.job_id}",
                agent_id="IntakeAgent",
                target_status=JobStatus.INTAKE.value,
                reason="Starting repository intake stage.",
                budget_state=b_res.state,
            )

        if current_status == JobStatus.INTAKE:
            return SupervisorDecision(
                action=SupervisorAction.EXECUTE,
                task_id=f"intake-profile-{job.job_id}",
                agent_id="IntakeAgent",
                target_status=JobStatus.ANALYZING.value,
                reason="Executing repository intake & AST profiling.",
                budget_state=b_res.state,
            )

        if current_status == JobStatus.ANALYZING:
            # Artifact-driven routing through Analyzer -> Architect -> Feasibility
            if "LEGACYMODEL" not in artifact_types:
                return SupervisorDecision(
                    action=SupervisorAction.EXECUTE,
                    task_id=f"analyze-{job.job_id}",
                    agent_id="AnalyzerCoordinator",
                    target_status=JobStatus.ANALYZING.value,
                    reason="Repository inventory available; executing legacy AST analysis and entity mapping.",
                    budget_state=b_res.state,
                    dependency_state={"inputs": ["REPOSITORY_SNAPSHOT", "REPOSITORY_INVENTORY"], "ready": True},
                )
            elif "TARGETBLUEPRINT" not in artifact_types:
                return SupervisorDecision(
                    action=SupervisorAction.EXECUTE,
                    task_id=f"architect-{job.job_id}",
                    agent_id="ARCHITECT",
                    target_status=JobStatus.ANALYZING.value,
                    reason="Legacy model established; generating target architecture blueprint.",
                    budget_state=b_res.state,
                    dependency_state={"inputs": ["LEGACY_MODEL"], "ready": True},
                )
            elif "FEASIBILITYREPORT" not in artifact_types:
                return SupervisorDecision(
                    action=SupervisorAction.EXECUTE,
                    task_id=f"feasibility-{job.job_id}",
                    agent_id="FEASIBILITY",
                    target_status=JobStatus.ANALYZING.value,
                    reason="Target blueprint synthesized; scoring implementation feasibility.",
                    budget_state=b_res.state,
                    dependency_state={"inputs": ["TARGET_BLUEPRINT"], "ready": True},
                )
            else:
                # All three Phase 1 artifacts present -> Open Gate G1
                return SupervisorDecision(
                    action=SupervisorAction.ADVANCE_GATE,
                    agent_id="AnalyzerCoordinator",
                    target_status=JobStatus.AWAITING_GATE_G1.value,
                    reason="Analysis, Blueprint, and Feasibility artifacts validated; Gate G1 ready for human approval.",
                    budget_state=b_res.state,
                    dependency_state={"required_artifacts": ["LEGACY_MODEL", "TARGET_BLUEPRINT", "FEASIBILITY_REPORT"], "satisfied": True},
                )

        # -------------------------------------------------------------------
        # Phase 2: Characterization & Schema/Data
        # -------------------------------------------------------------------
        if current_status == JobStatus.CHARACTERIZING:
            if "CHARACTERIZATIONSUITE" not in artifact_types:
                return SupervisorDecision(
                    action=SupervisorAction.EXECUTE,
                    task_id=f"characterize-{job.job_id}",
                    agent_id="CharacterizerAgent",
                    target_status=JobStatus.CHARACTERIZING.value,
                    reason="Gate G1 approved; generating behavioral characterization suite and golden vectors.",
                    budget_state=b_res.state,
                    dependency_state={"inputs": ["TARGET_BLUEPRINT", "LEGACY_MODEL"], "ready": True},
                )
            elif "SCHEMAMIGRATIONPLAN" not in artifact_types:
                return SupervisorDecision(
                    action=SupervisorAction.EXECUTE,
                    task_id=f"schema-{job.job_id}",
                    agent_id="SCHEMA_DATA",
                    target_status=JobStatus.CHARACTERIZING.value,
                    reason="Characterization baseline established; executing database schema and DDL migration analysis.",
                    budget_state=b_res.state,
                    dependency_state={"inputs": ["CHARACTERIZATION_SUITE", "TARGET_BLUEPRINT"], "ready": True},
                )
            else:
                # Both baseline characterization and schema migration plan exist -> Open Gate G2
                return SupervisorDecision(
                    action=SupervisorAction.ADVANCE_GATE,
                    agent_id="CharacterizerAgent",
                    target_status=JobStatus.AWAITING_GATE_G2.value,
                    reason="Characterization suite and Schema Migration Plan generated; Gate G2 ready for baseline freeze.",
                    budget_state=b_res.state,
                    dependency_state={"required_artifacts": ["CHARACTERIZATION_SUITE", "SCHEMA_MIGRATION_PLAN"], "satisfied": True},
                )

        # -------------------------------------------------------------------
        # Phase 3: Planning & DAG Generation
        # -------------------------------------------------------------------
        if current_status == JobStatus.PLANNING:
            try:
                from app.services.supervisor_service import supervisor_service
                await supervisor_service.require_planning_eligibility(db, job)
            except ConflictException:
                return SupervisorDecision(action=SupervisorAction.WAIT, reason="Planning blocked: current frozen G2 approval is required.", gate_state={"gate": "G2", "eligible": False})
            if "CONVERSIONPLAN" not in artifact_types:
                return SupervisorDecision(
                    action=SupervisorAction.EXECUTE,
                    task_id=f"plan-{job.job_id}",
                    agent_id="PlannerCoordinator",
                    target_status=JobStatus.PLANNING.value,
                    reason="Gate G2 approved; executing module planner pool and aggregating conversion DAG.",
                    budget_state=b_res.state,
                    dependency_state={"inputs": ["TARGET_BLUEPRINT", "CHARACTERIZATION_SUITE", "SCHEMA_MIGRATION_PLAN"], "ready": True},
                )
            else:
                return SupervisorDecision(
                    action=SupervisorAction.ADVANCE_GATE,
                    agent_id="PlannerCoordinator",
                    target_status=JobStatus.AWAITING_GATE_G3.value,
                    reason="Modular conversion plan and DAG validated acyclic; Gate G3 ready for human approval.",
                    budget_state=b_res.state,
                    dependency_state={"required_artifacts": ["CONVERSION_PLAN"], "satisfied": True},
                )

        # -------------------------------------------------------------------
        # Phase 4: Conversion, Verification, and Deadlock Evaluation
        # -------------------------------------------------------------------
        if current_status in (JobStatus.CONVERTING, JobStatus.VERIFYING):
            modules = list(
                (
                    await db.execute(
                        select(Module)
                        .where(Module.job_id == job.job_id)
                        .order_by(Module.wave_number.asc(), Module.created_at.asc())
                    )
                ).scalars().all()
            )

            if not modules:
                return SupervisorDecision(
                    action=SupervisorAction.ESCALATE,
                    reason="No conversion modules found for job in CONVERTING state.",
                    target_status=JobStatus.FAILED.value,
                    budget_state=b_res.state,
                )

            now = utc_now()
            completed_ids = {str(m.module_id) for m in modules if m.status == "COMPLETED"}
            verified_ids = {str(m.module_id) for m in modules if m.status in ("VERIFIED", "COMPLETED")}
            active_modules = [
                m for m in modules
                if m.status in ("LEASED", "RUNNING") and (m.lease_expires_at is None or m.lease_expires_at > now)
            ]

            # 4a. Check if any generated modules need independent verification
            generated_modules = [m for m in modules if m.status == "GENERATED"]
            if generated_modules:
                target_mod = generated_modules[0]
                return SupervisorDecision(
                    action=SupervisorAction.EXECUTE,
                    task_id=f"verify-{target_mod.module_id}",
                    agent_id="Verifier",
                    target_status=JobStatus.VERIFYING.value,
                    reason=f"Module {target_mod.name} is generated; running independent verification.",
                    budget_state=b_res.state,
                    dependency_state={"module_id": str(target_mod.module_id), "status": target_mod.status},
                    metadata={"module_id": str(target_mod.module_id), "module_name": target_mod.name},
                )

            # 4b. Check for ready pending modules whose DAG dependencies are satisfied
            ready_modules: List[Module] = []
            for m in modules:
                if m.status == "PENDING":
                    deps = set(m.dependency_module_ids or [])
                    if deps.issubset(verified_ids | completed_ids):
                        ready_modules.append(m)

            if ready_modules:
                target_mod = ready_modules[0]
                action = SupervisorAction.REPAIR if target_mod.retry_count > 0 else SupervisorAction.EXECUTE
                return SupervisorDecision(
                    action=action,
                    task_id=f"convert-{target_mod.module_id}",
                    agent_id="CodeWriter",
                    target_status=JobStatus.CONVERTING.value,
                    reason=f"Module {target_mod.name} is ready for conversion (Wave {target_mod.wave_number}).",
                    budget_state=b_res.state,
                    dependency_state={"module_id": str(target_mod.module_id), "wave": target_mod.wave_number, "dependencies_satisfied": True},
                    metadata={"module_id": str(target_mod.module_id), "module_name": target_mod.name},
                )

            # 4c. If workers are actively running, wait
            if active_modules:
                return SupervisorDecision(
                    action=SupervisorAction.WAIT,
                    reason=f"Waiting for {len(active_modules)} active worker tasks to complete.",
                    budget_state=b_res.state,
                    dependency_state={"active_workers_count": len(active_modules)},
                    metadata={"active_count": len(active_modules)},
                )

            # 4d. Check if all modules are verified or completed
            uncompleted = [m for m in modules if m.status not in ("VERIFIED", "COMPLETED")]
            if not uncompleted:
                # All modules converted and verified! Advance to INTEGRATING
                return SupervisorDecision(
                    action=SupervisorAction.EXECUTE,
                    agent_id="Integrator",
                    target_status=JobStatus.INTEGRATING.value,
                    reason="All modules successfully converted and verified; advancing to system integration.",
                    budget_state=b_res.state,
                    dependency_state={"total_modules": len(modules), "all_verified": True},
                )

            # 4e. DEADLOCK DETECTION:
            # Uncompleted modules exist, none ready, no active workers
            uncompleted_names = [m.name for m in uncompleted]
            return SupervisorDecision(
                action=SupervisorAction.ESCALATE,
                reason=f"DEPENDENCY_DEADLOCK: Remaining modules {uncompleted_names} cannot proceed; circular or unsatisfied dependencies detected.",
                target_status=JobStatus.FAILED.value,
                budget_state=b_res.state,
                dependency_state={"deadlocked_count": len(uncompleted), "uncompleted": uncompleted_names},
                metadata={"deadlocked_modules": [str(m.module_id) for m in uncompleted]},
            )

        # -------------------------------------------------------------------
        # Phase 5: System Integration & Delivery
        # -------------------------------------------------------------------
        if current_status == JobStatus.INTEGRATING:
            return SupervisorDecision(
                action=SupervisorAction.EXECUTE,
                task_id=f"integrate-{job.job_id}",
                agent_id="Integrator",
                target_status=JobStatus.AWAITING_GATE_G4.value,
                reason="Running workspace integration, cross-module contracts, and system verification.",
                budget_state=b_res.state,
                dependency_state={"all_modules_verified": True},
            )

        return SupervisorDecision(
            action=SupervisorAction.WAIT,
            reason=f"Supervisor waiting in status {current_status.value}.",
            budget_state=b_res.state,
        )


supervisor_router = SupervisorRouter()
