"""SupervisorCommandService: The Single Authoritative Command Interface for Modernization Workflows.

All workflow mutations, state transitions, gate decisions, background task launches,
and job cancellations MUST pass through this authoritative service.
Direct mutations to jobs.status or modules.status outside this service are strictly prohibited.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional
import uuid
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictException,
    ForbiddenException,
    IllegalStateTransitionException,
    NotFoundException,
)
from app.domain.state_machine import GatePolicy, JobStateMachine
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.workflow import WorkflowCheckpoint, WorkflowGate, WorkflowOutbox
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, GateType
from app.schemas.jobs import JobStatus
from app.schemas.workflow import WorkflowEvent
from app.services.gate_service import gate_service
from app.services.supervisor_service import supervisor_service

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def normalize_actor_type(actor_type: str) -> str:
    if actor_type in ("USER", "HUMAN"):
        return "USER"
    if actor_type in ("SYSTEM", "SERVICE"):
        return "SYSTEM"
    if actor_type in ("AGENT", "MODEL"):
        return "AGENT"
    return "USER"


class SupervisorCommandType(str, Enum):
    START_JOB = "START_JOB"
    RECORD_STAGE_RESULT = "RECORD_STAGE_RESULT"
    REQUEST_GATE_DECISION = "REQUEST_GATE_DECISION"
    APPROVE_GATE = "APPROVE_GATE"
    REJECT_GATE = "REJECT_GATE"
    SCHEDULE_TASK = "SCHEDULE_TASK"
    RECORD_VERIFICATION = "RECORD_VERIFICATION"
    PAUSE_JOB = "PAUSE_JOB"
    RESUME_JOB = "RESUME_JOB"
    CANCEL_JOB = "CANCEL_JOB"
    ESCALATE = "ESCALATE"
    FINALIZE_CANDIDATE = "FINALIZE_CANDIDATE"
    DELIVER = "DELIVER"
    RETRY_FAILED_JOB = "RETRY_FAILED_JOB"


class BaseSupervisorCommand(BaseModel):
    command_id: UUID = Field(default_factory=uuid.uuid4)
    command_type: SupervisorCommandType
    job_id: UUID
    actor_id: str = "SYSTEM"
    actor_type: str = "HUMAN"
    actor_role: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    expected_version: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class CommandReceipt(BaseModel):
    command_id: UUID
    job_id: UUID
    command_type: SupervisorCommandType
    status: str  # ACCEPTED, EXECUTED, REPLAYED
    current_job_status: str
    generation: int
    checkpoint_sequence: int
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    executed_at: datetime = Field(default_factory=utc_now)


class StartJobCommand(BaseSupervisorCommand):
    command_type: SupervisorCommandType = SupervisorCommandType.START_JOB


class PauseJobCommand(BaseSupervisorCommand):
    command_type: SupervisorCommandType = SupervisorCommandType.PAUSE_JOB
    reason: str = "Workflow paused by operator"


class ResumeJobCommand(BaseSupervisorCommand):
    command_type: SupervisorCommandType = SupervisorCommandType.RESUME_JOB
    reason: Optional[str] = None


class CancelJobCommand(BaseSupervisorCommand):
    command_type: SupervisorCommandType = SupervisorCommandType.CANCEL_JOB
    reason: str = "Workflow cancelled by operator"


class ApproveGateCommand(BaseSupervisorCommand):
    command_type: SupervisorCommandType = SupervisorCommandType.APPROVE_GATE
    gate_id: UUID
    rationale: str
    artifact_hashes: Dict[str, str] = Field(default_factory=dict)


class RejectGateCommand(BaseSupervisorCommand):
    command_type: SupervisorCommandType = SupervisorCommandType.REJECT_GATE
    gate_id: UUID
    rationale: str
    feedback: Optional[str] = None


class EscalateCommand(BaseSupervisorCommand):
    command_type: SupervisorCommandType = SupervisorCommandType.ESCALATE
    reason: str
    error_details: Optional[Dict[str, Any]] = None


class RecordVerificationCommand(BaseSupervisorCommand):
    command_type: SupervisorCommandType = SupervisorCommandType.RECORD_VERIFICATION
    module_id: UUID
    attempt_id: UUID
    verdict: str
    verification_evidence: Dict[str, Any] = Field(default_factory=dict)


class RetryFailedJobCommand(BaseSupervisorCommand):
    command_type: SupervisorCommandType = SupervisorCommandType.RETRY_FAILED_JOB
    rationale: str
    target_module_id: Optional[UUID] = None


class SupervisorCommandService:
    """The authoritative command executor and coordinator."""

    def __init__(self):
        self._command_locks: Dict[str, asyncio.Lock] = {}

    def _get_job_lock(self, job_id: UUID) -> asyncio.Lock:
        key = str(job_id)
        if key not in self._command_locks:
            self._command_locks[key] = asyncio.Lock()
        return self._command_locks[key]

    async def enqueue_command(
        self,
        db: AsyncSession,
        command: BaseSupervisorCommand,
    ) -> CommandReceipt:
        """Enqueues a command transactionally, returning 202 Accepted semantics."""
        job = await db.get(Job, command.job_id)
        if not job:
            raise NotFoundException("Job", str(command.job_id))

        # Check terminal state
        current_status = JobStatus(job.status)
        if current_status in JobStateMachine.TERMINAL_STATES and command.command_type != SupervisorCommandType.RETRY_FAILED_JOB:
            raise IllegalStateTransitionException(
                current_state=current_status.value,
                target_state="MUTATION_REJECTED",
                reason=f"Job is in terminal state '{current_status.value}' and cannot accept commands.",
            )

        # Enqueue in WorkflowOutbox
        outbox_event = WorkflowOutbox(
            job_id=command.job_id,
            event_type=f"COMMAND_{command.command_type.value}",
            payload={
                "command_id": str(command.command_id),
                "command_type": command.command_type.value,
                "actor_id": command.actor_id,
                "actor_type": command.actor_type,
                "payload": command.payload,
            },
            idempotency_key=command.idempotency_key or str(command.command_id),
        )
        db.add(outbox_event)
        await db.commit()

        # Asynchronously trigger execution in background
        asyncio.create_task(self._process_command_background(command.job_id, command))

        return CommandReceipt(
            command_id=command.command_id,
            job_id=command.job_id,
            command_type=command.command_type,
            status="ACCEPTED",
            current_job_status=job.status,
            generation=job.orchestration_generation,
            checkpoint_sequence=job.last_checkpoint_sequence,
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
        )

    async def _process_command_background(self, job_id: UUID, command: BaseSupervisorCommand) -> None:
        from app.core.database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as db:
                await self.execute_command(db, command)
        except Exception as exc:
            logger.exception("Background execution of command %s failed: %s", command.command_id, exc)

    async def execute_command(
        self,
        db: AsyncSession,
        command: BaseSupervisorCommand,
    ) -> CommandReceipt:
        """Synchronously and authoritatively executes a workflow command in the DB session."""
        lock = self._get_job_lock(command.job_id)
        async with lock:
            # 1. Fetch locked job
            stmt = select(Job).where(Job.job_id == command.job_id).with_for_update()
            res = await db.execute(stmt)
            job = res.scalar_one_or_none()
            if not job:
                raise NotFoundException("Job", str(command.job_id))

            # 2. Idempotency Check
            if command.idempotency_key:
                existing_event = await db.scalar(
                    select(AuditEvent).where(
                        AuditEvent.job_id == command.job_id,
                        AuditEvent.payload.op("->>")("idempotency_key") == command.idempotency_key,
                    ).limit(1)
                )
                if existing_event:
                    logger.info("Idempotent replay of command %s with key %s", command.command_id, command.idempotency_key)
                    return CommandReceipt(
                        command_id=command.command_id,
                        job_id=command.job_id,
                        command_type=command.command_type,
                        status="REPLAYED",
                        current_job_status=job.status,
                        generation=job.orchestration_generation,
                        checkpoint_sequence=job.last_checkpoint_sequence,
                        correlation_id=command.correlation_id,
                        causation_id=command.causation_id,
                    )

            # 3. Version Guard
            if command.expected_version is not None:
                if job.orchestration_generation != command.expected_version and job.last_checkpoint_sequence != command.expected_version:
                    raise ConflictException(
                        f"Workflow version conflict: expected {command.expected_version}, "
                        f"current generation {job.orchestration_generation}, seq {job.last_checkpoint_sequence}"
                    )

            current_status = JobStatus(job.status)

            # 4. Check terminal states
            if current_status in JobStateMachine.TERMINAL_STATES:
                if command.command_type == SupervisorCommandType.CANCEL_JOB and current_status == JobStatus.CANCELLED:
                    return CommandReceipt(
                        command_id=command.command_id,
                        job_id=job.job_id,
                        command_type=command.command_type,
                        status="REPLAYED",
                        current_job_status=job.status,
                        generation=job.orchestration_generation,
                        checkpoint_sequence=job.last_checkpoint_sequence,
                        correlation_id=command.correlation_id,
                        causation_id=command.causation_id,
                    )
                if command.command_type != SupervisorCommandType.RETRY_FAILED_JOB:
                    raise IllegalStateTransitionException(
                        current_state=current_status.value,
                        target_state="REJECTED",
                        reason=f"Job is in terminal state '{current_status.value}' and cannot accept commands.",
                    )

            # 5. Dispatch command to specific handler
            if command.command_type == SupervisorCommandType.START_JOB:
                await self._handle_start_job(db, job, command)
            elif command.command_type == SupervisorCommandType.PAUSE_JOB:
                await self._handle_pause_job(db, job, command)
            elif command.command_type == SupervisorCommandType.RESUME_JOB:
                await self._handle_resume_job(db, job, command)
            elif command.command_type == SupervisorCommandType.CANCEL_JOB:
                await self._handle_cancel_job(db, job, command)
            elif command.command_type == SupervisorCommandType.APPROVE_GATE:
                await self._handle_approve_gate(db, job, command)
            elif command.command_type == SupervisorCommandType.REJECT_GATE:
                await self._handle_reject_gate(db, job, command)
            elif command.command_type == SupervisorCommandType.ESCALATE:
                await self._handle_escalate(db, job, command)
            elif command.command_type == SupervisorCommandType.RECORD_VERIFICATION:
                await self._handle_record_verification(db, job, command)
            elif command.command_type == SupervisorCommandType.RETRY_FAILED_JOB:
                await self._handle_retry_failed_job(db, job, command)
            else:
                logger.error("Unknown command type: %s", command.command_type)
                raise ConflictException(f"Unsupported command type: {command.command_type}")

            # 6. Record Audit Event for Command
            audit_evt = AuditEvent(
                job_id=job.job_id,
                event_type=f"SUPERVISOR_COMMAND_{command.command_type.value}",
                actor_type=normalize_actor_type(command.actor_type),
                actor_id=command.actor_id,
                correlation_id=command.correlation_id,
                payload={
                    "command_id": str(command.command_id),
                    "command_type": command.command_type.value,
                    "idempotency_key": command.idempotency_key,
                    "causation_id": command.causation_id,
                    "previous_status": current_status.value,
                    "resulting_status": job.status,
                    "generation": job.orchestration_generation,
                },
            )
            db.add(audit_evt)
            await db.commit()
            await db.refresh(job)

            return CommandReceipt(
                command_id=command.command_id,
                job_id=job.job_id,
                command_type=command.command_type,
                status="EXECUTED",
                current_job_status=job.status,
                generation=job.orchestration_generation,
                checkpoint_sequence=job.last_checkpoint_sequence,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
            )

    async def _handle_start_job(self, db: AsyncSession, job: Job, command: BaseSupervisorCommand) -> None:
        if job.status != JobStatus.CREATED.value:
            raise IllegalStateTransitionException(
                current_state=job.status,
                target_state=JobStatus.INTAKE.value,
                reason="Only jobs in CREATED status can be started.",
            )
        await supervisor_service.transition(
            db, job.job_id, JobStatus.INTAKE,
            actor_id=command.actor_id, correlation_id=command.correlation_id,
        )
        supervisor_service.schedule_drive(job.job_id, correlation_id=command.correlation_id)

    async def _handle_pause_job(self, db: AsyncSession, job: Job, command: BaseSupervisorCommand) -> None:
        reason = getattr(command, "reason", "Paused by operator")
        await supervisor_service.pause(
            db, job.job_id,
            actor_id=command.actor_id,
            reason=reason,
            correlation_id=command.correlation_id,
        )

    async def _handle_resume_job(self, db: AsyncSession, job: Job, command: BaseSupervisorCommand) -> None:
        await supervisor_service.resume(
            db, job.job_id,
            actor_id=command.actor_id,
            correlation_id=command.correlation_id,
        )

    async def _handle_cancel_job(self, db: AsyncSession, job: Job, command: BaseSupervisorCommand) -> None:
        """Controlled 4-stage cancellation protocol."""
        reason = getattr(command, "reason", "Cancelled by operator")

        # Stage 1: Mark intent
        db.add(AuditEvent(
            job_id=job.job_id,
            event_type="CANCELLATION_REQUESTED",
            actor_type=normalize_actor_type(command.actor_type),
            actor_id=command.actor_id,
            correlation_id=command.correlation_id,
            payload={"reason": reason},
        ))

        # Stage 2: Signal running background tasks
        key = str(job.job_id)
        task = supervisor_service._running_tasks.get(key)
        if task and not task.done():
            logger.info("Cancelling active supervisor background task for job %s", job.job_id)
            task.cancel()

        # Stage 3: Reclaim active module attempts and worker leases
        active_attempts = (await db.execute(
            select(ModuleAttempt).join(Module).where(
                Module.job_id == job.job_id,
                ModuleAttempt.status == "RUNNING",
            )
        )).scalars().all()
        for att in active_attempts:
            att.status = "CANCELLED"
            att.failure_reason = "Job cancelled by operator"

        active_modules = (await db.execute(
            select(Module).where(Module.job_id == job.job_id, Module.status.in_(["RUNNING", "LEASED"]))
        )).scalars().all()
        for mod in active_modules:
            mod.status = "PENDING"
            mod.lease_owner = None
            mod.lease_expires_at = None

        job.orchestration_owner = None
        job.orchestration_lease_expires_at = None

        # Stage 4: Persist cancellation checkpoint and transition job
        await supervisor_service.cancel(
            db, job.job_id,
            actor_id=command.actor_id,
            correlation_id=command.correlation_id,
        )

    async def _handle_approve_gate(self, db: AsyncSession, job: Job, command: BaseSupervisorCommand) -> None:
        gate_id = getattr(command, "gate_id", None) or UUID(command.payload["gate_id"])
        rationale = getattr(command, "rationale", command.payload.get("rationale", ""))
        hashes = getattr(command, "artifact_hashes", command.payload.get("artifact_hashes", {}))

        gate = await db.get(WorkflowGate, gate_id)
        if not gate or gate.job_id != job.job_id:
            raise NotFoundException("WorkflowGate", str(gate_id))

        role = command.actor_role or "REVIEWER"
        req = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale=rationale,
            artifact_hashes=hashes,
            idempotency_key=command.idempotency_key,
        )
        await gate_service.decide(
            db, gate.gate_id, req,
            actor_id=UUID(command.actor_id) if len(command.actor_id) == 36 else uuid.uuid4(),
            actor_role=role,
            correlation_id=command.correlation_id,
        )

    async def _handle_reject_gate(self, db: AsyncSession, job: Job, command: BaseSupervisorCommand) -> None:
        gate_id = getattr(command, "gate_id", None) or UUID(command.payload["gate_id"])
        rationale = getattr(command, "rationale", command.payload.get("rationale", ""))

        gate = await db.get(WorkflowGate, gate_id)
        if not gate or gate.job_id != job.job_id:
            raise NotFoundException("WorkflowGate", str(gate_id))

        role = command.actor_role or "REVIEWER"
        req = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED,
            rationale=rationale,
            idempotency_key=command.idempotency_key,
        )
        await gate_service.decide(
            db, gate.gate_id, req,
            actor_id=UUID(command.actor_id) if len(command.actor_id) == 36 else uuid.uuid4(),
            actor_role=role,
            correlation_id=command.correlation_id,
        )

    async def _handle_escalate(self, db: AsyncSession, job: Job, command: BaseSupervisorCommand) -> None:
        """Escalation sets blocking reason and pauses workflow for review; does not auto-fail."""
        reason = getattr(command, "reason", command.payload.get("reason", "Operator escalation"))
        job.blocking_reason = reason
        job.active_node = "escalation"
        if job.status not in JobStateMachine.TERMINAL_STATES:
            if job.status != JobStatus.PAUSED.value:
                job.paused_from_status = job.status
                job.status = JobStatus.PAUSED.value

        db.add(AuditEvent(
            job_id=job.job_id,
            event_type="WORKFLOW_ESCALATED",
            actor_type=normalize_actor_type(command.actor_type),
            actor_id=command.actor_id,
            correlation_id=command.correlation_id,
            payload={"reason": reason, "status": job.status},
        ))

    async def _handle_record_verification(self, db: AsyncSession, job: Job, command: BaseSupervisorCommand) -> None:
        module_id = getattr(command, "module_id", None) or UUID(command.payload["module_id"])
        attempt_id = getattr(command, "attempt_id", None) or UUID(command.payload["attempt_id"])
        verdict = getattr(command, "verdict", command.payload.get("verdict", "SUCCESS"))

        attempt = await db.get(ModuleAttempt, attempt_id)
        module = await db.get(Module, module_id)
        if not attempt or not module:
            raise NotFoundException("ModuleAttempt", str(attempt_id))

        if verdict == "VERIFIED":
            attempt.status = "VERIFIED"
            module.status = "VERIFIED"
            module.lease_owner = None
            module.lease_expires_at = None
        else:
            attempt.status = "FAILED"
            module.status = "PENDING"
            module.lease_owner = None
            module.lease_expires_at = None

    async def _handle_retry_failed_job(self, db: AsyncSession, job: Job, command: BaseSupervisorCommand) -> None:
        """Authorized recovery creating an explicit new generation from terminal FAILED."""
        if getattr(command, "actor_role", None) not in ("ADMIN", "SUPER_ADMIN"):
            raise ForbiddenException("Only administrators can retry a failed workflow.")
        rationale = getattr(command, "rationale", command.payload.get("rationale", ""))
        if len(rationale) < 10:
            raise ConflictException("Authorized retry requires a minimum 10-character diagnostic rationale.")

        target_module_id = getattr(command, "target_module_id", None)
        await supervisor_service.recover_failed_phase6_job(
            db, job.job_id, rationale=rationale, target_module_id=target_module_id, actor_id=command.actor_id
        )


supervisor_command_service = SupervisorCommandService()
