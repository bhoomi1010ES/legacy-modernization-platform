"""Durable Worker Dispatch, Leasing, Fencing and Recovery Service (W05).

Implements the Claim -> Run -> Persist -> Acknowledge protocol with:
- Monotonic lease generation fencing (prevents stale commits after lease expiry)
- Cryptographic lease token validation
- Outbox event persistence for TASK_LEASED and TASK_COMPLETED
- Parallel task fan-out respecting dependency DAG, gates, and budget limits
- Worker registry lifecycle and heartbeating
- Automatic crash / expired lease reclamation with generation bumping
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, NotFoundException
from app.models.agent import AgentRun
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.base import utc_now
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.worker import WorkerRegistry
from app.models.workflow import WorkflowGate, WorkflowOutbox

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerDispatchService:
    ACTIVE_STATUSES = ("LEASED", "RUNNING")

    # =========================================================================
    # 1. Worker Registry Lifecycle
    # =========================================================================

    async def register_worker(
        self,
        db: AsyncSession,
        worker_id: str,
        worker_type: str,
        version: str = "1.0.0",
        metadata_payload: Optional[Dict[str, Any]] = None,
    ) -> WorkerRegistry:
        """Register or update an active worker in the persistent worker registry."""
        worker = await db.get(WorkerRegistry, worker_id)
        now = _now()
        if worker is None:
            worker = WorkerRegistry(
                worker_id=worker_id,
                worker_type=worker_type,
                version=version,
                status="ACTIVE",
                started_at=now,
                last_heartbeat=now,
                metadata_payload=metadata_payload or {},
            )
            db.add(worker)
        else:
            worker.worker_type = worker_type
            worker.version = version
            worker.status = "ACTIVE"
            worker.last_heartbeat = now
            if metadata_payload:
                worker.metadata_payload = {
                    **(worker.metadata_payload or {}),
                    **metadata_payload,
                }
        await db.commit()
        await db.refresh(worker)
        return worker

    async def heartbeat_worker(
        self,
        db: AsyncSession,
        worker_id: str,
    ) -> bool:
        """Update last heartbeat timestamp for a registered worker."""
        res = await db.execute(
            update(WorkerRegistry)
            .where(WorkerRegistry.worker_id == worker_id, WorkerRegistry.status == "ACTIVE")
            .values(last_heartbeat=_now())
        )
        await db.commit()
        return res.rowcount == 1

    async def deregister_worker(
        self,
        db: AsyncSession,
        worker_id: str,
        status: str = "STOPPED",
    ) -> bool:
        """Mark a worker as STOPPED or DRAINING."""
        res = await db.execute(
            update(WorkerRegistry)
            .where(WorkerRegistry.worker_id == worker_id)
            .values(status=status, last_heartbeat=_now())
        )
        await db.commit()
        return res.rowcount == 1

    async def get_active_workers(
        self,
        db: AsyncSession,
        heartbeat_timeout_seconds: int = 120,
    ) -> List[WorkerRegistry]:
        """List active registered workers whose heartbeats are fresh."""
        cutoff = _now() - timedelta(seconds=heartbeat_timeout_seconds)
        stmt = (
            select(WorkerRegistry)
            .where(
                WorkerRegistry.status == "ACTIVE",
                WorkerRegistry.last_heartbeat >= cutoff,
            )
            .order_by(WorkerRegistry.started_at.asc())
        )
        return list((await db.execute(stmt)).scalars().all())

    # =========================================================================
    # 2. Claim Ready Modules (Protocol Step 1)
    # =========================================================================

    async def claim_ready_tasks(
        self,
        db: AsyncSession,
        job_id: UUID,
        *,
        worker_id: str,
        limit: int = 1,
        lease_seconds: int = 300,
        module_ids: Optional[List[UUID]] = None,
        expected_input_hashes: Optional[Dict[str, str]] = None,
        commit: bool = True,
    ) -> List[Dict[str, Any]]:
        """In a short DB transaction, lock eligible modules with SKIP LOCKED,
        increment lease_generation, assign lease_token and lease_owner,
        create ModuleAttempt, and persist TASK_LEASED outbox event.
        """
        now = _now()
        job = await db.scalar(select(Job).where(Job.job_id == job_id).with_for_update())
        if not job:
            raise NotFoundException("Job", str(job_id))
        if job.status not in ("CONVERTING", "RUNNING"):
            raise ConflictException(
                f"Task dispatch is allowed only while job is CONVERTING or RUNNING (current: {job.status})."
            )
        if Decimal(job.budget_used_usd) >= Decimal(job.budget_limit_usd):
            raise ConflictException("Job budget exhausted; supervisor pause or escalation required.")

        # Ensure G1-G3 gate approvals
        if not await self._required_gates_approved(db, job_id):
            raise ConflictException("Workers cannot claim conversion tasks before G1, G2, and G3 gates are approved.")

        # Concurrency capacity check
        active_count = await db.scalar(
            select(func.count(Module.module_id)).where(
                Module.job_id == job_id,
                Module.status.in_(self.ACTIVE_STATUSES),
                Module.lease_expires_at > now,
            )
        ) or 0

        max_allowed = min(
            getattr(job, "max_parallel_tasks", 4) or 4,
            getattr(job, "provider_concurrency_limit", 4) or 4,
            getattr(job, "sandbox_concurrency_limit", 4) or 4,
        )
        capacity = max_allowed - active_count
        if capacity <= 0:
            return []

        # Find candidate pending modules
        stmt = (
            select(Module)
            .where(
                Module.job_id == job_id,
                Module.module_id.in_(module_ids) if module_ids is not None else True,
                or_(
                    Module.status == "PENDING",
                    and_(Module.status.in_(self.ACTIVE_STATUSES), Module.lease_expires_at <= now),
                ),
            )
            .order_by(Module.wave_number.asc(), Module.created_at.asc())
            .with_for_update(skip_locked=True)
        )
        candidates = list((await db.execute(stmt)).scalars().all())
        if not candidates:
            return []

        # Completed / Verified module IDs for dependency DAG check
        completed_ids = set(
            (
                await db.execute(
                    select(Module.module_id).where(
                        Module.job_id == job_id,
                        Module.status.in_(("VERIFIED", "COMPLETED")),
                    )
                )
            ).scalars().all()
        )

        claimed_tasks: List[Dict[str, Any]] = []
        max_to_claim = min(limit, capacity)

        for module in candidates:
            # Check DAG dependencies
            dependencies = {UUID(val) for val in (module.dependency_module_ids or [])}
            if not dependencies.issubset(completed_ids):
                continue

            # Check module budget
            if module.budget_limit_usd and Decimal(module.budget_used_usd) >= Decimal(module.budget_limit_usd):
                continue

            # Increment monotonic lease generation and issue unique lease token
            module.lease_generation += 1
            lease_token = str(uuid.uuid4())
            expires_at = now + timedelta(seconds=lease_seconds)

            module.status = "RUNNING"
            module.lease_owner = worker_id
            module.lease_token = lease_token
            module.lease_expires_at = expires_at
            module.lease_heartbeat_at = now

            # Record expected input hash if provided
            input_hash = None
            if expected_input_hashes:
                input_hash = expected_input_hashes.get(str(module.module_id))
                module.expected_input_hash = input_hash

            # Allocate next attempt number
            max_attempt = await db.scalar(
                select(func.max(ModuleAttempt.attempt_number)).where(
                    ModuleAttempt.module_id == module.module_id
                )
            )
            next_attempt_num = (max_attempt or 0) + 1

            attempt = ModuleAttempt(
                module_id=module.module_id,
                attempt_number=next_attempt_num,
                status="RUNNING",
                worker_id=worker_id,
                git_branch=f"rebase/wave{module.wave_number}-{module.name}-att{next_attempt_num}",
                started_at=now,
                lease_generation=module.lease_generation,
                lease_token=lease_token,
            )
            db.add(attempt)
            await db.flush()

            # Persist TASK_LEASED outbox event in the SAME transaction
            outbox_event = WorkflowOutbox(
                job_id=job.job_id,
                idempotency_key=f"task-leased-{attempt.attempt_id}-{module.lease_generation}",
                event_type="TASK_LEASED",
                payload={
                    "job_id": str(job.job_id),
                    "module_id": str(module.module_id),
                    "module_name": module.name,
                    "attempt_id": str(attempt.attempt_id),
                    "attempt_number": attempt.attempt_number,
                    "worker_id": worker_id,
                    "lease_generation": module.lease_generation,
                    "lease_token": lease_token,
                    "lease_expires_at": expires_at.isoformat(),
                    "expected_input_hash": input_hash,
                },
                status="PENDING",
            )
            db.add(outbox_event)

            # Record audit event
            db.add(
                AuditEvent(
                    job_id=job.job_id,
                    event_type="TASK_LEASED",
                    actor_type="SYSTEM",
                    actor_id=worker_id,
                    target_resource=str(attempt.attempt_id),
                    payload={
                        "module_id": str(module.module_id),
                        "attempt_number": attempt.attempt_number,
                        "lease_generation": module.lease_generation,
                        "lease_expires_at": expires_at.isoformat(),
                    },
                )
            )

            claimed_tasks.append(
                {
                    "module_id": module.module_id,
                    "module_name": module.name,
                    "attempt_id": attempt.attempt_id,
                    "attempt_number": attempt.attempt_number,
                    "git_branch": attempt.git_branch,
                    "worker_id": worker_id,
                    "lease_generation": module.lease_generation,
                    "lease_token": lease_token,
                    "lease_expires_at": expires_at,
                    "expected_input_hash": input_hash,
                }
            )

            if len(claimed_tasks) >= max_to_claim:
                break

        if commit:
            await db.commit()
        else:
            await db.flush()

        return claimed_tasks

    # =========================================================================
    # 3. Lease Heartbeat & Renewal (Protocol Step 2)
    # =========================================================================

    async def renew_lease(
        self,
        db: AsyncSession,
        module_id: UUID,
        *,
        worker_id: str,
        lease_token: str,
        lease_generation: int,
        lease_seconds: int = 300,
    ) -> bool:
        """Renew active lease only if worker_id, lease_token, and lease_generation match
        and lease has not already expired.
        """
        now = _now()
        stmt = (
            update(Module)
            .where(
                Module.module_id == module_id,
                Module.lease_owner == worker_id,
                Module.lease_generation == lease_generation,
                Module.status.in_(self.ACTIVE_STATUSES),
                Module.lease_expires_at > now,
                or_(Module.lease_token == lease_token, Module.lease_token.is_(None)),
            )
            .values(
                lease_heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        res = await db.execute(stmt)
        await db.commit()
        return res.rowcount == 1

    # =========================================================================
    # 4. Compare-and-Set Fencing Result Commit (Protocol Steps 4, 5, 6)
    # =========================================================================

    async def commit_stage_result(
        self,
        db: AsyncSession,
        *,
        job_id: UUID,
        module_id: UUID,
        attempt_id: UUID,
        worker_id: str,
        lease_token: str,
        lease_generation: int,
        result_status: str,  # VERIFIED, FAILED, ESCALATED
        result_hash: str,
        expected_input_hash: Optional[str] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        failure_reason: Optional[str] = None,
        agent_run_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Atomically commit worker results using Compare-and-Set SQL fencing.
        Rejects commits from stale workers whose leases expired or whose generation was bumped.
        """
        now = _now()

        # Check job active state
        job = await db.get(Job, job_id)
        if not job:
            raise NotFoundException("Job", str(job_id))
        if job.status in ("CANCELLED", "FAILED"):
            raise ConflictException(
                f"Cannot commit result on terminal job (status: {job.status}). Worker work is quarantined."
            )

        # Atomic Compare-and-Set Update
        # Must match: module_id, status=RUNNING, lease_owner, lease_generation, lease not expired
        cas_stmt = (
            update(Module)
            .where(
                Module.module_id == module_id,
                Module.status.in_(self.ACTIVE_STATUSES),
                Module.lease_owner == worker_id,
                Module.lease_generation == lease_generation,
                Module.lease_expires_at > now,
                or_(Module.lease_token == lease_token, Module.lease_token.is_(None)),
                Module.expected_input_hash == expected_input_hash
                if expected_input_hash is not None
                else True,
            )
            .values(
                status=result_status,
                accepted_result_hash=result_hash,
                lease_owner=None,
                lease_expires_at=None,
                lease_heartbeat_at=None,
                lease_token=None,
                updated_at=now,
            )
        )
        res = await db.execute(cas_stmt)
        if res.rowcount == 0:
            # FENCE TRIP: The worker lease expired, was stolen, or input hash diverged!
            logger.warning(
                "CAS FENCE TRIP: Worker commit rejected for module %s | worker=%s | gen=%s",
                module_id,
                worker_id,
                lease_generation,
            )
            raise ConflictException(
                f"Worker lease for module {module_id} is stale or expired; result commit fenced (gen={lease_generation})."
            )

        # Update the ModuleAttempt record
        attempt = await db.get(ModuleAttempt, attempt_id)
        if attempt:
            attempt.status = result_status
            attempt.failure_reason = failure_reason
            attempt.completed_at = now
            if agent_run_id:
                attempt.agent_run_id = agent_run_id

        # Update AgentRun if provided
        if agent_run_id:
            agent_run = await db.get(AgentRun, agent_run_id)
            if agent_run:
                agent_run.status = "SUCCEEDED" if result_status == "VERIFIED" else "FAILED"
                agent_run.completed_at = now
                if failure_reason:
                    agent_run.error_message = failure_reason

        # Persist TASK_COMPLETED outbox event
        outbox_event = WorkflowOutbox(
            job_id=job_id,
            idempotency_key=f"task-completed-{attempt_id}-{result_hash[:16]}",
            event_type="TASK_COMPLETED",
            payload={
                "job_id": str(job_id),
                "module_id": str(module_id),
                "attempt_id": str(attempt_id),
                "worker_id": worker_id,
                "result_status": result_status,
                "result_hash": result_hash,
                "completed_at": now.isoformat(),
                "artifact_count": len(artifacts or []),
            },
            status="PENDING",
        )
        db.add(outbox_event)

        # Record AuditEvent
        db.add(
            AuditEvent(
                job_id=job_id,
                event_type=f"MODULE_{result_status}",
                actor_type="SYSTEM",
                actor_id=worker_id,
                target_resource=str(attempt_id),
                payload={
                    "module_id": str(module_id),
                    "status": result_status,
                    "result_hash": result_hash,
                    "lease_generation": lease_generation,
                },
            )
        )

        await db.commit()
        return {
            "status": "COMMITTED",
            "module_id": str(module_id),
            "attempt_id": str(attempt_id),
            "result_status": result_status,
            "result_hash": result_hash,
            "lease_generation": lease_generation,
        }

    # =========================================================================
    # 5. Crash & Expired Lease Recovery (Protocol Step 8)
    # =========================================================================

    async def reclaim_expired_leases(
        self,
        db: AsyncSession,
        job_id: Optional[UUID] = None,
    ) -> int:
        """Scan for expired active leases, block interrupted attempts,
        and reclaim modules with a new monotonic generation.
        """
        now = _now()
        stmt = (
            select(Module)
            .where(
                Module.job_id == job_id if job_id is not None else True,
                Module.status.in_(self.ACTIVE_STATUSES),
                Module.lease_expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        stale_modules = list((await db.execute(stmt)).scalars().all())
        if not stale_modules:
            return 0

        reclaimed_count = 0
        for module in stale_modules:
            old_gen = module.lease_generation
            module.lease_generation += 1  # Increment monotonic generation
            module.status = "PENDING"
            module.lease_owner = None
            module.lease_expires_at = None
            module.lease_heartbeat_at = None
            module.lease_token = None
            module.retry_count += 1

            # Mark interrupted attempts as BLOCKED
            attempts = list(
                (
                    await db.execute(
                        select(ModuleAttempt).where(
                            ModuleAttempt.module_id == module.module_id,
                            ModuleAttempt.status == "RUNNING",
                        )
                    )
                ).scalars().all()
            )
            for att in attempts:
                att.status = "BLOCKED"
                att.failure_reason = (
                    f"Worker lease expired at {now.isoformat()}; reclaimed with new generation {module.lease_generation}"
                )
                att.completed_at = now

            # Audit event
            db.add(
                AuditEvent(
                    job_id=module.job_id,
                    event_type="LEASE_EXPIRED_RECLAIMED",
                    actor_type="SYSTEM",
                    actor_id="SupervisorRecovery",
                    target_resource=str(module.module_id),
                    payload={
                        "module_id": str(module.module_id),
                        "old_generation": old_gen,
                        "new_generation": module.lease_generation,
                        "retry_count": module.retry_count,
                    },
                )
            )

            # Outbox event
            db.add(
                WorkflowOutbox(
                    job_id=module.job_id,
                    idempotency_key=f"lease-reclaimed-{module.module_id}-{module.lease_generation}",
                    event_type="TASK_RECLAIMED",
                    payload={
                        "job_id": str(module.job_id),
                        "module_id": str(module.module_id),
                        "new_generation": module.lease_generation,
                    },
                    status="PENDING",
                )
            )
            reclaimed_count += 1

        await db.commit()
        logger.info("Reclaimed %d expired worker leases", reclaimed_count)
        return reclaimed_count

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _required_gates_approved(self, db: AsyncSession, job_id: UUID) -> bool:
        """Ensure G1, G2, G3 gates are all in APPROVED status."""
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


worker_dispatch_service = WorkerDispatchService()

