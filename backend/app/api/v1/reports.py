"""Compatibility reports derive metrics from execution, never test discovery/status guesses."""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import require_job_access
from app.core.database import get_db
from app.models.module import Module
from app.models.test_case import TestCase, TestResult
from app.schemas.reports import DeliveryReportResponse, VerificationReportResponse
from app.services import phase6_service, phase7_service
from app.core.errors import NotFoundException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs/{job_id}/reports", tags=["Reports"])


@router.get("/verification", response_model=VerificationReportResponse, operation_id="reports_verification")
async def get_verification_report(access=Depends(require_job_access()), db=Depends(get_db)):
    try:
        job, _ = access
        try:
            artifact = await phase7_service.artifact_view(db, job.job_id, "JOB_REPORT")
        except NotFoundException:
            cases = list((await db.execute(select(TestCase).where(TestCase.job_id == job.job_id))).scalars())
            scoped = [case for case in cases if case.is_frozen] or cases
            expected = {case.test_case_id for case in scoped}
            outcomes = {}
            modules = list((await db.execute(select(Module).where(Module.job_id == job.job_id))).scalars())
            for module in modules:
                attempt = await phase6_service.newest(db, module.module_id)
                if attempt is None:
                    continue
                rows = list((await db.execute(select(TestResult).where(TestResult.attempt_id == attempt.attempt_id, TestResult.invalidated.is_(False)))).scalars())
                for row in rows:
                    if row.test_case_id in expected and outcomes.get(row.test_case_id) != "FAILED":
                        outcomes[row.test_case_id] = row.outcome
            total, passing = len(expected), sum(value == "PASSED" for value in outcomes.values())
            failed = sum(value == "FAILED" for value in outcomes.values())
            limitations = ["Latest module-attempt observations only; not full-system or line/branch coverage", f"{total-len(outcomes)} scenarios have no current converted execution evidence"]
        else:
            integration = await phase7_service.artifact_view(db, job.job_id, "INTEGRATION_REPORT")
            ids = [row for row in integration["content"]["test_result_ids"]]
            import uuid
            rows = list((await db.execute(select(TestResult).where(TestResult.result_id.in_([uuid.UUID(row) for row in ids]), TestResult.invalidated.is_(False)))).scalars())
            total = artifact["content"]["counts"]["total"]
            passing, failed = sum(row.outcome == "PASSED" for row in rows), sum(row.outcome == "FAILED" for row in rows)
            limitations = artifact["content"]["limitations"]
        return VerificationReportResponse(job_id=str(job.job_id), total_tests=total, passing_tests=passing, behavioral_equivalence_pct=round(100*passing/total, 2) if total else 0, regressions_count=failed, intended_differences_count=0, uncovered_code_pct=None, differences=[], limitations=limitations)
    except Exception:
        logger.exception("reports.get_verification_report failed")
        raise


@router.get("/delivery", response_model=DeliveryReportResponse, operation_id="reports_delivery")
async def get_delivery_report(access=Depends(require_job_access()), db=Depends(get_db)):
    try:
        job, _ = access
        package = await phase7_service.delivery(db, job)
        report, record = package.get("report"), package.get("delivery_record")
        counts = report["content"]["counts"] if report else {"total": 0, "passed": 0}
        return DeliveryReportResponse(job_id=str(job.job_id), project_name=job.name, integration_branch=report["content"]["branch"] if report else "", pull_request_url=package["pull_request"].get("url"), equivalence_pct=100*counts["passed"]/counts["total"] if package["delivery_ready"] and counts["total"] else 0, signed_waivers_count=len(record["content"]["waivers"]) if record else 0, production_cutover_included=False, included_artifacts=list(report["content"]["evidence"]) if report else [], delivered_at=record["content"]["delivered_at"] if record else None)
    except Exception:
        logger.exception("reports.get_delivery_report failed")
        raise
