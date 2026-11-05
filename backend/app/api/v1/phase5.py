"""Authenticated characterization and disposable schema/data review endpoints."""

import logging
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_job_access, get_current_user_and_permissions
from app.core.database import get_db
from app.core.errors import NotFoundException
from app.models.job import Job
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.phase5 import CaptureRequest, FreezeRequest, ValidationRequest
from app.services import phase5_service as service

router = APIRouter(tags=["Characterization and schema/data"])
logger = logging.getLogger(__name__)


@router.post("/jobs/{job_id}/characterization-runs", status_code=201)
async def capture_run(
    payload: CaptureRequest,
    access: tuple[Job, User] = Depends(require_job_access()),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await service.capture(db, access[0], payload, str(access[1].user_id))
    except Exception:
        logger.exception("phase5.capture_run failed")
        raise


@router.get("/jobs/{job_id}/characterization-report")
async def characterization_report(
    access: tuple[Job, User] = Depends(require_job_access()),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await service.report(db, access[0].job_id)
    except Exception:
        logger.exception("phase5.characterization_report failed")
        raise


@router.get("/jobs/{job_id}/test-cases")
async def test_cases(
    module: str | None = None,
    outcome: str | None = None,
    version: int | None = Query(None, ge=1),
    access: tuple[Job, User] = Depends(require_job_access()),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        from app.models.artifact import Artifact

        artifact = None
        if version is not None:
            artifact = await db.scalar(
                select(Artifact).where(
                    Artifact.job_id == access[0].job_id,
                    Artifact.artifact_type == "CHARACTERIZATION_SUITE",
                    Artifact.version == version,
                )
            )
            if artifact is None:
                raise NotFoundException("Suite version", str(version))
        report = await service.report(db, access[0].job_id, artifact)
        items = [
            c
            for c in report["cases"]
            if (module is None or c["module"] == module)
            and (outcome is None or c["outcome"] == outcome)
        ]
        return {
            "items": items,
            "version": report["version"],
            "status": report["status"],
            "content_hash": report["content_hash"],
            "coverage": report["coverage"],
        }
    except Exception:
        logger.exception("phase5.test_cases failed")
        raise


@router.get("/test-cases/{test_case_id}")
async def test_case_detail(
    test_case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth=Depends(get_current_user_and_permissions),
) -> dict:
    try:
        case = await db.get(TestCase, test_case_id)
        if case is None:
            raise NotFoundException("TestCase", str(test_case_id))
        # Reuse job membership checks and anti-IDOR policy; never expose evidence before authorization.
        await require_job_access()(job_id=str(case.job_id), auth_data=auth, db=db)
        return {
            "test_case_id": str(case.test_case_id),
            "name": case.name,
            "is_frozen": case.is_frozen,
            **(case.fixture_payload or {}),
        }
    except Exception:
        logger.exception("phase5.test_case_detail failed")
        raise


@router.post("/jobs/{job_id}/g2/freeze")
async def request_freeze(
    payload: FreezeRequest,
    access: tuple[Job, User] = Depends(require_job_access()),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await service.freeze(
            db, access[0], payload, actor_id=str(access[1].user_id)
        )
    except Exception:
        logger.exception("phase5.request_freeze failed")
        raise


@router.get("/jobs/{job_id}/schema-analysis")
async def schema_analysis(
    access: tuple[Job, User] = Depends(require_job_access()),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        plan = await service.read_payload(
            await service.latest(db, access[0].job_id, "SCHEMA_MIGRATION_PLAN")
        )
        return {
            "status": plan.get("status", "REVIEW_REQUIRED"),
            **{
                k: plan[k]
                for k in (
                    "tables",
                    "source_tables",
                    "differences",
                    "limitations",
                    "inventory_evidence",
                    "schema_files",
                )
            },
        }
    except Exception:
        logger.exception("phase5.schema_analysis failed")
        raise


@router.get("/jobs/{job_id}/data-migration-plan")
async def data_plan(
    access: tuple[Job, User] = Depends(require_job_access()),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        artifact = await service.latest(db, access[0].job_id, "SCHEMA_MIGRATION_PLAN")
        return {
            **await service.read_payload(artifact),
            "validation_status": await service.validation_status(
                db, access[0].job_id, artifact.content_hash
            ),
            "artifact_id": str(artifact.artifact_id),
            "content_hash": artifact.content_hash,
            "version": artifact.version,
        }
    except Exception:
        logger.exception("phase5.data_plan failed")
        raise


@router.post("/jobs/{job_id}/data-migration-plan/validate")
async def validate_data(
    payload: ValidationRequest,
    access: tuple[Job, User] = Depends(require_job_access()),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await service.validate_plan(
            db, access[0], payload, str(access[1].user_id)
        )
    except Exception:
        logger.exception("phase5.validate_data failed")
        raise
