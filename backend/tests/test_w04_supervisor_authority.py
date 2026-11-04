"""W04 Test Suite: Single Supervisor Authority, LangGraph Checkpointing, and Command Integrity.

Covers:
- FLOW-02: Competing Orchestration Engines and Deprecated Bypass Routes
- FLOW-03: Autonomous Continuation Failure (Graph Premature Exit on Wait / Pause)
- FLOW-05: Native LangGraph Postgres Checkpointer (AsyncPostgresSaver)
- FLOW-06: Terminal FAILED Immutability & Generation-Guarded Authorized Recovery
- FLOW-07: Fail-Closed Dispatch on Unknown Agent or Missing Inputs
- SupervisorCommandService: Idempotency, Version Guards, and Multi-Stage Cancellation
"""

from decimal import Decimal
import os
import uuid
from uuid import UUID

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictException, ForbiddenException, IllegalStateTransitionException
from app.domain.state_machine import JobStateMachine
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.user import User
from app.models.workflow import WorkflowCheckpoint, WorkflowGate
from app.schemas.jobs import JobStatus
from app.services.continuous_pipeline import continuous_pipeline_service
from app.services.supervisor_command_service import (
    ApproveGateCommand,
    CancelJobCommand,
    CommandReceipt,
    EscalateCommand,
    PauseJobCommand,
    ResumeJobCommand,
    RetryFailedJobCommand,
    StartJobCommand,
    SupervisorCommandType,
    supervisor_command_service,
)
from app.services.supervisor_graph import (
    authoritative_supervisor_graph,
    node_execute_agent,
    node_handle_escalation,
)
from app.services.workflow_checkpointer import AsyncPostgresSaver


async def _get_test_users(db):
    owner = await db.scalar(select(User).order_by(User.created_at.asc()).limit(1))
    admin = await db.scalar(select(User).where(User.role == "ADMIN", User.user_id != owner.user_id).limit(1))
    if not admin:
        admin = User(
            user_id=uuid.uuid4(),
            email=f"w04_admin_{uuid.uuid4().hex[:6]}@acme.corp",
            full_name="W04 Admin User",
            password_hash="argon2_test_hash",
            role="ADMIN",
            status="ACTIVE",
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    return owner, admin


async def _create_test_job(db, status: JobStatus = JobStatus.CREATED) -> Job:
    owner, _ = await _get_test_users(db)
    job = Job(
        job_id=uuid.uuid4(),
        name=f"w04-test-{uuid.uuid4().hex[:8]}",
        source_repository="https://github.com/example/w04-repo.git",
        owner_user_id=owner.user_id,
        status=status.value,
        active_node=status.value.lower(),
        budget_used_usd=Decimal("0.00"),
        budget_limit_usd=Decimal("150.00"),
        orchestration_generation=1,
        last_checkpoint_sequence=0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@pytest.mark.asyncio
async def test_supervisor_command_service_lifecycle():
    """Verifies that StartJob, PauseJob, ResumeJob, and CancelJob transition job state authoritatively."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, JobStatus.CREATED)
        owner, _ = await _get_test_users(db)
        owner_id = str(owner.user_id)

        # 1. StartJob
        start_cmd = StartJobCommand(job_id=job.job_id, actor_id=owner_id)
        receipt = await supervisor_command_service.execute_command(db, start_cmd)
        assert receipt.status == "EXECUTED"
        assert receipt.current_job_status == JobStatus.INTAKE.value

        # Transition to ANALYZING to test pause
        job.status = JobStatus.ANALYZING.value
        await db.commit()

        # 2. PauseJob
        pause_cmd = PauseJobCommand(job_id=job.job_id, actor_id=owner_id, reason="Scheduled freeze")
        pause_receipt = await supervisor_command_service.execute_command(db, pause_cmd)
        assert pause_receipt.current_job_status == JobStatus.PAUSED.value

        # 3. ResumeJob
        resume_cmd = ResumeJobCommand(job_id=job.job_id, actor_id=owner_id)
        resume_receipt = await supervisor_command_service.execute_command(db, resume_cmd)
        assert resume_receipt.current_job_status == JobStatus.ANALYZING.value

        # 4. CancelJob (Multi-stage cancellation)
        cancel_cmd = CancelJobCommand(job_id=job.job_id, actor_id=owner_id, reason="Operator abort")
        cancel_receipt = await supervisor_command_service.execute_command(db, cancel_cmd)
        assert cancel_receipt.current_job_status == JobStatus.CANCELLED.value

        # Verify CANCELLATION_REQUESTED audit event exists
        cancel_evt = await db.scalar(
            select(AuditEvent).where(
                AuditEvent.job_id == job.job_id,
                AuditEvent.event_type == "CANCELLATION_REQUESTED",
            ).limit(1)
        )
        assert cancel_evt is not None
        assert cancel_evt.payload["reason"] == "Operator abort"


@pytest.mark.asyncio
async def test_supervisor_command_idempotency_and_version_guard():
    """Verifies command idempotency replay and rejects mismatched expected_version."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, JobStatus.CREATED)
        owner, _ = await _get_test_users(db)
        owner_id = str(owner.user_id)
        idem_key = f"idem-{uuid.uuid4()}"

        # 1. First execution
        cmd1 = StartJobCommand(
            job_id=job.job_id,
            actor_id=owner_id,
            idempotency_key=idem_key,
            expected_version=1,
        )
        receipt1 = await supervisor_command_service.execute_command(db, cmd1)
        assert receipt1.status == "EXECUTED"

        # 2. Duplicate execution with same idempotency key
        cmd2 = StartJobCommand(
            job_id=job.job_id,
            actor_id=owner_id,
            idempotency_key=idem_key,
            expected_version=1,
        )
        receipt2 = await supervisor_command_service.execute_command(db, cmd2)
        assert receipt2.status == "REPLAYED"

        # 3. Version conflict rejection
        cmd_conflict = PauseJobCommand(
            job_id=job.job_id,
            actor_id=owner_id,
            expected_version=999,  # Mismatched expected version
        )
        with pytest.raises(ConflictException, match="Workflow version conflict"):
            await supervisor_command_service.execute_command(db, cmd_conflict)


@pytest.mark.asyncio
async def test_unknown_agent_fails_closed_flow07():
    """FLOW-07: Unrecognized agent identifier must FAIL CLOSED (verdict=ESCALATE), never default to SUCCESS."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, JobStatus.ANALYZING)
        state = {
            "job_id": str(job.job_id),
            "status": job.status,
            "selected_agent": "NonExistentMaliciousAgent_99",
            "correlation_id": f"corr-{uuid.uuid4().hex[:6]}",
        }
        res = await node_execute_agent(state)
        assert res["execution_verdict"] == "ESCALATE"
        assert "unrecognized agent identifier" in res["blocking_reason"]
        assert res["events"][0]["type"] == "UNKNOWN_AGENT_ESCALATION"


@pytest.mark.asyncio
async def test_missing_prerequisites_fail_closed_flow07():
    """FLOW-07: Architect and Feasibility agents must FAIL CLOSED when prerequisite models are missing."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, JobStatus.ANALYZING)

        # 1. Architect without LegacyModelRecord
        state_arch = {
            "job_id": str(job.job_id),
            "status": job.status,
            "selected_agent": "ARCHITECT",
            "correlation_id": f"corr-{uuid.uuid4().hex[:6]}",
        }
        res_arch = await node_execute_agent(state_arch)
        assert res_arch["execution_verdict"] == "ESCALATE"
        assert "missing prerequisite LegacyModelRecord" in res_arch["blocking_reason"]

        # 2. Feasibility without TargetBlueprintModel
        state_feas = {
            "job_id": str(job.job_id),
            "status": job.status,
            "selected_agent": "FEASIBILITY",
            "correlation_id": f"corr-{uuid.uuid4().hex[:6]}",
        }
        res_feas = await node_execute_agent(state_feas)
        assert res_feas["execution_verdict"] == "ESCALATE"
        assert "missing prerequisite" in res_feas["blocking_reason"]


@pytest.mark.asyncio
async def test_langgraph_postgres_checkpointer_flow05():
    """FLOW-05: AsyncPostgresSaver implements BaseCheckpointSaver and stores checkpoints with thread_id=job_id."""
    saver = AsyncPostgresSaver()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    checkpoint = {"id": "cp_001", "channel_values": {"status": "INTAKE", "step": 1}}
    metadata = {"source": "supervisor_loop", "step": "node_load_state"}

    # 1. Put checkpoint
    res_cfg = await saver.aput(config, checkpoint, metadata, {})
    assert res_cfg["configurable"]["thread_id"] == thread_id
    assert res_cfg["configurable"]["checkpoint_id"] == "cp_001"

    # 2. Retrieve tuple
    cp_tuple = await saver.aget_tuple(config)
    assert cp_tuple is not None
    assert cp_tuple.checkpoint["id"] == "cp_001"
    assert cp_tuple.checkpoint["channel_values"]["status"] == "INTAKE"


@pytest.mark.asyncio
async def test_escalation_does_not_auto_fail_flow03():
    """FLOW-03 & Requirement 8: Escalation sets blocking reason and pauses; does NOT automatically mark job as FAILED."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, JobStatus.ANALYZING)
        state = {
            "job_id": str(job.job_id),
            "status": job.status,
            "blocking_reason": "Human architect intervention required",
            "correlation_id": f"corr-{uuid.uuid4().hex[:6]}",
        }
        res = await node_handle_escalation(state)
        assert res["status"] != JobStatus.FAILED.value
        await db.refresh(job)
        assert job.status != JobStatus.FAILED.value
        assert job.blocking_reason == "Human architect intervention required"

        # Verify WORKFLOW_ESCALATED audit event
        esc_evt = await db.scalar(
            select(AuditEvent).where(
                AuditEvent.job_id == job.job_id,
                AuditEvent.event_type == "WORKFLOW_ESCALATED",
            ).limit(1)
        )
        assert esc_evt is not None


@pytest.mark.asyncio
async def test_terminal_failed_immutability_and_authorized_recovery_flow06():
    """FLOW-06: Terminal FAILED cannot be modified by standard transitions; explicit authorized retry required."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, JobStatus.FAILED)
        owner, admin = await _get_test_users(db)
        owner_id = str(owner.user_id)
        admin_id = str(admin.user_id)

        # 1. Standard commands rejected on FAILED job
        start_cmd = StartJobCommand(job_id=job.job_id, actor_id=owner_id)
        with pytest.raises(IllegalStateTransitionException, match="Job is in terminal state 'FAILED'"):
            await supervisor_command_service.execute_command(db, start_cmd)

        # 2. Unauthorized retry rejected (non-admin role)
        retry_dev = RetryFailedJobCommand(
            job_id=job.job_id,
            actor_id=owner_id,
            actor_role="DEVELOPER",
            rationale="Developer attempting unauthorized retry without administrative signoff.",
        )
        with pytest.raises(ForbiddenException, match="Only administrators can retry a failed workflow"):
            await supervisor_command_service.execute_command(db, retry_dev)

        # 3. Short rationale rejected
        retry_short = RetryFailedJobCommand(
            job_id=job.job_id,
            actor_id=admin_id,
            actor_role="ADMIN",
            rationale="Short",
        )
        with pytest.raises(ConflictException, match="minimum 10-character diagnostic rationale"):
            await supervisor_command_service.execute_command(db, retry_short)


def test_continuous_pipeline_disabled_in_production_flow02(monkeypatch):
    """FLOW-02: Direct ContinuousPipelineService invocation in production raises ConflictException."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ENABLE_LEGACY_CONTINUOUS_PIPELINE", False)

    with pytest.raises(ConflictException, match="Direct invocation of deprecated ContinuousPipelineService is disabled in production"):
        continuous_pipeline_service.trigger_continuous_pipeline(uuid.uuid4())


def test_enqueue_command_api_endpoint(client: TestClient):
    """Verifies that POST /api/v1/jobs/{job_id}/commands returns HTTP 202 Accepted with CommandReceipt."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "AdminSecure123!"},
    )
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    # Create job
    create_resp = client.post(
        "/api/v1/jobs",
        json={
            "name": "Command Enqueue Test Job",
            "source_repository": "https://github.com/example/cmd-queue-repo.git",
            "budget": 120.0,
        },
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    job_id = create_resp.json()["job_id"]

    # Enqueue PauseJobCommand via API
    cmd_payload = {
        "command_type": "PAUSE_JOB",
        "job_id": job_id,
        "payload": {"reason": "Maintenance window pause"},
    }
    resp = client.post(
        f"/api/v1/jobs/{job_id}/commands",
        json=cmd_payload,
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "ACCEPTED"
    assert data["command_type"] == "PAUSE_JOB"
    assert data["job_id"] == job_id
