"""W03 Verification Suite: Alembic Clean Bootstrap, Schema Drift Resolution & Historic Data Reconciler."""

import os
import subprocess
import sys
import uuid
import pytest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.testing_infrastructure import DisposableDatabaseManager
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.role import Role
from app.models.workflow import WorkflowGate, WorkflowOutbox
from app.services.reconciliation_service import ReconciliationService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ==============================================================================
# 1. Alembic Clean Bootstrap & Zero Schema Drift (DATA-02 Verification)
# ==============================================================================


@pytest.mark.db_integration
def test_alembic_clean_bootstrap_and_zero_drift():
    """Verify that empty DB upgrades to head and alembic check reports zero drift."""
    manager = DisposableDatabaseManager()
    db_name = manager.generate_database_name()
    manager.create_database(db_name)

    backend_dir = Path(__file__).resolve().parent.parent
    db_url = f"postgresql+asyncpg://postgres:postres123@localhost:5432/{db_name}"
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["ENVIRONMENT"] = "testing"

    try:
        # Step 1: alembic upgrade head
        up_res = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        assert up_res.returncode == 0, f"Alembic upgrade failed:\n{up_res.stderr}"

        # Step 2: alembic check
        chk_res = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        assert (
            chk_res.returncode == 0
        ), f"Alembic check detected drift:\n{chk_res.stdout}\n{chk_res.stderr}"
        assert "No new upgrade operations detected" in chk_res.stdout
    finally:
        manager.drop_database(db_name)


# ==============================================================================
# 2. Immutable System Roles Seeded in Migrations
# ==============================================================================


@pytest.mark.db_integration
@pytest.mark.asyncio
async def test_system_roles_seeded(db_session: AsyncSession):
    """Verify that all 5 immutable system roles exist in the database with permissions."""
    stmt = select(Role).order_by(Role.role_id)
    res = await db_session.execute(stmt)
    roles = {r.role_id: r for r in res.scalars().all()}

    expected_roles = ["ADMIN", "DEVELOPER", "REVIEWER", "SUPER_ADMIN", "VIEWER"]
    for role_id in expected_roles:
        assert role_id in roles, f"Role '{role_id}' is missing from seeded roles."
        assert (
            len(roles[role_id].permissions) > 0
        ), f"Role '{role_id}' has empty permissions."


# ==============================================================================
# 3. Data Consistency Reconciler: Dry Run & Controlled Apply (DATA-03, 04, 05, 06)
# ==============================================================================


@pytest.mark.db_integration
@pytest.mark.asyncio
async def test_reconciler_dry_run_and_apply(db_session: AsyncSession):
    """Verify that dry-run is deterministic (no mutations) and apply is idempotent."""
    now = utc_now()

    from app.models.user import User

    test_user = User(
        user_id=uuid.uuid4(),
        email=f"w03_test_user_{uuid.uuid4().hex[:6]}@example.com",
        full_name="W03 Test User",
        password_hash="mock_hash_xyz",
        role="DEVELOPER",
        status="ACTIVE",
    )
    db_session.add(test_user)
    await db_session.flush()

    # 1. Seed contradictory test records in an isolated transaction
    test_job = Job(
        job_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        name="W03 Reconciliation Test Job",
        source_repository="https://github.com/example/reconcile-test.git",
        source_revision="main",
        source_stack="python",
        target_stack="django",
        status="FAILED",  # Terminal status
        workflow_phase="FAILED",
        budget_limit_usd=100.0,
        budget_used_usd=10.0,
        max_repair_attempts=3,
        owner_user_id=test_user.user_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(test_job)

    # 1a. Module marked VERIFIED without any attempts (DATA-03 contradiction)
    orphan_verified_module = Module(
        module_id=uuid.uuid4(),
        job_id=test_job.job_id,
        name="orphan_verified_module.py",
        legacy_path="app/orphan.py",
        target_path="app/orphan.py",
        status="VERIFIED",
        risk_level="MEDIUM",
        wave_number=1,
        dependency_module_ids=[],
        budget_limit_usd=10.0,
        budget_used_usd=2.0,
        retry_count=0,
        lease_generation=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(orphan_verified_module)

    # 1b. Module with RUNNING attempt (DATA-04 contradiction)
    running_module = Module(
        module_id=uuid.uuid4(),
        job_id=test_job.job_id,
        name="stale_running_module.py",
        legacy_path="app/stale.py",
        target_path="app/stale.py",
        status="RUNNING",
        risk_level="MEDIUM",
        wave_number=1,
        dependency_module_ids=[],
        budget_limit_usd=10.0,
        budget_used_usd=5.0,
        lease_owner="worker-xyz",
        lease_expires_at=now,
        retry_count=1,
        lease_generation=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(running_module)

    stale_attempt = ModuleAttempt(
        attempt_id=uuid.uuid4(),
        module_id=running_module.module_id,
        attempt_number=1,
        status="RUNNING",
        git_branch="rebase/stale-attempt-1",
        started_at=now,
        lease_generation=1,
    )
    db_session.add(stale_attempt)

    # 1c. PENDING gate on a FAILED job (DATA-06 contradiction)
    contradictory_gate = WorkflowGate(
        gate_id=uuid.uuid4(),
        job_id=test_job.job_id,
        gate_type="G2",
        version=1,
        status="PENDING",
        artifact_ids=[],
        artifact_hashes=[],
        requested_at=now,
    )
    db_session.add(contradictory_gate)

    await db_session.commit()

    # ==========================================================================
    # Step 2: Test Dry Run Mode (Preview Only)
    # ==========================================================================
    manifest = await ReconciliationService.analyze(db_session)
    assert manifest.dry_run is True
    assert manifest.summary["total_actions"] >= 3
    assert manifest.summary["evidence_reverify"] >= 1
    assert manifest.summary["stale_worker_quarantine"] >= 1
    assert manifest.summary["gate_reconcile"] >= 1

    # Assert ZERO records were mutated during dry-run
    mod_check = await db_session.get(Module, orphan_verified_module.module_id)
    assert mod_check.status == "VERIFIED", "Dry run must NOT mutate module status."

    att_check = await db_session.get(ModuleAttempt, stale_attempt.attempt_id)
    assert att_check.status == "RUNNING", "Dry run must NOT mutate attempt status."

    gate_check = await db_session.get(WorkflowGate, contradictory_gate.gate_id)
    assert gate_check.status == "PENDING", "Dry run must NOT mutate gate status."

    # ==========================================================================
    # Step 3: Test Apply Mode (Controlled Transactional Execution)
    # ==========================================================================
    apply_result = await ReconciliationService.apply(db_session, manifest)
    assert apply_result["status"] == "APPLIED"
    assert apply_result["applied_counts"]["evidence_reverify"] >= 1
    assert apply_result["applied_counts"]["stale_worker_quarantine"] >= 1
    assert apply_result["applied_counts"]["gate_reconcile"] >= 1

    # Verify post-reconciliation states in DB
    await db_session.refresh(mod_check)
    assert (
        mod_check.status == "PENDING"
    ), "Module eligibility must be revoked to PENDING."

    await db_session.refresh(att_check)
    assert att_check.status == "FAILED", "Stale attempt must be transitioned to FAILED."
    assert "Quarantined by Reconciler" in att_check.failure_reason

    await db_session.refresh(gate_check)
    assert gate_check.status == "INVALIDATED", "Contradictory gate must be INVALIDATED."

    # Verify audit event was recorded
    audit_stmt = (
        select(AuditEvent)
        .where(AuditEvent.event_type == "data.reconciliation_applied")
        .where(AuditEvent.target_resource == "database.reconciliation")
        .order_by(AuditEvent.created_at.desc())
    )
    audit_res = await db_session.execute(audit_stmt)
    audit_event = audit_res.scalars().first()
    assert audit_event is not None
    assert audit_event.payload["batch_id"] == manifest.batch_id

    # ==========================================================================
    # Step 4: Idempotency Proof
    # ==========================================================================
    second_manifest = await ReconciliationService.analyze(db_session)
    # Target entities must no longer appear in the second manifest
    reconciled_ids = {a.entity_id for a in second_manifest.actions}
    assert str(orphan_verified_module.module_id) not in reconciled_ids
    assert str(stale_attempt.attempt_id) not in reconciled_ids
    assert str(contradictory_gate.gate_id) not in reconciled_ids


# ==============================================================================
# 4. Integrity Query Invariants
# ==============================================================================


@pytest.mark.db_integration
@pytest.mark.asyncio
async def test_integrity_query_invariants(db_session: AsyncSession):
    """Verify that integrity invariant queries run without syntax errors."""
    # Query 1: Verified module must have verified attempt
    stmt1 = select(func.count(Module.module_id)).where(
        Module.status == "VERIFIED",
        ~Module.module_id.in_(
            select(ModuleAttempt.module_id).where(ModuleAttempt.status == "VERIFIED")
        ),
    )
    res1 = await db_session.execute(stmt1)
    assert isinstance(res1.scalar(), int)

    # Query 2: Active attempts with expired lease
    stmt2 = select(func.count(ModuleAttempt.attempt_id)).where(
        ModuleAttempt.status == "RUNNING"
    )
    res2 = await db_session.execute(stmt2)
    assert isinstance(res2.scalar(), int)


# ==============================================================================
# 5. Full Bootstrap & Registration Flow Proof (Without Manual SQL)
# ==============================================================================


@pytest.mark.db_integration
def test_empty_db_bootstrap_to_first_job_flow():
    """Proof: empty DB -> upgrade head -> check clean -> register -> login -> create job without manual SQL."""
    manager = DisposableDatabaseManager()
    db_name = manager.generate_database_name()
    manager.create_database(db_name)

    backend_dir = Path(__file__).resolve().parent.parent
    db_url = f"postgresql+asyncpg://postgres:postres123@localhost:5432/{db_name}"
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["ENVIRONMENT"] = "testing"

    try:
        # Step 1: Migration & Check
        up_res = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        assert up_res.returncode == 0, f"Upgrade failed: {up_res.stderr}"

        chk_res = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        assert chk_res.returncode == 0, f"Check failed: {chk_res.stdout}"
        assert "No new upgrade operations detected" in chk_res.stdout

        # Step 2: TestClient flow against this disposable DB
        from app.core.config import settings

        orig_db = settings.DATABASE_URL
        object.__setattr__(settings, "DATABASE_URL", db_url)

        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            # Register user
            user_email = f"bootstrap_user_{uuid.uuid4().hex[:6]}@example.com"
            reg_resp = client.post(
                "/api/v1/auth/register",
                json={
                    "email": user_email,
                    "password": "SecurePassword123!",
                    "full_name": "Bootstrap Verification User",
                },
            )
            assert reg_resp.status_code == 201
            assert reg_resp.json()["role"] in ("DEVELOPER", "VIEWER")

            # Login
            login_resp = client.post(
                "/api/v1/auth/login",
                json={"email": user_email, "password": "SecurePassword123!"},
            )
            assert login_resp.status_code == 200

            # Create first job
            job_resp = client.post(
                "/api/v1/jobs",
                json={
                    "name": "Bootstrap Verification Job",
                    "source_repository": "https://github.com/example/sample-repo.git",
                    "source_revision": "main",
                    "budget": 15000.0,
                },
            )
            assert job_resp.status_code == 201
            assert job_resp.json()["status"] in ("CREATED", "INTAKE")

        object.__setattr__(settings, "DATABASE_URL", orig_db)

    finally:
        manager.drop_database(db_name)
