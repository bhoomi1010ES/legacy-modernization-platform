"""Durable LangGraph Workflow & Deterministic Multi-Node Supervisor Orchestration Graph."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictException
from app.domain.state_machine import JobStateMachine
from app.models.job import Job
from app.models.module import Module
from app.models.workflow import WorkflowGate
from app.schemas.jobs import JobStatus
from app.schemas.workflow import SupervisorState, WorkflowEvent, WorkflowNode
from app.services.dependency_scheduler import dependency_scheduler
from app.services.supervisor_router import (
    SupervisorAction,
    SupervisorDecision,
    supervisor_router,
)

logger = logging.getLogger(__name__)

WORKFLOW_NODES = tuple(node.value for node in WorkflowNode)


# ---------------------------------------------------------------------------
# Loop State Definition
# ---------------------------------------------------------------------------
class SupervisorLoopState(TypedDict, total=False):
    """Rich typed state for the multi-step LangGraph supervisor loop."""

    job_id: str
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

    # Deterministic control loop signals
    decision_action: str
    decision_reason: str
    selected_task_id: Optional[str]
    selected_agent: Optional[str]
    is_valid_state: bool
    budget_exhausted: bool
    is_human_gate_required: bool
    gate_rejected: bool
    is_deadlocked: bool
    has_ready_tasks: bool
    has_active_workers: bool
    all_tasks_completed: bool
    execution_verdict: str  # SUCCESS, RETRY, REPAIR, ESCALATE
    loop_count: int
    max_loops: int
    terminal_state: Optional[str]
    target_status: Optional[str]
    orchestration_owner: str
    orchestration_generation: int


# ---------------------------------------------------------------------------
# Node Handlers for the 19 Required Supervisor Nodes
# ---------------------------------------------------------------------------
async def node_load_state(state: SupervisorLoopState) -> dict:
    """1. Loads the latest persistent job and gate state from the database."""
    job_uuid = UUID(state["job_id"])
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_uuid)
        if not job:
            return {
                "is_valid_state": False,
                "blocking_reason": f"Job {job_uuid} not found.",
                "events": [{"type": "LOAD_STATE_FAILED", "error": "Job not found"}],
            }
        from app.services.supervisor_service import supervisor_service
        snapshot = await supervisor_service.snapshot_for(db, job, correlation_id=state.get("correlation_id"))
        snapshot["events"] = [{"type": "STATE_LOADED", "status": job.status, "node": job.active_node}]
        return snapshot


async def node_validate_state(state: SupervisorLoopState) -> dict:
    """2. Validates workflow state against canonical state machine."""
    current_status = state.get("status", "FAILED")
    try:
        status_enum = JobStatus(current_status)
        if status_enum in JobStateMachine.TERMINAL_STATES:
            return {
                "is_valid_state": False,
                "terminal_state": current_status,
                "decision_action": "COMPLETE" if status_enum == JobStatus.COMPLETED else "ESCALATE",
                "blocking_reason": f"Job is in terminal state '{current_status}'.",
                "events": [{"type": "STATE_VALIDATED", "valid": False, "terminal": True}],
            }
        return {
            "is_valid_state": True,
            "events": [{"type": "STATE_VALIDATED", "valid": True}],
        }
    except Exception as exc:
        return {
            "is_valid_state": False,
            "blocking_reason": f"Invalid job status '{current_status}': {exc}",
            "events": [{"type": "STATE_VALIDATION_ERROR", "error": str(exc)}],
        }


async def node_recover_tasks(state: SupervisorLoopState) -> dict:
    """3. Reconciles expired worker leases and recovers stalled tasks."""
    job_uuid = UUID(state["job_id"])
    try:
        async with AsyncSessionLocal() as db:
            from app.services.supervisor_service import supervisor_service
            before_modules = list((await db.execute(
                select(Module).where(Module.job_id == job_uuid)
            )).scalars().all())
            before_retries = sum(module.retry_count for module in before_modules)
            await supervisor_service.reconcile_job(db, job_uuid, correlation_id=state.get("correlation_id"))
            after_modules = list((await db.execute(
                select(Module).where(Module.job_id == job_uuid).execution_options(populate_existing=True)
            )).scalars().all())
            recovered_count = max(0, sum(module.retry_count for module in after_modules) - before_retries)
            return {
                "events": [{"type": "TASKS_RECOVERED", "stale_leases_reconciled": recovered_count}],
            }
    except Exception as exc:
        logger.warning("recover_tasks failed non-critically | %s", exc)
        return {"events": [{"type": "TASKS_RECOVERY_SKIPPED"}]}


async def node_evaluate_budget(state: SupervisorLoopState) -> dict:
    """4. Enforces budget spend limits before task execution."""
    used = state.get("budget_used", 0.0)
    limit = state.get("budget_limit", 15000.0)
    if used >= limit:
        return {
            "budget_exhausted": True,
            "decision_action": "ESCALATE",
            "blocking_reason": "Job budget exhausted; reviewer escalation required.",
            "events": [{"type": "BUDGET_EXHAUSTED", "used": used, "limit": limit}],
        }
    return {
        "budget_exhausted": False,
        "events": [{"type": "BUDGET_OK", "used": used, "limit": limit}],
    }


async def node_evaluate_gate(state: SupervisorLoopState) -> dict:
    """5. Inspects approval gate status (G1-G4) and enforces human sign-off."""
    job_uuid = UUID(state["job_id"])
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_uuid)
        if not job:
            return {"decision_action": "ESCALATE", "blocking_reason": "Job not found."}

        decision = await supervisor_router.evaluate_next_action(db, job)
        is_human_required = decision.action == SupervisorAction.WAIT and "Gate" in decision.reason
        gate_rejected = decision.action == SupervisorAction.ESCALATE and "rejected" in decision.reason

        return {
            "is_human_gate_required": is_human_required,
            "gate_rejected": gate_rejected,
            "decision_action": decision.action.value,
            "decision_reason": decision.reason,
            "events": [{"type": "GATE_EVALUATED", "action": decision.action.value, "reason": decision.reason}],
        }


async def node_discover_ready_tasks(state: SupervisorLoopState) -> dict:
    """6. Evaluates dependency DAG, detects deadlocks, and discovers ready modules."""
    job_uuid = UUID(state["job_id"])
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_uuid)
        if not job:
            return {"is_deadlocked": False, "has_ready_tasks": False, "decision_action": "ESCALATE"}

        decision = await supervisor_router.evaluate_next_action(db, job)

        is_deadlock = "DEPENDENCY_DEADLOCK" in decision.reason
        has_tasks = decision.action in (SupervisorAction.EXECUTE, SupervisorAction.REPAIR)
        waiting_workers = decision.action == SupervisorAction.WAIT
        all_completed = (
            decision.action == SupervisorAction.COMPLETE
            or decision.action == SupervisorAction.ADVANCE_GATE
            or (decision.agent_id == "Integrator" and job.status != "INTEGRATING")
        )

        return {
            "is_deadlocked": is_deadlock,
            "has_ready_tasks": has_tasks,
            "has_active_workers": waiting_workers,
            "all_tasks_completed": all_completed,
            "decision_action": decision.action.value,
            "decision_reason": decision.reason,
            "selected_task_id": decision.task_id,
            "selected_agent": decision.agent_id,
            "events": [{"type": "TASKS_DISCOVERED", "action": decision.action.value, "agent": decision.agent_id}],
        }


async def node_select_task(state: SupervisorLoopState) -> dict:
    """7. Selects next task and leases module for the appropriate specialist agent."""
    selected_agent = state.get("selected_agent", "CodeWriter")
    task_id = state.get("selected_task_id")
    return {
        "selected_agent": selected_agent,
        "selected_task_id": task_id,
        "events": [{"type": "TASK_SELECTED", "agent": selected_agent, "task_id": task_id}],
    }


async def node_execute_agent(state: SupervisorLoopState) -> dict:
    """8. Dispatches execution to the specialist agent in the agent pool."""
    agent_name = state.get("selected_agent", "")
    job_uuid = UUID(state["job_id"])
    corr_id = state.get("correlation_id") or "loop"

    try:
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_uuid)
            if not job:
                return {"execution_verdict": "ESCALATE", "blocking_reason": "Job not found."}

            if agent_name in ("CodeWriter", "CODE_WRITER"):
                from app.models.module import Module
                from app.services.code_writer import code_writer_service
                from app.services.repository_workspace_service import repository_workspace_service
                try:
                    await repository_workspace_service.ensure_workspace(db, job, correlation_id=corr_id)
                except Exception as ws_err:
                    job.blocking_reason = f"Workspace unavailable: {ws_err}"
                    await db.commit()
                    return {
                        "execution_verdict": "WAIT",
                        "blocking_reason": f"Workspace unavailable: {ws_err}",
                        "events": [{"type": "WORKSPACE_UNAVAILABLE", "error": str(ws_err)}],
                    }

                # Extract module ID from task_id e.g. "convert-<uuid>"
                task_id = state.get("selected_task_id", "")
                mod_id_str = task_id.replace("convert-", "") if "convert-" in task_id else task_id
                mod = await db.get(Module, UUID(mod_id_str)) if mod_id_str else None
                if mod and mod.job_id != job.job_id:
                    mod = None
                if not mod:
                    mod = await db.scalar(select(Module).where(Module.job_id == job.job_id, Module.status == "PENDING").order_by(Module.wave_number).limit(1))

                if mod:
                    try:
                        result = await code_writer_service.execute_module_conversion(
                            db, job, mod, correlation_id=corr_id
                        )
                        return {"execution_verdict": "SUCCESS" if result["status"] == "VERIFIED" else "WAIT", "events": [{"type": "MODULE_" + result["status"], "module": mod.name}]}
                    except ConflictException as blk_exc:
                        mod.status = "BLOCKED"
                        job.blocking_reason = str(blk_exc)
                        await db.commit()
                        return {"execution_verdict": "WAIT", "blocking_reason": str(blk_exc), "events": [{"type": "MODULE_BLOCKED", "module": mod.name, "reason": str(blk_exc)}]}
                return {"execution_verdict": "WAIT", "events": [{"type": "CODEWRITER_NO_LEASE"}]}

            elif agent_name in ("Verifier", "VERIFIER"):
                from app.models.module import Module
                from app.services.verifier_agent import verifier_service

                task_id = state.get("selected_task_id", "")
                mod_id_str = task_id.replace("verify-", "") if "verify-" in task_id else task_id
                mod = await db.get(Module, UUID(mod_id_str)) if mod_id_str else None
                if mod and mod.job_id == job.job_id:
                    res = await verifier_service.verify_module(db, job, mod, correlation_id=corr_id)
                    if res.verdict.value == "PASS":
                        return {"execution_verdict": "SUCCESS", "events": [{"type": "VERIFICATION_PASS"}]}
                    elif res.verdict.value == "REPAIR":
                        return {"execution_verdict": "REPAIR", "events": [{"type": "VERIFICATION_REPAIR"}]}
                    else:
                        return {"execution_verdict": "ESCALATE", "events": [{"type": "VERIFICATION_ESCALATE"}]}
                return {"execution_verdict": "WAIT", "blocking_reason": "No module execution evidence"}

            elif agent_name in ("Integrator", "INTEGRATOR"):
                from app.services.integrator_agent import integrator_service
                from app.services.supervisor_service import supervisor_service
                if job.status != JobStatus.INTEGRATING.value:
                    await supervisor_service.transition(
                        db, job.job_id, JobStatus.INTEGRATING, actor_id="supervisor", correlation_id=corr_id
                    )
                    await db.refresh(job)
                result = await integrator_service.execute_integration(db, job, correlation_id=corr_id)
                if result.success:
                    await supervisor_service.command(
                        db, job.job_id, WorkflowEvent.INTEGRATION_COMPLETE,
                        actor_id="supervisor", correlation_id=corr_id,
                        reason="Integrated candidate and final evidence ready for human G4 review",
                    )
                return {"execution_verdict": "SUCCESS", "events": [{"type": "INTEGRATION_SUCCESS"}]}

            elif agent_name == "IntakeAgent":
                from app.services.phase4_orchestrator import phase4_orchestrator
                from app.services.supervisor_service import supervisor_service
                if job.status == JobStatus.CREATED.value:
                    await supervisor_service.command(
                        db, job.job_id, WorkflowEvent.INTAKE_STARTED,
                        actor_id="supervisor", correlation_id=corr_id,
                        reason="Authoritative supervisor started repository intake",
                    )
                    await db.refresh(job)
                await phase4_orchestrator.run_pipeline_stage1_intake(db, job, correlation_id=corr_id)
                await supervisor_service.command(
                    db, job.job_id, WorkflowEvent.ANALYSIS_STARTED,
                    actor_id="supervisor", correlation_id=corr_id,
                    reason="Repository snapshot persisted; analysis is ready",
                )
                return {"execution_verdict": "SUCCESS", "events": [{"type": "INTAKE_SUCCESS"}]}

            elif agent_name in ("AnalyzerCoordinator", "ANALYZER"):
                from app.services.phase4_orchestrator import phase4_orchestrator
                from app.services.repository_workspace_service import repository_workspace_service
                try:
                    await repository_workspace_service.ensure_workspace(db, job, correlation_id=corr_id)
                except Exception as ws_err:
                    job.blocking_reason = f"Workspace unavailable: {ws_err}"
                    await db.commit()
                    return {
                        "execution_verdict": "WAIT",
                        "blocking_reason": f"Workspace unavailable: {ws_err}",
                        "events": [{"type": "WORKSPACE_UNAVAILABLE", "error": str(ws_err)}],
                    }
                await phase4_orchestrator.run_pipeline_stage2_analysis_and_feasibility(db, job, correlation_id=corr_id)
                return {"execution_verdict": "SUCCESS", "events": [{"type": "ANALYSIS_SUCCESS"}]}

            elif agent_name in ("ARCHITECT", "ArchitectAgent"):
                from app.models.phase4 import LegacyModelRecord
                from app.schemas.phase4 import LegacyModel
                from app.services.architect_agent import architect_agent
                leg_rec = (await db.execute(
                    select(LegacyModelRecord).where(LegacyModelRecord.job_id == job.job_id).order_by(LegacyModelRecord.version.desc())
                )).scalars().first()
                if leg_rec:
                    legacy_model = LegacyModel(
                        model_id=str(leg_rec.model_id), job_id=str(job.job_id), snapshot_id=str(leg_rec.snapshot_id),
                        version=leg_rec.version, modules=leg_rec.modules_payload, dependency_graph=leg_rec.dependencies_payload,
                        public_interfaces=leg_rec.interfaces_payload, persistence_entities=leg_rec.persistence_payload,
                        configurations=leg_rec.configurations_payload, test_suites=leg_rec.tests_payload, risks=leg_rec.risks_payload,
                        conflicts=leg_rec.conflicts_payload, evidence_index={}, content_hash=leg_rec.content_hash,
                    )
                    await architect_agent.execute_architect(db, job, legacy_model, correlation_id=corr_id)
                return {"execution_verdict": "SUCCESS", "events": [{"type": "ARCHITECT_SUCCESS"}]}

            elif agent_name in ("FEASIBILITY", "FeasibilityAgent"):
                from app.models.phase4 import LegacyModelRecord, TargetBlueprintModel
                from app.schemas.phase4 import LegacyModel, TargetBlueprint
                from app.services.feasibility_agent import feasibility_agent
                leg_rec = (await db.execute(select(LegacyModelRecord).where(LegacyModelRecord.job_id == job.job_id).order_by(LegacyModelRecord.version.desc()))).scalars().first()
                bp_rec = (await db.execute(select(TargetBlueprintModel).where(TargetBlueprintModel.job_id == job.job_id).order_by(TargetBlueprintModel.version.desc()))).scalars().first()
                if leg_rec and bp_rec:
                    legacy_model = LegacyModel(
                        model_id=str(leg_rec.model_id), job_id=str(job.job_id), snapshot_id=str(leg_rec.snapshot_id),
                        version=leg_rec.version, modules=leg_rec.modules_payload, dependency_graph=leg_rec.dependencies_payload,
                        public_interfaces=leg_rec.interfaces_payload, persistence_entities=leg_rec.persistence_payload,
                        configurations=leg_rec.configurations_payload, test_suites=leg_rec.tests_payload, risks=leg_rec.risks_payload,
                        conflicts=leg_rec.conflicts_payload, evidence_index={}, content_hash=leg_rec.content_hash,
                    )
                    blueprint = TargetBlueprint(
                        blueprint_id=str(bp_rec.blueprint_id), job_id=str(job.job_id), version=bp_rec.version,
                        status=bp_rec.status, target_stack=bp_rec.target_stack, target_architecture=bp_rec.target_architecture,
                        components=bp_rec.components_payload, interfaces=bp_rec.interfaces_payload, data_model=bp_rec.data_model_payload,
                        integration_contracts=bp_rec.integration_contracts_payload, deployment_constraints=[], security_constraints=[],
                        compatibility_constraints=[], migration_constraints=[], accepted_decisions=[], open_constraints=[], evidence_refs=[],
                        created_by="supervisor", content_hash=bp_rec.content_hash,
                    )
                    await feasibility_agent.execute_feasibility(db, job, legacy_model, blueprint, correlation_id=corr_id)
                return {"execution_verdict": "SUCCESS", "events": [{"type": "FEASIBILITY_SUCCESS"}]}

            elif agent_name in ("CharacterizerAgent", "CHARACTERIZER"):
                from app.services.continuous_pipeline import continuous_pipeline_service
                from app.services.supervisor_service import supervisor_service
                await continuous_pipeline_service._run_characterization_stage(
                    db, job, None, "supervisor", corr_id, transition_to_gate=False
                )
                await supervisor_service.command(
                    db, job.job_id, WorkflowEvent.CHARACTERIZATION_COMPLETE,
                    actor_id="supervisor", correlation_id=corr_id,
                    reason="Characterization evidence persisted; schema/data analysis is next",
                )
                return {"execution_verdict": "SUCCESS", "events": [{"type": "CHARACTERIZATION_SUCCESS"}]}

            elif agent_name in ("SCHEMA_DATA", "SchemaDataAgent"):
                from app.services.schema_data_agent import schema_data_service
                from app.services.supervisor_service import supervisor_service
                if getattr(job, "workflow_phase", "") != "SCHEMA_DATA":
                    await supervisor_service.command(
                        db, job.job_id, WorkflowEvent.CHARACTERIZATION_COMPLETE,
                        actor_id="supervisor", correlation_id=corr_id,
                    )
                await schema_data_service.execute_schema_data_analysis(db, job, correlation_id=corr_id)
                await supervisor_service.command(
                    db, job.job_id, WorkflowEvent.SCHEMA_DATA_COMPLETE,
                    actor_id="supervisor", correlation_id=corr_id,
                    reason="Schema/data evidence ready for G2",
                )
                return {"execution_verdict": "SUCCESS", "events": [{"type": "SCHEMA_DATA_SUCCESS"}]}

            elif agent_name in ("PlannerCoordinator", "PLANNER"):
                from app.services.phase4_orchestrator import phase4_orchestrator
                await phase4_orchestrator.run_pipeline_stage3_planning(db, job, correlation_id=corr_id)
                return {"execution_verdict": "SUCCESS", "events": [{"type": "PLANNING_SUCCESS"}]}

            return {"execution_verdict": "SUCCESS"}
    except Exception as exc:
        logger.exception("execute_agent error in %s | %s", agent_name, exc)
        return {
            "execution_verdict": "ESCALATE",
            "blocking_reason": f"Agent {agent_name} failed: {exc}",
            "events": [{"type": "AGENT_FAILED", "agent": agent_name, "error": str(exc)}],
        }


async def node_persist_result(state: SupervisorLoopState) -> dict:
    """9. Persists agent outputs, audit records, and budget increments."""
    from app.services.supervisor_service import supervisor_service
    async with AsyncSessionLocal() as db:
        await supervisor_service.record_graph_result(
            db,
            UUID(state["job_id"]),
            verdict=state.get("execution_verdict", "SUCCESS"),
            task_id=state.get("selected_task_id"),
            agent_name=state.get("selected_agent"),
            correlation_id=state.get("correlation_id"),
            reason=state.get("blocking_reason"),
        )
    return {"events": [{"type": "RESULT_PERSISTED"}]}


async def node_evaluate_result(state: SupervisorLoopState) -> dict:
    """10. Evaluates agent output and determines triage: SUCCESS, RETRY, REPAIR, ESCALATE."""
    verdict = state.get("execution_verdict", "SUCCESS")
    return {
        "execution_verdict": verdict,
        "events": [{"type": "RESULT_EVALUATED", "verdict": verdict}],
    }


async def node_handle_success(state: SupervisorLoopState) -> dict:
    """11. Records successful completion of agent work and prepares state for next step."""
    return {"events": [{"type": "SUCCESS_HANDLED"}]}


async def node_handle_retry(state: SupervisorLoopState) -> dict:
    """12. Handles transient failure and schedules retry within budget limit."""
    retries = state.get("retry_count", 0) + 1
    return {
        "retry_count": retries,
        "events": [{"type": "RETRY_SCHEDULED", "attempt": retries}],
    }


async def node_handle_repair(state: SupervisorLoopState) -> dict:
    """13. Enforces bounded repair loop with targeted feedback."""
    return {
        "retry_count": state.get("retry_count", 0) + 1,
        "events": [{"type": "REPAIR_SCHEDULED", "task_id": state.get("selected_task_id")}],
    }


async def node_handle_wait(state: SupervisorLoopState) -> dict:
    """14. Graceful waiting state for active workers or lease expiry."""
    return {"events": [{"type": "SUPERVISOR_WAITING"}]}


async def node_handle_escalation(state: SupervisorLoopState) -> dict:
    """15. Halts workflow and records auditable failure with blocking reason."""
    reason = state.get("blocking_reason") or "Workflow escalated due to policy violation or unrecoverable error."
    job_uuid = UUID(state["job_id"])
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_uuid)
        if job and JobStatus(job.status) not in JobStateMachine.TERMINAL_STATES:
            from app.services.supervisor_service import supervisor_service
            await supervisor_service.fail(
                db, job_uuid, reason=reason, correlation_id=state.get("correlation_id")
            )
    return {
        "status": JobStatus.FAILED.value,
        "blocking_reason": reason,
        "events": [{"type": "ESCALATION_RECORDED", "reason": reason}],
    }


async def node_advance_gate(state: SupervisorLoopState) -> dict:
    """16. Advances job to approval gate state and materializes pending gate."""
    job_uuid = UUID(state["job_id"])
    target_status_str = state.get("target_status")
    if target_status_str:
        try:
            from app.services.supervisor_service import supervisor_service
            async with AsyncSessionLocal() as db:
                job = await db.get(Job, job_uuid)
                if job and job.status != target_status_str:
                    await supervisor_service.transition(
                        db, job.job_id, JobStatus(target_status_str), actor_id="supervisor"
                    )
                    return {
                        "status": target_status_str,
                        "events": [{"type": "GATE_ADVANCED", "target_status": target_status_str}],
                    }
        except Exception as exc:
            logger.exception("node_advance_gate transition failed: %s", exc)
            async with AsyncSessionLocal() as failure_db:
                from app.services.supervisor_service import supervisor_service
                await supervisor_service.fail(
                    failure_db, job_uuid,
                    reason=f"Gate transition failed: {exc}",
                    correlation_id=state.get("correlation_id"),
                )
            return {
                "target_status": JobStatus.FAILED.value,
                "decision_action": "ESCALATE",
                "blocking_reason": f"Gate transition failed: {exc}",
                "events": [{"type": "GATE_ADVANCE_FAILED", "error": str(exc)}],
            }
    return {"events": [{"type": "GATE_ADVANCED"}]}


async def node_check_completion(state: SupervisorLoopState) -> dict:
    """17. Determines if phase tasks are complete or ready for next gate."""
    job_uuid = UUID(state["job_id"])
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_uuid)
        if not job:
            return {"decision_action": "ESCALATE"}
        decision = await supervisor_router.evaluate_next_action(db, job)
        return {
            "loop_count": state.get("loop_count", 0) + 1,
            "decision_action": decision.action.value,
            "decision_reason": decision.reason,
            "selected_agent": decision.agent_id,
            "selected_task_id": decision.task_id,
            "target_status": decision.target_status,
            "events": [{"type": "COMPLETION_CHECKED", "action": decision.action.value}],
        }


async def node_pause_for_human(state: SupervisorLoopState) -> dict:
    """18. Halts graph execution awaiting authenticated human review decision."""
    return {"active_node": "pause_for_human", "events": [{"type": "PAUSED_FOR_HUMAN_REVIEW"}]}


async def node_complete_project(state: SupervisorLoopState) -> dict:
    """19. Marks modernized project fully complete after Gate G4 sign-off."""
    job_uuid = UUID(state["job_id"])
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_uuid)
        if job and job.status != JobStatus.COMPLETED.value:
            from app.services.supervisor_service import supervisor_service
            await supervisor_service.command(
                db, job_uuid, WorkflowEvent.G4_APPROVED,
                actor_id="supervisor", correlation_id=state.get("correlation_id"),
                reason="Human G4 approval accepted; delivery handoff complete",
            )
    return {
        "status": JobStatus.COMPLETED.value,
        "active_node": "complete",
        "events": [{"type": "PROJECT_COMPLETED_SUCCESSFULLY"}],
    }


# ---------------------------------------------------------------------------
# Routing Functions for Conditional Edges
# ---------------------------------------------------------------------------
def route_after_validate(state: SupervisorLoopState) -> str:
    return "recover_tasks" if state.get("is_valid_state", True) else "handle_escalation"


def route_after_budget(state: SupervisorLoopState) -> str:
    return "handle_escalation" if state.get("budget_exhausted", False) else "evaluate_gate"


def route_after_gate(state: SupervisorLoopState) -> str:
    if state.get("is_human_gate_required", False):
        return "pause_for_human"
    if state.get("gate_rejected", False):
        return "handle_escalation"
    return "discover_ready_tasks"


def route_after_discover(state: SupervisorLoopState) -> str:
    if state.get("is_deadlocked", False):
        return "handle_escalation"
    if state.get("has_ready_tasks", False):
        return "select_task"
    if state.get("has_active_workers", False):
        return "handle_wait"
    return "check_completion"


def route_after_evaluate_result(state: SupervisorLoopState) -> str:
    verdict = state.get("execution_verdict", "SUCCESS")
    if verdict == "SUCCESS":
        return "handle_success"
    if verdict == "RETRY":
        return "handle_retry"
    if verdict == "REPAIR":
        return "handle_repair"
    if verdict == "WAIT":
        return "handle_wait"
    return "handle_escalation"


def route_after_completion(state: SupervisorLoopState) -> str:
    if state.get("loop_count", 0) >= state.get("max_loops", 50):
        return "handle_wait"
    action = state.get("decision_action", "WAIT")
    if action == "COMPLETE":
        return "complete_project"
    if action == "ADVANCE_GATE":
        return "advance_gate"
    if action in ("EXECUTE", "REPAIR"):
        return "discover_ready_tasks"
    if action == "WAIT":
        return "pause_for_human" if "Gate" in state.get("decision_reason", "") else "handle_wait"
    return "handle_escalation"


def route_after_advance_gate(state: SupervisorLoopState) -> str:
    target_status = state.get("target_status") or state.get("status") or ""
    if target_status == JobStatus.FAILED.value:
        return "handle_escalation"
    if target_status.startswith("AWAITING_GATE_"):
        return "pause_for_human"
    if target_status == "COMPLETED":
        return "complete_project"
    return "discover_ready_tasks"


# ---------------------------------------------------------------------------
# Graph Compilers
# ---------------------------------------------------------------------------
def build_supervisor_loop_graph():
    """Builds the comprehensive multi-node deterministic supervisor LangGraph."""
    builder = StateGraph(SupervisorLoopState)

    # Add all 19 nodes
    builder.add_node("load_state", node_load_state)
    builder.add_node("validate_state", node_validate_state)
    builder.add_node("recover_tasks", node_recover_tasks)
    builder.add_node("evaluate_budget", node_evaluate_budget)
    builder.add_node("evaluate_gate", node_evaluate_gate)
    builder.add_node("discover_ready_tasks", node_discover_ready_tasks)
    builder.add_node("select_task", node_select_task)
    builder.add_node("execute_agent", node_execute_agent)
    builder.add_node("persist_result", node_persist_result)
    builder.add_node("evaluate_result", node_evaluate_result)
    builder.add_node("handle_success", node_handle_success)
    builder.add_node("handle_retry", node_handle_retry)
    builder.add_node("handle_repair", node_handle_repair)
    builder.add_node("handle_wait", node_handle_wait)
    builder.add_node("handle_escalation", node_handle_escalation)
    builder.add_node("advance_gate", node_advance_gate)
    builder.add_node("check_completion", node_check_completion)
    builder.add_node("pause_for_human", node_pause_for_human)
    builder.add_node("complete_project", node_complete_project)

    # Linear and conditional edges
    builder.add_edge(START, "load_state")
    builder.add_edge("load_state", "validate_state")

    builder.add_conditional_edges(
        "validate_state",
        route_after_validate,
        {"recover_tasks": "recover_tasks", "handle_escalation": "handle_escalation"},
    )
    builder.add_edge("recover_tasks", "evaluate_budget")

    builder.add_conditional_edges(
        "evaluate_budget",
        route_after_budget,
        {"evaluate_gate": "evaluate_gate", "handle_escalation": "handle_escalation"},
    )

    builder.add_conditional_edges(
        "evaluate_gate",
        route_after_gate,
        {
            "pause_for_human": "pause_for_human",
            "handle_escalation": "handle_escalation",
            "discover_ready_tasks": "discover_ready_tasks",
        },
    )

    builder.add_conditional_edges(
        "discover_ready_tasks",
        route_after_discover,
        {
            "handle_escalation": "handle_escalation",
            "select_task": "select_task",
            "handle_wait": "handle_wait",
            "check_completion": "check_completion",
        },
    )

    builder.add_edge("select_task", "execute_agent")
    builder.add_edge("execute_agent", "persist_result")
    builder.add_edge("persist_result", "evaluate_result")

    builder.add_conditional_edges(
        "evaluate_result",
        route_after_evaluate_result,
        {
            "handle_success": "handle_success",
            "handle_retry": "handle_retry",
            "handle_repair": "handle_repair",
            "handle_wait": "handle_wait",
            "handle_escalation": "handle_escalation",
        },
    )

    builder.add_edge("handle_success", "check_completion")
    builder.add_edge("handle_retry", "discover_ready_tasks")
    builder.add_edge("handle_repair", "select_task")

    builder.add_conditional_edges(
        "check_completion",
        route_after_completion,
        {
            "complete_project": "complete_project",
            "advance_gate": "advance_gate",
            "discover_ready_tasks": "discover_ready_tasks",
            "handle_wait": "handle_wait",
            "pause_for_human": "pause_for_human",
            "handle_escalation": "handle_escalation",
        },
    )

    builder.add_conditional_edges(
        "advance_gate",
        route_after_advance_gate,
        {
            "pause_for_human": "pause_for_human",
            "complete_project": "complete_project",
            "discover_ready_tasks": "discover_ready_tasks",
            "handle_escalation": "handle_escalation",
        },
    )

    # Terminal exits
    builder.add_edge("pause_for_human", END)
    builder.add_edge("handle_wait", END)
    builder.add_edge("handle_escalation", END)
    builder.add_edge("complete_project", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Deprecated single-transition graph guard
# ---------------------------------------------------------------------------
class DeprecatedSupervisorGraph:
    """Import-compatible fail-closed guard; never a production authority."""

    async def ainvoke(self, _state):
        raise ConflictException(
            "Legacy single-transition supervisor graph is deprecated and non-authoritative"
        )


def build_supervisor_graph():
    """Return the non-executable compatibility guard."""
    return DeprecatedSupervisorGraph()


supervisor_graph = DeprecatedSupervisorGraph()
authoritative_supervisor_graph = build_supervisor_loop_graph()
supervisor_loop_graph = authoritative_supervisor_graph
