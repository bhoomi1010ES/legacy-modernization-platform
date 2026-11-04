import uuid
import hashlib
import json
"""Dependency-aware PostgreSQL task leasing for conversion workers."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, NotFoundException
from app.models.job import Job
from app.models.module import Module
from app.models.workflow import WorkflowGate, WorkflowOutbox
from app.models.base import utc_now
from app.models.phase4 import ConversionPlanModel
from app.models.artifact import Artifact


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
        job = await db.scalar(select(Job).where(Job.job_id == job_id))
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
            select(Module.module_id).where(Module.job_id == job_id, Module.status == "VERIFIED")
        )).scalars().all())
        claimed: list[Module] = []
        from app.models.module import ModuleDependency
        latest_plan = await db.scalar(
            select(ConversionPlanModel)
            .where(ConversionPlanModel.job_id == job_id)
            .order_by(ConversionPlanModel.version.desc())
            .limit(1)
        )
        latest_g3 = await db.scalar(
            select(WorkflowGate)
            .where(WorkflowGate.job_id == job_id, WorkflowGate.gate_type == "G3")
            .order_by(WorkflowGate.version.desc())
            .limit(1)
        )
        for module in candidates:
            # The JSON and normalized DAG are both persisted representations. A
            # mismatch is corrupt plan state and must fail closed, never degrade
            # to whichever representation happens to have fewer dependencies.
            expected_parent_ids = set()
            try:
                expected_parent_ids = {UUID(value) for value in (module.dependency_module_ids or [])}
            except (ValueError, TypeError, AttributeError) as exc:
                raise ConflictException(f"Module {module.name} has an invalid materialized dependency id") from exc
            parent_ids = set((await db.execute(
                select(ModuleDependency.parent_id).where(
                    ModuleDependency.job_id == job_id,
                    ModuleDependency.child_id == module.module_id,
                )
            )).scalars().all())
            if parent_ids != expected_parent_ids:
                raise ConflictException(f"Module {module.name} dependency representations disagree; scheduling is blocked")
            if expected_parent_ids:
                valid_parent_ids = set((await db.execute(
                    select(Module.module_id).where(
                        Module.job_id == job_id,
                        Module.module_id.in_(expected_parent_ids),
                    )
                )).scalars().all())
                if valid_parent_ids != expected_parent_ids:
                    raise ConflictException(f"Module {module.name} has a dangling or cross-job dependency")

            if module.plan_hash:
                if not latest_plan:
                    raise ConflictException("Module contract is not bound to the current conversion plan snapshot")
                plan_artifact = await db.scalar(
                    select(Artifact).where(
                        Artifact.job_id == job_id,
                        Artifact.artifact_type == "CONVERSION_PLAN",
                        Artifact.version == latest_plan.version,
                    ).limit(1)
                )
                approved_hashes = (latest_g3.artifact_hashes or {}) if latest_g3 else {}
                if not plan_artifact or module.plan_hash != plan_artifact.content_hash:
                    raise ConflictException("Module contract does not match the current plan artifact content hash")
                if approved_hashes.get(str(plan_artifact.artifact_id)) != plan_artifact.content_hash:
                    raise ConflictException("G3 has not approved this exact conversion plan hash")
                if not module.upstream_approval_hashes:
                    raise ConflictException("Module is missing its upstream approval hash snapshot")
                current_approval_hashes = {}
                for gate_type in ("G1", "G2"):
                    gate = await db.scalar(
                        select(WorkflowGate).where(
                            WorkflowGate.job_id == job_id,
                            WorkflowGate.gate_type == gate_type,
                            WorkflowGate.status == "APPROVED",
                        ).order_by(WorkflowGate.version.desc()).limit(1)
                    )
                    if gate is None:
                        raise ConflictException(f"Module approval snapshot is missing {gate_type}")
                    encoded = json.dumps(
                        {"gate_id": str(gate.gate_id), "version": gate.version,
                         "artifact_hashes": gate.artifact_hashes or {}},
                        sort_keys=True, separators=(",", ":"),
                    )
                    current_approval_hashes[f"{gate_type.lower()}_approval_hash"] = hashlib.sha256(encoded.encode()).hexdigest()
                if current_approval_hashes != module.upstream_approval_hashes:
                    raise ConflictException("Module upstream approval hashes are stale; replanning is required")
            if not parent_ids.issubset(completed_ids):
                continue
            if module.budget_limit_usd and Decimal(module.budget_used_usd) >= Decimal(module.budget_limit_usd):
                continue
            module.status = "LEASED"
            module.lease_owner = worker_id
            module.lease_expires_at = now + timedelta(seconds=lease_seconds)
            module.lease_heartbeat_at = now
            module.lease_generation += 1
            module.lease_token = str(uuid.uuid4())
            db.add(WorkflowOutbox(
                job_id=job.job_id,
                idempotency_key=f"task-leased-{module.module_id}-{module.lease_generation}",
                event_type="TASK_LEASED",
                payload={
                    "job_id": str(job.job_id),
                    "module_id": str(module.module_id),
                    "module_name": module.name,
                    "worker_id": worker_id,
                    "lease_generation": module.lease_generation,
                    "lease_token": module.lease_token,
                    "lease_expires_at": module.lease_expires_at.isoformat(),
                },
                status="PENDING",
            ))
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
            from app.models.module import VerificationRun
            from app.services.phase5_engine import digest
            attempts = (await db.execute(select(ModuleAttempt).where(ModuleAttempt.module_id == module.module_id, ModuleAttempt.status.in_(("RUNNING", "VERIFYING", "GENERATED"))))).scalars().all()
            for attempt in attempts:
                run = await db.get(AgentRun, attempt.agent_run_id)
                if run and run.task_payload.get("phase") == 6:
                    attempt.status = "BLOCKED"
                    attempt.failure_reason = "Worker lease expired; preserved interrupted evidence requires a new bounded attempt"
                    attempt.completed_at = now
                    run.status, run.completed_at = "FAILED", now
                    # The controller may have finished while the API was
                    # unavailable. Keep its immutable inputs, but block the
                    # unfinalized result instead of silently leaving Verifier
                    # work QUEUED/RUNNING or reusing it for a later attempt.
                    records = (await db.execute(select(VerificationRun).where(
                        VerificationRun.attempt_id == attempt.attempt_id,
                        VerificationRun.status.in_(("QUEUED", "RUNNING")),
                    ).with_for_update())).scalars().all()
                    for record in records:
                        record.status = "BLOCKED"
                        record.finished_at = now
                        record.evidence = {
                            "status": "BLOCKED",
                            "reason": "API worker lease expired before verifier response was finalized; a new independent VerificationRun is required",
                            "candidate_hash": record.candidate_hash,
                            "suite_hash": record.suite_hash,
                            "profile_digest": record.profile_digest,
                            "input_hash": record.input_hash,
                        }
                        record.evidence_hash = digest(record.evidence)
                        verifier = await db.get(AgentRun, record.agent_run_id)
                        if verifier and verifier.status in {"QUEUED", "RUNNING"}:
                            verifier.status = "FAILED"
                            verifier.error_message = "API worker lease expired before verification finalization"
                            verifier.completed_at = now
                            verifier.trace_payload = {
                                **(verifier.trace_payload or {}),
                                "events": [*(verifier.trace_payload or {}).get("events", []), "RECOVERY_BLOCKED"],
                            }
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
