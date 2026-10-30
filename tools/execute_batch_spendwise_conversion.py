import asyncio
import json
import logging
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.phase4 import RepositorySnapshotModel
from app.models.test_case import TestResult
from app.services import phase6_service
from app.services.phase5_service import read_payload
from app.services.repository_workspace_service import repository_workspace_service
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("spendwise_batch_converter")

JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
REVIEWER_ID = uuid.UUID("bbacac52-6e67-43a3-9983-3ad6354343d2")

# Logical dependency-aware batches
BATCHES = [
    # Batch 1: Leaf / foundation modules
    [
        "comp_app-exceptions_c809b4",
        "comp_app-core_5ca8c3",
        "comp_app-database_230f00",
        "comp_middleware_b930cf",
        "comp_frontend_1f1bb4",
    ],
    # Batch 2: Data models, schemas, and migrations
    [
        "comp_app-models_681831",
        "comp_app-schemas_50e05e",
        "comp_alembic_4b7d87",
    ],
    # Batch 3: Repositories and dependency injection
    [
        "comp_app-dependencies_b6e453",
        "comp_app-repositories_d21529",
    ],
    # Batch 4: Business logic services
    [
        "comp_app-services_c452e0",
    ],
    # Batch 5: API presentation and application root
    [
        "comp_app-api_d930e3",
        "comp_app_10badd",
    ],
]

async def convert_one_module(db, job, module_name: str) -> bool:
    module = await db.scalar(select(Module).where(Module.job_id == job.job_id, Module.name == module_name))
    if not module:
        logger.error(f"Module {module_name} not found in database!")
        return False

    if module.status == "VERIFIED":
        logger.info(f"[SKIP] Module {module_name} is already VERIFIED.")
        return True

    logger.info(f"\n{'='*70}\nSTARTING CONVERSION: {module.name} ({module.module_id})\nTarget: {module.target_path}\n{'='*70}")

    # 1. Authoritative Workspace Validation
    snap = await db.scalar(
        select(RepositorySnapshotModel)
        .where(RepositorySnapshotModel.job_id == job.job_id)
        .order_by(RepositorySnapshotModel.version.desc())
    )
    ws_report = await repository_workspace_service.validate_workspace(
        job.job_id,
        expected_commit=snap.commit_sha if snap else None,
        expected_source=job.source_repository,
        raise_on_error=True,
    )
    logger.info(f"Workspace validated: commit={ws_report.commit_sha}")

    # 2. Queue or Repair
    max_attempts = job.max_repair_attempts or 3
    for current_try in range(max_attempts + 1):
        last = await phase6_service.newest(db, module.module_id)
        if last and last.status in ("REPAIR_REQUIRED", "BLOCKED", "REJECTED", "ESCALATED"):
            if last.attempt_number >= 50:
                logger.error(f"Module {module.name} has exceeded hard attempt limit (50 attempts).")
                return False
            logger.info(f"Queueing repair attempt #{last.attempt_number + 1} for {module.name}...")
            attempt = await phase6_service.queue(
                db,
                job,
                module,
                key=f"p6-{module.module_id}-repair-{last.attempt_number + 1}",
                actor=str(REVIEWER_ID),
                previous=last,
                rationale="Bounded repair to address previous attempt failure feedback",
            )
        elif not last or last.status == "QUEUED":
            attempt = last or await phase6_service.queue(
                db,
                job,
                module,
                key=f"p6-{module.module_id}-conversion",
                actor=str(REVIEWER_ID),
            )
        else:
            logger.info(f"Current attempt status: {last.status}")
            attempt = last

        # 3. Execute Attempt
        logger.info(f"Executing attempt #{attempt.attempt_number} (ID: {attempt.attempt_id})...")
        await phase6_service.execute_attempt(db, attempt.attempt_id)

        # 4. Refresh & Evaluate
        await db.refresh(attempt)
        await db.refresh(module)
        await db.refresh(job)

        run = await db.get(AgentRun, attempt.agent_run_id)
        logger.info(
            f"Attempt #{attempt.attempt_number} outcome: status={attempt.status}, "
            f"module_status={module.status}, cost=${run.cost_usd if run else '0.00'}"
        )

        if attempt.status == "VERIFIED" and module.status == "VERIFIED":
            logger.info(f"[SUCCESS] Module {module.name} reached VERIFIED on attempt #{attempt.attempt_number}!")
            return True

        if attempt.status not in ("REPAIR_REQUIRED", "BLOCKED"):
            logger.error(f"[FAILURE] Attempt #{attempt.attempt_number} ended with terminal status {attempt.status}: {attempt.failure_reason}")
            return False

        logger.warning(f"[REPAIR REQUIRED] Attempt #{attempt.attempt_number} failed: {attempt.failure_reason}. Retrying...")

    logger.error(f"[EXHAUSTED] Module {module.name} failed after {max_attempts} attempts.")
    return False

async def run_batch_conversions(single_module_only: str = None):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, JOB_ID)
        assert job is not None, f"Job {JOB_ID} not found"
        assert job.status == "CONVERTING", f"Job status is {job.status}, expected CONVERTING"

        if single_module_only:
            logger.info(f"Running single module conversion: {single_module_only}")
            success = await convert_one_module(db, job, single_module_only)
            logger.info(f"Module {single_module_only} result: {'PASS' if success else 'FAIL'}")
            return success

        total_modules = 0
        converted_modules = 0

        for batch_idx, batch in enumerate(BATCHES, start=1):
            logger.info(f"\n{'#'*80}\nSTARTING BATCH {batch_idx}/{len(BATCHES)}: {batch}\n{'#'*80}")
            for mod_name in batch:
                total_modules += 1
                success = await convert_one_module(db, job, mod_name)
                if not success:
                    logger.critical(f"[HALT] Batch {batch_idx} halted because {mod_name} failed conversion.")
                    return False
                converted_modules += 1

            logger.info(f"[BATCH COMPLETE] Batch {batch_idx} successfully converted and verified!")

        logger.info(f"\n{'='*80}\nALL 14 MODULES CONVERTED AND VERIFIED! ({converted_modules}/{total_modules})\n{'='*80}")
        return True

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    success = asyncio.run(run_batch_conversions(target))
    sys.exit(0 if success else 1)

