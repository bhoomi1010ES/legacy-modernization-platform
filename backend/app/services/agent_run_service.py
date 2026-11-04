"""Persistence orchestration for shared agent runtime executions."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ROOT_DIR
from app.models.agent import AgentRun
from app.models.audit import AuditEvent
from app.models.budget import BudgetUsage
from app.models.job import Job
from app.schemas.agent_runtime import AgentContext, AgentResult, AgentRunStatus, AgentTask
from app.services.agent_runtime import AgentRuntime
from app.services.model_gateway import build_default_gateway
from app.services.secret_redactor import get_secret_redactor
from app.services.tool_registry import build_read_only_repository_registry


AGENT_TOOL_ALLOWLISTS: dict[str, set[str]] = {
    "Supervisor": set(),
    "Intake": {"repository_list", "file_read"},
    "Legacy Analyzer": {"repository_list", "file_read"},
    "Feasibility": set(),
    "Characterizer": {"repository_list", "file_read"},
    "Architect": {"repository_list", "file_read"},
    "Planner": set(),
    "Schema & Data": {"repository_list", "file_read"},
    "CodeWriter": {"repository_list", "file_read"},
    "Verifier": {"repository_list", "file_read"},
    "Reviewer": {"repository_list", "file_read"},
    "Integrator": {"repository_list", "file_read"},
}


class AgentRunService:
    def __init__(self, runtime: Optional[AgentRuntime] = None) -> None:
        self.redactor = get_secret_redactor()
        self.runtime = runtime or AgentRuntime(
            build_default_gateway(), build_read_only_repository_registry(Path(ROOT_DIR))
        )

    def allowed_tools(self, agent_name: str, requested: Optional[list[str]]) -> list[str]:
        configured = AGENT_TOOL_ALLOWLISTS.get(agent_name, set())
        if requested is None:
            return sorted(configured)
        unsupported = set(requested) - configured
        if unsupported:
            raise ValueError(f"Tools are not allowlisted for {agent_name}: {sorted(unsupported)}")
        return list(dict.fromkeys(requested))

    async def execute(self, db: AsyncSession, job: Job, task: AgentTask, correlation_id: str, actor_id: str) -> AgentRun:
        run_uuid = uuid.uuid4()
        context = AgentContext(
            job_id=str(job.job_id), run_id=str(run_uuid), agent_name=task.agent_name,
            correlation_id=correlation_id, workspace_path=str(ROOT_DIR),
            permissions=["repository:read"],
        )
        row = AgentRun(
            run_id=run_uuid, job_id=job.job_id, task_id=task.task_id,
            correlation_id=correlation_id, agent_name=task.agent_name,
            model_provider=task.model_provider, model_identifier=task.model_identifier,
            status=AgentRunStatus.RUNNING.value,
            task_payload=self.redactor.redact_object(task.model_dump(mode="json")),
            input_artifact_refs=task.input_artifacts,
        )
        db.add(row)
        db.add(AuditEvent(
            job_id=job.job_id, event_type="AGENT_RUN_STARTED", actor_type="USER", actor_id=actor_id,
            correlation_id=correlation_id, target_resource=str(run_uuid),
            payload={"agent_name": task.agent_name, "task_id": task.task_id},
        ))
        await db.commit()
        result = await self.runtime.run(task, context, cancel_requested=lambda: row.cancel_requested)
        row.status = result.status.value
        row.input_tokens = result.input_tokens
        row.output_tokens = result.output_tokens
        row.cost_usd = Decimal(str(result.cost_usd))
        row.reported_input_tokens = getattr(result, "reported_input_tokens", None) or result.input_tokens
        row.reported_output_tokens = getattr(result, "reported_output_tokens", None) or result.output_tokens
        row.provider_request_id = getattr(result, "provider_request_id", None) or getattr(result.trace, "provider_request_id", None)
        row.provider_model_id = getattr(result, "provider_model_id", None) or task.model_identifier
        row.pricing_table_version = getattr(result, "pricing_table_version", None)
        row.estimated_cost = Decimal(str(result.cost_usd)) if result.cost_usd is not None else None
        row.billed_cost = Decimal(str(result.billed_cost)) if getattr(result, "billed_cost", None) is not None else None
        row.error_message = result.error_message
        row.failure_classification = result.failure_classification.value if result.failure_classification else None
        row.trace_payload = result.trace.model_dump(mode="json")
        row.output_payload = result.output_data
        row.output_artifact_refs = result.output_artifacts
        row.completed_at = result.completed_at
        job.budget_used_usd += Decimal(str(result.cost_usd))
        db.add(BudgetUsage(
            job_id=job.job_id, run_id=run_uuid, cost_type="LLM_INFERENCE",
            amount_usd=Decimal(str(result.cost_usd)), tokens=result.input_tokens + result.output_tokens,
        ))
        db.add(AuditEvent(
            job_id=job.job_id, event_type="AGENT_RUN_COMPLETED", actor_type="AGENT", actor_id=task.agent_name,
            correlation_id=correlation_id, target_resource=str(run_uuid),
            payload=self.redactor.redact_object({"status": result.status.value, "failure_classification": row.failure_classification, "usage": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "cost_usd": result.cost_usd}}),
        ))
        await db.commit()
        await db.refresh(row)
        return row

    async def list_for_job(self, db: AsyncSession, job_id: uuid.UUID, *, offset: int, limit: int) -> tuple[list[AgentRun], int]:
        total = (await db.execute(select(func.count(AgentRun.run_id)).where(AgentRun.job_id == job_id))).scalar() or 0
        rows = (await db.execute(
            select(AgentRun).where(AgentRun.job_id == job_id).order_by(AgentRun.started_at.desc()).offset(offset).limit(limit)
        )).scalars().all()
        return list(rows), total

    async def get(self, db: AsyncSession, run_id: uuid.UUID) -> Optional[AgentRun]:
        return (await db.execute(select(AgentRun).where(AgentRun.run_id == run_id))).scalar_one_or_none()
