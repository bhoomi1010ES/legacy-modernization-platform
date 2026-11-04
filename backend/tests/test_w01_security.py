"""Comprehensive Regression and Hardening Test Suite for W01 Security Invariants.

Verifies:
1. Universal password bypass removal (W01.1 / SEC-01).
2. Public registration role lockdown & extra fields rejection (W01.2 / SEC-02).
3. Administrative role assignment authorization (W01.2).
4. Job creator least-privilege DEVELOPER role assignment (W01.3 / SEC-03).
5. Separation of duties: Job creators cannot approve their own gates (W01.3, W01.6).
6. Anonymous stack scanning prohibited & SSRF / system path defense (W01.4 / SEC-04).
7. TrustedHostMiddleware & hardened CSRF origin checking (W01.5 / SEC-05 / SEC-08).
8. Versioned gate integrity and independent reviewer approvals (W01.6).
"""

from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.job import Job, JobMembership
from app.models.user import User
from app.models.workflow import WorkflowGate
from app.schemas.gates import DecisionOutcome, GateType


# -----------------------------------------------------------------------------
# W01.1 — Universal Password Bypass Removal
# -----------------------------------------------------------------------------

def test_w01_1_universal_passwords_rejected_for_user_with_different_password(client: TestClient):
    """Proves bypass passwords (Password123!, SecurePassword123!) are rejected for accounts with different passwords."""
    client.cookies.clear()

    # alex.morgan@acme.corp's actual password in database is AdminSecure123!
    # Test that formerly universal bypass passwords fail:
    for bypass_pw in ["Password123!", "SecurePassword123!", "FakeBypassPassword123!"]:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "alex.morgan@acme.corp", "password": bypass_pw},
        )
        assert resp.status_code == 401, f"Bypass password '{bypass_pw}' unexpectedly authenticated!"
        err = resp.json()["error"]
        assert err["code"] == "UNAUTHORIZED"
        assert "invalid email or password" in err["message"].lower()


def test_w01_1_valid_credentials_authenticate_successfully(client: TestClient):
    """Proves valid credentials authenticate and set session cookie."""
    client.cookies.clear()
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "AdminSecure123!"},
    )
    assert resp.status_code == 200
    assert settings.SESSION_COOKIE_NAME in resp.cookies
    data = resp.json()
    assert data["email"] == "alex.morgan@acme.corp"
    assert "password" not in data
    assert "password_hash" not in data


# -----------------------------------------------------------------------------
def test_w01_1_production_configuration_safeguards(monkeypatch):
    """Proves production configuration strictly rejects insecure default keys and wildcards."""
    monkeypatch.setenv("ENVIRONMENT", "production")

    from app.core.config import Settings

    # 1. Reject default dev secret key in production
    with pytest.raises(ValueError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="phase-0-development-secret-key-change-in-production-min32bytes!",
        )
    assert "insecure secret_key detected for production" in str(exc.value).lower()

    # 2. Reject wildcard allowed hosts in production
    with pytest.raises(ValueError) as exc2:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-sufficiently-long-and-cryptographically-secure-production-key-here!",
            ALLOWED_HOSTS=["*"],
        )
    assert "allowed_hosts cannot be empty or wildcard in production" in str(exc2.value).lower()

    # 3. Enforce secure cookies in production
    prod_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a-sufficiently-long-and-cryptographically-secure-production-key-here!",
        ALLOWED_HOSTS=["app.rebase.internal"],
        SESSION_COOKIE_SECURE=False,
    )
    assert prod_settings.SESSION_COOKIE_SECURE is True


# W01.2 — Public Registration Role Lockdown & Admin Assignment
# -----------------------------------------------------------------------------

def test_w01_2_public_registration_defaults_to_developer(client: TestClient):
    """Proves public self-registration defaults safely to DEVELOPER."""
    client.cookies.clear()
    unique_email = f"dev_{uuid.uuid4().hex[:8]}@acme.corp"
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "ValidPassword999!",
            "full_name": "Junior Developer",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "DEVELOPER"


@pytest.mark.parametrize("forbidden_role", ["REVIEWER", "ADMIN", "APPROVER", "SUPER_ADMIN", "PROJECT_MANAGER"])
def test_w01_2_public_registration_rejects_privileged_roles(client: TestClient, forbidden_role: str):
    """Proves public self-registration rejects any requested privileged role."""
    client.cookies.clear()
    unique_email = f"attacker_{uuid.uuid4().hex[:8]}@acme.corp"
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "ValidPassword999!",
            "full_name": "Privilege Escalator",
            "role": forbidden_role,
        },
    )
    assert resp.status_code in (403, 422), f"Role '{forbidden_role}' was not blocked!"


def test_w01_2_registration_rejects_injected_extra_fields(client: TestClient):
    """Proves registration schema forbids mass assignment (extra fields like permissions, status, is_superuser)."""
    client.cookies.clear()
    unique_email = f"injected_{uuid.uuid4().hex[:8]}@acme.corp"
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "ValidPassword999!",
            "full_name": "Payload Injector",
            "permissions": ["admin", "all"],
            "is_superuser": True,
        },
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_w01_2_admin_role_assignment_flow(client: TestClient):
    """Proves only an authorized administrator can assign privileged roles via the admin endpoint."""
    client.cookies.clear()
    # 1. Register a regular user
    unique_email = f"target_{uuid.uuid4().hex[:8]}@acme.corp"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "TargetPassword123!",
            "full_name": "Candidate Reviewer",
        },
    )
    assert reg_resp.status_code == 201
    target_user_id = reg_resp.json()["user_id"]

    # 2. Attempt role promotion without admin auth -> 401 Unauthorized
    client.cookies.clear()
    unauth_resp = client.post(
        f"/api/v1/auth/users/{target_user_id}/role",
        json={"role": "REVIEWER", "reason": "Promote to code reviewer"},
    )
    assert unauth_resp.status_code == 401

    # 3. Login as regular user and attempt self-promotion -> 403 Forbidden
    client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "TargetPassword123!"},
    )
    forbidden_resp = client.post(
        f"/api/v1/auth/users/{target_user_id}/role",
        json={"role": "ADMIN", "reason": "Self elevation"},
    )
    assert forbidden_resp.status_code == 403

    # 4. Login as admin alex.morgan@acme.corp and assign REVIEWER role -> 200 OK
    client.cookies.clear()
    client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "AdminSecure123!"},
    )
    admin_resp = client.post(
        f"/api/v1/auth/users/{target_user_id}/role",
        json={"role": "REVIEWER", "reason": "Official approval after security review"},
    )
    assert admin_resp.status_code == 200
    assert admin_resp.json()["role"] == "REVIEWER"


# -----------------------------------------------------------------------------
# W01.3 — Job Creator Least Privilege & Separation of Duties
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_w01_3_non_admin_creator_receives_developer_membership(client: TestClient):
    """Proves creating a job does NOT elevate a regular user to ADMIN."""
    client.cookies.clear()
    # 1. Register and login as developer
    unique_email = f"eng_{uuid.uuid4().hex[:8]}@acme.corp"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "DevPassword123!",
            "full_name": "Feature Engineer",
        },
    )
    user_id = uuid.UUID(reg_resp.json()["user_id"])

    client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "DevPassword123!"},
    )

    # 2. Create job
    create_resp = client.post(
        "/api/v1/jobs",
        json={
            "name": "Least Privilege Verification Job",
            "source_repository": "https://github.com/acme/least-privilege",
            "budget": 200.0,
        },
    )
    assert create_resp.status_code == 201
    job_id = uuid.UUID(create_resp.json()["job_id"])

    # 3. Verify in database: Creator membership role is DEVELOPER, not ADMIN
    async with AsyncSessionLocal() as session:
        stmt = select(JobMembership).where(
            JobMembership.job_id == job_id,
            JobMembership.user_id == user_id,
        )
        res = await session.execute(stmt)
        mem = res.scalar_one_or_none()
        assert mem is not None
        assert mem.role_id == "DEVELOPER", f"Expected DEVELOPER role, got '{mem.role_id}'"


@pytest.mark.asyncio
async def test_w01_3_and_6_job_creator_cannot_approve_own_gate(client: TestClient):
    """Proves separation of duties: A job creator cannot approve or reject gates for their own job."""
    client.cookies.clear()
    # 1. Login as admin alex.morgan@acme.corp and create a job
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "AdminSecure123!"},
    )
    assert login_resp.status_code == 200
    alex_token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    create_resp = client.post(
        "/api/v1/jobs",
        json={
            "name": "Gate Separation Test Job",
            "source_repository": "https://github.com/acme/gate-test",
            "budget": 150.0,
        },
    )
    assert create_resp.status_code == 201
    job_id = uuid.UUID(create_resp.json()["job_id"])

    # 2. Transition job to AWAITING_GATE_G1 and materialise pending gate in database
    gate_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        job.status = "AWAITING_GATE_G1"
        gate = WorkflowGate(
            gate_id=gate_id,
            job_id=job_id,
            gate_type="G1",
            version=1,
            status="PENDING",
            artifact_ids=[],
            artifact_hashes={},
        )
        session.add(gate)
        await session.commit()

    # 3. Creator (alex.morgan) attempts to approve the gate on their own job -> 403 Forbidden (Separation of duties)
    decision_resp = client.post(
        f"/api/v1/jobs/{job_id}/gates/{gate_id}/decisions",
        json={
            "decision": "APPROVED",
            "rationale": "Attempting self-approval as creator of the job",
            "artifact_hashes": {},
            "options": {"gap-1": "adapter"},
        },
        cookies={settings.SESSION_COOKIE_NAME: alex_token},
    )
    assert decision_resp.status_code == 403
    err = decision_resp.json()["error"]
    assert "separation of duties" in err["message"].lower()

    # 4. Provision an independent REVIEWER user
    reviewer_email = f"reviewer_{uuid.uuid4().hex[:8]}@acme.corp"
    reviewer_user_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        reviewer_user = User(
            user_id=reviewer_user_id,
            email=reviewer_email,
            full_name="Independent Reviewer",
            password_hash=hash_password("ReviewerPass123!"),
            role="REVIEWER",
            status="ACTIVE",
        )
        session.add(reviewer_user)
        # Grant reviewer membership on this job
        mem = JobMembership(
            job_id=job_id,
            user_id=reviewer_user_id,
            role_id="REVIEWER",
        )
        session.add(mem)
        await session.commit()

    # 5. Independent reviewer approves gate -> 200 OK
    client.cookies.clear()
    r_login = client.post(
        "/api/v1/auth/login",
        json={"email": reviewer_email, "password": "ReviewerPass123!"},
    )
    reviewer_token = r_login.cookies[settings.SESSION_COOKIE_NAME]

    ok_resp = client.post(
        f"/api/v1/jobs/{job_id}/gates/{gate_id}/decisions",
        json={
            "decision": "APPROVED",
            "rationale": "Independent third-party architectural signoff accepted",
            "artifact_hashes": {},
            "options": {"gap-1": "adapter"},
        },
        cookies={settings.SESSION_COOKIE_NAME: reviewer_token},
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["decision"] == "APPROVED"


# -----------------------------------------------------------------------------
# W01.4 — Stack Detection Security & SSRF / Path Probing Defense
# -----------------------------------------------------------------------------

def test_w01_4_stack_detection_requires_authentication(client: TestClient):
    """Proves /detect-stack and /detect-stack/local strictly require authentication."""
    client.cookies.clear()
    resp1 = client.post(
        "/api/v1/jobs/detect-stack",
        json={"source_repository": "https://github.com/acme/sample"},
    )
    assert resp1.status_code == 401

    resp2 = client.post(
        "/api/v1/jobs/detect-stack/local",
        data={"source_name": "local-proj"},
    )
    assert resp2.status_code == 401


def test_w01_4_stack_detection_blocks_ssrf_and_private_ips(client: TestClient):
    """Proves remote URLs targeting loopback, link-local, private IPs are rejected with 400 Bad Request."""
    client.cookies.clear()
    client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "AdminSecure123!"},
    )

    prohibited_urls = [
        "https://127.0.0.1/internal/repo.git",
        "https://localhost/internal/repo.git",
        "http://169.254.169.254/latest/meta-data",
        "https://192.168.1.100/private.git",
        "https://10.0.0.5/core.git",
    ]
    for url in prohibited_urls:
        resp = client.post(
            "/api/v1/jobs/detect-stack",
            json={"source_repository": url},
        )
        assert resp.status_code in (400, 422), f"URL '{url}' was not rejected as SSRF!"


def test_w01_4_stack_detection_blocks_system_directory_traversal(client: TestClient):
    """Proves attempts to scan system paths (C:\\Windows, /etc, etc.) are rejected with 403 Forbidden."""
    client.cookies.clear()
    client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "AdminSecure123!"},
    )

    dangerous_paths = [
        "C:\\Windows\\System32",
        "/etc",
        "/root",
        "/var/log",
    ]
    for p in dangerous_paths:
        resp = client.post(
            "/api/v1/jobs/detect-stack",
            json={"source_repository": p, "source_type": "local"},
        )
        assert resp.status_code == 403, f"Path '{p}' was not blocked with 403!"


# -----------------------------------------------------------------------------
# W01.5 / SEC-08 — Trusted Host & Hardened CSRF Origin Protection
# -----------------------------------------------------------------------------

def test_w01_5_trusted_host_middleware_blocks_spoofed_hosts(client: TestClient):
    """Proves requests with untrusted Host headers are rejected with 400."""
    resp = client.get(
        "/docs",
        headers={"Host": "malicious-spoofed-host.com"},
    )
    assert resp.status_code == 400


def test_w01_5_trusted_host_middleware_permits_allowed_hosts(client: TestClient):
    """Proves legitimate configured hosts (testserver, localhost) succeed."""
    resp = client.get(
        "/docs",
        headers={"Host": "testserver"},
    )
    assert resp.status_code == 200


def test_w01_5_csrf_blocks_loose_substring_origin_spoofing(client: TestClient):
    """Proves origins attempting substring match (e.g. http://localhost:3000.evil.com) are rejected with 403."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "AdminSecure123!"},
    )
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    # Attacker origin includes localhost:3000 as a substring
    spoofed_origin = "http://localhost:3000.attacker.com"
    resp = client.post(
        "/api/v1/jobs",
        cookies={settings.SESSION_COOKIE_NAME: token},
        headers={"Origin": spoofed_origin},
        json={
            "name": "CSRF Substring Bypass Attempt",
            "source_repository": "https://github.com/acme/legit",
            "budget": 100.0,
        },
    )
    assert resp.status_code == 403
    err = resp.json()["error"]
    assert err["code"] == "CSRF_FORBIDDEN"
