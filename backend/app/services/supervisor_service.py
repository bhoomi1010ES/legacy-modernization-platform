"""Durable supervisor transitions, recovery, quotas, and transactional side effects."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Dict
import asyncio
import re
import uuid
from uuid import UUID

def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, IllegalStateTransitionException, NotFoundException
from app.domain.state_machine import JobStateMachine
from app.models.audit import AuditEvent
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.agent import AgentRun
from app.models.base import utc_now
from app.models.module import Module, ModuleAttempt
from app.models.test_case import TestCase, TestResult
from app.models.workflow import WorkflowGate, WorkflowOutbox
from app.schemas.jobs import JobStatus
from app.schemas.workflow import SupervisorState, WorkflowEvent, WorkflowNode, WorkflowPhase
from app.services.workflow_checkpointer import PostgresWorkflowCheckpointer


STATUS_NODE = {
    JobStatus.CREATED: WorkflowNode.CREATED,
    JobStatus.INTAKE: WorkflowNode.INTAKE,
    JobStatus.ANALYZING: WorkflowNode.ANALYSIS,
    JobStatus.AWAITING_GATE_G1: WorkflowNode.GATE_G1,
    JobStatus.CHARACTERIZING: WorkflowNode.CHARACTERIZATION,
    JobStatus.AWAITING_GATE_G2: WorkflowNode.GATE_G2,
    JobStatus.PLANNING: WorkflowNode.PLANNING,
    JobStatus.AWAITING_GATE_G3: WorkflowNode.GATE_G3,
    JobStatus.CONVERTING: WorkflowNode.CONVERSION,
    JobStatus.VERIFYING: WorkflowNode.VERIFICATION,
    JobStatus.INTEGRATING: WorkflowNode.INTEGRATION,
    JobStatus.AWAITING_GATE_G4: WorkflowNode.GATE_G4,
    JobStatus.PAUSED: WorkflowNode.PAUSED,
    JobStatus.COMPLETED: WorkflowNode.COMPLETE,
    JobStatus.FAILED: WorkflowNode.FAILED,
    JobStatus.CANCELLED: WorkflowNode.CANCELLED,
}

STATUS_GATE = {
    JobStatus.AWAITING_GATE_G1: "G1",
    JobStatus.AWAITING_GATE_G2: "G2",
    JobStatus.AWAITING_GATE_G3: "G3",
    JobStatus.AWAITING_GATE_G4: "G4",
}

STATUS_PHASE = {
    JobStatus.CREATED: WorkflowPhase.INTAKE,
    JobStatus.INTAKE: WorkflowPhase.INTAKE,
    JobStatus.ANALYZING: WorkflowPhase.INTAKE,
    JobStatus.AWAITING_GATE_G1: WorkflowPhase.G1,
    JobStatus.CHARACTERIZING: WorkflowPhase.CHARACTERIZATION,
    JobStatus.AWAITING_GATE_G2: WorkflowPhase.G2,
    JobStatus.PLANNING: WorkflowPhase.PLANNING,
    JobStatus.AWAITING_GATE_G3: WorkflowPhase.G3,
    JobStatus.CONVERTING: WorkflowPhase.CONVERSION,
    JobStatus.VERIFYING: WorkflowPhase.VERIFICATION,
    JobStatus.INTEGRATING: WorkflowPhase.INTEGRATION,
    JobStatus.AWAITING_GATE_G4: WorkflowPhase.G4,
    JobStatus.COMPLETED: WorkflowPhase.COMPLETED,
    JobStatus.FAILED: WorkflowPhase.FAILED,
    JobStatus.CANCELLED: WorkflowPhase.CANCELLED,
}

PHASE_NODE = {
    WorkflowPhase.INTAKE: WorkflowNode.INTAKE,
    WorkflowPhase.G1: WorkflowNode.GATE_G1,
    WorkflowPhase.CHARACTERIZATION: WorkflowNode.CHARACTERIZATION,
    WorkflowPhase.SCHEMA_DATA: WorkflowNode.SCHEMA_DATA,
    WorkflowPhase.G2: WorkflowNode.GATE_G2,
    WorkflowPhase.PLANNING: WorkflowNode.PLANNING,
    WorkflowPhase.G3: WorkflowNode.GATE_G3,
    WorkflowPhase.CONVERSION: WorkflowNode.CONVERSION,
    WorkflowPhase.VERIFICATION: WorkflowNode.VERIFICATION,
    WorkflowPhase.INTEGRATION: WorkflowNode.INTEGRATION,
    WorkflowPhase.G4: WorkflowNode.GATE_G4,
    WorkflowPhase.COMPLETED: WorkflowNode.COMPLETE,
    WorkflowPhase.FAILED: WorkflowNode.FAILED,
    WorkflowPhase.CANCELLED: WorkflowNode.CANCELLED,
}

GATE_ARTIFACT_TYPES = {
    "G1": {"LEGACYMODEL", "TARGETBLUEPRINT", "FEASIBILITYREPORT"},
    "G2": {"CHARACTERIZATIONSUITE", "SCHEMAMIGRATIONPLAN"},
    "G3": {"CONVERSIONPLAN"},
    "G4": {"JOBREPORT", "SYSTEMVERIFICATION", "INTEGRATIONREPORT", "SBOM"},
}


def _artifact_key(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


TRANSITION_EVENTS: dict[tuple[JobStatus, JobStatus], WorkflowEvent] = {
    (JobStatus.CREATED, JobStatus.INTAKE): WorkflowEvent.INTAKE_STARTED,
    (JobStatus.INTAKE, JobStatus.ANALYZING): WorkflowEvent.ANALYSIS_STARTED,
    (JobStatus.ANALYZING, JobStatus.AWAITING_GATE_G1): WorkflowEvent.INTAKE_READY,
    (JobStatus.AWAITING_GATE_G1, JobStatus.CHARACTERIZING): WorkflowEvent.G1_APPROVED,
    (JobStatus.AWAITING_GATE_G1, JobStatus.ANALYZING): WorkflowEvent.G1_REJECTED,
    (JobStatus.CHARACTERIZING, JobStatus.AWAITING_GATE_G2): WorkflowEvent.SCHEMA_DATA_COMPLETE,
    (JobStatus.AWAITING_GATE_G2, JobStatus.PLANNING): WorkflowEvent.G2_APPROVED,
    (JobStatus.AWAITING_GATE_G2, JobStatus.CHARACTERIZING): WorkflowEvent.G2_REJECTED,
    (JobStatus.PLANNING, JobStatus.AWAITING_GATE_G3): WorkflowEvent.PLAN_COMPLETE,
    (JobStatus.AWAITING_GATE_G3, JobStatus.CONVERTING): WorkflowEvent.G3_APPROVED,
    (JobStatus.AWAITING_GATE_G3, JobStatus.PLANNING): WorkflowEvent.G3_REJECTED,
    (JobStatus.CONVERTING, JobStatus.VERIFYING): WorkflowEvent.CONVERSION_COMPLETE,
    (JobStatus.VERIFYING, JobStatus.INTEGRATING): WorkflowEvent.VERIFICATION_PASSED,
    (JobStatus.VERIFYING, JobStatus.CONVERTING): WorkflowEvent.VERIFICATION_FAILED,
    (JobStatus.INTEGRATING, JobStatus.AWAITING_GATE_G4): WorkflowEvent.INTEGRATION_COMPLETE,
    (JobStatus.AWAITING_GATE_G4, JobStatus.COMPLETED): WorkflowEvent.G4_APPROVED,
    (JobStatus.AWAITING_GATE_G4, JobStatus.CONVERTING): WorkflowEvent.G4_REJECTED,
}


class SupervisorService:
    def __init__(self, checkpointer: Optional[PostgresWorkflowCheckpointer] = None):
        self.checkpointer = checkpointer or PostgresWorkflowCheckpointer()
        self._running_tasks: dict[str, Any] = {}
        self._recovery_task: Optional[asyncio.Task] = None
        # One drive can hold a workflow session while its lease heartbeat briefly
        # opens another. Keep restart recovery below the default five-connection
        # SQLAlchemy pool instead of scheduling every stale job simultaneously.
        self._drive_semaphore = asyncio.Semaphore(2)

    @staticmethod
    def state_for(
        job: Job,
        *,
        target: Optional[JobStatus] = None,
        phase: Optional[WorkflowPhase] = None,
        correlation_id: Optional[str] = None,
    ) -> SupervisorState:
        """Return the JSON-safe core of the durable workflow state.

        ``snapshot_for`` enriches this core with task, gate, artifact and
        dependency state before every persisted checkpoint.
        """
        target_status = target or JobStatus(job.status)
        target_phase = phase or WorkflowPhase(job.workflow_phase or STATUS_PHASE[target_status].value)
        return {
            "job_id": str(job.job_id),
            "workflow_id": str(job.workflow_id),
            "current_phase": target_phase.value,
            "status": target_status.value,
            "active_node": job.active_node,
            "target_node": PHASE_NODE.get(target_phase, STATUS_NODE[target_status]).value,
            "checkpoint_sequence": job.last_checkpoint_sequence,
            "retry_count": job.workflow_retry_count,
            "budget_used": float(job.budget_used_usd),
            "budget_limit": float(job.budget_limit_usd),
            "budget_state": {
                "used": float(job.budget_used_usd),
                "limit": float(job.budget_limit_usd),
                "exhausted": Decimal(job.budget_used_usd) >= Decimal(job.budget_limit_usd),
            },
            "blocking_reason": job.blocking_reason,
            "correlation_id": correlation_id,
            "active_task_ids": [],
            "completed_task_ids": [],
            "blocked_task_ids": [],
            "failed_task_ids": [],
            "pending_gate_id": None,
            "approved_artifact_versions": {},
            "artifact_hashes": {},
            "retry_counts": {"workflow": job.workflow_retry_count},
            "dependency_state": {},
            "last_checkpoint": None,
            "last_transition": job.last_transition,
            "failure_reason": job.blocking_reason if target_status == JobStatus.FAILED else None,
            "terminal_reason": job.terminal_reason,
            "events": [],
        }

    async def snapshot_for(
        self,
        db: AsyncSession,
        job: Job,
        *,
        target: Optional[JobStatus] = None,
        phase: Optional[WorkflowPhase] = None,
        correlation_id: Optional[str] = None,
    ) -> SupervisorState:
        state = self.state_for(job, target=target, phase=phase, correlation_id=correlation_id)
        modules = list((await db.execute(
            select(Module).where(Module.job_id == job.job_id).order_by(Module.wave_number, Module.created_at)
        )).scalars().all())
        statuses: dict[str, list[str]] = {
            "active_task_ids": [], "completed_task_ids": [],
            "blocked_task_ids": [], "failed_task_ids": [],
        }
        dependency_state: dict[str, Any] = {}
        module_retries: dict[str, int] = {}
        for module in modules:
            module_id = str(module.module_id)
            module_retries[module_id] = module.retry_count
            dependency_state[module_id] = {
                "status": module.status,
                "dependencies": list(module.dependency_module_ids or []),
                "lease_generation": module.lease_generation,
            }
            if module.status in {"LEASED", "RUNNING", "GENERATED", "VERIFYING"}:
                statuses["active_task_ids"].append(module_id)
            elif module.status in {"VERIFIED", "COMPLETED"}:
                statuses["completed_task_ids"].append(module_id)
            elif module.status in {"BLOCKED", "REPAIR_REQUIRED", "PENDING"}:
                statuses["blocked_task_ids"].append(module_id)
            elif module.status in {"FAILED", "CANCELLED"}:
                statuses["failed_task_ids"].append(module_id)
        state.update(statuses)
        state["dependency_state"] = dependency_state
        state["retry_counts"] = {"workflow": job.workflow_retry_count, **module_retries}

        pending = await db.scalar(
            select(WorkflowGate)
            .where(WorkflowGate.job_id == job.job_id, WorkflowGate.status == "PENDING")
            .order_by(WorkflowGate.requested_at.desc())
            .limit(1)
        )
        state["pending_gate_id"] = str(pending.gate_id) if pending else None
        approved = list((await db.execute(
            select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.status == "APPROVED")
        )).scalars().all())
        approved_hashes: dict[str, str] = {}
        for gate in approved:
            approved_hashes.update(gate.artifact_hashes or {})
        state["artifact_hashes"] = approved_hashes
        if approved_hashes:
            artifact_ids = []
            for item in approved_hashes:
                try:
                    artifact_ids.append(UUID(item))
                except (ValueError, TypeError, AttributeError):
                    pass
            if artifact_ids:
                rows = list((await db.execute(select(Artifact).where(Artifact.artifact_id.in_(artifact_ids)))).scalars().all())
                state["approved_artifact_versions"] = {
                    str(artifact.artifact_id): artifact.version for artifact in rows
                }
        latest = await self.checkpointer.latest(db, job.job_id)
        if latest:
            state["last_checkpoint"] = {
                "checkpoint_id": str(latest.checkpoint_id),
                "sequence": latest.sequence,
                "kind": latest.checkpoint_kind,
                "node": latest.node_name,
            }
        return state

    async def _locked_job(self, db: AsyncSession, job_id: UUID) -> Job:
        result = await db.execute(
            select(Job).where(Job.job_id == job_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundException("Job", str(job_id))
        return job

    async def _gate_artifacts(self, db: AsyncSession, job: Job, gate_type: str) -> list[Artifact]:
        artifacts = list((await db.execute(
            select(Artifact).where(Artifact.job_id == job.job_id).order_by(
                Artifact.artifact_type.asc(), Artifact.version.desc(), Artifact.created_at.desc()
            )
        )).scalars().all())
        latest: dict[str, Artifact] = {}
        for artifact in artifacts:
            latest.setdefault(_artifact_key(artifact.artifact_type), artifact)
        required = GATE_ARTIFACT_TYPES[gate_type]
        missing = sorted(required - set(latest))
        if missing:
            raise ConflictException(
                f"{gate_type} requires current workflow-owned artifacts: {', '.join(missing)}"
            )
        return [latest[item] for item in sorted(required)]

    async def _materialize_gate(
        self,
        db: AsyncSession,
        job: Job,
        gate_type: str,
        *,
        reason: Optional[str],
    ) -> WorkflowGate:
        existing = await db.scalar(select(WorkflowGate).where(
            WorkflowGate.job_id == job.job_id,
            WorkflowGate.gate_type == gate_type,
            WorkflowGate.status == "PENDING",
        ).order_by(WorkflowGate.version.desc()).limit(1))
        artifacts = await self._gate_artifacts(db, job, gate_type)
        hashes = {str(item.artifact_id): item.content_hash for item in artifacts}
        if existing:
            if existing.artifact_hashes != hashes:
                existing.artifact_ids = list(hashes)
                existing.artifact_hashes = dict(hashes)
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(existing, "artifact_hashes")
                flag_modified(existing, "artifact_ids")
                await db.flush()
            return existing
        latest_version = await db.scalar(select(func.max(WorkflowGate.version)).where(
            WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == gate_type
        ))
        gate = WorkflowGate(
            job_id=job.job_id,
            gate_type=gate_type,
            version=(latest_version or 0) + 1,
            artifact_ids=list(hashes),
            artifact_hashes=hashes,
            blocking_reason=reason or f"Human decision required for {gate_type}.",
        )
        db.add(gate)
        await db.flush()
        return gate

    async def _release_task_leases(self, db: AsyncSession, job: Job) -> None:
        modules = list((await db.execute(
            select(Module).where(
                Module.job_id == job.job_id,
                Module.status.in_(("LEASED", "RUNNING")),
            ).with_for_update()
        )).scalars().all())
        for module in modules:
            module.status = "PENDING"
            module.lease_owner = None
            module.lease_expires_at = None
            module.lease_heartbeat_at = None
            module.lease_generation += 1

    async def _apply_transition_locked(
        self,
        db: AsyncSession,
        job: Job,
        target: JobStatus,
        event: WorkflowEvent,
        *,
        phase: Optional[WorkflowPhase] = None,
        actor_id: str,
        actor_type: str,
        correlation_id: Optional[str],
        reason: Optional[str],
        idempotency_key: Optional[str],
    ) -> Job:
        current = JobStatus(job.status)
        previous_phase = WorkflowPhase(job.workflow_phase or STATUS_PHASE[current].value)
        target_phase = phase or STATUS_PHASE[target]
        if current == target and previous_phase == target_phase:
            if target in STATUS_GATE:
                gate = await self._materialize_gate(
                    db, job, STATUS_GATE[target], reason=reason
                )
                job.blocking_reason = reason or f"Human decision required for {gate.gate_type}."
            return job
        if current != target:
            JobStateMachine.validate_transition(current, target)
        if target == JobStatus.PLANNING:
            await self.require_planning_eligibility(db, job, require_state=False)
        if target == JobStatus.INTEGRATING:
            await self.require_integration_eligibility(db, job)
        if Decimal(job.budget_used_usd) >= Decimal(job.budget_limit_usd) and target not in {
            JobStatus.PAUSED, JobStatus.CANCELLED, JobStatus.FAILED
        }:
            raise ConflictException("Job budget is exhausted; pause/escalation is required before further work.")

        if idempotency_key:
            existing_command = await db.scalar(
                select(WorkflowOutbox).where(WorkflowOutbox.idempotency_key == idempotency_key)
            )
            if existing_command:
                if existing_command.job_id != job.job_id or existing_command.event_type != f"SUPERVISOR_COMMAND:{event.value}":
                    raise ConflictException("Idempotency key belongs to another supervisor command")
                return job

        before = await self.snapshot_for(
            db, job, target=target, phase=target_phase, correlation_id=correlation_id
        )
        await self.checkpointer.save(
            db, job, kind="BEFORE", node_name=before["target_node"], state=before,
            correlation_id=correlation_id,
        )

        if target == JobStatus.PAUSED:
            job.paused_from_status = current.value
        elif current == JobStatus.PAUSED:
            job.paused_from_status = None
        job.status = target.value
        job.workflow_phase = target_phase.value
        job.active_node = PHASE_NODE.get(target_phase, STATUS_NODE[target]).value
        job.workflow_version += 1
        job.last_transition = event.value
        job.blocking_reason = reason
        if target in JobStateMachine.TERMINAL_STATES:
            job.terminal_reason = reason or event.value

        gate: Optional[WorkflowGate] = None
        if target in STATUS_GATE:
            gate = await self._materialize_gate(
                db, job, STATUS_GATE[target], reason=reason
            )
            job.blocking_reason = reason or f"Human decision required for {gate.gate_type}."

        if target == JobStatus.PAUSED or target in STATUS_GATE or target == JobStatus.CANCELLED:
            await self._release_task_leases(db, job)

        after = await self.snapshot_for(db, job, correlation_id=correlation_id)
        after["events"] = [{
            "type": "WORKFLOW_COMMAND_APPLIED",
            "event": event.value,
            "from": current.value,
            "to": target.value,
        }]
        if gate:
            after["pending_gate_id"] = str(gate.gate_id)
        checkpoint_kind = "INTERRUPT" if target in STATUS_GATE or target == JobStatus.PAUSED else "AFTER"
        checkpoint = await self.checkpointer.save(
            db, job, kind=checkpoint_kind, node_name=job.active_node, state=after,
            correlation_id=correlation_id,
        )

        if idempotency_key:
            db.add(WorkflowOutbox(
                job_id=job.job_id,
                idempotency_key=idempotency_key,
                event_type=f"SUPERVISOR_COMMAND:{event.value}",
                payload={"job_id": str(job.job_id), "workflow_version": job.workflow_version},
                status="PROCESSED",
                processed_at=utc_now(),
            ))
        db.add(AuditEvent(
            job_id=job.job_id,
            event_type="WORKFLOW_TRANSITION",
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=correlation_id,
            target_resource=str(job.job_id),
            payload={
                "workflow_id": str(job.workflow_id),
                "command": event.value,
                "previous_state": current.value,
                "new_state": target.value,
                "previous_phase": previous_phase.value,
                "new_phase": target_phase.value,
                "checkpoint_id": str(checkpoint.checkpoint_id),
                "artifact_hashes": after.get("artifact_hashes", {}),
                "active_task_ids": after.get("active_task_ids", []),
                "reason": reason,
            },
        ))
        return job

    async def transition(
        self,
        db: AsyncSession,
        job_id: UUID,
        target: JobStatus,
        *,
        actor_id: str = "supervisor",
        correlation_id: Optional[str] = None,
        reason: Optional[str] = None,
        side_effect_type: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        commit: bool = True,
    ) -> Job:
        job = await self._locked_job(db, job_id)
        current = JobStatus(job.status)
        if current == target:
            if target in STATUS_GATE:
                gate = await self._materialize_gate(
                    db, job, STATUS_GATE[target], reason=reason
                )
                job.blocking_reason = reason or f"Human decision required for {gate.gate_type}."
                if commit:
                    await db.commit()
            return job
        event = TRANSITION_EVENTS.get((current, target))
        if target == JobStatus.PAUSED:
            event = WorkflowEvent.PAUSE_REQUESTED
        elif target == JobStatus.CANCELLED:
            event = WorkflowEvent.CANCEL_REQUESTED
        elif target == JobStatus.FAILED:
            event = WorkflowEvent.RETRY_EXHAUSTED
        elif current == JobStatus.PAUSED:
            event = WorkflowEvent.RESUME_REQUESTED
        if event is None:
            raise IllegalStateTransitionException(current.value, target.value, "No authoritative workflow command maps this transition")
        await self._apply_transition_locked(
            db,
            job,
            target,
            event,
            phase=(
                WorkflowPhase(job.workflow_phase or STATUS_PHASE[current].value)
                if current == JobStatus.PAUSED or target == JobStatus.PAUSED
                else None
            ),
            actor_id=actor_id,
            actor_type="SYSTEM" if actor_id.lower() in {"supervisor", "system"} else "USER",
            correlation_id=correlation_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        if side_effect_type:
            if not idempotency_key:
                raise ValueError("External side effects require an idempotency key")
            db.add(WorkflowOutbox(
                job_id=job.job_id,
                idempotency_key=f"effect:{idempotency_key}",
                event_type=side_effect_type,
                payload={"job_id": str(job.job_id), "status": target.value},
            ))
        if commit:
            await db.commit()
            await db.refresh(job)
        return job

    async def command(
        self,
        db: AsyncSession,
        job_id: UUID,
        event: WorkflowEvent,
        *,
        actor_id: str = "supervisor",
        actor_type: str = "SYSTEM",
        correlation_id: Optional[str] = None,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        commit: bool = True,
    ) -> Job:
        """The sole event-oriented public workflow transition boundary."""
        job = await self._locked_job(db, job_id)
        current = JobStatus(job.status)
        phase = WorkflowPhase(job.workflow_phase or STATUS_PHASE[current].value)

        if event == WorkflowEvent.CHARACTERIZATION_COMPLETE:
            if current != JobStatus.CHARACTERIZING or phase != WorkflowPhase.CHARACTERIZATION:
                raise IllegalStateTransitionException(current.value, event.value, "Characterization is not active")
            required = await self._gate_artifacts_for_types(db, job, {"CHARACTERIZATIONSUITE"})
            if not required:
                raise ConflictException("Characterization completion requires a persisted suite")
            target, target_phase = current, WorkflowPhase.SCHEMA_DATA
        elif event == WorkflowEvent.RECOVERY_RECONCILED:
            target, target_phase = current, phase
        else:
            candidates = [
                (target, mapped)
                for (source, target), mapped in TRANSITION_EVENTS.items()
                if source == current and mapped == event
            ]
            if event == WorkflowEvent.PAUSE_REQUESTED:
                target, target_phase = JobStatus.PAUSED, phase
            elif event == WorkflowEvent.CANCEL_REQUESTED:
                target, target_phase = JobStatus.CANCELLED, WorkflowPhase.CANCELLED
            elif event == WorkflowEvent.RETRY_EXHAUSTED:
                target, target_phase = JobStatus.FAILED, WorkflowPhase.FAILED
            elif event == WorkflowEvent.RESUME_REQUESTED:
                if current != JobStatus.PAUSED or not job.paused_from_status:
                    raise IllegalStateTransitionException(current.value, event.value, "Job has no resumable state")
                target, target_phase = JobStatus(job.paused_from_status), phase
            elif candidates:
                target = candidates[0][0]
                target_phase = STATUS_PHASE[target]
            else:
                raise IllegalStateTransitionException(current.value, event.value, "Command is not legal in the current state")

        await self._apply_transition_locked(
            db,
            job,
            target,
            event,
            phase=target_phase,
            actor_id=actor_id,
            actor_type=actor_type,
            correlation_id=correlation_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        if commit:
            await db.commit()
            await db.refresh(job)
        return job

    async def _gate_artifacts_for_types(
        self, db: AsyncSession, job: Job, required: set[str]
    ) -> list[Artifact]:
        rows = list((await db.execute(
            select(Artifact).where(Artifact.job_id == job.job_id).order_by(
                Artifact.artifact_type.asc(), Artifact.version.desc(), Artifact.created_at.desc()
            )
        )).scalars().all())
        latest: dict[str, Artifact] = {}
        for artifact in rows:
            latest.setdefault(_artifact_key(artifact.artifact_type), artifact)
        return [latest[key] for key in sorted(required) if key in latest]

    async def record_graph_result(
        self,
        db: AsyncSession,
        job_id: UUID,
        *,
        verdict: str,
        task_id: Optional[str],
        agent_name: Optional[str],
        correlation_id: Optional[str],
        reason: Optional[str] = None,
    ) -> None:
        job = await self._locked_job(db, job_id)
        if verdict == "RETRY":
            job.workflow_retry_count += 1
            if job.workflow_retry_count > job.max_repair_attempts:
                await self._apply_transition_locked(
                    db, job, JobStatus.FAILED, WorkflowEvent.RETRY_EXHAUSTED,
                    phase=WorkflowPhase.FAILED, actor_id="supervisor", actor_type="SYSTEM",
                    correlation_id=correlation_id,
                    reason=reason or "Supervisor retry limit exhausted",
                    idempotency_key=None,
                )
        state = await self.snapshot_for(db, job, correlation_id=correlation_id)
        state["events"] = [{
            "type": "AGENT_RESULT_RECORDED", "verdict": verdict,
            "task_id": task_id, "agent": agent_name,
        }]
        await self.checkpointer.save(
            db, job, kind="AFTER", node_name="persist_result", state=state,
            correlation_id=correlation_id,
        )
        db.add(AuditEvent(
            job_id=job.job_id,
            event_type="AGENT_RESULT_RECORDED",
            actor_type="SYSTEM",
            actor_id="supervisor",
            correlation_id=correlation_id,
            target_resource=task_id,
            payload={
                "workflow_id": str(job.workflow_id), "task_id": task_id,
                "agent": agent_name, "verdict": verdict, "reason": reason,
            },
        ))
        await db.commit()

    async def fail(
        self, db: AsyncSession, job_id: UUID, *, reason: str,
        correlation_id: Optional[str] = None,
    ) -> Job:
        return await self.command(
            db, job_id, WorkflowEvent.RETRY_EXHAUSTED,
            reason=reason, correlation_id=correlation_id,
        )

    async def acquire_orchestration_lease(
        self, db: AsyncSession, job_id: UUID, *, owner: str, lease_seconds: int = 60
    ) -> Optional[int]:
        job = await self._locked_job(db, job_id)
        now = utc_now()
        lease_expires = _normalize_dt(job.orchestration_lease_expires_at)
        if (
            job.orchestration_owner
            and job.orchestration_owner != owner
            and lease_expires
            and lease_expires > now
        ):
            await db.rollback()
            return None
        job.orchestration_owner = owner
        job.orchestration_generation += 1
        job.orchestration_lease_expires_at = now + timedelta(seconds=lease_seconds)
        generation = job.orchestration_generation
        await db.commit()
        return generation

    async def release_orchestration_lease(
        self, db: AsyncSession, job_id: UUID, *, owner: str, generation: int
    ) -> bool:
        job = await self._locked_job(db, job_id)
        if job.orchestration_owner != owner or job.orchestration_generation != generation:
            await db.rollback()
            return False
        job.orchestration_owner = None
        job.orchestration_lease_expires_at = None
        await db.commit()
        return True

    async def renew_orchestration_lease(
        self,
        db: AsyncSession,
        job_id: UUID,
        *,
        owner: str,
        generation: int,
        lease_seconds: int,
    ) -> bool:
        result = await db.execute(
            update(Job)
            .where(
                Job.job_id == job_id,
                Job.orchestration_owner == owner,
                Job.orchestration_generation == generation,
            )
            .values(orchestration_lease_expires_at=utc_now() + timedelta(seconds=lease_seconds))
        )
        await db.commit()
        return result.rowcount == 1

    async def rewind_for_invalidation(
        self,
        db: AsyncSession,
        job: Job,
        *,
        target: JobStatus,
        phase: WorkflowPhase,
        reason: str,
        actor_id: str = "supervisor",
        correlation_id: Optional[str] = None,
        commit: bool = False,
    ) -> Job:
        """Supervisor-owned exceptional rewind after evidence invalidation."""
        current = JobStatus(job.status)
        before = await self.snapshot_for(
            db, job, target=target, phase=phase, correlation_id=correlation_id
        )
        await self.checkpointer.save(
            db, job, kind="BEFORE", node_name=PHASE_NODE[phase].value,
            state=before, correlation_id=correlation_id,
        )
        await self._release_task_leases(db, job)
        job.status = target.value
        job.workflow_phase = phase.value
        job.active_node = PHASE_NODE[phase].value
        job.blocking_reason = reason
        job.last_transition = WorkflowEvent.BASELINE_INVALIDATED.value
        job.workflow_version += 1
        after = await self.snapshot_for(db, job, correlation_id=correlation_id)
        checkpoint = await self.checkpointer.save(
            db, job, kind="AFTER", node_name=job.active_node,
            state=after, correlation_id=correlation_id,
        )
        db.add(AuditEvent(
            job_id=job.job_id,
            event_type="WORKFLOW_TRANSITION",
            actor_type="SYSTEM",
            actor_id=actor_id,
            correlation_id=correlation_id,
            target_resource=str(job.job_id),
            payload={
                "workflow_id": str(job.workflow_id),
                "command": WorkflowEvent.BASELINE_INVALIDATED.value,
                "previous_state": current.value,
                "new_state": target.value,
                "new_phase": phase.value,
                "checkpoint_id": str(checkpoint.checkpoint_id),
                "reason": reason,
            },
        ))
        if commit:
            await db.commit()
            await db.refresh(job)
        return job


    async def record_baseline_revision(self, db: AsyncSession, job: Job, *, actor_id: str) -> None:
        """Own the artifact-revision rewind and dependent evidence invalidation."""
        try:
            await db.execute(
                update(WorkflowGate)
                .where(
                    WorkflowGate.job_id == job.job_id,
                    WorkflowGate.gate_type.in_(("G2", "G3", "G4")),
                    WorkflowGate.status.in_(("APPROVED", "PENDING")),
                )
                .values(
                    status="INVALIDATED",
                    blocking_reason="Baseline revised; new G2 approval required",
                )
            )
            await db.execute(
                update(TestResult)
                .where(
                    TestResult.test_case_id.in_(
                        select(TestCase.test_case_id).where(TestCase.job_id == job.job_id)
                    )
                )
                .values(
                    invalidated=True,
                    invalidation_reason="Characterization baseline revised",
                )
            )
            await db.execute(
                update(Module)
                .where(
                    Module.job_id == job.job_id
                )
                .values(
                    status="PENDING", lease_owner=None, lease_expires_at=None,
                    lease_heartbeat_at=None, lease_generation=Module.lease_generation + 1,
                )
            )
            await self.rewind_for_invalidation(
                db,
                job,
                target=JobStatus.CHARACTERIZING,
                phase=WorkflowPhase.CHARACTERIZATION,
                reason="Review captured evidence and request G2 freeze",
                actor_id=actor_id,
            )
            db.add(AuditEvent(job_id=job.job_id, event_type="BASELINE_REVISION_RECORDED", actor_type="USER", actor_id=actor_id,
                              payload={"status": job.status, "reason": job.blocking_reason}))
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.record_baseline_revision failed")
            raise

    async def request_baseline_review(self, db: AsyncSession, job_id: UUID, request, *, actor_id: str = "supervisor") -> dict:
        """Prepare G2 through the canonical transition; approval stays in GateService."""
        try:
            from app.services.phase5_service import latest, read_payload
            job = await db.scalar(
                select(Job).where(Job.job_id == job_id).with_for_update()
            )
            artifact = await latest(db, job_id)
            if (
                str(artifact.artifact_id) != request.suite_id
                or artifact.content_hash != request.content_hash
            ):
                raise ConflictException(
                    "Suite changed; reload the current version before G2 freeze"
                )
            payload = await read_payload(artifact)
            if any(c["outcome"] in ("FAILED", "NON_REPRODUCIBLE") for c in payload["cases"]):
                raise ConflictException(
                    "Failing baseline cases must be resolved before freeze"
                )
            gate = await db.scalar(
                select(WorkflowGate)
                .where(
                    WorkflowGate.job_id == job_id,
                    WorkflowGate.gate_type == "G2",
                    WorkflowGate.status.in_(("PENDING", "APPROVED")),
                )
                .order_by(WorkflowGate.version.desc())
                .limit(1)
            )
            if gate and str(artifact.artifact_id) in gate.artifact_hashes:
                return {
                    "gate_id": str(gate.gate_id),
                    "artifact_hashes": gate.artifact_hashes,
                    "status": gate.status,
                }
            if job.status != "CHARACTERIZING":
                raise ConflictException("G2 freeze requires characterization state")
    
            await self.transition(
                db,
                job_id,
                JobStatus.AWAITING_GATE_G2,
                actor_id=actor_id,
                reason="Review suite, gaps, normalization and disposable schema plan",
            )
            gate = await db.scalar(
                select(WorkflowGate).where(
                    WorkflowGate.job_id == job_id,
                    WorkflowGate.gate_type == "G2",
                    WorkflowGate.status == "PENDING",
                )
            )
            return {
                "gate_id": str(gate.gate_id),
                "artifact_hashes": gate.artifact_hashes,
                "status": gate.status,
            }
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.request_baseline_review failed")
            raise

    async def require_characterization_eligibility(self, db: AsyncSession, job: Job) -> None:
        try:
            if job.status not in {"CHARACTERIZING", "AWAITING_GATE_G2", "PLANNING", "AWAITING_GATE_G3", "CONVERTING", "VERIFYING", "INTEGRATING", "AWAITING_GATE_G4"}:
                raise ConflictException("Characterization requires an active workflow after G1")
            gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G1").order_by(WorkflowGate.version.desc()).limit(1))
            if gate is None or gate.status != "APPROVED":
                raise ConflictException("Characterization requires current human G1 approval")
            if job.budget_used_usd >= job.budget_limit_usd:
                raise ConflictException("Budget exhausted; characterization is blocked")
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.require_characterization_eligibility failed")
            raise

    async def require_planning_eligibility(self, db: AsyncSession, job: Job, *, require_state: bool = True) -> WorkflowGate:
        """Planning requires the latest approved G2 bound to current, frozen evidence."""
        try:
            gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G2").order_by(WorkflowGate.version.desc()).limit(1))
            if (require_state and job.status != JobStatus.PLANNING.value) or gate is None or gate.status != "APPROVED":
                raise ConflictException("Planning requires current human G2 approval")
            from app.services.phase5_service import decide_g2
            await decide_g2(db, gate, True, freeze_cases=False)
            return gate
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.require_planning_eligibility failed")
            raise

    async def require_conversion_eligibility(self, db: AsyncSession, job: Job, *, require_state: bool = True) -> dict:
        """Only current human G1/G2/G3 and frozen, untampered evidence authorize Phase 6."""
        try:
            from app.services.phase5_service import latest, read_payload
            allowed_states = ("CONVERTING", "VERIFYING") if require_state else ("CONVERTING", "VERIFYING", "INTEGRATING", "AWAITING_GATE_G4", "COMPLETED")
            if job.status not in allowed_states:
                raise ConflictException("Phase 6 requires the canonical conversion state")
            gates = {}
            for kind in ("G1", "G2", "G3"):
                gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == kind).order_by(WorkflowGate.version.desc()).limit(1))
                if gate is None or gate.status != "APPROVED":
                    raise ConflictException("Phase 6 requires current human G1, G2 and G3 approvals")
                gates[kind] = gate
            await self.require_planning_eligibility(db, job, require_state=False)
            suite = await latest(db, job.job_id)
            payload = await read_payload(suite)
            from app.models.test_case import TestCase
            for case in payload["cases"]:
                record = await db.get(TestCase, UUID(case["test_case_id"]))
                if record is None or not record.is_frozen or record.job_id != job.job_id:
                    raise ConflictException("Phase 6 requires frozen characterization definitions")
            # Prefer the exact artifact recorded in G3 approval, fallback to latest
            approved_art_ids = [UUID(k) for k in gates["G3"].artifact_hashes.keys() if re.fullmatch(r"[0-9a-fA-F-]{36}", k)]
            plan = None
            if approved_art_ids:
                plan = await db.scalar(
                    select(Artifact)
                    .where(
                        Artifact.job_id == job.job_id,
                        Artifact.artifact_id.in_(approved_art_ids),
                        Artifact.artifact_type.in_(["CONVERSION_PLAN", "ConversionPlan"]),
                    )
                    .order_by(Artifact.version.desc())
                    .limit(1)
                )
            if plan is None:
                plan = await db.scalar(
                    select(Artifact)
                    .where(
                        Artifact.job_id == job.job_id,
                        Artifact.artifact_type.in_(["CONVERSION_PLAN", "ConversionPlan"]),
                    )
                    .order_by(Artifact.created_at.desc(), Artifact.version.desc())
                    .limit(1)
                )
            if plan is None:
                raise ConflictException("An approved immutable conversion plan is required")
            approved_plan = await read_payload(plan)
            if gates["G3"].artifact_hashes.get(str(plan.artifact_id)) != plan.content_hash and plan.content_hash not in gates["G3"].artifact_hashes.values():
                raise ConflictException("G3 does not approve the current conversion plan")
            return {"baseline_hash": suite.content_hash, "baseline_id": str(suite.artifact_id), "cases": payload["cases"], "plan_hash": plan.content_hash, "approved_modules": approved_plan.get("modules", []), "gate_ids": {k: str(v.gate_id) for k, v in gates.items()}}
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.require_conversion_eligibility failed")
            raise

    async def require_integration_eligibility(self, db, job):
        try:
            from app.services.phase6_service import newest, detail
            current = await self.require_conversion_eligibility(db, job, require_state=job.status in ("CONVERTING", "VERIFYING"))
            modules = list((await db.execute(select(Module).where(Module.job_id == job.job_id))).scalars().all())
            if not modules:
                raise ConflictException("Integration requires real module attempts")
            for module in modules:
                attempt = await newest(db, module.module_id)
                if module.status != "VERIFIED" or not attempt or attempt.status != "VERIFIED":
                    raise ConflictException("Integration requires every module independently verified")
                evidence = (await detail(db, attempt))["evidence"]
                if evidence.get("baseline_hash") != current["baseline_hash"] or evidence.get("plan_hash") != current["plan_hash"] or not evidence.get("verification", {}).get("passed") or evidence.get("review", {}).get("status") != "PASS":
                    raise ConflictException("Integration evidence is stale, unobserved or rejected")
            return current
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.require_integration_eligibility failed")
            raise

    async def queue_integration(self, db, job, key, actor):
        try:
            from app.services.phase7_service import queue_integration
            from app.services.repository_workspace_service import repository_workspace_service
            if job.status not in ("CONVERTING", "VERIFYING", "INTEGRATING"):
                raise ConflictException("Integration requires the canonical verified/integrating state")
            await self.require_integration_eligibility(db, job)
            await repository_workspace_service.ensure_workspace(db, job)
            if job.status == "CONVERTING":
                await self.transition(db, job.job_id, JobStatus.VERIFYING, actor_id=actor, reason="All module verification evidence checked before integration")
            if job.status != "INTEGRATING":
                await self.transition(db, job.job_id, JobStatus.INTEGRATING, actor_id=actor, reason="Verified module evidence ready for controlled integration")
            return await queue_integration(db, job, key, actor)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.queue_integration failed")
            raise

    async def submit_final_review(self, db, job, report_hash, actor):
        try:
            from app.services.phase7_service import validate_package
            await validate_package(db, job, report_hash)
            if job.status not in ("INTEGRATING", "AWAITING_GATE_G4"):
                raise ConflictException("G4 submission requires an integrated candidate")
            await self.transition(db, job.job_id, JobStatus.AWAITING_GATE_G4, actor_id=actor, reason="Review exact integrated commit, JobReport, SBOM and uncovered behavior")
            return await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G4", WorkflowGate.status == "PENDING").order_by(WorkflowGate.version.desc()).limit(1))
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.submit_final_review failed")
            raise

    async def record_integration_disposition(self, db, job, run):
        try:
            current_job = await self._locked_job(db, job.job_id)
            await db.refresh(current_job)
            if current_job.status != "INTEGRATING":
                raise ConflictException("Workflow changed before integration disposition")
            current_job.integration_branch = run.output_payload.get("branch")
            current_job.blocking_reason = None if run.output_payload.get("status") == "READY_FOR_REVIEW" else "Integration conflict, missing SBOM or failing/unavailable full-system verification; inspect the versioned report"
            db.add(AuditEvent(job_id=job.job_id, event_type="INTEGRATION_" + run.output_payload["status"], actor_type="SYSTEM", actor_id="Supervisor", target_resource=str(run.run_id), payload=run.output_payload))
            await db.commit()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.record_integration_disposition failed")
            raise

    async def queue_module_conversion(self, db, job, module, key, actor, **kwargs):
        import logging

        from app.services.phase6_service import queue
        from app.services.repository_workspace_service import repository_workspace_service

        logical_task_id = f"p6-{module.module_id}"
        try:
            # This is the dispatch boundary used by API and graph callers. A
            # lease/attempt is not created until the exact job snapshot is ready.
            workspace_path = await repository_workspace_service.ensure_workspace(db, job)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "agent.dispatch.blocked_workspace | job_id=%s task_id=%s attempt_id=%s "
                "agent=CodeWriter workspace_path=%s source=%s worker_id=%s code=%s",
                job.job_id, logical_task_id, None,
                repository_workspace_service.get_workspace_path(job.job_id),
                repository_workspace_service._source_identity(job.source_repository), actor,
                getattr(exc, "code", type(exc).__name__),
            )
            raise
        logging.getLogger(__name__).info(
            "agent.dispatch.workspace_ready | job_id=%s task_id=%s attempt_id=%s "
            "agent=CodeWriter workspace_path=%s source=%s worker_id=%s",
            job.job_id, logical_task_id, None, workspace_path,
            repository_workspace_service._source_identity(job.source_repository), actor,
        )
        try:
            return await queue(db, job, module, key, actor, **kwargs)
        except Exception:
            logging.getLogger(__name__).exception("Supervisor.queue_module_conversion failed")
            raise

    async def record_module_disposition(self, db, job, module, attempt, run, status, reason):
        try:
            from app.models.base import utc_now
            now = utc_now()
            lease_expires = _normalize_dt(module.lease_expires_at)
            if (
                attempt.lease_generation != module.lease_generation
                or not module.lease_owner
                or not lease_expires
                or lease_expires <= now
            ):
                raise ConflictException(
                    "Stale worker result rejected by the supervisor lease fence"
                )
            if status == "VERIFIED":
                current = await self.require_conversion_eligibility(db, job)
                evidence = run.output_payload or {}
                if not evidence.get("verification", {}).get("passed") or not evidence.get("verification", {}).get("available") or evidence.get("review", {}).get("status") != "PASS" or evidence.get("baseline_hash") != current["baseline_hash"]:
                    raise ConflictException("Cannot verify a module without independent current execution and review evidence")
            module.status = attempt.status = status
            module.lease_owner = module.lease_expires_at = module.lease_heartbeat_at = None
            module.retry_count = attempt.attempt_number - 1
            attempt.failure_reason = reason
            attempt.completed_at = run.completed_at = now
            run.status = "SUCCEEDED" if status == "VERIFIED" else "FAILED"
            run.error_message = reason
            run.trace_payload = {**run.trace_payload, "events": [*run.trace_payload.get("events", []), status]}
            db.add(AuditEvent(job_id=job.job_id, event_type="MODULE_" + status, actor_type="SYSTEM", actor_id="Supervisor", target_resource=str(attempt.attempt_id), payload={"reason": reason, "attempt_number": attempt.attempt_number, "baseline_hash": (run.output_payload or {}).get("baseline_hash")}))
            await db.commit()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.record_module_disposition failed")
            raise

    async def run_module_conversion(self, db, job, module, *, user=None, repair_instruction=None):
        try:
            from app.services.phase6_service import execute_attempt, newest, detail
            from app.services.repository_workspace_service import repository_workspace_service
            await repository_workspace_service.ensure_workspace(db, job)
            previous = await newest(db, module.module_id) if repair_instruction else None
            attempt = await self.queue_module_conversion(db, job, module, str(__import__("uuid").uuid4()), str(user.user_id) if user else "Supervisor", previous=previous, rationale=repair_instruction)
            await execute_attempt(db, attempt.attempt_id)
            return await detail(db, attempt)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.run_module_conversion failed")
            raise

    async def run_phase6_pool(self, db, job, *, actor_id="Supervisor", correlation_id=None):
        """Dependency waves and bounded repairs, with a private DB session per parallel worker."""
        try:
            import asyncio
            from sqlalchemy.ext.asyncio import async_sessionmaker
            from app.services.phase6_service import execute_attempt, newest, detail
            from app.services.repository_workspace_service import repository_workspace_service
            await self.require_conversion_eligibility(db, job)
            await repository_workspace_service.ensure_workspace(db, job, correlation_id=correlation_id)
            factory = async_sessionmaker(db.bind, expire_on_commit=False)
            async def worker(attempt_id):
                try:
                    async with factory() as worker_db:
                        await execute_attempt(worker_db, attempt_id)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("Supervisor Phase 6 worker failed")
                    raise
            for wave in range(6 * max(1, job.max_parallel_tasks) + 100):
                modules = list((await db.execute(select(Module).where(Module.job_id == job.job_id).execution_options(populate_existing=True))).scalars().all())
                if not modules:
                    raise ConflictException("Phase 4 approved module inventory is required; no synthetic module may be created")
                pending = []
                for module in modules:
                    last = await newest(db, module.module_id)
                    if last and last.status == "QUEUED":
                        pending.append(last.attempt_id)
                    elif module.status in ("PENDING", "REPAIR_REQUIRED"):
                        try:
                            attempt = await self.queue_module_conversion(db, job, module, f"supervisor-{last.attempt_id if last else module.module_id}", actor_id, previous=last, rationale="Repair exact recorded verification/reviewer evidence" if last else None)
                            pending.append(attempt.attempt_id)
                        except ConflictException:
                            await db.rollback()
                            await db.refresh(job)
                            for item in modules:
                                await db.refresh(item)
                            # Pending dependencies/capacity do not authorize bypassing their blockers.
                            continue
                await db.commit()
                if not pending:
                    break
                await asyncio.gather(*(worker(a) for a in pending))
                await db.refresh(job)
            modules = list((await db.execute(select(Module).where(Module.job_id == job.job_id).execution_options(populate_existing=True))).scalars().all())
            ready = bool(modules)
            for module in modules:
                last = await newest(db, module.module_id)
                if not last or module.status != "VERIFIED" or last.status != "VERIFIED":
                    ready = False
                    continue
                evidence = (await detail(db, last))["evidence"]
                current = await self.require_conversion_eligibility(db, job)
                if evidence.get("baseline_hash") != current["baseline_hash"] or not evidence.get("verification", {}).get("passed"):
                    ready = False
            if ready:
                if job.status == "CONVERTING":
                    await self.transition(db, job.job_id, JobStatus.VERIFYING, actor_id=actor_id, correlation_id=correlation_id)
                await self.transition(db, job.job_id, JobStatus.INTEGRATING, actor_id=actor_id, correlation_id=correlation_id, reason="All modules have actual independent verification and review evidence")
            else:
                job.blocking_reason = "Phase 6 blocked: module execution, dependency, review or runtime evidence is incomplete. See module attempts."
                await db.commit()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Supervisor.run_phase6_pool failed")
            raise

    async def pause(self, db: AsyncSession, job_id: UUID, *, actor_id: str, reason: str, correlation_id: Optional[str] = None) -> Job:
        return await self.transition(db, job_id, JobStatus.PAUSED, actor_id=actor_id, reason=reason, correlation_id=correlation_id)

    async def execute_intake(
        self,
        db: AsyncSession,
        job_id: UUID,
        *,
        actor_id: str,
        user: Any = None,
        git_token: Optional[str] = None,
        preview_snapshot_id: Optional[str] = None,
        snapshot_fingerprint: Optional[str] = None,
        workspace_override: Optional[Path] = None,
        correlation_id: Optional[str] = None,
    ) -> tuple[Any, Any, Job]:
        """Run repository intake through the authoritative command boundary.

        Credentials remain request-scoped and are never stored in workflow state.
        A failed intake remains durably in INTAKE and can be reconciled/retried.
        """
        job = await self._locked_job(db, job_id)
        if job.status == JobStatus.CREATED.value:
            await db.rollback()
            job = await self.command(
                db, job_id, WorkflowEvent.INTAKE_STARTED,
                actor_id=actor_id, actor_type="USER",
                correlation_id=correlation_id,
                reason="Repository intake accepted by authoritative supervisor",
            )
        elif job.status != JobStatus.INTAKE.value:
            await db.rollback()
            raise ConflictException(f"Intake cannot run while job is {job.status}")
        else:
            await db.rollback()

        # Re-fetch unexpired job and user instance after rollback/command commit
        job = await self._locked_job(db, job_id)
        if actor_id:
            try:
                from app.models.user import User
                user = await db.scalar(select(User).where(User.user_id == UUID(actor_id)))
            except Exception:
                pass

        from app.services.phase4_orchestrator import phase4_orchestrator
        snapshot, inventory = await phase4_orchestrator.run_pipeline_stage1_intake(
            db, job, user,
            git_token=git_token,
            preview_snapshot_id=preview_snapshot_id,
            snapshot_fingerprint=snapshot_fingerprint,
            workspace_override=workspace_override,
            correlation_id=correlation_id,
        )
        job = await self.command(
            db, job_id, WorkflowEvent.ANALYSIS_STARTED,
            actor_id="supervisor", correlation_id=correlation_id,
            reason="Repository snapshot and deterministic inventory persisted",
        )
        return snapshot, inventory, job

    async def resume(self, db: AsyncSession, job_id: UUID, *, actor_id: str, correlation_id: Optional[str] = None) -> Job:
        job = await self._locked_job(db, job_id)
        if job.status != JobStatus.PAUSED.value or not job.paused_from_status:
            raise IllegalStateTransitionException(job.status, "RESUME", "Job has no resumable checkpoint state.")
        resume_to = JobStatus(job.paused_from_status)
        await db.rollback()
        return await self.transition(db, job_id, resume_to, actor_id=actor_id, correlation_id=correlation_id)

    async def cancel(self, db: AsyncSession, job_id: UUID, *, actor_id: str, correlation_id: Optional[str] = None) -> Job:
        return await self.transition(db, job_id, JobStatus.CANCELLED, actor_id=actor_id, correlation_id=correlation_id)

    async def recover(self, db: AsyncSession, job_id: UUID, *, correlation_id: Optional[str] = None) -> Job:
        return await self.reconcile_job(db, job_id, correlation_id=correlation_id)

    async def reconcile_job(
        self, db: AsyncSession, job_id: UUID, *, correlation_id: Optional[str] = None
    ) -> Job:
        """Reconstruct durable state and classify stale work before resumption."""
        from app.services.dependency_scheduler import dependency_scheduler

        stale_modules = await dependency_scheduler.reconcile_stale_leases(db, job_id)
        job = await self._locked_job(db, job_id)
        if job.status in {
            "ANALYZING", "CHARACTERIZING", "PLANNING", "CONVERTING",
            "VERIFYING", "INTEGRATING",
        }:
            from app.services.repository_workspace_service import repository_workspace_service

            try:
                await repository_workspace_service.ensure_workspace(
                    db, job, correlation_id=correlation_id or "service-restart"
                )
                job = await self._locked_job(db, job_id)
            except Exception as workspace_error:
                job.blocking_reason = (
                    "Repository workspace recovery failed during reconciliation: "
                    f"{getattr(workspace_error, 'message', str(workspace_error))}"
                )
                db.add(AuditEvent(
                    job_id=job.job_id,
                    event_type="WORKSPACE_RECOVERY_FAILED",
                    actor_type="SYSTEM",
                    actor_id="Supervisor",
                    correlation_id=correlation_id,
                    target_resource=str(job.job_id),
                    payload={
                        "error_code": getattr(
                            workspace_error, "code", type(workspace_error).__name__
                        ),
                        "during": "lease_reconciliation",
                    },
                ))
        now = utc_now()
        stale_before = now - timedelta(minutes=10)
        reconciled_runs: list[dict[str, str]] = []
        active_runs = list((await db.execute(
            select(AgentRun).where(
                AgentRun.job_id == job_id,
                AgentRun.status.in_(("QUEUED", "RUNNING")),
            ).with_for_update(skip_locked=True)
        )).scalars().all())
        for run in active_runs:
            attempt = await db.scalar(
                select(ModuleAttempt).where(ModuleAttempt.agent_run_id == run.run_id).limit(1)
            )
            classification = "SAFE_TO_RECONCILE"
            if attempt:
                module = await db.get(Module, attempt.module_id)
                lease_expires = _normalize_dt(module.lease_expires_at) if module else None
                lease_current = bool(
                    module
                    and module.lease_owner
                    and lease_expires
                    and lease_expires > now
                    and attempt.lease_generation == module.lease_generation
                )
                if not lease_current:
                    attempt.status = "BLOCKED"
                    attempt.failure_reason = "Recovered orphaned execution; worker lease is no longer current"
                    attempt.completed_at = now
                    run.status = "FAILED"
                    run.failure_classification = "ORPHANED_WORKER"
                    run.error_message = attempt.failure_reason
                    run.completed_at = now
                    classification = "SAFE_TO_RETRY"
            elif run.status == "RUNNING" and run.started_at <= stale_before:
                run.status = "FAILED"
                run.failure_classification = "ORPHANED_AGENT_RUN"
                run.error_message = "Application restarted without durable ownership for this diagnostic run"
                run.completed_at = now
                classification = "REQUIRES_HUMAN"
            else:
                continue
            reconciled_runs.append({"run_id": str(run.run_id), "classification": classification})

        pending_gate = await db.scalar(select(WorkflowGate).where(
            WorkflowGate.job_id == job.job_id,
            WorkflowGate.status == "PENDING",
        ).order_by(WorkflowGate.version.desc()).limit(1))
        if job.status.startswith("AWAITING_GATE_") and pending_gate is None:
            gate_type = job.status.removeprefix("AWAITING_GATE_")
            try:
                pending_gate = await self._materialize_gate(
                    db, job, gate_type, reason=f"Recovered missing pending {gate_type} gate"
                )
            except ConflictException as exc:
                job.blocking_reason = f"Recovery requires human intervention: {exc.message}"

        latest = await self.checkpointer.latest(db, job.job_id)
        state = await self.snapshot_for(db, job, correlation_id=correlation_id)
        state["events"] = [{
            "type": "RECOVERY_RECONCILED",
            "from_sequence": latest.sequence if latest else None,
            "stale_modules": stale_modules,
            "agent_runs": reconciled_runs,
        }]
        await self.checkpointer.save(
            db, job, kind="RECOVERY", node_name=job.active_node,
            state=state, correlation_id=correlation_id,
        )
        db.add(AuditEvent(
            job_id=job.job_id,
            event_type="WORKFLOW_RECOVERED",
            actor_type="SYSTEM",
            actor_id="supervisor",
            correlation_id=correlation_id,
            target_resource=str(job.workflow_id),
            payload={
                "stale_modules": stale_modules,
                "reconciled_runs": reconciled_runs,
                "pending_gate_id": str(pending_gate.gate_id) if pending_gate else None,
            },
        ))
        if not job.status.startswith("AWAITING_GATE_") and job.status != "PAUSED":
            outbox_key = f"recovery:{job.job_id}:{job.last_checkpoint_sequence}"
            existing_outbox = await db.scalar(
                select(WorkflowOutbox).where(WorkflowOutbox.idempotency_key == outbox_key)
            )
            if not existing_outbox:
                db.add(WorkflowOutbox(
                    job_id=job.job_id,
                    idempotency_key=outbox_key,
                    event_type="SUPERVISOR_RESUME",
                    payload={
                        "job_id": str(job.job_id),
                        "status": job.status,
                        "correlation_id": correlation_id or "service-restart",
                    },
                    status="PENDING",
                ))
        await db.commit()
        await db.refresh(job)
        return job

    async def recover_active_jobs(
        self,
        db: AsyncSession,
        *,
        job_ids: Optional[list[UUID]] = None,
        auto_schedule: bool = True,
    ) -> int:
        """Reconcile non-terminal jobs after a service restart.

        Pattern:
        1. State reconciliation
        2. Recovery checkpoint & Audit trail
        3. Transactional Outbox event
        4. Commit transaction
        5. Background supervisor drive (if auto_schedule is True)
        """
        if job_ids is not None:
            active_ids = list(job_ids)
        else:
            executing_statuses = (
                "INTAKE", "ANALYZING", "CHARACTERIZING", "PLANNING",
                "CONVERTING", "VERIFYING", "INTEGRATING",
            )
            active_ids = list((await db.execute(
                select(Job.job_id)
                .where(Job.status.in_(executing_statuses))
                .order_by(Job.created_at.desc())
            )).scalars().all())

        recovered = 0
        to_schedule: list[UUID] = []
        for job_id in active_ids:
            try:
                job = await self.reconcile_job(db, job_id, correlation_id="service-restart")
                if not job.status.startswith("AWAITING_GATE_") and job.status != "PAUSED":
                    to_schedule.append(job_id)
            except Exception:
                await db.rollback()
                continue
            recovered += 1

        if auto_schedule and to_schedule:
            async def drain_recovery_queue() -> None:
                for recovered_job_id in to_schedule:
                    try:
                        task = self.schedule_drive(
                            recovered_job_id, correlation_id="service-restart"
                        )
                        await task
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # Reconciliation and its durable outbox record already
                        # succeeded. Continue draining other recoverable jobs.
                        continue

            self._recovery_task = asyncio.create_task(
                drain_recovery_queue(), name="supervisor-recovery-drain"
            )

        return recovered

    async def drive_job_sync(
        self,
        db: AsyncSession,
        job_id: UUID,
        *,
        correlation_id: Optional[str] = None,
        max_steps: int = 1,
    ) -> Job:
        """Synchronously step/drive the supervisor for deterministic tests."""
        return await self.run_orchestration_loop(
            db, job_id, correlation_id=correlation_id, max_steps=max_steps
        )

    async def run_orchestration_loop(
        self,
        db: AsyncSession,
        job_id: UUID,
        *,
        actor_id: str = "supervisor",
        correlation_id: Optional[str] = None,
        max_steps: int = 50,
    ) -> Job:
        """Executes the durable LangGraph supervisor loop until wait state, escalation, or completion."""
        import asyncio
        corr_id = correlation_id or f"loop-{uuid.uuid4().hex[:12]}"
        from app.services.supervisor_graph import authoritative_supervisor_graph

        job = await db.get(Job, job_id)
        if not job:
            raise NotFoundException("Job", str(job_id))
        if JobStatus(job.status) in JobStateMachine.TERMINAL_STATES:
            return job

        owner = f"supervisor:{uuid.uuid4().hex}"
        lease_seconds = max(60, min(300, max_steps * 5))
        generation = await self.acquire_orchestration_lease(
            db, job_id, owner=owner, lease_seconds=lease_seconds
        )
        if generation is None:
            return await db.get(Job, job_id)

        initial_state = {
            **(await self.snapshot_for(db, job, correlation_id=corr_id)),
            "correlation_id": corr_id,
            "events": [],
            "loop_count": 0,
            "max_loops": max_steps,
            "orchestration_owner": owner,
            "orchestration_generation": generation,
        }

        heartbeat_stop = asyncio.Event()
        lease_lost = asyncio.Event()

        async def heartbeat() -> None:
            from app.core.database import AsyncSessionLocal
            while not heartbeat_stop.is_set():
                try:
                    await asyncio.wait_for(
                        heartbeat_stop.wait(), timeout=max(5, lease_seconds // 3)
                    )
                except asyncio.TimeoutError:
                    async with AsyncSessionLocal() as heartbeat_db:
                        renewed = await self.renew_orchestration_lease(
                            heartbeat_db, job_id, owner=owner,
                            generation=generation, lease_seconds=lease_seconds,
                        )
                        if not renewed:
                            lease_lost.set()
                            return

        heartbeat_task = asyncio.create_task(
            heartbeat(), name=f"supervisor-heartbeat-{job_id}"
        )
        try:
            graph_task = asyncio.create_task(authoritative_supervisor_graph.ainvoke(initial_state))
            lease_lost_task = asyncio.create_task(lease_lost.wait())
            done, _ = await asyncio.wait(
                {graph_task, lease_lost_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if lease_lost_task in done and lease_lost.is_set() and not graph_task.done():
                graph_task.cancel()
                try:
                    await graph_task
                except asyncio.CancelledError:
                    pass
                raise ConflictException("Supervisor orchestration lease was lost; execution stopped for recovery")
            lease_lost_task.cancel()
            try:
                await lease_lost_task
            except asyncio.CancelledError:
                pass
            await graph_task
        finally:
            heartbeat_stop.set()
            await heartbeat_task
            await self.release_orchestration_lease(
                db, job_id, owner=owner, generation=generation
            )
        await db.refresh(job)
        return job

    async def drive_job(
        self, job_id: UUID, *, correlation_id: Optional[str] = None, max_steps: int = 50
    ) -> None:
        """Background entrypoint used by APIs and restart recovery."""
        import logging
        from app.core.database import AsyncSessionLocal
        from app.models.job import Job
        from app.models.audit import AuditEvent

        logger = logging.getLogger(__name__)

        async with self._drive_semaphore:
            try:
                async with AsyncSessionLocal() as db:
                    await self.run_orchestration_loop(
                        db, job_id, correlation_id=correlation_id, max_steps=max_steps
                    )
            except Exception as exc:
                logger.exception("Supervisor orchestration crashed for job %s: %s", job_id, exc)
                try:
                    async with AsyncSessionLocal() as err_db:
                        j = await err_db.get(Job, job_id)
                        if j:
                            j.blocking_reason = f"Supervisor run crashed: {exc}"
                            err_db.add(
                                AuditEvent(
                                    job_id=job_id,
                                    event_type="SUPERVISOR_CRASH",
                                    actor_type="SYSTEM",
                                    actor_id="Supervisor",
                                    correlation_id=correlation_id,
                                    target_resource=str(job_id),
                                    payload={"error": str(exc), "type": type(exc).__name__},
                                )
                            )
                            await err_db.commit()
                except Exception:
                    logger.exception("Failed to persist supervisor crash details for job %s", job_id)
                raise

    def schedule_drive(self, job_id: UUID, *, correlation_id: Optional[str] = None):
        """Schedule only the authoritative supervisor loop in this process."""
        import asyncio
        import logging
        key = str(job_id)
        existing = self._running_tasks.get(key)
        if existing and not existing.done():
            return existing
        task = asyncio.create_task(
            self.drive_job(job_id, correlation_id=correlation_id),
            name=f"supervisor-{job_id}",
        )
        self._running_tasks[key] = task

        def _cleanup(t: asyncio.Task) -> None:
            if self._running_tasks.get(key) is t:
                self._running_tasks.pop(key, None)
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    logging.getLogger(__name__).error(
                        "Supervisor background task %s terminated with exception: %s", key, exc
                    )

        task.add_done_callback(_cleanup)
        return task


    async def recover_failed_phase6_job(
        self,
        db: AsyncSession,
        job_id: UUID,
        rationale: str,
        target_module_id: Optional[UUID] = None,
        *,
        actor_id: str = "SupervisorRecovery",
    ) -> Dict[str, Any]:
        """Authoritative recovery of a failed Phase 6 job after diagnosing and fixing defects.
        
        Strictly enforces:
        1. G1, G2, G3 human approvals exist and are valid.
        2. No live worker holds orchestration or module leases.
        3. Workspace repository integrity is valid.
        4. Budget limit is not exceeded.
        5. Preserves attempt history and retry counts.
        6. Persists an audited RECOVERY checkpoint and audit log.
        """
        job = await db.get(Job, job_id)
        if not job:
            raise NotFoundException("Job", str(job_id))

        gates = (await db.execute(
            select(WorkflowGate).where(
                WorkflowGate.job_id == job_id,
                WorkflowGate.status == "APPROVED"
            )
        )).scalars().all()
        approved_types = {g.gate_type for g in gates}
        if not {"G1", "G2", "G3"}.issubset(approved_types):
            raise ConflictException(f"Cannot recover Phase 6 job: missing approved gates (approved: {approved_types})")

        now = utc_now()
        if job.orchestration_owner and job.orchestration_lease_expires_at:
            if _normalize_dt(job.orchestration_lease_expires_at) > now:
                raise ConflictException(f"Job is actively leased to worker {job.orchestration_owner}")

        if job.budget_limit_usd and job.budget_used_usd and job.budget_used_usd >= job.budget_limit_usd:
            raise ConflictException("Cannot recover job: budget exhausted")

        from app.services.repository_workspace_service import repository_workspace_service
        ws_valid = await repository_workspace_service.validate_workspace(job.job_id)
        if not ws_valid.is_ready:
            raise ConflictException(f"Repository workspace is invalid: {ws_valid.error_message}")

        target_mod = None
        if target_module_id:
            target_mod = await db.get(Module, target_module_id)
            if not target_mod or target_mod.job_id != job.job_id:
                raise NotFoundException("Module", str(target_module_id))
            target_mod.status = "PENDING"
            target_mod.lease_owner = None
            target_mod.lease_expires_at = None
            target_mod.lease_generation += 1

        correlation_id = str(uuid.uuid4())
        checkpoint_state = {
            "action": "RECOVER_PHASE6",
            "rationale": rationale,
            "target_module_id": str(target_module_id) if target_module_id else None,
            "previous_status": job.status,
            "previous_blocking_reason": job.blocking_reason,
            "status": "CONVERTING",
            "active_node": "supervisor",
        }
        checkpoint = await self.checkpointer.save(
            db,
            job,
            kind="RECOVERY",
            node_name="supervisor",
            state=checkpoint_state,
            correlation_id=correlation_id,
        )

        job.status = "CONVERTING"
        job.active_node = "supervisor"
        job.blocking_reason = None
        job.last_transition = "RECOVERED"
        job.orchestration_owner = None
        job.orchestration_lease_expires_at = None
        job.orchestration_generation += 1

        db.add(AuditEvent(
            job_id=job.job_id,
            event_type="JOB_RECOVERED",
            actor_type="SYSTEM",
            actor_id=actor_id,
            target_resource=str(job.job_id),
            payload={
                "rationale": rationale,
                "target_module_id": str(target_module_id) if target_module_id else None,
                "checkpoint_sequence": checkpoint.sequence,
            },
        ))
        await db.commit()
        return {
            "job_id": str(job.job_id),
            "status": job.status,
            "target_module": target_mod.name if target_mod else None,
            "checkpoint_sequence": checkpoint.sequence,
        }

supervisor_service = SupervisorService()

