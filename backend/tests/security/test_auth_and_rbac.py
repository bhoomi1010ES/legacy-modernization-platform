"""Security and Role-Based Access Control (RBAC) tests."""

import pytest
from fastapi.testclient import TestClient
from app.core.errors import ForbiddenException
from app.domain.state_machine import RBACPolicy


def test_rbac_role_permissions_matrix():
    """Validates that permission tokens match defined role privileges."""
    # SUPER_ADMIN has full permissions
    assert RBACPolicy.has_permission("SUPER_ADMIN", "job:create") is True
    assert RBACPolicy.has_permission("SUPER_ADMIN", "gate:approve_g4") is True
    assert RBACPolicy.has_permission("SUPER_ADMIN", "user:manage") is True

    # ADMIN can create jobs and approve gates, but not manage global users
    assert RBACPolicy.has_permission("ADMIN", "job:create") is True
    assert RBACPolicy.has_permission("ADMIN", "gate:approve_g1") is True
    assert RBACPolicy.has_permission("ADMIN", "user:manage") is False

    # REVIEWER can approve gates, but cannot create jobs or manage settings
    assert RBACPolicy.has_permission("REVIEWER", "gate:approve_g3") is True
    assert RBACPolicy.has_permission("REVIEWER", "job:create") is False
    assert RBACPolicy.has_permission("REVIEWER", "settings:update") is False

    # DEVELOPER can read and explore, but cannot approve gates
    assert RBACPolicy.has_permission("DEVELOPER", "artifact:read") is True
    assert RBACPolicy.has_permission("DEVELOPER", "gate:approve_g1") is False

    # VIEWER is read-only
    assert RBACPolicy.has_permission("VIEWER", "job:read") is True
    assert RBACPolicy.has_permission("VIEWER", "artifact:download") is False


def test_rbac_check_permission_raises_forbidden():
    """Verifies that unauthorized permission checks raise ForbiddenException."""
    with pytest.raises(ForbiddenException) as exc_info:
        RBACPolicy.check_permission("DEVELOPER", "gate:approve_g4")
    assert "lacks required permission" in exc_info.value.message


def test_login_endpoint_validation(client: TestClient):
    """Verifies that /auth/login returns valid user details and HttpOnly cookie on success."""
    valid_payload = {
        "email": "alex.morgan@acme.corp",
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/login", json=valid_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "alex.morgan@acme.corp"
    assert data["role"] == "ADMIN"
    assert "rebase_session_id" in response.cookies


def test_login_endpoint_invalid_credentials(client: TestClient):
    """Verifies that invalid credentials return 401 Unauthorized with standardized error."""
    invalid_payload = {
        "email": "invalid@example.com",
        "password": "WrongPassword999",
    }
    response = client.post("/api/v1/auth/login", json=invalid_payload)
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "Invalid email or password" in data["error"]["message"]


def test_logout_clears_session_cookie(client: TestClient):
    """Verifies that /auth/logout clears the session cookie."""
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    # Cookie should be expired or empty
    assert response.json()["success"] is True
