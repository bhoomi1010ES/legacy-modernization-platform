"""Specialist agents and execution traces router with PostgreSQL persistence."""

from typing import Tuple
import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_job_access
from app.core.errors import NotFoundException
from app.models.agent import AgentRun
from app.models.job import Job
from app.models.user import User
from app.schemas.agents import (
    AgentRunDetailResponse,
    AgentRunListResponse,
    AgentRunResponse,
)

router = APIRouter(prefix="/jobs/{job_id}/agents", tags=["Agents"])

AGENT_META = {
    "Supervisor": ("Routes work, enforces budgets, and coordinates human approval gates.", "Workflow router · Checkpoint store"),
    "Intake": ("Clones repositories and detects languages, entry points, and build systems.", "Git · cloc · secret_scan"),
    "Legacy Analyzer": ("Maps dependencies, integrations, schemas, and business capabilities.", "tree-sitter · SQL parser"),
    "Architect": ("Generates modular TargetBlueprint and conversion wave DAG.", "Blueprint synthesizer · ADR validator"),
    "CodeWriter": ("Converts isolated modules on individual Git branches in rootless sandboxes.", "Docker / gVisor sandbox · compiler"),
    "Verifier": ("Replays frozen tests and classifies behavioral differences.", "Test runner · diff_classifier"),
}


def _agent_to_response(run: AgentRun) -> AgentRunResponse:
    meta = AGENT_META.get(run.agent_name, ("Specialist modernization agent.", "Standard sandbox tooling"))
    return AgentRunResponse(
        run_id=str(run.run_id),
        job_id=str(run.job_id),
        agent_name=run.agent_name,
        status=run.status,
        role_description=meta[0],
        tooling=meta[1],
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        cost_usd=float(run.cost_usd),
        started_at=run.started_at.isoformat() if hasattr(run.started_at, "isoformat") else str(run.started_at),
        completed_at=run.completed_at.isoformat() if run.completed_at and hasattr(run.completed_at, "isoformat") else (str(run.completed_at) if run.completed_at else None),
    )


@router.get(
    "",
    response_model=AgentRunListResponse,
    status_code=status.HTTP_200_OK,
    summary="List specialist agents and execution runs for a job",
    operation_id="agents_list",
)
async def list_agents(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> AgentRunListResponse:
    job, user = access
    stmt = (
        select(AgentRun)
        .where(AgentRun.job_id == job.job_id)
        .order_by(AgentRun.started_at.asc())
    )
    res = await db.execute(stmt)
    runs = list(res.scalars().all())
    items = [_agent_to_response(r) for r in runs]
    return AgentRunListResponse(items=items, total=len(items))


@router.get(
    "/{run_id}",
    response_model=AgentRunDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve detailed agent execution trace and token metrics",
    operation_id="agents_get_trace",
)
async def get_agent_trace(
    job_id: str,
    run_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> AgentRunDetailResponse:
    job, user = access
    try:
        r_uuid = uuid.UUID(run_id)
    except ValueError:
        raise NotFoundException("AgentRun", run_id)

    stmt = select(AgentRun).where(AgentRun.job_id == job.job_id, AgentRun.run_id == r_uuid)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if not run:
        raise NotFoundException("AgentRun", run_id)

    base = _agent_to_response(run)
    return AgentRunDetailResponse(
        **base.model_dump(),
        model=run.model_identifier,
        prompt_version="v1.0.0",
        execution_trace=[
            f"Run initialized at {base.started_at}",
            f"Tokens consumed: {base.input_tokens} in / {base.output_tokens} out",
            f"Execution status: {base.status}",
        ],
    )
