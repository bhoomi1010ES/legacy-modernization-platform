"""Authoritative Budget & Resource Governance Manager for the Supervisor."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.base import utc_now
from app.models.budget import BudgetUsage
from app.models.job import Job
from app.models.module import Module

logger = logging.getLogger(__name__)


class BudgetEvaluationResult(BaseModel):
    is_exceeded: bool
    exceeded_dimension: Optional[str] = None  # PROJECT_USD, TOKEN, TIME, CONCURRENCY, AGENT, TASK
    blocking_reason: Optional[str] = None
    state: Dict[str, Any] = Field(default_factory=dict)


class BudgetManager:
    """Evaluates multi-dimensional financial, token, time, and concurrency quotas."""

    def __init__(self):
        self.default_token_limit: int = 5_000_000
        self.default_time_limit_seconds: int = 86_400  # 24 hours
        self.default_agent_cost_limit: float = 10_000.0
        self.default_task_cost_limit: float = 2_500.0

    async def evaluate_budget(
        self,
        db: AsyncSession,
        job: Job,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        estimated_cost: Optional[float] = None,
    ) -> BudgetEvaluationResult:
        """Evaluates whether any resource quota or spend cap is exhausted."""
        job_uuid = job.job_id
        used_usd = float(job.budget_used_usd)
        limit_usd = float(job.budget_limit_usd)

        # 1. Project USD Budget Cap
        if Decimal(job.budget_used_usd) >= Decimal(job.budget_limit_usd):
            return BudgetEvaluationResult(
                is_exceeded=True,
                exceeded_dimension="PROJECT_USD",
                blocking_reason=f"Project budget exhausted: ${used_usd:.2f} used >= limit ${limit_usd:.2f}.",
                state={"used_usd": used_usd, "limit_usd": limit_usd},
            )

        # 2. Cumulative Token Spend Limit
        total_tokens = await db.scalar(
            select(func.coalesce(func.sum(BudgetUsage.tokens), 0)).where(
                BudgetUsage.job_id == job_uuid
            )
        ) or 0
        meta = getattr(job, "stack_metadata", None) or {}
        token_limit = int(meta.get("token_limit", self.default_token_limit))
        if total_tokens >= token_limit:
            return BudgetEvaluationResult(
                is_exceeded=True,
                exceeded_dimension="TOKEN",
                blocking_reason=f"Cumulative token budget exhausted: {total_tokens:,} tokens >= limit {token_limit:,}.",
                state={"used_tokens": total_tokens, "limit_tokens": token_limit, "used_usd": used_usd, "limit_usd": limit_usd},
            )

        # 3. Execution Time Limit
        now = utc_now()
        created_at = getattr(job, "created_at", None) or now
        # SQLite replay databases return naive UTC timestamps even for timezone=True columns.
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=now.tzinfo)
        elapsed_seconds = (now - created_at).total_seconds()
        time_limit_seconds = float(meta.get("time_limit_seconds", self.default_time_limit_seconds))
        if elapsed_seconds >= time_limit_seconds:
            return BudgetEvaluationResult(
                is_exceeded=True,
                exceeded_dimension="TIME",
                blocking_reason=f"Project execution time exceeded: {elapsed_seconds:.0f}s >= limit {time_limit_seconds:.0f}s.",
                state={"elapsed_seconds": elapsed_seconds, "time_limit_seconds": time_limit_seconds, "used_usd": used_usd},
            )

        # 4. Concurrency Limit
        active_modules_count = await db.scalar(
            select(func.count(Module.module_id)).where(
                Module.job_id == job_uuid,
                Module.status.in_(("LEASED", "RUNNING")),
                Module.lease_expires_at > now,
            )
        ) or 0
        max_concurrency = job.max_parallel_tasks or 4
        if active_modules_count >= max_concurrency:
            return BudgetEvaluationResult(
                is_exceeded=True,
                exceeded_dimension="CONCURRENCY",
                blocking_reason=f"Active worker concurrency limit reached: {active_modules_count} active >= max {max_concurrency}.",
                state={"active_concurrency": active_modules_count, "max_concurrency": max_concurrency},
            )

        # 5. Per-Agent Budget Cap
        if agent_id:
            agent_cost = await db.scalar(
                select(func.coalesce(func.sum(AgentRun.cost_usd), Decimal("0"))).where(
                    AgentRun.job_id == job_uuid,
                    AgentRun.agent_name == agent_id,
                )
            ) or Decimal("0")
            agent_cost_float = float(agent_cost)
            agent_limit = float(
                meta.get(f"{agent_id}_budget_usd", self.default_agent_cost_limit)
            )
            if agent_cost_float >= agent_limit:
                return BudgetEvaluationResult(
                    is_exceeded=True,
                    exceeded_dimension="AGENT",
                    blocking_reason=f"Agent '{agent_id}' budget cap exceeded: ${agent_cost_float:.2f} >= cap ${agent_limit:.2f}.",
                    state={"agent_id": agent_id, "agent_cost": agent_cost_float, "agent_limit": agent_limit},
                )

        # 6. Per-Task Budget Cap
        if task_id:
            task_cost = await db.scalar(
                select(func.coalesce(func.sum(AgentRun.cost_usd), Decimal("0"))).where(
                    AgentRun.job_id == job_uuid,
                    AgentRun.task_id == task_id,
                )
            ) or Decimal("0")
            task_cost_float = float(task_cost)
            task_limit = float(
                meta.get(f"{task_id}_budget_usd", self.default_task_cost_limit)
            )
            if task_cost_float >= task_limit:
                return BudgetEvaluationResult(
                    is_exceeded=True,
                    exceeded_dimension="TASK",
                    blocking_reason=f"Task '{task_id}' budget cap exceeded: ${task_cost_float:.2f} >= cap ${task_limit:.2f}.",
                    state={"task_id": task_id, "task_cost": task_cost_float, "task_limit": task_limit},
                )

        return BudgetEvaluationResult(
            is_exceeded=False,
            state={
                "used_usd": used_usd,
                "limit_usd": limit_usd,
                "used_tokens": total_tokens,
                "token_limit": token_limit,
                "elapsed_seconds": elapsed_seconds,
                "time_limit_seconds": time_limit_seconds,
                "active_concurrency": active_modules_count,
                "max_concurrency": max_concurrency,
            },
        )


budget_manager = BudgetManager()
