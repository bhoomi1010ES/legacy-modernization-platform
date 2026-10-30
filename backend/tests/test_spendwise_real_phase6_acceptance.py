"""Real-environment Phase 6 Acceptance Tests for the Spendwise Repository.

Covers:
1. Full end-to-end acceptance flow against the real Spendwise repository:
   - G3 human approval verification & governance
   - Authoritative repository workspace validation
   - CodeWriter execution with real LLM and token accounting
   - Real isolated Git branch and worktree creation
   - Real converted files committed to repository
   - Docker verifier execution across all frozen characterization cases & checks
   - Reviewer / SAST verification with 0 security findings
   - ModuleAttempt and Module status verified
2. Workspace recovery acceptance:
   - Detecting workspace corruption/missing state
   - Authoritative ensure_workspace / validate_workspace recovery
3. Multi-module and attempt worktree isolation:
   - Independent branches and worktrees per attempt
   - Target scope containment checks
"""

import os
import uuid
import pytest
from pathlib import Path
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.workflow import WorkflowGate
from app.models.gate import GateDecision
from app.models.audit import AuditEvent
from app.models.test_case import TestResult
from app.models.phase4 import RepositorySnapshotModel
from app.services.phase5_service import read_payload
from app.services.repository_workspace_service import repository_workspace_service
from app.services import phase6_workspace as ws

SPENDWISE_JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
APP_UTILS_MODULE_ID = uuid.UUID("8a53e2d8-e298-5112-a9a7-cca8fe8cc3c3")


@pytest.mark.asyncio
async def test_spendwise_real_phase6_full_acceptance():
    """Verify that the Spendwise repository underwent a real Phase 6 conversion.

    All layers (Git, DB, Artifacts, Verifier, Reviewer, Supervisor) agree on VERIFIED.
    """
    async with AsyncSessionLocal() as db:
        # 1. Job and Governance Status
        job = await db.get(Job, SPENDWISE_JOB_ID)
        assert job is not None, f"Spendwise job {SPENDWISE_JOB_ID} not found"
        assert job.status in ("CONVERTING", "AWAITING_GATE_G4", "COMPLETED"), f"Invalid job status: {job.status}"

        # 2. Gate G3 Human Approval Verification
        g3_gate = await db.scalar(
            select(WorkflowGate)
            .where(WorkflowGate.job_id == SPENDWISE_JOB_ID, WorkflowGate.gate_type == "G3")
            .order_by(WorkflowGate.version.desc())
        )
        assert g3_gate is not None, "Gate G3 not found"
        assert g3_gate.status == "APPROVED", f"G3 gate status: {g3_gate.status}"

        g3_decision = await db.scalar(
            select(GateDecision)
            .where(GateDecision.gate_id == g3_gate.gate_id)
            .order_by(GateDecision.decided_at.desc())
        )
        assert g3_decision is not None, "Gate G3 decision record not found"
        assert g3_decision.decision == "APPROVED"
        assert len(g3_decision.rationale) >= 10
        assert g3_decision.reviewer_user_id is not None

        # Verify audit event for G3 decision
        audit = await db.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.job_id == SPENDWISE_JOB_ID,
                AuditEvent.event_type == "GATE_DECIDED",
                AuditEvent.target_resource == str(g3_gate.gate_id),
            )
        )
        assert audit is not None, "AuditEvent for G3 GATE_DECIDED missing"

        # 3. Spendwise Repository Workspace Validation
        snap = await db.scalar(
            select(RepositorySnapshotModel)
            .where(RepositorySnapshotModel.job_id == SPENDWISE_JOB_ID)
            .order_by(RepositorySnapshotModel.version.desc())
        )
        ws_report = await repository_workspace_service.validate_workspace(
            job.job_id,
            expected_commit=snap.commit_sha if snap else None,
            expected_source=job.source_repository,
            raise_on_error=True,
        )
        assert ws_report.is_ready is True
        assert ws_report.commit_sha == snap.commit_sha

        # 4. Module & ModuleAttempt State
        module = await db.get(Module, APP_UTILS_MODULE_ID)
        assert module is not None, "Module comp_app-utils_b30e84 not found"
        assert module.status == "VERIFIED", f"Module status is {module.status}, expected VERIFIED"

        attempts = (
            await db.execute(
                select(ModuleAttempt)
                .where(ModuleAttempt.module_id == APP_UTILS_MODULE_ID)
                .order_by(ModuleAttempt.attempt_number.desc())
            )
        ).scalars().all()
        assert len(attempts) >= 1, "No attempts recorded for module"

        verified_attempt = next((a for a in attempts if a.status == "VERIFIED"), None)
        assert verified_attempt is not None, "No VERIFIED attempt found for module"
        assert verified_attempt.git_branch.startswith(f"job/{SPENDWISE_JOB_ID}/module/{APP_UTILS_MODULE_ID}/attempt/")

        # 5. AgentRun Metrics
        run = await db.get(AgentRun, verified_attempt.agent_run_id)
        assert run is not None
        assert run.agent_name == "CodeWriter"
        assert run.input_tokens > 0
        assert run.output_tokens > 0
        assert run.cost_usd > 0

        # 6. Real Git Worktree and Branch Verification
        ws_root = Path(__file__).resolve().parents[1] / "repo_workspaces" / "phase6" / str(verified_attempt.attempt_id)
        assert ws_root.is_dir(), f"Worktree directory {ws_root} does not exist"

        # Check git commit in worktree
        repo_path = repository_workspace_service.get_workspace_path(SPENDWISE_JOB_ID)
        rc, out, _ = repository_workspace_service._safe_git_exec(
            ws_root, ["log", "-1", "--format=%H"]
        )
        assert rc == 0
        commit_sha = out.strip()
        assert len(commit_sha) == 40

        # Check real changed files in worktree
        rc, out, _ = repository_workspace_service._safe_git_exec(
            ws_root, ["diff", "--name-only", f"{snap.commit_sha}..HEAD"]
        )
        assert rc == 0
        changed = [line.strip().replace("\\", "/") for line in out.strip().splitlines() if line.strip()]
        assert "app/modules/app-utils_b30e84/csv_utils.py" in changed
        assert "app/modules/app-utils_b30e84/date_utils.py" in changed
        assert "app/modules/app-utils_b30e84/pagination.py" in changed
        assert "app/modules/app-utils_b30e84/__init__.py" in changed

        # 7. Published Artifacts Verification
        artifacts = (
            await db.execute(
                select(Artifact)
                .where(
                    Artifact.job_id == SPENDWISE_JOB_ID,
                    Artifact.module_id == APP_UTILS_MODULE_ID,
                )
                .order_by(Artifact.created_at.desc())
            )
        ).scalars().all()

        attempt_artifacts = [
            a for a in artifacts if a.extra_metadata.get("attempt_id") == str(verified_attempt.attempt_id)
        ]
        types = {a.artifact_type for a in attempt_artifacts}
        assert "CONVERTED_MODULE" in types
        assert "VERIFICATION_REPORT" in types
        assert "REVIEW_REPORT" in types

        verif_art = next(a for a in attempt_artifacts if a.artifact_type == "VERIFICATION_REPORT")
        verif_data = await read_payload(verif_art)
        assert verif_data.get("available") is True
        assert verif_data.get("passed") is True
        assert verif_data.get("source_unchanged") is True
        assert all(c.get("status") == "PASS" for c in verif_data.get("checks", []))
        assert len(verif_data.get("cases", [])) == 141
        assert all(c.get("status") == "PASS" for c in verif_data.get("cases", []))

        rev_art = next(a for a in attempt_artifacts if a.artifact_type == "REVIEW_REPORT")
        rev_data = await read_payload(rev_art)
        assert rev_data.get("status") == "PASS"
        assert len(rev_data.get("findings", [])) == 0

        # 8. TestResult Rows in Database
        test_results = (
            await db.execute(
                select(TestResult).where(TestResult.attempt_id == verified_attempt.attempt_id)
            )
        ).scalars().all()
        assert len(test_results) == 141
        assert all(r.outcome == "PASSED" for r in test_results)


@pytest.mark.asyncio
async def test_spendwise_workspace_recovery_acceptance():
    """Verify repository workspace validation and recovery mechanism."""
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, SPENDWISE_JOB_ID)
        assert job is not None

        snap = await db.scalar(
            select(RepositorySnapshotModel)
            .where(RepositorySnapshotModel.job_id == SPENDWISE_JOB_ID)
            .order_by(RepositorySnapshotModel.version.desc())
        )

        # 1. Authoritative workspace path
        ws_path = repository_workspace_service.get_workspace_path(job.job_id)
        assert ws_path.is_dir()

        # 2. Workspace validation succeeds against authoritative snapshot commit
        res = await repository_workspace_service.validate_workspace(
            job.job_id,
            expected_commit=snap.commit_sha,
            expected_source=job.source_repository,
            raise_on_error=True,
        )
        assert res.is_ready is True
        assert res.commit_sha == snap.commit_sha

        # 3. Tampering/Wrong commit detection fails closed
        res_bad = await repository_workspace_service.validate_workspace(
            job.job_id,
            expected_commit="0000000000000000000000000000000000000000",
            expected_source=job.source_repository,
            raise_on_error=False,
        )
        assert res_bad.is_ready is False
        assert res_bad.error_code == "WORKSPACE_WRONG_REPOSITORY"


def test_spendwise_multi_module_worktree_isolation():
    """Verify that Git worktrees are strictly isolated and enforce target boundaries."""
    repo_path = repository_workspace_service.get_workspace_path(SPENDWISE_JOB_ID)
    rc, out, _ = repository_workspace_service._safe_git_exec(repo_path, ["worktree", "list"])
    assert rc == 0

    lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
    # At least the main workspace and our attempt worktree must exist
    assert len(lines) >= 2

    # Paths must be distinct
    paths = [line.split()[0] for line in lines]
    assert len(paths) == len(set(paths)), "Worktree paths collision detected"

    # Verify target path containment
    valid_target = ws.safe_target(
        repo_path,
        "app/modules/app-utils_b30e84/csv_utils.py",
        "app/modules/app-utils_b30e84",
    )
    assert valid_target.name == "csv_utils.py"

    # Out-of-bounds target path must be rejected
    with pytest.raises(ValueError, match="Unsafe target path|cannot edit"):
        ws.safe_target(
            repo_path,
            "tests/test_fake.py",
            "app/modules/app-utils_b30e84",
        )
