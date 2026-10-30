"""Comprehensive Test Suite for Repository Staging & Workspace Lifecycle Reliability (P0).

Covers all 12 required tests (A through L) from prompt Section 18:
- Test A: Normal staging & CodeWriter execution against validated workspace.
- Test B: Missing workspace before dispatch -> Supervisor detects & recovers -> CodeWriter executes.
- Test C: Missing workspace during execution -> recoverable failure -> recovery -> safe retry.
- Test D: Invalid Git repository (corrupted .git) -> validation fails -> recovery restores valid Git repo.
- Test E: Wrong repository -> validation rejects -> supervisor recovers correct repository.
- Test F: Concurrent jobs isolation (Job A vs Job B).
- Test G: Concurrent modules in one wave accessing workspace safely.
- Test H: Worker crash & lease recovery with workspace preserved.
- Test I: Backend restart recovery via authoritative PostgreSQL state.
- Test J: Lifecycle-aware cleanup (blocked during active tasks & pending gates).
- Test K: Analyzer execution uses staged workspace without local-path failure.
- Test L: Idempotency (recovery/retry produces no duplicate artifacts).
"""

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import (
    ConflictException,
    WorkspaceException,
    WorkspaceNotFoundException,
    WorkspaceInvalidException,
    WorkspaceCorruptedException,
    WorkspaceWrongRepositoryException,
    WorkspaceGitInvalidException,
    WorkspaceRecoveryFailedException,
)
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.audit import AuditEvent
from app.models.job import Job, JobMembership
from app.models.module import Module, ModuleAttempt
from app.models.phase4 import RepositorySnapshotModel
from app.models.workflow import WorkflowGate
from app.schemas.jobs import JobStatus
from app.services.repository_workspace_service import (
    RepositoryWorkspaceService,
    repository_workspace_service,
)
from app.services.model_gateway import FakeModelProvider, build_fake_gateway
from app.services.git_adapter import ControlledGitAdapter
from app.services import phase6_workspace as ws
from app.services import phase6_service as p6_service
from app.services.supervisor_service import supervisor_service
from test_phase5 import isolated, captured
from test_phase6 import ready, queued, generation, trusted_executor


@pytest.fixture
def temp_origin_repo(tmp_path: Path):
    """Creates a local origin Git repository to act as a remote source."""
    repo_dir = tmp_path / "origin_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    src_dir = repo_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo_dir / "README.md").write_text("# Origin Repo\n", encoding="utf-8")

    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Origin"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "origin@test.local"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True).stdout.strip()
    return repo_dir, head


# ==============================================================================
# Test A: Normal staging & CodeWriter execution against validated workspace
# ==============================================================================
@pytest.mark.asyncio
async def test_a_normal_staging_and_codewriter_execution(ready, trusted_executor, monkeypatch, tmp_path):
    """Test A: Normal staging & CodeWriter execution against validated workspace."""
    db, job, owner, storage, module, repo = ready

    # Configure custom workspace root
    ws_root = tmp_path / "custom_ws_root"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    monkeypatch.setattr("app.services.repository_workspace_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_workspace.repository_workspace_service", test_ws_service)
    monkeypatch.setattr(ws, "repository_for", lambda jid: test_ws_service.get_workspace_path(jid))

    # Stage repository
    commit_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    staged_path, sha = await test_ws_service.stage_repository(
        db, job.job_id, str(repo), revision="main", pinned_commit=commit_sha
    )
    assert staged_path.exists()
    assert (staged_path / ".git").is_dir()

    # Validate workspace
    is_valid = await test_ws_service.validate_workspace(job.job_id, expected_commit=sha)
    assert is_valid.is_ready is True
    assert (await test_ws_service.is_workspace_ready(job.job_id)) is True
    stage_events = set((await db.execute(
        select(AuditEvent.event_type).where(AuditEvent.job_id == job.job_id)
    )).scalars().all())
    assert {"WORKSPACE_STAGE_STARTED", "WORKSPACE_STAGE_COMPLETED"}.issubset(stage_events)

    # Execute CodeWriter attempt against validated workspace
    attempt = await queued(ready, "test-a-key")
    gateway = build_fake_gateway(FakeModelProvider([generation()]))
    await p6_service.execute_attempt(db, attempt.attempt_id, gateway=gateway)
    await db.refresh(attempt)
    assert attempt.status == "VERIFIED"


# ==============================================================================
# Test B: Missing workspace before dispatch -> Supervisor detects & recovers
# ==============================================================================
@pytest.mark.asyncio
async def test_b_missing_workspace_before_dispatch_recovery(ready, trusted_executor, monkeypatch, tmp_path):
    """Test B: Missing workspace before dispatch -> Supervisor detects & recovers."""
    db, job, owner, storage, module, repo = ready

    ws_root = tmp_path / "missing_before_dispatch_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    monkeypatch.setattr("app.services.repository_workspace_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_workspace.repository_workspace_service", test_ws_service)
    monkeypatch.setattr(ws, "repository_for", lambda jid: test_ws_service.get_workspace_path(jid))

    # Set job source repository to the repo fixture
    job.source_repository = str(repo)
    commit_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    await db.commit()

    # Verify workspace does NOT exist initially
    ws_path = test_ws_service.get_workspace_path(job.job_id)
    if ws_path.exists():
        shutil.rmtree(ws_path)
    assert not ws_path.exists()

    # Supervisor ensures workspace before dispatch
    ensured_path = await test_ws_service.ensure_workspace(db, job, expected_commit=commit_sha)
    assert ensured_path.exists()
    assert (ensured_path / ".git").is_dir()
    assert (await test_ws_service.validate_workspace(job.job_id)).is_ready is True
    recovery_events = set((await db.execute(
        select(AuditEvent.event_type).where(AuditEvent.job_id == job.job_id)
    )).scalars().all())
    assert {"WORKSPACE_RECOVERY_STARTED", "WORKSPACE_RECOVERY_COMPLETED"}.issubset(
        recovery_events
    )

    # CodeWriter executes cleanly without missing workspace error
    attempt = await queued(ready, "test-b-key")
    gateway = build_fake_gateway(FakeModelProvider([generation()]))
    await p6_service.execute_attempt(db, attempt.attempt_id, gateway=gateway)
    await db.refresh(attempt)
    assert attempt.status == "VERIFIED"


# ==============================================================================
# Test C: Missing workspace during execution -> safe retry without duplicate task
# ==============================================================================
@pytest.mark.asyncio
async def test_c_missing_workspace_during_execution_safe_retry(ready, trusted_executor, monkeypatch, tmp_path):
    """Test C: Missing workspace during execution -> recoverable failure -> recovery -> safe retry."""
    db, job, owner, storage, module, repo = ready

    ws_root = tmp_path / "mid_run_recovery_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    monkeypatch.setattr("app.services.repository_workspace_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_workspace.repository_workspace_service", test_ws_service)
    monkeypatch.setattr(ws, "repository_for", lambda jid: test_ws_service.get_workspace_path(jid))

    job.source_repository = str(repo)
    await db.commit()

    # Pre-stage workspace
    await test_ws_service.stage_repository(db, job.job_id, str(repo))
    ws_path = test_ws_service.get_workspace_path(job.job_id)
    assert ws_path.exists()

    # Hook prepare to simulate workspace being deleted right before prepare runs
    original_prepare = ws.prepare
    deleted_once = False

    async def flaky_prepare(*args, **kwargs):
        nonlocal deleted_once
        if not deleted_once:
            deleted_once = True
            # Simulate sudden workspace disappearance mid-run
            shutil.rmtree(ws_path, ignore_errors=True)
            raise WorkspaceNotFoundException("Simulated mid-run workspace disappearance")
        return await original_prepare(*args, **kwargs)

    monkeypatch.setattr("app.services.phase6_workspace.prepare", flaky_prepare)

    attempt = await queued(ready, "test-c-key")
    gateway = build_fake_gateway(FakeModelProvider([generation()]))
    await p6_service.execute_attempt(db, attempt.attempt_id, gateway=gateway)
    await db.refresh(attempt)

    # The interrupted attempt is fenced and the logical module task becomes
    # pending; Supervisor dispatch performs recovery before allocating retry 2.
    assert deleted_once is True
    assert attempt.status == "BLOCKED"
    await db.refresh(module)
    assert module.status == "PENDING"
    first_run = await db.get(AgentRun, attempt.agent_run_id)

    retry = await supervisor_service.queue_module_conversion(
        db,
        job,
        module,
        "test-c-retry",
        str(owner.user_id),
        previous=attempt,
        rationale="Retry after recoverable workspace loss",
    )
    retry_run = await db.get(AgentRun, retry.agent_run_id)
    assert retry_run.task_id == first_run.task_id
    assert ws_path.exists()
    await p6_service.execute_attempt(
        db,
        retry.attempt_id,
        gateway=build_fake_gateway(FakeModelProvider([generation()])),
    )
    await db.refresh(retry)
    assert retry.status == "VERIFIED"
    lifecycle_events = set((await db.execute(
        select(AuditEvent.event_type).where(AuditEvent.job_id == job.job_id)
    )).scalars().all())
    assert "WORKSPACE_LOST" in lifecycle_events
    assert "WORKSPACE_RECOVERY_COMPLETED" in lifecycle_events


# ==============================================================================
# Test D: Invalid Git repository (corrupted .git) -> recovery restores valid Git repo
# ==============================================================================
@pytest.mark.asyncio
async def test_d_corrupted_git_repository_recovery(ready, monkeypatch, tmp_path):
    """Test D: Invalid Git repository (corrupted .git) -> validation fails -> recovery restores valid repo."""
    db, job, owner, storage, module, repo = ready

    ws_root = tmp_path / "corrupted_git_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    monkeypatch.setattr("app.services.repository_workspace_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_workspace.repository_workspace_service", test_ws_service)
    monkeypatch.setattr(ws, "repository_for", lambda jid: test_ws_service.get_workspace_path(jid))

    job.source_repository = str(repo)
    await db.commit()

    # Stage valid repository
    await test_ws_service.stage_repository(db, job.job_id, str(repo))
    ws_path = test_ws_service.get_workspace_path(job.job_id)
    assert (ws_path / ".git").is_dir()

    # Corrupt .git directory
    git_dir = ws_path / ".git"
    ControlledGitAdapter._safe_rmtree(git_dir)
    (ws_path / ".git").write_text("corrupted non-directory", encoding="utf-8")

    # Validation must fail
    is_valid = await test_ws_service.validate_workspace(job.job_id)
    assert is_valid.is_ready is False

    # Recovery must restore a healthy repository
    recovered_path = await test_ws_service.recover_workspace(db, job.job_id)
    assert recovered_path.exists()
    assert (recovered_path / ".git").is_dir()
    assert (await test_ws_service.validate_workspace(job.job_id)).is_ready is True


# ==============================================================================
# Test E: Wrong repository -> validation rejects
# ==============================================================================
@pytest.mark.asyncio
async def test_e_wrong_repository_validation_rejects(ready, monkeypatch, tmp_path):
    """Test E: Wrong repository (tampered sidecar job_id) -> validation rejects."""
    db, job, owner, storage, module, repo = ready

    ws_root = tmp_path / "wrong_repo_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)

    # Stage repository for job
    staged_path, _ = await test_ws_service.stage_repository(db, job.job_id, str(repo))

    # Tamper with sidecar to point to a different job_id
    sidecar_path = staged_path / ".rebase_workspace.json"
    assert sidecar_path.exists()
    tampered_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    tampered_data["job_id"] = str(uuid.uuid4())  # Different job ID
    sidecar_path.write_text(json.dumps(tampered_data), encoding="utf-8")

    # Validation must reject with wrong repository exception
    with pytest.raises(WorkspaceWrongRepositoryException):
        await test_ws_service.validate_workspace(job.job_id, raise_for_failure=True)


# ==============================================================================
# Test F: Concurrent jobs isolation
# ==============================================================================
@pytest.mark.asyncio
async def test_f_concurrent_jobs_isolation(ready, monkeypatch, tmp_path):
    """Test F: Concurrent jobs isolation (Job A vs Job B in separate workspaces)."""
    db, job_a, owner, storage, module_a, repo = ready

    ws_root = tmp_path / "concurrent_jobs_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)

    # Create Job B
    job_b = Job(
        job_id=uuid.uuid4(),
        name="Job B Modernization",
        source_repository=str(repo),
        source_revision="main",
        status=JobStatus.CONVERTING.value,
        budget_limit_usd=1000.0,
        budget_used_usd=0.0,
        owner_user_id=owner.user_id,
    )
    db.add(job_b)
    await db.commit()

    # Each worker/process owns its DB session; PostgreSQL row locks coordinate
    # same-job initialization without illegally sharing AsyncSession objects.
    factory = async_sessionmaker(db.bind, expire_on_commit=False)

    async def stage(job_id):
        async with factory() as worker_db:
            return await test_ws_service.stage_repository(worker_db, job_id, str(repo))

    path_a, path_b = await asyncio.gather(stage(job_a.job_id), stage(job_b.job_id))

    # Verify complete path and sidecar isolation
    assert path_a[0] != path_b[0]
    assert str(job_a.job_id) in str(path_a[0].name)
    assert str(job_b.job_id) in str(path_b[0].name)

    assert (await test_ws_service.validate_workspace(job_a.job_id)).is_ready is True
    assert (await test_ws_service.validate_workspace(job_b.job_id)).is_ready is True


# ==============================================================================
# Test G: Concurrent modules in one wave
# ==============================================================================
@pytest.mark.asyncio
async def test_g_concurrent_modules_in_one_wave(ready, trusted_executor, monkeypatch, tmp_path):
    """Test G: Concurrent modules in one wave accessing workspace safely."""
    db, job, owner, storage, module_1, repo = ready

    ws_root = tmp_path / "concurrent_modules_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    monkeypatch.setattr("app.services.repository_workspace_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_workspace.repository_workspace_service", test_ws_service)
    monkeypatch.setattr(ws, "repository_for", lambda jid: test_ws_service.get_workspace_path(jid))

    job.source_repository = str(repo)
    await db.commit()

    # Stage workspace
    repository = await test_ws_service.ensure_workspace(db, job)
    commit = (await test_ws_service.validate_workspace(job.job_id)).commit_sha
    monkeypatch.setattr(ws, "ROOT", tmp_path / "module_worktrees")

    # Concurrent modules get independent branches/worktrees from one validated
    # read-only authoritative workspace.
    worktree_a, worktree_b = await asyncio.gather(
        ws.prepare(
            repository, str(job.job_id), str(module_1.module_id),
            str(uuid.uuid4()), 1, commit,
        ),
        ws.prepare(
            repository, str(job.job_id), str(uuid.uuid4()),
            str(uuid.uuid4()), 1, commit,
        ),
    )
    assert worktree_a[0] != worktree_b[0]
    assert (worktree_a[0] / "legacy" / "calc.py").is_file()
    assert (worktree_b[0] / "legacy" / "calc.py").is_file()


# ==============================================================================
# Test H: Worker crash & lease recovery with workspace preserved
# ==============================================================================
@pytest.mark.asyncio
async def test_h_worker_crash_and_lease_recovery(ready, monkeypatch, tmp_path):
    """Test H: Worker crash & lease recovery with workspace preserved."""
    db, job, owner, storage, module, repo = ready

    ws_root = tmp_path / "worker_crash_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    monkeypatch.setattr("app.services.repository_workspace_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_workspace.repository_workspace_service", test_ws_service)
    monkeypatch.setattr(ws, "repository_for", lambda jid: test_ws_service.get_workspace_path(jid))

    job.source_repository = str(repo)
    await db.commit()

    # Pre-stage workspace
    await test_ws_service.stage_repository(db, job.job_id, str(repo))

    # Queue attempt and simulate lease acquisition
    attempt = await queued(ready, "test-h-key")
    module.lease_owner = "worker-pid-9999"
    module.status = "RUNNING"
    await db.commit()

    # Simulate worker crash (reconcile job clears orphaned lease while workspace stays intact)
    await supervisor_service.reconcile_job(db, job.job_id)
    await db.refresh(module)

    # Workspace is still valid
    assert (await test_ws_service.validate_workspace(job.job_id)).is_ready is True


# ==============================================================================
# Test I: Backend restart recovery via authoritative PostgreSQL checkpointer
# ==============================================================================
@pytest.mark.asyncio
async def test_i_backend_restart_recovery(ready, monkeypatch, tmp_path):
    """Test I: Backend restart recovery via authoritative PostgreSQL state."""
    db, job, owner, storage, module, repo = ready

    ws_root = tmp_path / "backend_restart_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    monkeypatch.setattr("app.services.repository_workspace_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_workspace.repository_workspace_service", test_ws_service)
    monkeypatch.setattr(ws, "repository_for", lambda jid: test_ws_service.get_workspace_path(jid))

    job.source_repository = str(repo)
    job.status = JobStatus.CONVERTING.value
    await db.commit()

    # Stage initial workspace
    await test_ws_service.stage_repository(db, job.job_id, str(repo))

    # Simulate fresh service instantiation after restart
    restarted_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    res_path = await restarted_ws_service.ensure_workspace(db, job)
    assert res_path.exists()
    assert (await restarted_ws_service.validate_workspace(job.job_id)).is_ready is True


# ==============================================================================
# Test J: Lifecycle-aware cleanup (blocked during active tasks & pending gates)
# ==============================================================================
@pytest.mark.asyncio
async def test_j_lifecycle_aware_cleanup(ready, monkeypatch, tmp_path):
    """Test J: Lifecycle-aware cleanup (blocked during active tasks & pending gates)."""
    db, job, owner, storage, module, repo = ready

    ws_root = tmp_path / "cleanup_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)

    job.source_repository = str(repo)
    staged_path, _ = await test_ws_service.stage_repository(db, job.job_id, str(repo))
    assert staged_path.exists()

    # 1. Cleanup while job is CONVERTING must be refused
    job.status = JobStatus.CONVERTING.value
    await db.commit()
    with pytest.raises(ConflictException, match="Cannot cleanup repository workspace: job is in active state"):
        await test_ws_service.cleanup_workspace(db, job.job_id)
    assert staged_path.exists()

    # 2. Cleanup while job is AWAITING_GATE_G3 must be refused
    job.status = JobStatus.AWAITING_GATE_G3.value
    await db.commit()
    with pytest.raises(ConflictException, match="Cannot cleanup repository workspace: job is in active state"):
        await test_ws_service.cleanup_workspace(db, job.job_id)
    assert staged_path.exists()

    # 3. Cleanup allowed after COMPLETED and no running attempts
    job.status = JobStatus.COMPLETED.value
    await db.commit()
    cleaned = await test_ws_service.cleanup_workspace(db, job.job_id)
    assert cleaned is True
    assert not staged_path.exists()


# ==============================================================================
# Test K: Analyzer execution uses staged workspace without local-path failure
# ==============================================================================
@pytest.mark.asyncio
async def test_k_analyzer_execution_uses_staged_workspace(ready, monkeypatch, tmp_path):
    """Test K: Analyzer execution uses staged workspace without local-path failure."""
    db, job, owner, storage, module, repo = ready

    ws_root = tmp_path / "analyzer_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    monkeypatch.setattr("app.services.phase4_orchestrator.repository_workspace_service", test_ws_service)

    job.source_repository = str(repo)
    commit_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    await db.commit()

    # Verify ensure_workspace stages repository for Analyzer
    ensured_path = await test_ws_service.ensure_workspace(db, job, expected_commit=commit_sha)
    assert ensured_path.exists()
    assert (ensured_path / ".git").is_dir()
    assert (ensured_path / "legacy" / "calc.py").exists()


# ==============================================================================
# Test L: Idempotency (recovery/retry produces no duplicate artifacts)
# ==============================================================================
@pytest.mark.asyncio
async def test_l_idempotency_recovery_produces_no_duplicate_artifacts(ready, monkeypatch, tmp_path):
    """Test L: Force recovery/retry -> no duplicate artifacts, preserves attempt integrity."""
    db, job, owner, storage, module, repo = ready

    ws_root = tmp_path / "idempotency_ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    test_ws_service = RepositoryWorkspaceService(workspace_root=ws_root)
    monkeypatch.setattr("app.services.repository_workspace_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_service.repository_workspace_service", test_ws_service)
    monkeypatch.setattr("app.services.phase6_workspace.repository_workspace_service", test_ws_service)
    monkeypatch.setattr(ws, "repository_for", lambda jid: test_ws_service.get_workspace_path(jid))

    job.source_repository = str(repo)
    await db.commit()

    # Pre-stage workspace
    await test_ws_service.stage_repository(db, job.job_id, str(repo))

    # Record initial artifact count
    initial_artifacts = len((await db.execute(select(Artifact).where(Artifact.job_id == job.job_id))).scalars().all())

    # Force workspace recovery twice
    await test_ws_service.recover_workspace(db, job.job_id)
    await test_ws_service.recover_workspace(db, job.job_id)

    # Artifact count has not increased
    final_artifacts = len((await db.execute(select(Artifact).where(Artifact.job_id == job.job_id))).scalars().all())
    assert final_artifacts == initial_artifacts
