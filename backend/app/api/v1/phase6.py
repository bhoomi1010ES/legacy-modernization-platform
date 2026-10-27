"""Authorized, job-scoped module execution and evidence APIs. No caller commands accepted."""

import logging
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from app.api.deps import require_job_access, get_current_user_and_permissions
from app.core.database import get_db
from app.core.errors import NotFoundException
from app.domain.state_machine import RBACPolicy
from app.models.job import JobMembership
from app.models.module import Module, ModuleAttempt
from app.schemas.phase6 import QueueConversion, RepairRequest, WaiverRequest
from app.services import phase6_service as service
from app.services.supervisor_service import supervisor_service

router = APIRouter(tags=["Module execution"])
logger = logging.getLogger(__name__)


async def actions(db, job, user):
    try:
        role = (
            user.role
            if user.role == "SUPER_ADMIN"
            else await db.scalar(
                select(JobMembership.role_id).where(
                    JobMembership.job_id == job.job_id,
                    JobMembership.user_id == user.user_id,
                )
            )
        )
        return [
            action
            for action, permission in (
                ("queue", "module:convert"),
                ("repair", "module:repair"),
                ("waiver", "module:waive"),
            )
            if RBACPolicy.has_permission(role, permission)
        ]
    except Exception:
        logger.exception("phase6.actions failed")
        raise


async def resume_pool(job_id):
    try:
        from app.services.continuous_pipeline import continuous_pipeline_service

        # Existing Supervisor runner owns task deduplication and gate/recovery handling.
        continuous_pipeline_service.trigger_continuous_pipeline(job_id)
    except Exception:
        logger.exception("phase6.resume_pool failed | job_id=%s", job_id)


async def attempt_access(attempt_id, db, auth, permission="job:read"):
    try:
        attempt = await db.get(ModuleAttempt, attempt_id)
        module = await db.get(Module, attempt.module_id) if attempt else None
        if not module:
            raise NotFoundException("ModuleAttempt", str(attempt_id))
        job, user = await require_job_access(permission)(
            job_id=str(module.job_id), auth_data=auth, db=db
        )
        return attempt, module, job, user
    except Exception:
        logger.exception("phase6.attempt_access denied or failed")
        raise


@router.post("/jobs/{job_id}/modules/{module_id}/conversion-runs", status_code=202)
async def queue_conversion(
    module_id: UUID,
    payload: QueueConversion,
    background: BackgroundTasks,
    access=Depends(require_job_access("module:convert")),
    db=Depends(get_db),
):
    try:
        job, user = access
        module = await db.get(Module, module_id)
        if module is None or module.job_id != job.job_id:
            raise NotFoundException("Module", str(module_id))
        attempt = await supervisor_service.queue_module_conversion(
            db, job, module, payload.idempotency_key, str(user.user_id)
        )
        response = await service.detail(db, attempt)
        background.add_task(resume_pool, job.job_id)
        return response
    except Exception:
        logger.exception("phase6.queue_conversion failed")
        raise


@router.get("/jobs/{job_id}/module-attempts")
async def board(access=Depends(require_job_access()), db=Depends(get_db)):
    try:
        job, user = access
        allowed = await actions(db, job, user)
        modules = list(
            (
                await db.execute(
                    select(Module)
                    .where(Module.job_id == job.job_id)
                    .order_by(Module.wave_number, Module.name)
                )
            )
            .scalars()
            .all()
        )
        completed = {str(m.module_id) for m in modules if m.status == "VERIFIED"}
        items, rows = [], []
        for module in modules:
            attempts = list(
                (
                    await db.execute(
                        select(ModuleAttempt)
                        .where(ModuleAttempt.module_id == module.module_id)
                        .order_by(ModuleAttempt.attempt_number)
                    )
                )
                .scalars()
                .all()
            )
            details = []
            for attempt in attempts:
                info = await service.detail(db, attempt)
                info["allowed_actions"] = allowed if attempt == attempts[-1] else []
                details.append(info)
            items.extend(details)
            rows.append(
                {
                    "module_id": str(module.module_id),
                    "name": module.name,
                    "status": module.status,
                    "dependency_blockers": [
                        d
                        for d in module.dependency_module_ids or []
                        if d not in completed
                    ],
                    "attempts": details,
                }
            )
        # Configuration is not proof the daemon/image is available. Only executed evidence is.
        runtime_available = any(
            i["evidence"].get("verification", {}).get("available") for i in items
        )
        return {
            "modules": rows,
            "items": items,
            "runtime_available": runtime_available,
            "allowed_actions": allowed,
        }
    except Exception:
        logger.exception("phase6.board failed")
        raise


@router.get("/module-attempts/{attempt_id}")
async def attempt_detail(
    attempt_id: UUID, db=Depends(get_db), auth=Depends(get_current_user_and_permissions)
):
    try:
        attempt, module, job, user = await attempt_access(attempt_id, db, auth)
        result = await service.detail(db, attempt)
        latest = await service.newest(db, module.module_id)
        result["allowed_actions"] = (
            await actions(db, job, user)
            if latest.attempt_id == attempt.attempt_id
            else []
        )
        return result
    except Exception:
        logger.exception("phase6.attempt_detail failed")
        raise


@router.get("/module-attempts/{attempt_id}/diff")
async def attempt_diff(
    attempt_id: UUID, db=Depends(get_db), auth=Depends(get_current_user_and_permissions)
):
    try:
        attempt, *_ = await attempt_access(attempt_id, db, auth)
        evidence = (await service.detail(db, attempt))["evidence"]
        return {
            "diff": evidence.get("diff", ""),
            "changed_files": evidence.get("changed_files", []),
        }
    except Exception:
        logger.exception("phase6.attempt_diff failed")
        raise


@router.get("/module-attempts/{attempt_id}/test-results")
async def attempt_results(
    attempt_id: UUID, db=Depends(get_db), auth=Depends(get_current_user_and_permissions)
):
    try:
        attempt, *_ = await attempt_access(attempt_id, db, auth)
        evidence = (await service.detail(db, attempt))["evidence"]
        return {
            "checks": evidence.get("checks", []),
            "results": evidence.get("results", []),
        }
    except Exception:
        logger.exception("phase6.attempt_results failed")
        raise


@router.get("/module-attempts/{attempt_id}/review")
async def attempt_review(
    attempt_id: UUID, db=Depends(get_db), auth=Depends(get_current_user_and_permissions)
):
    try:
        attempt, *_ = await attempt_access(attempt_id, db, auth)
        evidence = (await service.detail(db, attempt))["evidence"]
        return evidence.get("review", {"status": "UNAVAILABLE", "findings": []})
    except Exception:
        logger.exception("phase6.attempt_review failed")
        raise


@router.post("/module-attempts/{attempt_id}/repair", status_code=202)
async def repair_attempt(
    attempt_id: UUID,
    payload: RepairRequest,
    background: BackgroundTasks,
    db=Depends(get_db),
    auth=Depends(get_current_user_and_permissions),
):
    try:
        attempt, module, job, user = await attempt_access(
            attempt_id, db, auth, "module:repair"
        )
        new = await supervisor_service.queue_module_conversion(
            db,
            job,
            module,
            payload.idempotency_key,
            str(user.user_id),
            previous=attempt,
            rationale=payload.rationale,
        )
        result = await service.detail(db, new)
        background.add_task(resume_pool, job.job_id)
        return result
    except Exception:
        logger.exception("phase6.repair_attempt failed")
        raise


@router.post("/module-attempts/{attempt_id}/waivers", status_code=202)
async def request_waiver(
    attempt_id: UUID,
    payload: WaiverRequest,
    db=Depends(get_db),
    auth=Depends(get_current_user_and_permissions),
):
    try:
        attempt, module, job, user = await attempt_access(
            attempt_id, db, auth, "module:waive"
        )
        return await service.request_waiver(
            db, attempt, payload.finding_id, payload.rationale, str(user.user_id)
        )
    except Exception:
        logger.exception("phase6.request_waiver failed")
        raise
