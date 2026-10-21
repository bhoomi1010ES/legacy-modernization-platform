"""Phase 1 Transactional Job Creation, State Machine Transitions, and Append-Only Audit Tests."""

import pytest
import uuid
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.errors import ForbiddenException, IllegalStateTransitionException
from app.domain.state_machine import JobStateMachine
from app.models.audit import AuditEvent
from app.models.job import Job, JobMembership
from app.schemas.jobs import JobStatus
from app.services.audit_service import AuditService


@pytest.mark.asyncio
async def test_transactional_job_creation(client: TestClient):
    """Proves job creation atomically commits Job, JobMembership (owner), and initial AuditEvent."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    create_payload = {
        "name": "Atomic Transaction Job",
        "source_repository": "https://github.com/acme/atomic-service",
        "source_revision": "main",
        "budget": 175.0,
        "max_repair_attempts": 3,
    }

    resp = client.post(
        "/api/v1/jobs",
        json=create_payload,
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert resp.status_code == 201
    job_data = resp.json()
    job_id = uuid.UUID(job_data["job_id"])

    async with AsyncSessionLocal() as db_session:
        # Verify Job row in database
        job_stmt = select(Job).where(Job.job_id == job_id)
        job_res = await db_session.execute(job_stmt)
        job = job_res.scalar_one_or_none()
        assert job is not None
        assert job.status == "CREATED"
        assert job.budget_limit_usd == Decimal("175.00")

        # Verify Owner JobMembership
        mem_stmt = select(JobMembership).where(JobMembership.job_id == job_id)
        mem_res = await db_session.execute(mem_stmt)
        membership = mem_res.scalar_one_or_none()
        assert membership is not None
        assert membership.role_id == "ADMIN"

        # Verify Initial AuditEvent
        audit_stmt = select(AuditEvent).where(
            AuditEvent.job_id == job_id, AuditEvent.event_type == "JOB_CREATED"
        )
        audit_res = await db_session.execute(audit_stmt)
        audit = audit_res.scalar_one_or_none()
        assert audit is not None
        assert audit.target_resource == str(job_id)


def test_invalid_state_transitions_rejected():
    """Proves illegal state transitions are rejected by JobStateMachine."""
    # Cannot transition directly from CREATED to CONVERTING (bypassing intake, analysis, G1, characterization, G2, planning, G3)
    assert not JobStateMachine.can_transition(JobStatus.CREATED, JobStatus.CONVERTING)
    with pytest.raises(IllegalStateTransitionException):
        JobStateMachine.validate_transition(JobStatus.CREATED, JobStatus.CONVERTING)

    # Terminal state COMPLETED cannot transition to anything
    assert not JobStateMachine.can_transition(JobStatus.COMPLETED, JobStatus.CONVERTING)
    with pytest.raises(IllegalStateTransitionException):
        JobStateMachine.validate_transition(JobStatus.COMPLETED, JobStatus.CONVERTING)


def test_job_cancellation_idempotency(client: TestClient):
    """Proves cancellation is permitted from non-terminal states and repeated calls are idempotent."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    # Create job
    create_resp = client.post(
        "/api/v1/jobs",
        json={
            "name": "Cancel Test Job",
            "source_repository": "https://github.com/acme/cancel-test",
            "budget": 100.0,
        },
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    job_id = create_resp.json()["job_id"]

    # First cancel
    c1 = client.post(f"/api/v1/jobs/{job_id}/cancel", cookies={settings.SESSION_COOKIE_NAME: token})
    assert c1.status_code == 200
    assert c1.json()["status"] == "CANCELLED"

    # Second cancel (idempotent)
    c2 = client.post(f"/api/v1/jobs/{job_id}/cancel", cookies={settings.SESSION_COOKIE_NAME: token})
    assert c2.status_code == 200
    assert c2.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_audit_records_immutable_append_only():
    """Proves application service explicitly prohibits updating or deleting audit records."""
    with pytest.raises(ForbiddenException):
        await AuditService.update_event("any_id", payload={})

    with pytest.raises(ForbiddenException):
        await AuditService.delete_event("any_id")
