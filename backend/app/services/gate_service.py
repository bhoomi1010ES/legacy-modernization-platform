"""Version-bound G1-G4 gate creation, decisions, and invalidation."""

from datetime import timezone
from typing import Optional
import logging
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, ForbiddenException, NotFoundException
from app.domain.state_machine import GatePolicy, RBACPolicy
from app.models.artifact import Artifact, ArtifactType
from app.models.audit import AuditEvent
from app.models.gate import GateDecision
from app.models.job import Job
from app.models.test_case import TestCase, TestResult
from app.models.workflow import WorkflowGate
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, GateType
from app.schemas.jobs import JobStatus
from app.services.supervisor_service import SupervisorService

logger = logging.getLogger(__name__)


GATE_WAITING_STATUS = {
    GateType.G1: JobStatus.AWAITING_GATE_G1,
    GateType.G2: JobStatus.AWAITING_GATE_G2,
    GateType.G3: JobStatus.AWAITING_GATE_G3,
    GateType.G4: JobStatus.AWAITING_GATE_G4,
}
GATE_SUCCESS_STATUS = {
    GateType.G1: JobStatus.CHARACTERIZING,
    GateType.G2: JobStatus.PLANNING,
    GateType.G3: JobStatus.CONVERTING,
    GateType.G4: JobStatus.COMPLETED,
}
GATE_REVISION_STATUS = {
    GateType.G1: JobStatus.ANALYZING,
    GateType.G2: JobStatus.CHARACTERIZING,
    GateType.G3: JobStatus.PLANNING,
    GateType.G4: JobStatus.CONVERTING,
}


class GateService:
    def __init__(self, supervisor: Optional[SupervisorService] = None):
        if supervisor is not None:
            self.supervisor = supervisor
        else:
            from app.services.supervisor_service import supervisor_service
            self.supervisor = supervisor_service

    async def create_pending(
        self,
        db: AsyncSession,
        job_id: UUID,
        gate_type: GateType,
        *,
        artifact_ids: list[UUID],
        blocking_reason: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> WorkflowGate:
        """Return the pending gate created by the supervisor transition.

        This compatibility method deliberately cannot create gates, because a
        separately-created gate would bypass the workflow transition/checkpoint.
        """
        job = await db.scalar(select(Job).where(Job.job_id == job_id).with_for_update())
        if not job:
            raise NotFoundException("Job", str(job_id))
        expected = GATE_WAITING_STATUS[gate_type]
        if job.status != expected.value:
            raise ConflictException(f"{gate_type.value} can only be opened while job is {expected.value}.")
        gate = await db.scalar(select(WorkflowGate).where(
            WorkflowGate.job_id == job_id,
            WorkflowGate.gate_type == gate_type.value,
            WorkflowGate.status == "PENDING",
        ).order_by(WorkflowGate.version.desc()).limit(1))
        if not gate:
            raise ConflictException("Pending gates may only be materialized by a supervisor transition.")
        supplied = {str(item) for item in artifact_ids}
        if supplied and supplied != set(gate.artifact_ids or []):
            raise ConflictException("Supplied evidence does not match the authoritative gate package.")
        return gate

    async def decide(
        self,
        db: AsyncSession,
        gate_id: UUID,
        payload: GateDecisionRequest,
        *,
        actor_id: UUID,
        actor_role: str,
        correlation_id: Optional[str] = None,
    ) -> tuple[GateDecision, WorkflowGate, Job, bool]:
        if payload.idempotency_key:
            existing = await db.scalar(select(GateDecision).where(GateDecision.idempotency_key == payload.idempotency_key))
            if existing:
                if existing.gate_id != gate_id or existing.reviewer_user_id != actor_id:
                    raise ConflictException("Idempotency key belongs to another gate or reviewer")
                gate = await db.get(WorkflowGate, existing.gate_id)
                job = await db.get(Job, existing.job_id)
                if gate.gate_type == "G2" and existing.decision == "APPROVED":
                    if gate.status != "APPROVED":
                        raise ConflictException("G2 approval was invalidated; stale approval cannot be replayed")
                    from app.services.phase5_service import decide_g2
                    await decide_g2(db, gate, True, freeze_cases=False)
                if gate.gate_type == "G4" and existing.decision == "APPROVED":
                    if gate.status != "APPROVED":
                        raise ConflictException("Stale G4 approval cannot be replayed")
                    from app.services.phase7_service import validate_package
                    report = await db.scalar(select(Artifact).where(Artifact.job_id == job.job_id, Artifact.artifact_type == ArtifactType.JOB_REPORT.value).order_by(Artifact.version.desc()).limit(1))
                    await validate_package(db, job, report.content_hash if report else "", gate=gate)
                return existing, gate, job, True

        gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.gate_id == gate_id).with_for_update())
        if not gate:
            raise NotFoundException("Gate", str(gate_id))
        job = await db.scalar(select(Job).where(Job.job_id == gate.job_id).with_for_update())
        if not job:
            raise NotFoundException("Job", str(gate.job_id))

        if gate.status != "PENDING":
            raise ConflictException(f"Gate already has terminal status {gate.status}.")
        gate_type = GateType(gate.gate_type)
        if job.status != GATE_WAITING_STATUS[gate_type].value:
            raise ConflictException("Gate is stale relative to the current workflow state.")

        # Enforce separation of duties: job creator cannot approve or reject gates for their own job
        creator_id = getattr(job, "created_by_user_id", None) or getattr(job, "owner_user_id", None)
        if actor_id and creator_id and str(creator_id) == str(actor_id):
            raise ForbiddenException(
                "Separation of duties violation: Job creator cannot approve or reject gates for their own job."
            )

        # RBAC removed: all authenticated human users can decide gates
        effective_role = actor_role or "USER" 

        GatePolicy.validate_decision(
            gate_type,
            payload.decision,
            payload.rationale,
            actor_role,
            is_human=True,
            gap_options=payload.options,
        )
        if dict(payload.artifact_hashes) != dict(gate.artifact_hashes):
            raise ConflictException("Artifact version changed during review. Reload the gate before deciding.")

        if gate_type == GateType.G2:
            from app.services.phase5_service import decide_g2
            await decide_g2(db, gate, payload.decision == DecisionOutcome.APPROVED)
        if gate_type == GateType.G4:
            from app.services.phase7_service import decide_g4
            await decide_g4(db, job, gate, payload)

        decision = GateDecision(
            job_id=gate.job_id,
            gate_id=gate.gate_id,
            gate_type=gate.gate_type,
            decision=payload.decision.value,
            rationale=payload.rationale.strip(),
            waivers=[item.model_dump() for item in payload.waivers],
            selected_options=dict(payload.options or {}),
            artifact_hashes=dict(payload.artifact_hashes),
            idempotency_key=payload.idempotency_key,
            reviewer_user_id=actor_id,
        )
        from app.models.base import utc_now
        decision.decided_at = utc_now()
        db.add(decision)
        gate.status = payload.decision.value
        gate.decided_at = decision.decided_at
        job.blocking_reason = None

        target = GATE_SUCCESS_STATUS[gate_type] if payload.decision == DecisionOutcome.APPROVED else GATE_REVISION_STATUS[gate_type]
        if gate_type == GateType.G3 and payload.decision == DecisionOutcome.APPROVED:
            if not await self._conversion_prerequisites_approved(db, gate.job_id, current_gate=gate):
                raise ConflictException("Conversion requires current G1, G2 and G3 approvals.")
        if gate_type == GateType.G4 and payload.decision == DecisionOutcome.APPROVED:
            from app.services.phase7_service import record_delivery
            await record_delivery(db, job, gate, decision)

        # Keep decision, supervisor transition, checkpoints and audit in one transaction.
        await db.flush()
        await self.supervisor.transition(
            db,
            job.job_id,
            target,
            actor_id=str(actor_id),
            correlation_id=correlation_id,
            reason=(
                f"Human {gate_type.value} approval accepted"
                if payload.decision == DecisionOutcome.APPROVED
                else f"Human {gate_type.value} requested revision"
            ),
            commit=False,
        )
        db.add(AuditEvent(
            job_id=job.job_id,
            event_type="GATE_DECIDED",
            actor_type="USER",
            actor_id=str(actor_id),
            correlation_id=correlation_id,
            target_resource=str(gate.gate_id),
            payload={
                "gate_type": gate.gate_type,
                "version": gate.version,
                "decision": payload.decision.value,
                "rationale": payload.rationale.strip(),
                "artifact_hashes": dict(payload.artifact_hashes),
                "selected_options": dict(payload.options or {}),
            },
        ))
        await db.commit()
        await db.refresh(decision)
        await db.refresh(gate)
        await db.refresh(job)
        if decision.decided_at and decision.decided_at.tzinfo is None:
            decision.decided_at = decision.decided_at.replace(tzinfo=timezone.utc)
        if gate.decided_at and gate.decided_at.tzinfo is None:
            gate.decided_at = gate.decided_at.replace(tzinfo=timezone.utc)

        # Resume only the authoritative supervisor graph after commit.
        if payload.decision == DecisionOutcome.APPROVED and gate_type in (GateType.G1, GateType.G2, GateType.G3):
            try:
                self.supervisor.schedule_drive(job.job_id, correlation_id=correlation_id)
            except Exception as auto_exc:
                logger.warning("Failed to auto-trigger continuous pipeline | job_id=%s | %s", job.job_id, auto_exc)

        return decision, gate, job, False

    async def _conversion_prerequisites_approved(
        self, db: AsyncSession, job_id: UUID, *, current_gate: Optional[WorkflowGate] = None
    ) -> bool:
        for gate_type in (GateType.G1, GateType.G2, GateType.G3):
            if current_gate and current_gate.gate_type == gate_type.value and current_gate.status == "APPROVED":
                continue
            latest = await db.scalar(
                select(WorkflowGate)
                .where(WorkflowGate.job_id == job_id, WorkflowGate.gate_type == gate_type.value)
                .order_by(WorkflowGate.version.desc())
                .limit(1)
            )
            if not latest or latest.status != "APPROVED":
                return False
        return True

    async def invalidate_for_artifact(
        self, db: AsyncSession, job_id: UUID, artifact_id: UUID, new_hash: str, *, reason: str
    ) -> list[WorkflowGate]:
        gates = list((await db.execute(
            select(WorkflowGate)
            .where(WorkflowGate.job_id == job_id, WorkflowGate.status == "APPROVED")
            .order_by(WorkflowGate.version.desc())
            .with_for_update()
        )).scalars().all())
        invalidated: list[WorkflowGate] = []
        artifact_key = str(artifact_id)
        affected_types: set[str] = set()
        for gate in gates:
            old_hash = gate.artifact_hashes.get(artifact_key)
            if old_hash is not None and old_hash != new_hash:
                gate.status = "INVALIDATED"
                gate.blocking_reason = reason
                invalidated.append(gate)
                affected_types.add(gate.gate_type)

        if affected_types:
            order = ["G1", "G2", "G3", "G4"]
            earliest = min(order.index(item) for item in affected_types)
            downstream = order[earliest + 1 :]
            if downstream:
                downstream_gates = list((await db.execute(
                    select(WorkflowGate).where(
                        WorkflowGate.job_id == job_id,
                        WorkflowGate.gate_type.in_(downstream),
                        WorkflowGate.status == "APPROVED",
                    ).with_for_update()
                )).scalars().all())
                for gate in downstream_gates:
                    gate.status = "INVALIDATED"
                    gate.blocking_reason = f"Upstream artifact invalidated: {reason}"
                    invalidated.append(gate)
            await db.execute(
                update(TestResult)
                .where(TestResult.test_case_id.in_(select(TestCase.test_case_id).where(TestCase.job_id == job_id)))
                .values(invalidated=True, invalidation_reason=reason)
            )
            job = await db.scalar(select(Job).where(Job.job_id == job_id).with_for_update())
            route = {0: JobStatus.ANALYZING, 1: JobStatus.CHARACTERIZING, 2: JobStatus.PLANNING, 3: JobStatus.CONVERTING}[earliest]
            from app.schemas.workflow import WorkflowPhase
            phase = {
                JobStatus.ANALYZING: WorkflowPhase.INTAKE,
                JobStatus.CHARACTERIZING: WorkflowPhase.CHARACTERIZATION,
                JobStatus.PLANNING: WorkflowPhase.PLANNING,
                JobStatus.CONVERTING: WorkflowPhase.CONVERSION,
            }[route]
            await self.supervisor.rewind_for_invalidation(
                db,
                job,
                target=route,
                phase=phase,
                reason=reason,
            )
            db.add(AuditEvent(
                job_id=job_id,
                event_type="GATE_APPROVALS_INVALIDATED",
                actor_type="SYSTEM",
                actor_id="supervisor",
                payload={"artifact_id": artifact_key, "new_hash": new_hash, "reason": reason, "gate_ids": [str(g.gate_id) for g in invalidated]},
            ))
        await db.commit()
        return invalidated


gate_service = GateService()
