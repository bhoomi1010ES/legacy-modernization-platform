"""Phase 1 Authorization, Job Membership, and Resource-Level Isolation Tests."""

import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job, JobMembership
from app.models.user import User


@pytest.mark.asyncio
async def test_job_isolation_non_member_access_denied(client: TestClient):
    """Proves user cannot access another user's job where they have no membership."""
    client.cookies.clear()
    async with AsyncSessionLocal() as db_session:
        # 1. Provision User B
        stmt = select(User).where(User.email == "user.b@acme.corp")
        res = await db_session.execute(stmt)
        user_b = res.scalar_one_or_none()
        if not user_b:
            user_b = User(
                email="user.b@acme.corp",
                full_name="User B (External)",
                password_hash=hash_password("Password123!"),
                role="DEVELOPER",
                status="ACTIVE",
            )
            db_session.add(user_b)
            await db_session.commit()
            await db_session.refresh(user_b)

        # 2. Login as User B
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "user.b@acme.corp", "password": "Password123!"},
        )
        assert login_resp.status_code == 200
        token_b = login_resp.cookies[settings.SESSION_COOKIE_NAME]

        # 3. Create Private Job for User A
        user_a_stmt = select(User).where(User.email == "alex.morgan@acme.corp")
        user_a_res = await db_session.execute(user_a_stmt)
        user_a = user_a_res.scalar_one()

        private_job_id = uuid.uuid4()
        job_a = Job(
            job_id=private_job_id,
            name="User A Confidential Job",
            source_repository="https://github.com/acme/confidential",
            status="CREATED",
            owner_user_id=user_a.user_id,
        )
        db_session.add(job_a)
        membership_a = JobMembership(job_id=private_job_id, user_id=user_a.user_id, role_id="ADMIN")
        db_session.add(membership_a)

        # Add artifact and audit event to Job A
        art_id = uuid.uuid4()
        artifact_a = Artifact(
            artifact_id=art_id,
            job_id=private_job_id,
            artifact_type="ConfidentialModel",
            version=1,
            content_hash="sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            storage_path=f"jobs/{private_job_id}/artifacts/ConfidentialModel_v1.json",
            producing_agent="SecurityAnalyzer",
        )
        db_session.add(artifact_a)

        audit_a = AuditEvent(
            job_id=private_job_id,
            event_type="CONFIDENTIAL_ACTION",
            actor_type="USER",
            actor_id=str(user_a.user_id),
        )
        db_session.add(audit_a)
        await db_session.commit()

    # 4. User B attempts to view Job A -> Denied with 404 (IDOR mask)
    job_resp = client.get(
        f"/api/v1/jobs/{private_job_id}",
        cookies={settings.SESSION_COOKIE_NAME: token_b},
    )
    assert job_resp.status_code == 404
    assert job_resp.json()["error"]["code"] == "NOT_FOUND"

    # 5. User B attempts to list artifacts for Job A -> Denied with 404
    art_resp = client.get(
        f"/api/v1/jobs/{private_job_id}/artifacts",
        cookies={settings.SESSION_COOKIE_NAME: token_b},
    )
    assert art_resp.status_code == 404

    # 6. User B attempts to view audit events for Job A -> Denied with 404
    audit_resp = client.get(
        f"/api/v1/jobs/{private_job_id}/audit",
        cookies={settings.SESSION_COOKIE_NAME: token_b},
    )
    assert audit_resp.status_code == 404

    # 7. User B attempts to cancel Job A -> Denied with 404
    cancel_resp = client.post(
        f"/api/v1/jobs/{private_job_id}/cancel",
        cookies={settings.SESSION_COOKIE_NAME: token_b},
    )
    assert cancel_resp.status_code == 404


@pytest.mark.asyncio
async def test_job_membership_role_restrictions(client: TestClient):
    """Proves a VIEWER job member cannot perform state mutations like cancel."""
    client.cookies.clear()
    async with AsyncSessionLocal() as db_session:
        # 1. Provision Viewer User
        stmt = select(User).where(User.email == "viewer.user@acme.corp")
        res = await db_session.execute(stmt)
        viewer_user = res.scalar_one_or_none()
        if not viewer_user:
            viewer_user = User(
                email="viewer.user@acme.corp",
                full_name="Read-Only Auditor",
                password_hash=hash_password("Password123!"),
                role="VIEWER",
                status="ACTIVE",
            )
            db_session.add(viewer_user)
            await db_session.commit()
            await db_session.refresh(viewer_user)

        # 2. Login as Viewer
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "viewer.user@acme.corp", "password": "Password123!"},
        )
        assert login_resp.status_code == 200
        viewer_token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

        # 3. Create Job and grant VIEWER membership
        test_job_id = uuid.uuid4()
        job = Job(
            job_id=test_job_id,
            name="Audited Project",
            source_repository="https://github.com/acme/audited",
            status="CREATED",
            owner_user_id=viewer_user.user_id,
        )
        db_session.add(job)
        membership = JobMembership(job_id=test_job_id, user_id=viewer_user.user_id, role_id="VIEWER")
        db_session.add(membership)
        await db_session.commit()

    # 4. Read job as VIEWER -> Permitted (200 OK)
    read_resp = client.get(
        f"/api/v1/jobs/{test_job_id}",
        cookies={settings.SESSION_COOKIE_NAME: viewer_token},
    )
    assert read_resp.status_code == 200
    assert read_resp.json()["name"] == "Audited Project"

    # 5. Attempt cancel as VIEWER -> Denied with 403 Forbidden
    cancel_resp = client.post(
        f"/api/v1/jobs/{test_job_id}/cancel",
        cookies={settings.SESSION_COOKIE_NAME: viewer_token},
    )
    assert cancel_resp.status_code == 403
    assert cancel_resp.json()["error"]["code"] == "FORBIDDEN"
