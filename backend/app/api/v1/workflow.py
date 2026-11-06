"""Durable workflow, progress-event and versioned gate APIs."""

from typing import Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_job_access
from app.core.database import get_db
from app.core.errors import ForbiddenException, NotFoundException
from app.domain.state_machine import RBACPolicy
from app.models.audit import AuditEvent
from app.models.job import Job, JobMembership
from app.models.phase4 import RepositorySnapshotModel
from app.models.user import User
from app.models.workflow import WorkflowGate
from app.schemas.gates import GateDecisionRequest, GateType
from app.schemas.jobs import JobStatus
from app.schemas.workflow import (
    GateDecisionResult,
    PhaseProgress,
    WorkflowEventResponse,
    WorkflowEventsResponse,
    WorkflowGateResponse,
    WorkflowNode,
    WorkflowStateResponse,
    WorkspaceProgress,
)
from app.services.gate_service import gate_service
from app.services.supervisor_service import PHASE_NODE, STATUS_NODE, supervisor_service
from app.schemas.workflow import WorkflowPhase

router = APIRouter(tags=["Workflow Supervisor"])

PHASES = [
    (WorkflowNode.INTAKE, "Repository intake"),
    (WorkflowNode.GATE_G1, "G1 feasibility decision"),
    (WorkflowNode.CHARACTERIZATION, "Characterization suite"),
    (WorkflowNode.SCHEMA_DATA, "Schema and data analysis"),
    (WorkflowNode.GATE_G2, "G2 characterization freeze"),
    (WorkflowNode.PLANNING, "Conversion planning"),
    (WorkflowNode.GATE_G3, "G3 plan approval"),
    (WorkflowNode.CONVERSION, "Dependency-aware conversion"),
    (WorkflowNode.VERIFICATION, "Behavioral verification"),
    (WorkflowNode.INTEGRATION, "Integration"),
    (WorkflowNode.GATE_G4, "G4 delivery review"),
    (WorkflowNode.COMPLETE, "Delivery complete"),
]


def _gate_response(gate: WorkflowGate, can_decide: bool = False) -> WorkflowGateResponse:
    return WorkflowGateResponse(
        gate_id=str(gate.gate_id),
        job_id=str(gate.job_id),
        gate_type=GateType(gate.gate_type),
        version=gate.version,
        status=gate.status,
        artifact_ids=list(gate.artifact_ids or []),
        artifact_hashes=dict(gate.artifact_hashes or {}),
        blocking_reason=gate.blocking_reason,
        requested_at=gate.requested_at.isoformat(),
        decided_at=gate.decided_at.isoformat() if gate.decided_at else None,
        allowed_actions=["approve", "reject", "request_changes"] if can_decide and gate.status == "PENDING" else [],
    )


async def _gate_access(db: AsyncSession, gate_id: UUID, user: User, permission: str = None) -> tuple[WorkflowGate, str]:
    gate = await db.get(WorkflowGate, gate_id)
    if not gate:
        raise NotFoundException("Gate", str(gate_id))
    # RBAC removed: all authenticated human users can access and decide gates
    return gate, "USER" 


@router.get("/jobs/{job_id}/workflow", response_model=WorkflowStateResponse)
async def get_workflow(
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowStateResponse:
    job, user = access
    snapshot = await supervisor_service.snapshot_for(db, job)
    current = STATUS_NODE.get(JobStatus(job.status), WorkflowNode.FAILED)
    current_phase = WorkflowPhase(snapshot["current_phase"])
    timeline_current = (
        STATUS_NODE.get(JobStatus(job.paused_from_status), WorkflowNode.INTAKE)
        if job.status == "PAUSED" and job.paused_from_status else current
    )
    if job.status != "PAUSED":
        timeline_current = PHASE_NODE.get(current_phase, timeline_current)
    if job.status in ("FAILED", "CANCELLED") and job.active_node:
        try:
            timeline_current = WorkflowNode(job.active_node)
        except (ValueError, KeyError):
            pass
    current_index = next((i for i, (node, _) in enumerate(PHASES) if node == timeline_current), 0)
    phases: list[PhaseProgress] = []
    for index, (node, label) in enumerate(PHASES):
        phase_status = "SUCCEEDED" if index < current_index else "PENDING"
        if index == current_index:
            phase_status = "BLOCKED" if job.status.startswith("AWAITING_GATE_") or job.status == "PAUSED" else "RUNNING"
        if job.status == "FAILED" and index == current_index:
            phase_status = "FAILED"
        if job.status == "CANCELLED" and index == current_index:
            phase_status = "CANCELLED"
        phases.append(PhaseProgress(node=node, label=label, status=phase_status))
    membership = await db.scalar(select(JobMembership).where(
        JobMembership.job_id == job.job_id, JobMembership.user_id == user.user_id
    ))
    effective_role = membership.role_id if membership else "DEVELOPER"
    allowed = []
    if job.status == "PAUSED":
        allowed.extend(["resume", "cancel"])
    elif job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
        allowed.extend(["pause", "cancel"])
    repository_snapshot = await db.scalar(
        select(RepositorySnapshotModel)
        .where(RepositorySnapshotModel.job_id == job.job_id)
        .order_by(RepositorySnapshotModel.version.desc())
        .limit(1)
    )
    latest_workspace_event = await db.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.job_id == job.job_id,
            AuditEvent.event_type.like("WORKSPACE_%"),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    )
    from app.services.repository_workspace_service import repository_workspace_service

    workspace_validation = await repository_workspace_service.validate_workspace(
        job.job_id,
        expected_commit=repository_snapshot.commit_sha if repository_snapshot else None,
        expected_source=job.source_repository,
    )
    workspace_status = "READY" if workspace_validation.is_ready else "UNAVAILABLE"
    if workspace_validation.is_ready:
        # Filesystem/Git/identity validation is current evidence. A historical
        # recovery-started audit must not make a restored workspace look stuck.
        workspace_status = "READY"
    elif not job.source_repository:
        workspace_status = "UNAVAILABLE"
    elif latest_workspace_event and latest_workspace_event.event_type == "WORKSPACE_RECOVERY_STARTED":
        workspace_status = "RECOVERING"
    elif latest_workspace_event and latest_workspace_event.event_type == "WORKSPACE_RECOVERY_FAILED":
        workspace_status = "RECOVERY_FAILED"
    elif not workspace_validation.is_ready and repository_snapshot is None:
        workspace_status = "RECEIVED"
    workspace_progress = WorkspaceProgress(
        status=workspace_status,
        received=bool(job.source_repository),
        staged=workspace_validation.path is not None and workspace_validation.path.exists(),
        validated=workspace_validation.is_ready,
        ready=workspace_validation.is_ready,
        workspace_name=(
            workspace_validation.path.name if workspace_validation.path is not None else None
        ),
        commit_sha=workspace_validation.commit_sha,
        error_code=workspace_validation.error_code,
        message=(
            "Repository workspace restored and ready."
            if workspace_validation.is_ready
            else workspace_validation.error_message
        ),
    )
    return WorkflowStateResponse(
        job_id=str(job.job_id), workflow_id=str(job.workflow_id or job.job_id),
        current_phase=current_phase, status=JobStatus(job.status), active_node=current,
        blocking_reason=job.blocking_reason, checkpoint_sequence=job.last_checkpoint_sequence,
        workflow_version=job.workflow_version, budget_used=float(job.budget_used_usd),
        budget_limit=float(job.budget_limit_usd),
        budget_warning=float(job.budget_limit_usd) > 0 and float(job.budget_used_usd) / float(job.budget_limit_usd) >= 0.8,
        allowed_actions=allowed, phases=phases, workspace=workspace_progress,
        active_task_ids=snapshot.get("active_task_ids", []),
        completed_task_ids=snapshot.get("completed_task_ids", []),
        blocked_task_ids=snapshot.get("blocked_task_ids", []),
        failed_task_ids=snapshot.get("failed_task_ids", []),
        pending_gate_id=snapshot.get("pending_gate_id"),
        approved_artifact_versions=snapshot.get("approved_artifact_versions", {}),
        artifact_hashes=snapshot.get("artifact_hashes", {}),
        retry_counts=snapshot.get("retry_counts", {}),
        dependency_state=snapshot.get("dependency_state", {}),
        last_transition=snapshot.get("last_transition"),
        failure_reason=snapshot.get("failure_reason"),
        terminal_reason=snapshot.get("terminal_reason"),
        updated_at=job.updated_at.isoformat(),
    )


@router.get("/jobs/{job_id}/events", response_model=WorkflowEventsResponse)
async def get_workflow_events(
    after: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowEventsResponse:
    job, _ = access
    query = select(AuditEvent).where(AuditEvent.job_id == job.job_id)
    if after:
        query = query.where(AuditEvent.event_id > UUID(after))
    rows = list((await db.execute(query.order_by(AuditEvent.created_at.asc()).limit(limit + 1))).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    return WorkflowEventsResponse(
        items=[WorkflowEventResponse(
            event_id=str(item.event_id), event_type=item.event_type, actor_type=item.actor_type,
            actor_id=item.actor_id, correlation_id=item.correlation_id,
            payload=item.payload or {}, created_at=item.created_at.isoformat(),
        ) for item in rows],
        next_cursor=str(rows[-1].event_id) if has_more and rows else None,
    )


@router.get("/gates/{gate_id}", response_model=WorkflowGateResponse)
async def get_versioned_gate(
    gate_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowGateResponse:
    gate, role = await _gate_access(db, gate_id, user)
    return _gate_response(gate, can_decide=True)


@router.post("/gates/{gate_id}/decision", response_model=GateDecisionResult, status_code=status.HTTP_200_OK)
async def decide_versioned_gate(
    gate_id: UUID,
    payload: GateDecisionRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GateDecisionResult:
    gate, role = await _gate_access(db, gate_id, user)
    decision, decided_gate, job, replay = await gate_service.decide(
        db, gate_id, payload, actor_id=user.user_id, actor_role=role,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return GateDecisionResult(
        decision_id=str(decision.decision_id), gate=_gate_response(decided_gate),
        job_status=JobStatus(job.status), idempotent_replay=replay,
    )
