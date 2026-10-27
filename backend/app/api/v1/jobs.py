"""Modernization jobs API router with PostgreSQL persistence and RBAC authorization."""

from typing import Optional, Tuple
import uuid
from fastapi import APIRouter, Depends, Query, Request, status, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from pathlib import Path
from app.api.deps import get_current_user, get_optional_user, get_db, require_job_access
from app.core.errors import ErrorDetail, NotFoundException, ValidationException
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
    JobIntakeRequest,
)
from app.services.job_service import JobService
from app.services.stack_detector import StackDetector
from app.services.supervisor_service import supervisor_service

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
    raw_path = payload.source_repository.strip()
    is_local_request = (payload.source_type == "local") or raw_path.startswith("local://")
    if not is_local_request:
        try:
            p = Path(raw_path)
            if p.is_absolute() and (p.exists() or not (raw_path.startswith("http://") or raw_path.startswith("https://") or raw_path.startswith("git@"))):
                is_local_request = True
        except Exception:
            pass

    if is_local_request:
        clean_path_str = raw_path.removeprefix("local://")
        local_dir = Path(clean_path_str).resolve()
        if not local_dir.exists():
            raise ValidationException(
                f"Local directory path '{clean_path_str}' was not found on this machine.",
                details=[ErrorDetail(field="source_repository", issue="Local directory does not exist")],
            )
        if local_dir.is_file() and clean_path_str.lower().endswith(".zip"):
            from app.services.local_source_adapter import LocalSourceAdapter
            adapter = LocalSourceAdapter()
            staging_dir, metadata = adapter.stage_preview_bundle(
                archive_path=local_dir,
                source_name=local_dir.stem,
                user_id=str(user.user_id) if user else "local-operator",
            )
            detected = StackDetector.detect_stack_from_workspace(
                workspace_path=staging_dir,
                source_name=local_dir.stem,
                source_revision="LOCAL",
                preview_snapshot_id=metadata.snapshot_id,
                snapshot_fingerprint=metadata.canonical_fingerprint,
                extra_warnings=metadata.warnings,
                is_complete=metadata.is_complete,
            )
            detected.source_repository = str(local_dir)
            detected.source_type = "local"
        elif not local_dir.is_dir():
            raise ValidationException(
                f"Path '{clean_path_str}' is neither a directory nor a .zip archive.",
                details=[ErrorDetail(field="source_repository", issue="Target must be a directory or .zip archive")],
            )
        else:
            from app.services.local_source_adapter import LocalSourceAdapter
            fingerprint = LocalSourceAdapter.calculate_canonical_fingerprint(local_dir)
            detected = StackDetector.detect_stack_from_workspace(
                workspace_path=local_dir,
                source_name=local_dir.name,
                source_revision="LOCAL",
                snapshot_fingerprint=fingerprint,
            )
            detected.source_repository = str(local_dir)
            detected.source_type = "local"
    else:
        detected = StackDetector.detect_stack(
            source_repository=payload.source_repository,
            source_revision=payload.source_revision or "main",
            access_token=payload.access_token,
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


@router.post(
    "/detect-stack/local",
    response_model=DetectedStackResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload and inspect local folder bundle, detecting technology stack",
    operation_id="jobs_detect_stack_local",
)
async def detect_stack_local(
    bundle: UploadFile = File(..., description="Zipped local project source bundle"),
    source_name: str = Form("local-project", description="Display name of local folder"),
    job_id: Optional[str] = Form(None, description="Optional job ID"),
    request: Request = None,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> DetectedStackResponse:
    import tempfile
    from pathlib import Path
    from app.services.local_source_adapter import LocalSourceAdapter

    adapter = LocalSourceAdapter()
    try:
        adapter.cleanup_staged_snapshots()
    except Exception:
        pass

    # Stream uploaded bundle to temporary file on disk to prevent memory spikes
    temp_zip = Path(tempfile.gettempdir()) / f"rebase_upload_{uuid.uuid4()}.zip"
    try:
        with open(temp_zip, "wb") as f:
            while chunk := await bundle.read(1024 * 1024):  # 1 MB chunks
                f.write(chunk)

        staging_dir, metadata = adapter.stage_preview_bundle(
            archive_path=temp_zip,
            source_name=source_name,
            user_id=str(user.user_id) if user else "anonymous",
        )

        detected = StackDetector.detect_stack_from_workspace(
            workspace_path=staging_dir,
            source_name=source_name,
            source_revision="LOCAL",
            preview_snapshot_id=metadata.snapshot_id,
            snapshot_fingerprint=metadata.canonical_fingerprint,
            extra_warnings=metadata.warnings,
            is_complete=metadata.is_complete,
        )

        if job_id and user:
            from app.models.job import Job
            from app.models.audit import AuditEvent
            from sqlalchemy import select

            try:
                clean_id = uuid.UUID(str(job_id))
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
                            "source_type": "local",
                            "snapshot_fingerprint": metadata.canonical_fingerprint,
                            "file_count": metadata.file_count,
                        },
                        correlation_id=getattr(request.state, "correlation_id", None) if request else None,
                    )
                    db.add(audit)
                    await db.commit()
            except (ValueError, TypeError):
                pass

        return detected
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass


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
    request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:pause_resume")),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    job, user = access
    paused = await supervisor_service.pause(
        db, job.job_id, actor_id=str(user.user_id), reason="Paused by authorized user.",
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return _job_to_response(paused, user.full_name)


@router.post(
    "/{job_id}/resume",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume a paused modernization job",
    operation_id="jobs_resume",
)
async def resume_job(
    job_id: str,
    request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:pause_resume")),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    job, user = access
    resumed = await supervisor_service.resume(
        db, job.job_id, actor_id=str(user.user_id),
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return _job_to_response(resumed, user.full_name)


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
    cancelled_job = await supervisor_service.cancel(
        db, job.job_id,
        actor_id=str(user.user_id),
        correlation_id=correlation_id,
    )
    return _job_to_response(cancelled_job, user.full_name)


@router.post(
    "/{job_id}/intake",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Acquire repository and initiate job intake stage",
    operation_id="jobs_intake",
)
async def intake_job(
    job_id: str,
    payload: JobIntakeRequest,
    request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:intake")),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    from app.models.audit import AuditEvent

    job, user = access
    # Extract pinned_commit if available from preview metadata
    pinned_commit = None
    snapshot_fingerprint = payload.snapshot_fingerprint
    preview_snapshot_id = payload.preview_snapshot_id

    if isinstance(job.stack_metadata, dict):
        pinned_commit = job.stack_metadata.get("pinned_commit")
        eff = job.stack_metadata.get("effective", {})
        det = job.stack_metadata.get("detected", {})
        if not preview_snapshot_id:
            preview_snapshot_id = (
                job.stack_metadata.get("preview_snapshot_id")
                or (eff.get("preview_snapshot_id") if isinstance(eff, dict) else None)
                or (det.get("preview_snapshot_id") if isinstance(det, dict) else None)
            )
        if not snapshot_fingerprint:
            snapshot_fingerprint = (
                job.stack_metadata.get("snapshot_fingerprint")
                or (eff.get("snapshot_fingerprint") if isinstance(eff, dict) else None)
                or (det.get("snapshot_fingerprint") if isinstance(det, dict) else None)
            )

    is_local = (job.source_repository or "").startswith("local://")

    correlation_id = getattr(request.state, "correlation_id", None)
    snapshot, inventory, job = await supervisor_service.execute_intake(
        db, job.job_id,
        actor_id=str(user.user_id),
        user=user,
        git_token=payload.git_token,
        preview_snapshot_id=preview_snapshot_id,
        snapshot_fingerprint=snapshot_fingerprint,
        correlation_id=correlation_id,
    )

    # Append audit event without credential leakage
    audit = AuditEvent(
        job_id=job.job_id,
        event_type="JOB_INTAKE_COMPLETED",
        actor_type="USER",
        actor_id=str(user.user_id),
        correlation_id=correlation_id,
        target_resource=str(job.job_id),
        payload={
            "source_type": "local" if is_local else "git",
            "resolved_commit": snapshot.metadata.commit_sha,
            "snapshot_fingerprint": snapshot.inventory_hash,
            "inventory_hash": snapshot.inventory_hash,
            "file_count": snapshot.metadata.file_count,
            "pinned_commit_enforced": bool(pinned_commit),
            "reused_staged_snapshot": bool(is_local and preview_snapshot_id),
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(job)
    supervisor_service.schedule_drive(job.job_id, correlation_id=correlation_id)
    return _job_to_response(job, user.full_name)



@router.post(
    "/{job_id}/intake/local",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Direct upload intake for local folder modernization job",
    operation_id="jobs_intake_local",
)
async def intake_job_local(
    job_id: str,
    bundle: UploadFile = File(..., description="Zipped local project source bundle"),
    expected_fingerprint: Optional[str] = Form(None, description="Optional expected snapshot fingerprint"),
    request: Request = None,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:intake")),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    from app.models.audit import AuditEvent
    import tempfile
    from pathlib import Path
    from app.services.local_source_adapter import LocalSourceAdapter

    job, user = access
    # Extract expected fingerprint from metadata if not given in form
    if not expected_fingerprint and isinstance(job.stack_metadata, dict):
        eff = job.stack_metadata.get("effective", {})
        det = job.stack_metadata.get("detected", {})
        expected_fingerprint = (
            job.stack_metadata.get("snapshot_fingerprint")
            or (eff.get("snapshot_fingerprint") if isinstance(eff, dict) else None)
            or (det.get("snapshot_fingerprint") if isinstance(det, dict) else None)
        )

    temp_zip = Path(tempfile.gettempdir()) / f"rebase_intake_{uuid.uuid4()}.zip"
    try:
        with open(temp_zip, "wb") as f:
            while chunk := await bundle.read(1024 * 1024):
                f.write(chunk)

        adapter = LocalSourceAdapter()
        workspace, fingerprint = adapter.materialize_direct_upload(
            archive_path=temp_zip,
            job_id=str(job.job_id),
            expected_fingerprint=expected_fingerprint,
        )

        correlation_id = getattr(request.state, "correlation_id", None) if request else None
        _, _, job = await supervisor_service.execute_intake(
            db, job.job_id,
            actor_id=str(user.user_id),
            user=user,
            snapshot_fingerprint=fingerprint,
            workspace_override=workspace,
            correlation_id=correlation_id,
        )
        audit = AuditEvent(
            job_id=job.job_id,
            event_type="JOB_INTAKE_COMPLETED",
            actor_type="USER",
            actor_id=str(user.user_id),
            correlation_id=correlation_id,
            target_resource=str(job.job_id),
            payload={
                "source_type": "local",
                "snapshot_fingerprint": fingerprint,
                "workspace_dir": workspace.name,
                "direct_upload": True,
            },
        )
        db.add(audit)
        await db.commit()
        await db.refresh(job)
        supervisor_service.schedule_drive(job.job_id, correlation_id=correlation_id)
        return _job_to_response(job, user.full_name)
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass

