"""Phase 2 agent-run launch, timeline, evidence and cancellation APIs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Tuple

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_job_access
from app.core.errors import ConflictException, ForbiddenException, NotFoundException, ValidationException
from app.models.agent import AgentRun
from app.models.job import Job
from app.models.user import User
from app.schemas.agent_runtime import (
    AgentRunListResponse, AgentRunStatus, AgentRunSummaryResponse, AgentTask,
    AgentTraceResponse, CancelAgentRunResponse, FailureClassification,
    LaunchAgentRunRequest, ToolCallSummaryItem,
)
from app.services.agent_run_service import AgentRunService

router = APIRouter(tags=["Agent Runs"])
service = AgentRunService()


def _iso(value) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else (str(value) if value is not None else None)


ROLE_DESCRIPTIONS: dict[str, str] = {
    "IntakeAgent": "Clones repository, extracts deterministic file tree, and AST scans technology profile.",
    "LegacyAnalyzer": "Decomposes legacy architectures, AST dependencies, domain packages, and risks.",
    "ArchitectAgent": "Synthesizes target clean architecture blueprints, domain boundaries, and interfaces.",
    "FeasibilityAgent": "Evaluates capability gaps, compatibility matrix, and migration viability score.",
    "CharacterizerAgent": "Generates frozen behavioral characterization suites and regression vectors.",
    "PlannerCoordinator": "Generates conversion tasks, dependency DAG, and 3-tier wave scheduling.",
    "SpecialistWorker": "Sandboxed autonomous conversion worker implementing module tasks.",
}


def _summary(row: AgentRun) -> AgentRunSummaryResponse:
    desc = (row.task_payload or {}).get("description") or ROLE_DESCRIPTIONS.get(row.agent_name, "Specialist modernization agent.")
    return AgentRunSummaryResponse(
        run_id=str(row.run_id), job_id=str(row.job_id), agent_name=row.agent_name,
        status=AgentRunStatus(row.status), model_identifier=f"{row.model_provider}/{row.model_identifier}",
        role_description=desc,
        input_tokens=row.input_tokens, output_tokens=row.output_tokens, cost_usd=float(row.cost_usd),
        started_at=_iso(row.started_at) or "", completed_at=_iso(row.completed_at),
        duration_seconds=float((row.trace_payload or {}).get("duration_seconds", 0)),
        failure_classification=FailureClassification(row.failure_classification) if row.failure_classification else None,
        error_message=row.error_message, evidence_artifact_ids=row.output_artifact_refs or [],
    )


@router.post("/jobs/{job_id}/agent-runs", response_model=AgentRunSummaryResponse, status_code=status.HTTP_201_CREATED)
async def launch_agent_run(
    payload: LaunchAgentRunRequest, request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> AgentRunSummaryResponse:
    job, user = access
    if user.role not in {"SUPER_ADMIN", "ADMIN"}:
        raise ForbiddenException("Only an administrator or orchestrator may launch agent runs.")
    try:
        tools = service.allowed_tools(payload.agent_name, payload.allowed_tools)
    except ValueError as exc:
        raise ValidationException(str(exc)) from exc
    if any(not service.runtime.tools.get_spec(name).is_read_only for name in tools):
        raise ForbiddenException("Manual agent runs are diagnostic-only and may use only read-only tools.")
    parameters = dict(payload.parameters or {})
    parameters.update({
        "execution_mode": "DIAGNOSTIC_NON_AUTHORITATIVE",
        "may_transition_workflow": False,
        "may_publish_workflow_artifacts": False,
    })
    task = AgentTask(
        job_id=str(job.job_id), agent_name=payload.agent_name, task_type=payload.task_type,
        instruction=(
            "DIAGNOSTIC ONLY: do not make workflow decisions, mutate source, or claim "
            "authoritative artifacts. " + payload.instruction
        ), parameters=parameters,
        input_artifacts=payload.input_artifacts, allowed_tools=tools,
        max_iterations=payload.max_iterations or 8, timeout_seconds=payload.timeout_seconds or 60,
        token_budget=payload.token_budget or 50_000, cost_budget_usd=payload.cost_budget_usd or 5,
        max_output_bytes=payload.max_output_bytes or 262_144, output_schema=payload.output_schema,
        model_provider=payload.model_provider, model_identifier=payload.model_identifier,
    )
    correlation_id = getattr(request.state, "correlation_id", f"corr_{uuid.uuid4().hex[:12]}")
    row = await service.execute(db, job, task, correlation_id, str(user.user_id))
    return _summary(row)


@router.get("/jobs/{job_id}/agent-runs", response_model=AgentRunListResponse)
async def list_agent_runs(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> AgentRunListResponse:
    job, _ = access
    rows, total = await service.list_for_job(db, job.job_id, offset=offset, limit=limit)
    return AgentRunListResponse(items=[_summary(row) for row in rows], total=total, offset=offset, limit=limit)


async def _authorized_run(run_id: str, user: User, db: AsyncSession) -> AgentRun:
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise NotFoundException("AgentRun", run_id)
    row = await service.get(db, run_uuid)
    if row is None:
        raise NotFoundException("AgentRun", run_id)
    # Reuse the same membership/IDOR rules through an explicit membership query for non-super-admin callers.
    if user.role != "SUPER_ADMIN":
        from app.models.job import JobMembership
        from sqlalchemy import select
        membership = (await db.execute(select(JobMembership).where(JobMembership.job_id == row.job_id, JobMembership.user_id == user.user_id))).scalar_one_or_none()
        if membership is None:
            raise NotFoundException("AgentRun", run_id)
    return row


@router.get("/agent-runs/{run_id}", response_model=AgentRunSummaryResponse)
async def get_agent_run(run_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> AgentRunSummaryResponse:
    return _summary(await _authorized_run(run_id, user, db))


@router.get("/agent-runs/{run_id}/trace", response_model=AgentTraceResponse)
async def get_agent_run_trace(run_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> AgentTraceResponse:
    row = await _authorized_run(run_id, user, db)
    trace = row.trace_payload or {}
    results = {item.get("call_id"): item for item in trace.get("tool_results", [])}
    calls = []
    for call in trace.get("tool_calls", []):
        result = results.get(call.get("call_id"), {})
        spec = service.runtime.tools.get_spec(call.get("tool_name"))
        calls.append(ToolCallSummaryItem(
            call_id=call.get("call_id", ""), tool_name=call.get("tool_name", ""), is_read_only=spec.is_read_only,
            ok=result.get("ok", False), duration_ms=result.get("duration_ms", 0), error=result.get("error"),
            arguments_summary=call.get("arguments", {}), output_summary=str(result.get("output"))[:500] if result.get("output") is not None else None,
            timestamp=call.get("timestamp", ""),
        ))
    return AgentTraceResponse(
        run_id=str(row.run_id), job_id=str(row.job_id), agent_name=row.agent_name,
        status=AgentRunStatus(row.status), model_identifier=f"{row.model_provider}/{row.model_identifier}",
        duration_seconds=float(trace.get("duration_seconds", 0)), total_tokens=row.input_tokens + row.output_tokens,
        cost_usd=float(row.cost_usd), started_at=_iso(row.started_at) or "", completed_at=_iso(row.completed_at),
        failure_classification=FailureClassification(row.failure_classification) if row.failure_classification else None,
        error_message=row.error_message, steps=trace.get("steps", []), tool_calls=calls,
        output_evidence=row.output_payload, evidence_artifacts=row.output_artifact_refs or [],
    )


@router.post("/agent-runs/{run_id}/cancel", response_model=CancelAgentRunResponse)
async def cancel_agent_run(run_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> CancelAgentRunResponse:
    if user.role not in {"SUPER_ADMIN", "ADMIN"}:
        raise ForbiddenException("Only an administrator or orchestrator may cancel agent runs.")
    row = await _authorized_run(run_id, user, db)
    if row.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        raise ConflictException(f"Run in terminal state '{row.status}' cannot be cancelled.")
    row.cancel_requested = True
    if row.status == "QUEUED":
        row.status = "CANCELLED"
        row.completed_at = datetime.now(timezone.utc)
        row.failure_classification = "CANCELLED"
    await db.commit()
    return CancelAgentRunResponse(run_id=str(row.run_id), status=AgentRunStatus(row.status), message="Cancellation requested", cancelled_at=datetime.now(timezone.utc).isoformat())
