"""Dependency-aware PostgreSQL task leasing for conversion workers."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, NotFoundException
from app.models.job import Job
from app.models.module import Module
from app.models.workflow import WorkflowGate
from app.models.base import utc_now


class DependencyScheduler:
    ACTIVE_STATUSES = ("LEASED", "RUNNING")

    async def claim_ready_modules(
        self,
        db: AsyncSession,
        job_id: UUID,
        *,
        worker_id: str,
        limit: int = 1,
        lease_seconds: int = 300,
        module_ids: list[UUID] | None = None,
        commit_lease: bool = True,
    ) -> list[Module]:
        job = await db.scalar(select(Job).where(Job.job_id == job_id).with_for_update())
        if not job:
            raise NotFoundException("Job", str(job_id))
        if job.status != "CONVERTING":
            raise ConflictException("CodeWriter scheduling is allowed only while the job is CONVERTING.")
        if Decimal(job.budget_used_usd) >= Decimal(job.budget_limit_usd):
            raise ConflictException(
                "Job budget exhausted; supervisor pause/escalation is required."
            )
        if not await self._required_gates_approved(db, job_id):
            raise ConflictException("CodeWriter cannot start before current G1, G2 and G3 approvals.")

        now = utc_now()
        active = list((await db.execute(
            select(Module).where(
                Module.job_id == job_id,
                Module.status.in_(self.ACTIVE_STATUSES),
                Module.lease_expires_at > now,
            )
        )).scalars().all())
        capacity = min(
            job.max_parallel_tasks,
            job.provider_concurrency_limit,
            job.sandbox_concurrency_limit,
        ) - len(active)
        if capacity <= 0:
            return []

        candidates = list((await db.execute(
            select(Module)
            .where(
                Module.job_id == job_id,
                Module.module_id.in_(module_ids) if module_ids is not None else True,
                or_(
                    Module.status == "PENDING",
                    (Module.status.in_(self.ACTIVE_STATUSES) & (Module.lease_expires_at <= now)),
                ),
            )
            .order_by(Module.wave_number.asc(), Module.created_at.asc())
            .with_for_update(skip_locked=True)
        )).scalars().all())
        completed_ids = set((await db.execute(
            select(Module.module_id).where(Module.job_id == job_id, Module.status.in_(("VERIFIED", "COMPLETED")))
        )).scalars().all())
        claimed: list[Module] = []
        for module in candidates:
            dependencies = {UUID(value) for value in (module.dependency_module_ids or [])}
            if not dependencies.issubset(completed_ids):
                continue
            if module.budget_limit_usd and Decimal(module.budget_used_usd) >= Decimal(module.budget_limit_usd):
                continue
            module.status = "LEASED"
            module.lease_owner = worker_id
            module.lease_expires_at = now + timedelta(seconds=lease_seconds)
            module.lease_heartbeat_at = now
            module.lease_generation += 1
            claimed.append(module)
            if len(claimed) >= min(limit, capacity):
                break
        if commit_lease:
            await db.commit()
        else:
            await db.flush()
        return claimed

    async def reconcile_stale_leases(self, db: AsyncSession, job_id: UUID) -> int:
        now = utc_now()
        stale = list((await db.execute(
            select(Module).where(
                Module.job_id == job_id,
                Module.status.in_(self.ACTIVE_STATUSES),
                Module.lease_expires_at <= now,
            ).with_for_update(skip_locked=True)
        )).scalars().all())
        for module in stale:
            from app.models.module import ModuleAttempt
            from app.models.agent import AgentRun
            attempts = (await db.execute(select(ModuleAttempt).where(ModuleAttempt.module_id == module.module_id, ModuleAttempt.status.in_(("RUNNING", "VERIFYING", "GENERATED"))))).scalars().all()
            for attempt in attempts:
                run = await db.get(AgentRun, attempt.agent_run_id)
                if run and run.task_payload.get("phase") == 6:
                    attempt.status = "BLOCKED"
                    attempt.failure_reason = "Worker lease expired; preserved interrupted evidence requires a new bounded attempt"
                    attempt.completed_at = now
                    run.status, run.completed_at = "FAILED", now
            module.status = "PENDING"
            module.lease_owner = None
            module.lease_expires_at = None
            module.lease_heartbeat_at = None
            module.lease_generation += 1
            module.retry_count += 1
        await db.commit()
        return len(stale)

    reclaim_expired_leases = reconcile_stale_leases

    async def renew_lease(
        self,
        db: AsyncSession,
        module_id: UUID,
        *,
        worker_id: str,
        lease_generation: int,
        lease_seconds: int = 300,
    ) -> bool:
        """Renew only the current fenced owner; stale workers cannot revive a lease."""
        now = utc_now()
        result = await db.execute(
            update(Module)
            .where(
                Module.module_id == module_id,
                Module.lease_owner == worker_id,
                Module.lease_generation == lease_generation,
                Module.status.in_(self.ACTIVE_STATUSES),
                Module.lease_expires_at > now,
            )
            .values(
                lease_heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        await db.commit()
        return result.rowcount == 1

    async def assert_current_lease(
        self,
        db: AsyncSession,
        module_id: UUID,
        *,
        worker_id: str,
        lease_generation: int,
    ) -> Module:
        module = await db.scalar(
            select(Module).where(
                Module.module_id == module_id,
                Module.lease_owner == worker_id,
                Module.lease_generation == lease_generation,
                Module.lease_expires_at > utc_now(),
            )
        )
        if module is None:
            raise ConflictException("Worker lease is stale; result commit is fenced")
        return module

    async def _required_gates_approved(self, db: AsyncSession, job_id: UUID) -> bool:
        for gate_type in ("G1", "G2", "G3"):
            latest = await db.scalar(
                select(WorkflowGate)
                .where(WorkflowGate.job_id == job_id, WorkflowGate.gate_type == gate_type)
                .order_by(WorkflowGate.version.desc())
                .limit(1)
            )
            if not latest or latest.status != "APPROVED":
                return False
        return True


dependency_scheduler = DependencyScheduler()
