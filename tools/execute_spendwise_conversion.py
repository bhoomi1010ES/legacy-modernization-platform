import asyncio
import json
import logging
import uuid
from pathlib import Path
from decimal import Decimal

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spendwise_acceptance")

JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
MODULE_ID = uuid.UUID("8a53e2d8-e298-5112-a9a7-cca8fe8cc3c3") # comp_app-utils_b30e84
REVIEWER_ID = uuid.UUID("bbacac52-6e67-43a3-9983-3ad6354343d2")

async def run_conversion():
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, JOB_ID)
        assert job is not None, f"Job {JOB_ID} not found"
        assert job.status == "CONVERTING", f"Expected job status CONVERTING, got {job.status}"
        print(f"[*] Job {job.job_id} confirmed in CONVERTING status")

        module = await db.get(Module, MODULE_ID)
        assert module is not None, f"Module {MODULE_ID} not found"
        print(f"[*] Target Module: {module.name} (Wave {module.wave_number})")
        print(f"    Legacy Path: {module.legacy_path}")
        print(f"    Target Path: {module.target_path}")

        # 1. Authoritative Workspace Validation
        print("[*] Validating Spendwise repository workspace before CodeWriter...")
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
        assert ws_report.is_ready is True, f"Workspace not ready: {ws_report}"
        print(f"[OK] Authoritative Workspace Validated: commit={ws_report.commit_sha}")

        # 2. Queue Module Conversion or Bounded Repair
        last = await phase6_service.newest(db, module.module_id)
        if last and last.status in ("REPAIR_REQUIRED", "BLOCKED", "REJECTED"):
            print(f"[*] Previous attempt {last.attempt_id} was {last.status}. Queueing bounded repair attempt {last.attempt_number + 1}...")
            attempt = await phase6_service.queue(
                db,
                job,
                module,
                key=f"p6-{module.module_id}-repair-{last.attempt_number + 1}",
                actor=str(REVIEWER_ID),
                previous=last,
                rationale="Bounded repair to execute against updated docker sandbox configuration",
            )
        else:
            print("[*] Queueing module conversion task via phase6_service.queue...")
            idempotency_key = f"p6-{module.module_id}-acceptance"
            attempt = await phase6_service.queue(
                db,
                job,
                module,
                key=idempotency_key,
                actor=str(REVIEWER_ID),
            )
        print(f"[OK] Queued ModuleAttempt: ID={attempt.attempt_id}, Number={attempt.attempt_number}, Branch={attempt.git_branch}")

        # 3. Execute Attempt (CodeWriter -> Worktree -> Apply Changes -> Verifier -> Reviewer)
        print("[*] Executing attempt with real LLM (gpt-4o-mini), Git worktree, and Docker Verifier...")
        await phase6_service.execute_attempt(db, attempt.attempt_id)

        # 4. Refresh & Verify Database State
        await db.refresh(attempt)
        await db.refresh(module)
        await db.refresh(job)

        run = await db.get(AgentRun, attempt.agent_run_id)

        print("\n" + "=" * 60)
        print("CONVERSION EXECUTION RESULTS")
        print("=" * 60)
        print(f"Attempt ID:         {attempt.attempt_id}")
        print(f"Attempt Status:     {attempt.status}")
        print(f"Module Status:      {module.status}")
        print(f"Git Branch:         {attempt.git_branch}")
        print(f"Model Provider:     {run.model_provider} / {run.model_identifier}")
        print(f"Tokens Used:        Input={run.input_tokens}, Output={run.output_tokens}")
        print(f"Cost USD:           ${run.cost_usd}")
        print(f"Job Budget Used:    ${job.budget_used_usd} / ${job.budget_limit_usd}")

        # 5. Retrieve Artifacts for this Attempt
        artifacts = (
            await db.execute(
                select(Artifact)
                .where(Artifact.job_id == JOB_ID, Artifact.module_id == MODULE_ID)
                .order_by(Artifact.created_at.desc())
            )
        ).scalars().all()

        attempt_artifacts = [
            a for a in artifacts if a.extra_metadata.get("attempt_id") == str(attempt.attempt_id)
        ]

        print(f"\nPublished Artifacts for Attempt {attempt.attempt_number} ({len(attempt_artifacts)}):")
        code_artifact = None
        verif_artifact = None
        rev_artifact = None
        for a in attempt_artifacts:
            print(f" - [{a.artifact_type}] ID={a.artifact_id}, v={a.version}, Hash={a.content_hash}")
            if a.artifact_type == "CONVERTED_MODULE" and not code_artifact:
                code_artifact = a
            elif a.artifact_type == "VERIFICATION_REPORT" and not verif_artifact:
                verif_artifact = a
            elif a.artifact_type == "REVIEW_REPORT" and not rev_artifact:
                rev_artifact = a

        assert code_artifact is not None, "CONVERTED_MODULE artifact missing"
        assert verif_artifact is not None, "VERIFICATION_REPORT artifact missing"
        assert rev_artifact is not None, "REVIEW_REPORT artifact missing"

        code_payload = await read_payload(code_artifact)
        verif_payload = await read_payload(verif_artifact)
        rev_payload = await read_payload(rev_artifact)

        print("\n--- Converted Code Details ---")
        print(f"Commit SHA:         {code_payload.get('commit')}")
        print(f"Changed Files:      {code_payload.get('changed_files')}")
        print(f"Diff Preview:\n{code_payload.get('diff', '')[:500]}...")

        print("\n--- Verifier Details ---")
        print(f"Available:          {verif_payload.get('available')}")
        print(f"Passed:             {verif_payload.get('passed')}")
        print(f"Image ID:           {verif_payload.get('image_id')}")
        print(f"Source Unchanged:   {verif_payload.get('source_unchanged')}")
        print(f"Checks Run ({len(verif_payload.get('checks', []))}):")
        for chk in verif_payload.get("checks", []):
            print(f"   [{chk.get('category')}] status={chk.get('status')} exit={chk.get('exit_code')} cmd={' '.join(chk.get('command', []))}")
        passed_cases = sum(1 for c in verif_payload.get("cases", []) if c.get("status") == "PASS")
        print(f"Cases Evaluated:    {passed_cases}/{len(verif_payload.get('cases', []))} PASSED")

        print("\n--- Reviewer / SAST Details ---")
        print(f"Review Status:      {rev_payload.get('status')}")
        print(f"Findings Count:     {len(rev_payload.get('findings', []))}")
        if rev_payload.get("findings"):
            for f in rev_payload.get("findings"):
                print(f"   Finding: {f.get('category')} severity={f.get('severity')} - {f.get('message')}")

        # 6. Verify TestResult Rows in Database
        test_results = (
            await db.execute(
                select(TestResult).where(TestResult.attempt_id == attempt.attempt_id)
            )
        ).scalars().all()
        print(f"\nRecorded TestResult DB rows: {len(test_results)}")
        passed_db = sum(1 for r in test_results if r.outcome == "PASSED")
        print(f"TestResult DB outcomes: {passed_db}/{len(test_results)} PASSED")

        assert attempt.status == "VERIFIED", f"Attempt status was {attempt.status}, expected VERIFIED"
        assert module.status == "VERIFIED", f"Module status was {module.status}, expected VERIFIED"
        print("\n[OK] REAL PHASE 6 CONVERSION ACCEPTANCE COMPLETED AND VERIFIED!")

if __name__ == "__main__":
    asyncio.run(run_conversion())
