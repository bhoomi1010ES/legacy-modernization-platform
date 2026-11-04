import pathlib

p = pathlib.Path("backend/app/api/v1/jobs.py")
content = p.read_text(encoding="utf-8")

# 1. Imports
target_import = """from app.models.job import Job
from app.models.user import User"""

replacement_import = """from app.models.job import Job
from app.models.module import Module
from app.models.user import User
from app.schemas.workflow_projection import WorkflowProjectionResponse
from sqlalchemy import func, select"""

assert target_import in content, "target_import not found"
content = content.replace(target_import, replacement_import, 1)

# 2. Add get_jobs_metrics and update _job_to_response
target_fn = """def _job_to_response(job: Job, owner_name: str = "Alex Morgan") -> JobDetailResponse:
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
    )"""

replacement_fn = """async def get_jobs_metrics(db: AsyncSession, jobs: List[Job]) -> Dict[uuid.UUID, Tuple[int, int]]:
    \"\"\"Calculates truthful module counts and weighted verification progress for jobs.\"\"\"
    if not jobs:
        return {}
    job_ids = [j.job_id for j in jobs]
    mod_stmt = (
        select(Module.job_id, func.count(Module.module_id))
        .where(Module.job_id.in_(job_ids))
        .group_by(Module.job_id)
    )
    mod_res = (await db.execute(mod_stmt)).all()
    mod_counts = {r[0]: r[1] for r in mod_res}

    ver_stmt = (
        select(Module.job_id, func.count(Module.module_id))
        .where(
            Module.job_id.in_(job_ids),
            Module.status == "VERIFIED",
        )
        .group_by(Module.job_id)
    )
    ver_res = (await db.execute(ver_stmt)).all()
    ver_counts = {r[0]: r[1] for r in ver_res}

    result: Dict[uuid.UUID, Tuple[int, int]] = {}
    for j in jobs:
        total = mod_counts.get(j.job_id, 0)
        if j.status == "COMPLETED":
            result[j.job_id] = (total, 100)
        elif total == 0:
            result[j.job_id] = (0, 0)
        else:
            verified = ver_counts.get(j.job_id, 0)
            result[j.job_id] = (total, int((verified / total) * 100))
    return result


def _job_to_response(
    job: Job,
    owner_name: str = "Alex Morgan",
    modules_count: int = 0,
    progress: Optional[int] = None,
) -> JobDetailResponse:
    if progress is None:
        progress = 100 if job.status == "COMPLETED" else 0
    return JobDetailResponse(
        job_id=str(job.job_id),
        name=job.name,
        source_repository=job.source_repository,
        source_revision=job.source_revision,
        source_stack=job.source_stack,
        target_stack=job.target_stack,
        status=JobStatus(job.status),
        progress=progress,
        modules=modules_count,
        cost=float(job.budget_used_usd),
        budget=float(job.budget_limit_usd),
        owner=owner_name,
        max_repair_attempts=job.max_repair_attempts,
        integration_branch=job.integration_branch,
        target_repository=job.target_repository,
        stack_metadata=job.stack_metadata,
        created_at=job.created_at.isoformat() if hasattr(job.created_at, "isoformat") else str(job.created_at),
        updated_at=job.updated_at.isoformat() if hasattr(job.updated_at, "isoformat") else str(job.updated_at),
    )"""

assert target_fn in content, "target_fn not found"
content = content.replace(target_fn, replacement_fn, 1)

# Ensure List and Dict are imported
if "from typing import " in content:
    content = content.replace("from typing import Optional, Tuple", "from typing import Dict, List, Optional, Tuple", 1)

# 3. Update list_jobs to use get_jobs_metrics
target_list = """    jobs, total = await job_service.list_jobs(
        db=db,
        user=user,
        limit=limit,
        offset=offset,
        status=status_filter.value if status_filter else None,
    )

    items = [_job_to_response(j, user.full_name) for j in jobs]"""

replacement_list = """    jobs, total = await job_service.list_jobs(
        db=db,
        user=user,
        limit=limit,
        offset=offset,
        status=status_filter.value if status_filter else None,
    )

    metrics = await get_jobs_metrics(db, jobs)
    items = [
        _job_to_response(
            j,
            user.full_name,
            modules_count=metrics.get(j.job_id, (0, 0))[0],
            progress=metrics.get(j.job_id, (0, 0))[1],
        )
        for j in jobs
    ]"""

assert target_list in content, "target_list not found"
content = content.replace(target_list, replacement_list, 1)

# 4. Update get_job to accept db and use get_jobs_metrics
target_get = """@router.get(
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
    return _job_to_response(job, user.full_name)"""

replacement_get = """@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve detailed job status and configuration",
    operation_id="jobs_get",
)
async def get_job(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    job, user = access
    metrics = await get_jobs_metrics(db, [job])
    modules_count, progress = metrics.get(job.job_id, (0, 0))
    return _job_to_response(job, user.full_name, modules_count=modules_count, progress=progress)


@router.get(
    "/{job_id}/projection",
    response_model=WorkflowProjectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve truthful workflow projection derived strictly from database evidence",
    operation_id="jobs_get_projection",
)
async def get_job_projection(
    job_id: str,
    since_seq: int = Query(0, ge=0, description="Monotonic audit sequence cursor for polling"),
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowProjectionResponse:
    job, user = access
    from app.services.workflow_projection_service import WorkflowProjectionService
    service = WorkflowProjectionService()
    return await service.get_projection(db, job.job_id, user, since_seq=since_seq)"""

assert target_get in content, "target_get not found"
content = content.replace(target_get, replacement_get, 1)

p.write_text(content, encoding="utf-8")
print("Successfully patched backend/app/api/v1/jobs.py")

