"""Tests for W12 - Truthful Workflow Projection and Frontend State Integrity."""

import uuid
from decimal import Decimal
from fastapi.testclient import TestClient
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.gate import GateDecision
from app.models.job import Job, JobMembership
from app.models.module import Module, ModuleAttempt, VerificationRun
from app.models.user import User
from app.models.workflow import WorkflowGate
from app.services.workflow_projection_service import WorkflowProjectionService


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        user_id=uuid.uuid4(),
        email=f"w12_test_{uuid.uuid4().hex[:6]}@example.com",
        full_name="W12 Test User",
        password_hash="mock_hash_for_testing",
        role="DEVELOPER",
        status="ACTIVE",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_no_agent_run_row_means_not_started(
    db_session: AsyncSession,
    test_user: User,
):
    """Proves: Without an AgentRun row, specialist stages are NOT_STARTED (UI-01 fix)."""
    job = Job(
        job_id=uuid.uuid4(),
        owner_user_id=test_user.user_id,
        name="Empty Job",
        source_repository="https://github.com/org/repo.git",
        source_revision="main",
        source_stack="Java",
        target_stack="NodeJS",
        status="ANALYZING",
        budget_limit_usd=Decimal("15000.00"),
        budget_used_usd=Decimal("0.00"),
    )
    db_session.add(job)
    await db_session.commit()

    service = WorkflowProjectionService()
    projection = await service.get_projection(db_session, job.job_id, test_user)

    assert projection.job_id == str(job.job_id)
    assert projection.status == "ANALYZING"

    # All analysis workers must be NOT_STARTED because no AgentRun exists
    worker_stages = [
        s for s in projection.stages
        if s.stage_id in (
            "structure_worker", "dependency_worker", "interface_worker",
            "data_worker", "test_worker", "integration_worker", "risk_worker",
            "architect", "feasibility"
        )
    ]
    assert len(worker_stages) == 9
    for stage in worker_stages:
        assert stage.status == "NOT_STARTED", f"Stage {stage.stage_id} must be NOT_STARTED, got {stage.status}"
        assert stage.evidence_available is False
        assert stage.agent_run_id is None


@pytest.mark.asyncio
async def test_missing_verifier_run_is_not_run_and_codewriter_is_succeeded_not_verified(
    db_session: AsyncSession,
    test_user: User,
):
    """Proves: Successful CodeWriter is SUCCEEDED, missing Verifier is NOT_RUN (never VERIFIED without verifier)."""
    job = Job(
        job_id=uuid.uuid4(),
        owner_user_id=test_user.user_id,
        name="Conversion Job",
        source_repository="https://github.com/org/repo.git",
        source_revision="main",
        source_stack="Java",
        target_stack="NodeJS",
        status="CONVERTING",
        budget_limit_usd=Decimal("15000.00"),
        budget_used_usd=Decimal("100.00"),
    )
    db_session.add(job)

    # CodeWriter finished successfully
    code_run = AgentRun(
        run_id=uuid.uuid4(),
        job_id=job.job_id,
        agent_name="CodeWriterAgent",
        status="SUCCEEDED",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=Decimal("1.50"),
    )
    db_session.add(code_run)

    # Module was converted by CodeWriter
    module = Module(
        module_id=uuid.uuid4(),
        job_id=job.job_id,
        name="auth_service",
        legacy_path="src/auth.py",
        target_path="dist/auth.ts",
        status="CONVERTED",
        risk_level="MEDIUM",
        wave_number=1,
    )
    db_session.add(module)

    attempt = ModuleAttempt(
        attempt_id=uuid.uuid4(),
        module_id=module.module_id,
        agent_run_id=code_run.run_id,
        attempt_number=1,
        status="SUCCEEDED",
        git_branch="conversion/attempt-1",
    )
    db_session.add(attempt)
    await db_session.commit()

    service = WorkflowProjectionService()
    projection = await service.get_projection(db_session, job.job_id, test_user)

    code_stage = next(s for s in projection.stages if s.stage_id == "code_writer")
    verifier_stage = next(s for s in projection.stages if s.stage_id == "verifier")

    # CodeWriter must NOT map to VERIFIED
    assert code_stage.status == "SUCCEEDED"
    assert code_stage.status != "VERIFIED"

    # Verifier must be NOT_RUN
    assert verifier_stage.status == "NOT_RUN"
    assert verifier_stage.agent_run_id is None

    # Module verification status must be NOT_RUN
    mod_proj = projection.modules[0]
    assert mod_proj.verification_status == "NOT_RUN"
    assert mod_proj.verification_run_id is None


@pytest.mark.asyncio
async def test_stale_or_invalidated_plan_blocks_gate(
    db_session: AsyncSession,
    test_user: User,
):
    """Proves: Invalidation or upstream drift produces STALE / FAILED gate projection with blocking reason."""
    job = Job(
        job_id=uuid.uuid4(),
        owner_user_id=test_user.user_id,
        name="Stale Plan Job",
        source_repository="https://github.com/org/repo.git",
        source_revision="main",
        source_stack="Java",
        target_stack="NodeJS",
        status="AWAITING_GATE_G3",
        budget_limit_usd=Decimal("15000.00"),
        budget_used_usd=Decimal("50.00"),
    )
    db_session.add(job)

    gate = WorkflowGate(
        gate_id=uuid.uuid4(),
        job_id=job.job_id,
        gate_type="G3",
        version=1,
        status="INVALIDATED",
        artifact_hashes={"CONVERSION_PLAN": "hash_plan_1"},
        blocking_reason="Upstream CharacterizationSuite modified; plan is stale",
    )
    db_session.add(gate)
    await db_session.commit()

    service = WorkflowProjectionService()
    projection = await service.get_projection(db_session, job.job_id, test_user)

    g3_proj = next(g for g in projection.gates if g.gate_type == "G3")
    assert g3_proj.status == "INVALIDATED"
    assert g3_proj.is_stale is True
    assert "stale" in g3_proj.blocking_reason.lower()

    g3_stage = next(s for s in projection.stages if s.stage_id == "gate_g3")
    assert g3_stage.status == "FAILED"
    assert "stale" in g3_stage.error_message.lower()


@pytest.mark.asyncio
async def test_truthful_progress_and_module_counts(
    db_session: AsyncSession,
    test_user: User,
):
    """Proves: UI-05 fix - progress reflects real verified modules, not coarse 0/50/100."""
    job = Job(
        job_id=uuid.uuid4(),
        owner_user_id=test_user.user_id,
        name="Progress Test Job",
        source_repository="https://github.com/org/repo.git",
        source_revision="main",
        source_stack="Java",
        target_stack="NodeJS",
        status="CONVERTING",
        budget_limit_usd=Decimal("15000.00"),
        budget_used_usd=Decimal("20.00"),
    )
    db_session.add(job)

    # 4 modules total: 2 verified, 1 converted, 1 pending
    m1 = Module(
        module_id=uuid.uuid4(),
        job_id=job.job_id,
        name="mod1",
        legacy_path="a",
        target_path="b",
        status="VERIFIED",
        risk_level="LOW",
        wave_number=1,
    )
    m2 = Module(
        module_id=uuid.uuid4(),
        job_id=job.job_id,
        name="mod2",
        legacy_path="c",
        target_path="d",
        status="VERIFIED",
        risk_level="LOW",
        wave_number=1,
    )
    m3 = Module(
        module_id=uuid.uuid4(),
        job_id=job.job_id,
        name="mod3",
        legacy_path="e",
        target_path="f",
        status="CONVERTED",
        risk_level="MEDIUM",
        wave_number=2,
    )
    m4 = Module(
        module_id=uuid.uuid4(),
        job_id=job.job_id,
        name="mod4",
        legacy_path="g",
        target_path="h",
        status="PENDING",
        risk_level="HIGH",
        wave_number=2,
    )
    db_session.add_all([m1, m2, m3, m4])

    # Add attempts with VerificationRun PASS for m1 and m2
    for m in (m1, m2):
        att = ModuleAttempt(
            attempt_id=uuid.uuid4(),
            module_id=m.module_id,
            attempt_number=1,
            status="SUCCEEDED",
            git_branch="branch",
        )
        db_session.add(att)
        vr = VerificationRun(
            verification_run_id=uuid.uuid4(),
            attempt_id=att.attempt_id,
            candidate_hash="cand123",
            suite_hash="suite123",
            profile_version="v1",
            profile_digest="prof123",
            input_hash="in123",
            status="PASS",
        )
        db_session.add(vr)

    await db_session.commit()

    service = WorkflowProjectionService()
    projection = await service.get_projection(db_session, job.job_id, test_user)

    assert projection.total_modules == 4
    # 2 out of 4 modules verified = 50%
    assert projection.progress == 50
    assert projection.is_progress_indeterminate is False


@pytest.mark.asyncio
async def test_indeterminate_progress_when_modules_unplanned(
    db_session: AsyncSession,
    test_user: User,
):
    """Proves: Before planning, progress is None and is_progress_indeterminate is True."""
    job = Job(
        job_id=uuid.uuid4(),
        owner_user_id=test_user.user_id,
        name="Unplanned Job",
        source_repository="https://github.com/org/repo.git",
        source_revision="main",
        source_stack="Java",
        target_stack="NodeJS",
        status="ANALYZING",
        budget_limit_usd=Decimal("15000.00"),
        budget_used_usd=Decimal("0.00"),
    )
    db_session.add(job)
    await db_session.commit()

    service = WorkflowProjectionService()
    projection = await service.get_projection(db_session, job.job_id, test_user)

    assert projection.total_modules == 0
    assert projection.progress is None
    assert projection.is_progress_indeterminate is True


@pytest.mark.asyncio
async def test_cross_tenant_isolation_raises_forbidden(
    db_session: AsyncSession,
    test_user: User,
):
    """Proves: A user from another tenant/account cannot query workflow projection."""
    other_user = User(
        user_id=uuid.uuid4(),
        email=f"other_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hash",
        full_name="Other User",
        role="DEVELOPER",
        status="ACTIVE",
    )
    job = Job(
        job_id=uuid.uuid4(),
        owner_user_id=other_user.user_id,
        name="Private Job",
        source_repository="https://github.com/org/repo.git",
        source_revision="main",
        source_stack="Java",
        target_stack="NodeJS",
        status="PLANNING",
        budget_limit_usd=Decimal("15000.00"),
        budget_used_usd=Decimal("0.00"),
    )
    db_session.add_all([other_user, job])
    await db_session.commit()

    service = WorkflowProjectionService()
    from app.core.errors import ForbiddenException
    with pytest.raises(ForbiddenException):
        await service.get_projection(db_session, job.job_id, test_user)


@pytest.mark.asyncio
async def test_monotonic_audit_sequence_and_cursor_filtering(
    db_session: AsyncSession,
    test_user: User,
):
    """Proves: Events have strictly monotonic sequences and cursor polling returns subsequent events."""
    from datetime import datetime, timezone
    job = Job(
        job_id=uuid.uuid4(),
        owner_user_id=test_user.user_id,
        name="Audit Job",
        source_repository="https://github.com/org/repo.git",
        source_revision="main",
        source_stack="Java",
        target_stack="NodeJS",
        status="INTAKE",
        budget_limit_usd=Decimal("15000.00"),
        budget_used_usd=Decimal("0.00"),
    )
    db_session.add(job)

    ev1 = AuditEvent(
        event_id=uuid.uuid4(),
        job_id=job.job_id,
        event_type="JOB_CREATED",
        actor_type="USER",
        actor_id=str(test_user.user_id),
        created_at=datetime(2026, 11, 3, 10, 0, 1, tzinfo=timezone.utc),
    )
    ev2 = AuditEvent(
        event_id=uuid.uuid4(),
        job_id=job.job_id,
        event_type="JOB_INTAKE_STARTED",
        actor_type="SYSTEM",
        actor_id="supervisor",
        created_at=datetime(2026, 11, 3, 10, 0, 2, tzinfo=timezone.utc),
    )
    ev3 = AuditEvent(
        event_id=uuid.uuid4(),
        job_id=job.job_id,
        event_type="JOB_INTAKE_COMPLETED",
        actor_type="AGENT",
        actor_id="intake_worker",
        created_at=datetime(2026, 11, 3, 10, 0, 3, tzinfo=timezone.utc),
    )
    db_session.add_all([ev1, ev2, ev3])
    await db_session.commit()

    service = WorkflowProjectionService()

    # Initial fetch: returns all 3 events with sequence 1, 2, 3
    proj1 = await service.get_projection(db_session, job.job_id, test_user, since_seq=0)
    assert len(proj1.events) == 3
    assert [e.sequence for e in proj1.events] == [1, 2, 3]
    assert proj1.latest_sequence == 3

    # Subsequent poll with since_seq=2: returns only event 3
    proj2 = await service.get_projection(db_session, job.job_id, test_user, since_seq=2)
    assert len(proj2.events) == 1
    assert proj2.events[0].sequence == 3
    assert proj2.events[0].event_type == "JOB_INTAKE_COMPLETED"
    assert proj2.latest_sequence == 3


@pytest.mark.asyncio
async def test_api_jobs_projection_endpoint(
    client: TestClient,
    db_session: AsyncSession,
):
    """Proves: GET /api/v1/jobs/{job_id}/projection returns truthful WorkflowProjectionResponse over HTTP."""
    from app.core.security import hash_password
    email = f"user_proj_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "Password123!"
    user = User(
        user_id=uuid.uuid4(),
        email=email,
        full_name="Projection User",
        password_hash=hash_password(pwd),
        role="DEVELOPER",
        status="ACTIVE",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    job = Job(
        job_id=uuid.uuid4(),
        owner_user_id=user.user_id,
        name="HTTP API Job",
        source_repository="https://github.com/org/repo.git",
        source_revision="main",
        source_stack="Java",
        target_stack="NodeJS",
        status="INTAKE",
        budget_limit_usd=Decimal("15000.00"),
        budget_used_usd=Decimal("0.00"),
    )
    membership = JobMembership(
        membership_id=uuid.uuid4(),
        job_id=job.job_id,
        user_id=user.user_id,
        role_id="ADMIN",
    )
    db_session.add_all([job, membership])
    await db_session.commit()

    # Login
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login_res.status_code == 200, login_res.text

    response = client.get(f"/api/v1/jobs/{job.job_id}/projection")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["job_id"] == str(job.job_id)
    assert data["projection_version"] == "v1"
    assert data["status"] == "INTAKE"
    assert "stages" in data
    assert len(data["stages"]) > 0
    assert data["is_progress_indeterminate"] is True
    assert data["total_modules"] == 0


@pytest.mark.asyncio
async def test_api_jobs_get_and_list_truthful_modules_and_progress(
    client: TestClient,
    db_session: AsyncSession,
):
    """Proves: UI-05 fix over HTTP - GET /jobs and GET /jobs/{id} return real modules count and weighted progress."""
    from app.core.security import hash_password
    email = f"user_prog_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "Password123!"
    user = User(
        user_id=uuid.uuid4(),
        email=email,
        full_name="Progress User",
        password_hash=hash_password(pwd),
        role="DEVELOPER",
        status="ACTIVE",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    job = Job(
        job_id=uuid.uuid4(),
        owner_user_id=user.user_id,
        name="Real Progress API Job",
        source_repository="https://github.com/org/repo.git",
        source_revision="main",
        source_stack="Java",
        target_stack="NodeJS",
        status="CONVERTING",
        budget_limit_usd=Decimal("15000.00"),
        budget_used_usd=Decimal("12.00"),
    )
    membership = JobMembership(
        membership_id=uuid.uuid4(),
        job_id=job.job_id,
        user_id=user.user_id,
        role_id="ADMIN",
    )
    db_session.add_all([job, membership])

    # Add 2 modules: 1 VERIFIED, 1 PENDING
    m1 = Module(
        module_id=uuid.uuid4(),
        job_id=job.job_id,
        name="auth",
        legacy_path="a",
        target_path="b",
        status="VERIFIED",
        risk_level="LOW",
        wave_number=1,
    )
    m2 = Module(
        module_id=uuid.uuid4(),
        job_id=job.job_id,
        name="users",
        legacy_path="c",
        target_path="d",
        status="PENDING",
        risk_level="LOW",
        wave_number=1,
    )
    db_session.add_all([m1, m2])
    await db_session.commit()

    # Login
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login_res.status_code == 200, login_res.text

    # 1. Test GET /jobs/{id}
    res_get = client.get(f"/api/v1/jobs/{job.job_id}")
    assert res_get.status_code == 200, res_get.text
    job_detail = res_get.json()
    assert job_detail["modules"] == 2
    # 1 verified of 2 = 50%
    assert job_detail["progress"] == 50

    # 2. Test GET /jobs
    res_list = client.get("/api/v1/jobs")
    assert res_list.status_code == 200, res_list.text
    job_list = res_list.json()
    matching = next((item for item in job_list["items"] if item["job_id"] == str(job.job_id)), None)
    assert matching is not None
    assert matching["modules"] == 2
    assert matching["progress"] == 50
