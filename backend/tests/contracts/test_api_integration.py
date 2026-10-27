"""End-to-end API integration tests for Phase 0 endpoints updated for Phase 1 session auth."""

from fastapi.testclient import TestClient


def test_auth_lifecycle_integration(client: TestClient):
    """Verifies complete authentication flow: login -> get identity -> logout."""
    # 1. Login with valid credentials
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200
    user_data = login_resp.json()
    assert user_data["email"] == "alex.morgan@acme.corp"
    assert user_data["role"] == "ADMIN"
    assert "rebase_session_id" in login_resp.cookies

    session_cookie = login_resp.cookies["rebase_session_id"]
    assert session_cookie is not None and len(session_cookie) >= 20

    # 2. Get current user identity (/me)
    me_resp = client.get("/api/v1/auth/me", cookies={"rebase_session_id": session_cookie})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "alex.morgan@acme.corp"

    # 3. Logout
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["success"] is True


def test_auth_login_validation_and_errors(client: TestClient):
    """Verifies invalid email format, short password, and bad credentials."""
    # Invalid email format -> 422
    resp_bad_email = client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "Password123!"},
    )
    assert resp_bad_email.status_code == 422
    assert resp_bad_email.json()["error"]["code"] == "VALIDATION_ERROR"

    # Short password (< 8 chars) -> 422
    resp_short_pw = client.post(
        "/api/v1/auth/login",
        json={"email": "alex@example.com", "password": "short"},
    )
    assert resp_short_pw.status_code == 422
    assert resp_short_pw.json()["error"]["code"] == "VALIDATION_ERROR"

    # Bad credentials -> 401
    resp_bad_cred = client.post(
        "/api/v1/auth/login",
        json={"email": "invalid@example.com", "password": "wrongpassword"},
    )
    assert resp_bad_cred.status_code == 401
    assert resp_bad_cred.json()["error"]["code"] == "UNAUTHORIZED"


def test_jobs_lifecycle_api_integration(client: TestClient):
    """Verifies job creation, retrieval, listing, and state transitions via HTTP API."""
    # Authenticate client
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200

    # 1. Create a job
    create_payload = {
        "name": "Integration Test Service",
        "source_repository": "https://github.com/acme/test-service",
        "source_revision": "main",
        "source_stack": "Java 11 / Spring Boot",
        "target_stack": "TypeScript / Node.js 22 / NestJS",
        "budget": 200.0,
        "max_repair_attempts": 3,
        "constraints": "Strict compliance with schema",
    }
    create_resp = client.post("/api/v1/jobs", json=create_payload)
    assert create_resp.status_code == 201
    job = create_resp.json()
    job_id = job["job_id"]
    assert job["name"] == "Integration Test Service"
    assert job["status"] in ("CREATED", "ANALYZING")

    # 2. Retrieve job by id
    get_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["job_id"] == job_id

    # 3. List jobs with status filter
    list_resp = client.get(f"/api/v1/jobs?status={job['status']}")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(j["job_id"] == job_id for j in items)

    # 4. Cancel job
    cancel_resp = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"


def test_detect_stack_api_integration(client: TestClient):
    """Verifies repository tech stack detection endpoint."""
    client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    detect_resp = client.post(
        "/api/v1/jobs/detect-stack",
        json={"source_repository": "https://github.com/acme/payment-gateway", "source_revision": "main"},
    )
    assert detect_resp.status_code == 200
    data = detect_resp.json()
    assert data["primary_language"] == "Java"
    assert "Spring Boot" in data["framework"]
    assert "Maven" in data["build_tool"]
    assert data["confidence_score"] >= 0.9
    assert len(data["summary_stack"]) > 5


def test_gate_decision_api_integration(client: TestClient):
    """Verifies approval gate decision submission and validation via HTTP API."""
    client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )

    create_payload = {
        "name": "Gate Decision Integration Service",
        "source_repository": "https://github.com/acme/gate-decision-service",
        "source_revision": "main",
        "source_stack": "Java 11 / Spring Boot",
        "target_stack": "TypeScript / Node.js 22 / NestJS",
        "budget": 200.0,
        "max_repair_attempts": 3,
        "constraints": "Strict compliance with schema",
    }
    create_resp = client.post("/api/v1/jobs", json=create_payload)
    assert create_resp.status_code == 201
    job = create_resp.json()
    job_id = job["job_id"]

    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.models.job import Job
    from sqlalchemy import select
    import uuid

    async def _set_awaiting():
        async with AsyncSessionLocal() as session:
            j = (await session.execute(select(Job).where(Job.job_id == uuid.UUID(job_id)))).scalar_one()
            j.status = "AWAITING_GATE_G1"
            await session.commit()
    asyncio.run(_set_awaiting())

    # 1. Fetch pending gates
    pending_resp = client.get("/api/v1/gates/pending")
    assert pending_resp.status_code == 200
    pending_items = pending_resp.json()["items"]
    assert len(pending_items) > 0

    target_gate = next(item for item in pending_items if item["job_id"] == job_id)
    gate_id = target_gate["gate_id"]

    # 2. Reject short rationale (< 10 chars) -> 422 Unprocessable Content (Schema validation)
    short_rationale_resp = client.post(
        f"/api/v1/jobs/{job_id}/gates/{gate_id}/decisions",
        json={"decision": "APPROVED", "rationale": "Ok"},
    )
    assert short_rationale_resp.status_code == 422
    assert short_rationale_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Valid decision with sufficient rationale -> 200 OK
    valid_decision_resp = client.post(
        f"/api/v1/jobs/{job_id}/gates/{gate_id}/decisions",
        json={
            "decision": "APPROVED",
            "rationale": "Architectural feasibility reviewed and verified against NestJS specs.",
            "options": {"gap1": "adapter_pattern"} if target_gate["gate_type"] == "G1" else None,
        },
    )
    assert valid_decision_resp.status_code == 200
    dec_body = valid_decision_resp.json()
    assert dec_body["decision"] == "APPROVED"
    assert dec_body["gate_id"] == gate_id


def test_reports_and_artifacts_endpoints(client: TestClient):
    """Verifies that verification reports, delivery reports, artifacts, and agents respond cleanly."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200

    job_id = "JOB-0248"

    # Verification report
    vr_resp = client.get(f"/api/v1/jobs/{job_id}/reports/verification")
    assert vr_resp.status_code == 200
    assert vr_resp.json()["job_id"] == job_id
    assert vr_resp.json()["behavioral_equivalence_pct"] > 90.0

    # Delivery report
    dr_resp = client.get(f"/api/v1/jobs/{job_id}/reports/delivery")
    assert dr_resp.status_code == 200
    assert dr_resp.json()["job_id"] == job_id
    assert "pull_request_url" in dr_resp.json()

    # Artifacts list
    art_resp = client.get(f"/api/v1/jobs/{job_id}/artifacts")
    assert art_resp.status_code == 200
    assert len(art_resp.json()["items"]) > 0

    # Agents list
    agent_resp = client.get(f"/api/v1/jobs/{job_id}/agents")
    assert agent_resp.status_code == 200
    assert len(agent_resp.json()["items"]) > 0

    # Audit list
    audit_resp = client.get(f"/api/v1/jobs/{job_id}/audit")
    assert audit_resp.status_code == 200
    assert len(audit_resp.json()["items"]) > 0
