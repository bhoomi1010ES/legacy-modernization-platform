"""Modernization jobs API router with PostgreSQL persistence and RBAC authorization."""

from typing import Optional, Tuple
import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_user, get_db, require_job_access
from app.core.errors import NotFoundException
from app.models.job import Job
from app.models.user import User
from app.schemas.jobs import (
    JobCreateRequest,
    JobDetailResponse,
    JobListResponse,
    JobStatus,
    JobSummaryResponse,
    StackDetectionRequest,
    DetectedStackResponse,
)
from app.services.job_service import JobService
from app.services.stack_detector import StackDetector
from app.domain.state_machine import JobStateMachine

router = APIRouter(prefix="/jobs", tags=["Jobs"])
job_service = JobService()


def _job_to_response(job: Job, owner_name: str = "Alex Morgan") -> JobDetailResponse:
    return JobDetailResponse(
        job_id=str(job.job_id),
        name=job.name,
        source_repository=job.source_repository,
        source_revision=job.source_revision,
        source_stack=job.source_stack,
        target_stack=job.target_stack,
        status=JobStatus(job.status),
        progress=100 if job.status == "COMPLETED" else (50 if job.status in ("CONVERTING", "VERIFYING") else 0),
        modules=0,
        cost=float(job.budget_used_usd),
        budget=float(job.budget_limit_usd),
        owner=owner_name,
        max_repair_attempts=job.max_repair_attempts,
        integration_branch=job.integration_branch,
        target_repository=job.target_repository,
        stack_metadata=job.stack_metadata,
        created_at=job.created_at.isoformat() if hasattr(job.created_at, "isoformat") else str(job.created_at),
        updated_at=job.updated_at.isoformat() if hasattr(job.updated_at, "isoformat") else str(job.updated_at),
    )


@router.get(
    "",
    response_model=JobListResponse,
    status_code=status.HTTP_200_OK,
    summary="List modernization jobs with optional status filter",
    operation_id="jobs_list",
)
async def list_jobs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    jobs, total = await job_service.list_jobs(
        db=db,
        user=user,
        limit=limit,
        offset=offset,
        status=status_filter.value if status_filter else None,
    )

    items = [_job_to_response(j, user.full_name) for j in jobs]

    return JobListResponse(
        items=[JobSummaryResponse(**item.model_dump()) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "",
    response_model=JobDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new modernization job transactionally",
    operation_id="jobs_create",
)
async def create_job(
    payload: JobCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    job = await job_service.create_job(
        db=db,
        payload=payload,
        user=user,
        correlation_id=correlation_id,
    )
    return _job_to_response(job, user.full_name)


@router.post(
    "/detect-stack",
    response_model=DetectedStackResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect repository manifests and detect legacy technology stack",
    operation_id="jobs_detect_stack",
)
async def detect_stack(
    payload: StackDetectionRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> DetectedStackResponse:
    detected = StackDetector.detect_stack(
        source_repository=payload.source_repository,
        source_revision=payload.source_revision or "main",
    )

    if payload.job_id and user:
        from app.models.job import Job
        from app.models.audit import AuditEvent
        from sqlalchemy import select
        import uuid

        try:
            clean_id = uuid.UUID(str(payload.job_id))
            res = await db.execute(select(Job).where(Job.job_id == clean_id))
            job = res.scalar_one_or_none()
            if job and (job.owner_user_id == user.user_id or user.role in ("ADMIN", "ARCHITECT")):
                job.stack_metadata = detected.model_dump()
                job.source_stack = detected.summary_stack[:100]
                audit = AuditEvent(
                    job_id=job.job_id,
                    event_type="JOB_STACK_DETECTED",
                    actor_type="USER",
                    actor_id=str(user.user_id),
                    payload={
                        "scan_status": detected.scan_status,
                        "primary_language": detected.primary_language,
                        "framework": detected.framework,
                        "confidence_score": detected.confidence_score,
                    },
                    correlation_id=getattr(request.state, "correlation_id", None),
                )
                db.add(audit)
                await db.commit()
        except (ValueError, TypeError) as e:
            pass

    return detected



@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve detailed job status and configuration",
    operation_id="jobs_get",
)
async def get_job(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
) -> JobDetailResponse:
    job, user = access
    return _job_to_response(job, user.full_name)


@router.post(
    "/{job_id}/pause",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Pause an active modernization job",
    operation_id="jobs_pause",
)
async def pause_job(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:pause_resume")),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    job, user = access
    current_status = JobStatus(job.status)
    JobStateMachine.validate_transition(current_status, JobStatus.PAUSED)
    job.status = JobStatus.PAUSED.value
    await db.commit()
    await db.refresh(job)
    return _job_to_response(job, user.full_name)


@router.post(
    "/{job_id}/resume",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume a paused modernization job",
    operation_id="jobs_resume",
)
async def resume_job(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:pause_resume")),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    job, user = access
    current_status = JobStatus(job.status)
    JobStateMachine.validate_transition(current_status, JobStatus.CONVERTING)
    job.status = JobStatus.CONVERTING.value
    await db.commit()
    await db.refresh(job)
    return _job_to_response(job, user.full_name)


@router.post(
    "/{job_id}/cancel",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel a modernization job and record audit trail",
    operation_id="jobs_cancel",
)
async def cancel_job(
    job_id: str,
    request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:cancel")),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    job, user = access
    correlation_id = getattr(request.state, "correlation_id", None)
    cancelled_job = await job_service.cancel_job(
        db=db,
        job=job,
        user=user,
        correlation_id=correlation_id,
    )
    return _job_to_response(cancelled_job, user.full_name)
