"""Job-scoped Phase 7 APIs. Runtime commands and approvals are never caller evidence."""

import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select

from app.api.deps import require_job_access
from app.core.database import get_db
from app.domain.state_machine import RBACPolicy
from app.models.job import JobMembership
from app.schemas.phase7 import IntegrationRequest, PackageRequest
from app.services import phase7_service as service
from app.services.supervisor_service import supervisor_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Integration and delivery"])


async def resume_integration(job_id):
    try:
        from app.services.continuous_pipeline import continuous_pipeline_service

        continuous_pipeline_service.trigger_continuous_pipeline(job_id)
    except Exception:
        logger.exception("phase7.resume_integration failed")
        raise


@router.post("/jobs/{job_id}/integration-runs", status_code=202)
async def queue_integration(
    payload: IntegrationRequest,
    background: BackgroundTasks,
    access=Depends(require_job_access("integration:run")),
    db=Depends(get_db),
):
    try:
        job, user = access
        run = await supervisor_service.queue_integration(
            db, job, payload.idempotency_key, str(user.user_id)
        )
        background.add_task(resume_integration, job.job_id)
        return {
            "run_id": str(run.run_id),
            "status": run.status,
            "result": run.output_payload,
        }
    except Exception:
        logger.exception("phase7.queue_integration API failed")
        raise


@router.get("/jobs/{job_id}/integration-report")
async def integration_report(
    version: int | None = Query(None, ge=1),
    access=Depends(require_job_access()),
    db=Depends(get_db),
):
    try:
        return await service.artifact_view(
            db, access[0].job_id, "INTEGRATION_REPORT", version
        )
    except Exception:
        logger.exception("phase7.integration_report API failed")
        raise


@router.get("/jobs/{job_id}/report")
async def job_report(
    version: int | None = Query(None, ge=1),
    access=Depends(require_job_access()),
    db=Depends(get_db),
):
    try:
        return await service.artifact_view(db, access[0].job_id, "JOB_REPORT", version)
    except Exception:
        logger.exception("phase7.job_report API failed")
        raise


@router.get("/jobs/{job_id}/sbom")
async def sbom_report(
    version: int | None = Query(None, ge=1),
    access=Depends(require_job_access()),
    db=Depends(get_db),
):
    try:
        result = await service.artifact_view(db, access[0].job_id, "SBOM", version)
        if result["content"]["status"] != "GENERATED":
            result["download_url"] = None
        return result
    except Exception:
        logger.exception("phase7.sbom_report API failed")
        raise


@router.post("/jobs/{job_id}/pull-request")
async def pull_request(
    payload: PackageRequest,
    access=Depends(require_job_access("delivery:publish")),
    db=Depends(get_db),
):
    try:
        job, user = access
        return await service.pull_request(db, job, payload, str(user.user_id))
    except Exception:
        logger.exception("phase7.pull_request API failed")
        raise


@router.get("/jobs/{job_id}/delivery")
async def delivery(access=Depends(require_job_access()), db=Depends(get_db)):
    try:
        job, user = access
        result = await service.delivery(db, job)
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
        result["allowed_actions"] = [
            action
            for action, capability in (
                ("integrate", "integration:run"),
                ("pull_request", "delivery:publish"),
                ("submit_g4", "integration:run"),
                ("decide_g4", "gate:approve_g4"),
                ("download", "artifact:download"),
            )
            if RBACPolicy.has_permission(role, capability)
        ]
        return result
    except Exception:
        logger.exception("phase7.delivery API failed")
        raise


@router.post("/jobs/{job_id}/g4/submit")
async def submit_g4(
    payload: PackageRequest,
    access=Depends(require_job_access("integration:run")),
    db=Depends(get_db),
):
    try:
        job, user = access
        gate = await supervisor_service.submit_final_review(
            db, job, payload.report_hash, str(user.user_id)
        )
        return {
            "gate_id": str(gate.gate_id),
            "status": gate.status,
            "artifact_hashes": gate.artifact_hashes,
        }
    except Exception:
        logger.exception("phase7.submit_g4 API failed")
        raise
