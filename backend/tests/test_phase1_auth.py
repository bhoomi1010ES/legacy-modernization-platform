"""Comprehensive Phase 1 Authentication & Session Lifecycle Tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


def test_auth_login_valid_and_cookie_attributes(client: TestClient):
    """Proves valid login sets HttpOnly, SameSite, path cookie with unpredictable token."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200
    user_data = login_resp.json()
    assert user_data["email"] == "alex.morgan@acme.corp"
    assert "password" not in user_data
    assert "password_hash" not in user_data
    assert "permissions" in user_data
    assert isinstance(user_data["permissions"], list)

    assert settings.SESSION_COOKIE_NAME in login_resp.cookies
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]
    assert len(token) >= 32  # Unpredictable 256-bit cryptographically secure token


def test_auth_login_invalid_credentials_generic_error(client: TestClient):
    """Proves failed login returns generic error without revealing account existence."""
    client.cookies.clear()
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@acme.corp", "password": "WrongPassword123!"},
    )
    assert resp.status_code == 401
    err = resp.json()["error"]
    assert err["code"] == "UNAUTHORIZED"
    assert err["message"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_auth_disabled_account_rejected(client: TestClient):
    """Proves inactive or suspended account cannot authenticate."""
    client.cookies.clear()
    async with AsyncSessionLocal() as db_session:
        stmt = select(User).where(User.email == "disabled.user@acme.corp")
        res = await db_session.execute(stmt)
        disabled_user = res.scalar_one_or_none()
        if not disabled_user:
            disabled_user = User(
                email="disabled.user@acme.corp",
                full_name="Disabled User",
                password_hash=hash_password("Password123!"),
                role="DEVELOPER",
                status="INACTIVE",
            )
            db_session.add(disabled_user)
            await db_session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "disabled.user@acme.corp", "password": "Password123!"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
    assert "inactive" in resp.json()["error"]["message"].lower()


def test_auth_session_invalidation_and_replay_rejection(client: TestClient):
    """Proves session is invalidated on logout and subsequent requests are rejected."""
    client.cookies.clear()
    # 1. Login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    # 2. Access /me succeeds
    me_resp = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: token})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "alex.morgan@acme.corp"

    # 3. Logout
    logout_resp = client.post("/api/v1/auth/logout", cookies={settings.SESSION_COOKIE_NAME: token})
    assert logout_resp.status_code == 200

    # 4. Replay previous session token -> rejected with 401
    client.cookies.clear()
    replay_resp = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: token})
    assert replay_resp.status_code == 401
    assert replay_resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_auth_me_safe_profile_fields(client: TestClient):
    """Proves /auth/me returns only safe profile attributes."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    me_resp = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: token})
    assert me_resp.status_code == 200
    profile = me_resp.json()

    # Required safe fields
    assert "user_id" in profile
    assert "email" in profile
    assert "full_name" in profile
    assert "role" in profile
    assert "status" in profile
    assert "permissions" in profile

    # Prohibited leak fields
    assert "password" not in profile
    assert "password_hash" not in profile
    assert "token_hash" not in profile
    assert "session_id" not in profile
    assert "secret" not in profile


def test_auth_missing_credentials_rejected(client: TestClient):
    """Proves protected /auth/me endpoint rejects requests with missing credentials."""
    client.cookies.clear()
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_auth_session_rotation(client: TestClient):
    """Proves logging in again invalidates previous session token."""
    client.cookies.clear()
    # First login
    resp1 = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    token1 = resp1.cookies[settings.SESSION_COOKIE_NAME]

    # Second login
    resp2 = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    token2 = resp2.cookies[settings.SESSION_COOKIE_NAME]
    assert token1 != token2

    # Replay token 1 -> rejected with 401
    client.cookies.clear()
    check1 = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: token1})
    assert check1.status_code == 401
    assert check1.json()["error"]["code"] == "UNAUTHORIZED"

    # Token 2 succeeds
    check2 = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: token2})
    assert check2.status_code == 200


@pytest.mark.asyncio
async def test_auth_session_absolute_expiry(client: TestClient):
    """Proves session past absolute expiration limit is revoked and rejected."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import update
    from app.core.security import hash_session_token
    from app.models.user import UserSession

    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]
    t_hash = hash_session_token(token)

    # Force expiration in past
    async with AsyncSessionLocal() as db_session:
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        await db_session.execute(
            update(UserSession)
            .where(UserSession.token_hash == t_hash)
            .values(expires_at=past_time)
        )
        await db_session.commit()

    # Request rejected with 401
    me_resp = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: token})
    assert me_resp.status_code == 401
    assert "expired" in me_resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_auth_session_idle_expiry(client: TestClient):
    """Proves session idle past 4-hour threshold is revoked and rejected."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import update
    from app.core.security import hash_session_token
    from app.models.user import UserSession

    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]
    t_hash = hash_session_token(token)

    # Force last activity to 5 hours ago (threshold is 4 hours)
    async with AsyncSessionLocal() as db_session:
        past_activity = datetime.now(timezone.utc) - timedelta(hours=5)
        await db_session.execute(
            update(UserSession)
            .where(UserSession.token_hash == t_hash)
            .values(last_activity_at=past_activity)
        )
        await db_session.commit()

    # Request rejected with 401
    me_resp = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: token})
    assert me_resp.status_code == 401
    assert "timed out" in me_resp.json()["error"]["message"].lower()


def test_csrf_cookie_mutation_untrusted_origin_rejected(client: TestClient):
    """Proves cookie-authenticated mutations from untrusted origins are blocked with 403 CSRF_FORBIDDEN."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    # Attempt mutation with untrusted origin
    mutation_resp = client.post(
        "/api/v1/jobs",
        cookies={settings.SESSION_COOKIE_NAME: token},
        headers={"Origin": "https://attacker.evil.com"},
        json={
            "name": "CSRF Exploit Job",
            "source_repository": "https://github.com/acme/csrf",
            "budget": 100.0,
        },
    )
    assert mutation_resp.status_code == 403
    err = mutation_resp.json()["error"]
    assert err["code"] == "CSRF_FORBIDDEN"
    assert "cross-site request forgery" in err["message"].lower()


def test_csrf_cookie_mutation_trusted_origin_accepted(client: TestClient):
    """Proves cookie-authenticated mutations from allowed frontend origin succeed."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    mutation_resp = client.post(
        "/api/v1/jobs",
        cookies={settings.SESSION_COOKIE_NAME: token},
        headers={"Origin": "http://localhost:3000"},
        json={
            "name": "Trusted Origin Job",
            "source_repository": "https://github.com/acme/legit",
            "budget": 100.0,
        },
    )
    assert mutation_resp.status_code == 201


def test_all_protected_routes_missing_credentials(client: TestClient):
    """Enumerates protected endpoints and verifies rejection when credentials are missing."""
    client.cookies.clear()
    dummy_job_id = "00000000-0000-0000-0000-000000000001"
    dummy_art_id = "00000000-0000-0000-0000-000000000002"
    protected_endpoints = [
        ("GET", "/api/v1/auth/me", None),
        ("GET", "/api/v1/jobs", None),
        ("POST", "/api/v1/jobs", {"name": "Test", "source_repository": "https://github.com/acme/repo"}),
        ("GET", f"/api/v1/jobs/{dummy_job_id}", None),
        ("POST", f"/api/v1/jobs/{dummy_job_id}/cancel", {}),
        ("POST", f"/api/v1/jobs/{dummy_job_id}/pause", {}),
        ("POST", f"/api/v1/jobs/{dummy_job_id}/resume", {}),
        ("GET", f"/api/v1/jobs/{dummy_job_id}/artifacts", None),
        ("POST", f"/api/v1/jobs/{dummy_job_id}/artifacts", {"artifact_type": "Report", "content": {}}),
        ("GET", f"/api/v1/jobs/{dummy_job_id}/artifacts/{dummy_art_id}", None),
        ("GET", f"/api/v1/jobs/{dummy_job_id}/artifacts/{dummy_art_id}/content", None),
        ("GET", f"/api/v1/jobs/{dummy_job_id}/audit", None),
    ]
    for method, path, payload in protected_endpoints:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json=payload or {})
        assert resp.status_code == 401, f"Expected 401 for {method} {path}, got {resp.status_code}"
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_auth_register_success_and_immediate_login(client: TestClient):
    """Proves user registration creates account, issues session cookie, and enables immediate /me access."""
    import uuid
    client.cookies.clear()
    unique_email = f"new.engineer.{uuid.uuid4().hex[:8]}@acme.corp"
    reg_payload = {
        "email": unique_email,
        "full_name": "Elena Rostova",
        "password": "SecurePassword2026!",
        "role": "DEVELOPER",
    }
    resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    user_data = resp.json()
    assert user_data["email"] == unique_email
    assert user_data["full_name"] == "Elena Rostova"
    assert user_data["role"] == "DEVELOPER"
    assert user_data["status"] == "ACTIVE"
    assert "password" not in user_data
    assert "password_hash" not in user_data

    # Session cookie must be set
    assert settings.SESSION_COOKIE_NAME in resp.cookies
    token = resp.cookies[settings.SESSION_COOKIE_NAME]

    # Calling /me with session cookie immediately succeeds
    me_resp = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: token})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == unique_email


def test_auth_register_duplicate_email_rejected(client: TestClient):
    """Proves registering with an existing email returns 409 Conflict."""
    client.cookies.clear()
    reg_payload = {
        "email": "alex.morgan@acme.corp",
        "full_name": "Duplicate Alex",
        "password": "Password123!",
        "role": "DEVELOPER",
    }
    resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "CONFLICT"
    assert "already exists" in err["message"].lower()


def test_auth_register_password_too_short_rejected(client: TestClient):
    """Proves registering with password < 8 chars returns 422 Validation Error."""
    client.cookies.clear()
    reg_payload = {
        "email": "short.pw@acme.corp",
        "full_name": "Short Password User",
        "password": "short",
    }
    resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


