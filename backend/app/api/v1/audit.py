"""Audit trail API router with append-only database persistence and RBAC authorization."""

from typing import Optional, Tuple
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_job_access
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.user import User
from app.schemas.audit import AuditEventResponse, AuditListResponse
from app.services.audit_service import AuditService

router = APIRouter(tags=["Audit Trail"])


def _event_to_response(evt: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        event_id=str(evt.event_id),
        job_id=str(evt.job_id) if evt.job_id else None,
        event_type=evt.event_type,
        actor_type=evt.actor_type,
        actor_id=evt.actor_id,
        action=f"{evt.event_type} on {evt.target_resource or 'job'}",
        correlation_id=evt.correlation_id,
        payload=evt.payload,
        created_at=evt.created_at.isoformat() if hasattr(evt.created_at, "isoformat") else str(evt.created_at),
    )


@router.get(
    "/audit",
    response_model=AuditListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve platform-wide chronological audit history",
    operation_id="audit_list_global",
)
async def list_global_audit_events(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    actor_type: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuditListResponse:
    events, total = await AuditService.list_all_events(
        db=db,
        limit=limit,
        offset=offset,
        actor_type=actor_type,
    )
    return AuditListResponse(
        items=[_event_to_response(e) for e in events],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/jobs/{job_id}/audit",
    response_model=AuditListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve chronological audit history for a job",
    operation_id="audit_list_job",
)
async def list_job_audit_events(
    job_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    actor_type: Optional[str] = Query(None),
    access: Tuple[Job, User] = Depends(require_job_access(permission="audit:read")),
    db: AsyncSession = Depends(get_db),
) -> AuditListResponse:
    job, user = access
    events, total = await AuditService.list_job_events(
        db=db,
        job_id=job.job_id,
        limit=limit,
        offset=offset,
    )
    if actor_type:
        events = [e for e in events if e.actor_type.upper() == actor_type.upper()]

    return AuditListResponse(
        items=[_event_to_response(e) for e in events],
        total=total,
        offset=offset,
        limit=limit,
    )
