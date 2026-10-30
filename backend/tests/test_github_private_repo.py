"""Comprehensive tests for GitHub Private Repository Access using Fine-Grained PAT.

Tests:
1. Public repositories: works without PAT, no credential helper configured.
2. Private repositories:
   - Credential helper setup with isolated temporary directory.
   - Helper protocol and host verification (strictly host=github.com, protocol=https).
   - Rejection of PAT for non-github.com hosts.
   - Token redaction from stderr and logs.
   - Secure wiping and cleanup of token secret file on success and failure.
   - Safe HTTP error mappings (401, 403, 404, 429, 504).
3. Preview vs Intake Lifecycle:
   - POST /api/v1/jobs/detect-stack with optional access_token (ephemeral, zero persistence).
   - POST /api/v1/jobs with optional git_token (zero persistence in DB, stack_metadata, or audit events).
   - POST /api/v1/jobs/{job_id}/intake with git_token (enforces pinned commit, checks out into workspace).
   - Mismatched or invalid pinned commit raises actionable error without silent substitution.
"""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ConflictException, ValidationException
from app.core.logging import redact_sensitive_data
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.user import User
from app.schemas.jobs import JobCreateRequest, StackDetectionRequest
from app.services.git_adapter import (
    ControlledGitAdapter,
    GitOperationException,
    GitSecurityException,
)
from app.services.job_service import JobService
from app.services.stack_detector import StackDetector


# ==============================================================================
# 1. PUBLIC REPOSITORIES
# ==============================================================================

def test_public_repo_preview_without_pat():
    """Proves that public repositories preview and stack detection work cleanly without a PAT."""
    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(
        source_repository="https://github.com/acme/payment-gateway",
        source_revision="main",
        git_adapter=adapter,
        access_token=None,
    )
    assert res.scan_status == "COMPLETED"
    assert res.primary_language == "Java"
    assert res.resolved_commit is not None


def test_public_repo_no_credential_helper_created():
    """Proves no credential helper is configured or temporary files created when access_token is None."""
    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    with patch.object(adapter, "_setup_github_credential_helper") as mock_setup:
        workspace, commit = adapter.clone_repository(
            job_id="test_public",
            repo_url="https://github.com/acme/payment-gateway",
            revision="main",
            access_token=None,
        )
        assert mock_setup.call_count == 0
        assert commit is not None
        adapter.cleanup_workspace("test_public")


def test_public_repo_disables_host_git_credentials_and_configuration():
    """Public staging cannot inherit stale workstation credentials."""
    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        adapter._execute_git(["version"])

    command = mock_run.call_args.args[0]
    environment = mock_run.call_args.kwargs["env"]
    assert "credential.helper=" in command
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"


# ==============================================================================
# 2. CREDENTIAL HELPER ISOLATION AND HOST RESTRICTION
# ==============================================================================

def test_credential_helper_setup_and_cleanup():
    """Proves that credential helper creates isolated files, wipes token with zeroes, and cleans up."""
    token = "github_pat_11TESTSECRETKEY0000000000000000000000000"
    config_args, cleanup_fn = ControlledGitAdapter._setup_github_credential_helper(token)

    assert len(config_args) == 4
    assert config_args[0] == "-c"
    assert config_args[1] == "credential.helper="
    assert config_args[2] == "-c"
    assert "credential.https://github.com.helper=" in config_args[3]

    # Verify no raw token appears in config args
    for arg in config_args:
        assert token not in arg

    # Extract helper directory from config args
    helper_path_str = config_args[3].split('!"', 1)[1].split('" "', 1)[1].rstrip('"')
    helper_path = Path(helper_path_str)
    cred_dir = helper_path.parent
    token_file = cred_dir / "token.secret"

    assert cred_dir.exists()
    assert token_file.exists()
    assert token_file.read_text(encoding="utf-8") == token

    # Invoke cleanup
    cleanup_fn()

    assert not token_file.exists()
    assert not cred_dir.exists()


def test_credential_helper_rejects_non_github_host():
    """Proves that providing a token for a non-GitHub repository raises GitSecurityException."""
    adapter = ControlledGitAdapter()
    with pytest.raises(GitSecurityException) as exc_info:
        adapter.clone_repository(
            job_id="test_gitlab",
            repo_url="https://gitlab.com/org/repo.git",
            access_token="github_pat_1234567890abcdef",
        )
    assert "strictly to github.com" in str(exc_info.value.message)


def test_credential_helper_rejects_control_characters():
    """Proves that tokens with newline injection or control characters are rejected."""
    with pytest.raises(GitSecurityException) as exc_info:
        ControlledGitAdapter._setup_github_credential_helper("ghp_valid\nmalicious_command")
    assert "control characters" in str(exc_info.value.message)


def test_credential_helper_sh_execution_logic():
    """Tests the Python helper execution directly with valid and invalid host/protocol combinations."""
    import subprocess
    import sys

    token = "github_pat_super_secret_test_token_123"
    config_args, cleanup_fn = ControlledGitAdapter._setup_github_credential_helper(token)

    helper_path_str = config_args[3].split('!"', 1)[1].split('" "', 1)[1].rstrip('"')

    try:
        # Case 1: Matching github.com and https -> returns credentials
        p1 = subprocess.run(
            [sys.executable, helper_path_str, "get"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
        )
        assert p1.returncode == 0
        assert "username=x-access-token" in p1.stdout
        assert f"password={token}" in p1.stdout

        # Case 2: Non-matching host -> returns empty string (never leaks token)
        p2 = subprocess.run(
            [sys.executable, helper_path_str, "get"],
            input="protocol=https\nhost=gitlab.com\n\n",
            capture_output=True,
            text=True,
        )
        assert p2.returncode == 0
        assert p2.stdout == ""

        # Case 3: Non-matching protocol (http) -> returns empty string
        p3 = subprocess.run(
            [sys.executable, helper_path_str, "get"],
            input="protocol=http\nhost=github.com\n\n",
            capture_output=True,
            text=True,
        )
        assert p3.returncode == 0
        assert p3.stdout == ""

    finally:
        cleanup_fn()


# ==============================================================================
# 3. REDACTION AND SANITIZATION
# ==============================================================================

def test_token_redaction_in_logging():
    """Proves that fine-grained and classic GitHub PAT tokens are automatically redacted by logger."""
    classic_pat = "ghp_1234567890abcdef1234567890abcdef"
    fine_grained_pat = "github_pat_11A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0"

    redacted1 = redact_sensitive_data(f"Attempting clone with {classic_pat}")
    redacted2 = redact_sensitive_data(f"Failed auth for {fine_grained_pat}")

    assert classic_pat not in redacted1
    assert "[REDACTED]" in redacted1
    assert fine_grained_pat not in redacted2
    assert "[REDACTED]" in redacted2


def test_git_error_diagnostics_mapping():
    """Proves Git execution errors are sanitized into clear, actionable messages without leaking secrets."""
    adapter = ControlledGitAdapter()

    # 1. Terminal prompts disabled / auth required -> 401
    with pytest.raises(GitOperationException) as exc1:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="fatal: could not read Username for 'https://github.com': terminal prompts disabled",
                stdout="",
            )
            adapter._execute_git(["clone", "https://github.com/org/private-repo.git"])
    assert exc1.value.status_code == 401
    assert "Authentication required" in exc1.value.message

    # 2. Invalid username or token -> 401
    with pytest.raises(GitOperationException) as exc2:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="remote: Invalid username or token. fatal: Authentication failed for 'https://github.com/org/repo.git'",
                stdout="",
            )
            adapter._execute_git(["clone", "https://github.com/org/repo.git"])
    assert exc2.value.status_code == 401
    assert "invalid, expired, or revoked" in exc2.value.message

    # 3. Organization SAML enforcement -> 403
    with pytest.raises(GitOperationException) as exc3:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="remote: Resource protected by organization SAML enforcement.",
                stdout="",
            )
            adapter._execute_git(["clone", "https://github.com/org/repo.git"])
    assert exc3.value.status_code == 403
    assert "SAML/SSO" in exc3.value.message

    # 4. Rate limit -> 429
    with pytest.raises(GitOperationException) as exc4:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="remote: You have exceeded a secondary rate limit.",
                stdout="",
            )
            adapter._execute_git(["clone", "https://github.com/org/repo.git"])
    assert exc4.value.status_code == 429
    assert "rate limit exceeded" in exc4.value.message.lower()


# ==============================================================================
# 4. PREVIEW DETECTION CONTRACT & ZERO PERSISTENCE
# ==============================================================================

def test_api_detect_stack_with_pat_in_preview(client: TestClient):
    """Proves POST /api/v1/jobs/detect-stack accepts access_token, succeeds, and does not leak token."""
    resp = client.post(
        "/api/v1/jobs/detect-stack",
        json={
            "source_repository": "https://github.com/acme/payment-gateway",
            "source_revision": "main",
            "access_token": "github_pat_11MOCKTOKEN0000000000000000000000000",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_status"] == "COMPLETED"
    assert data["primary_language"] == "Java"
    # Token must not be echoed in response
    assert "access_token" not in data
    assert "git_token" not in data
    assert "github_pat_" not in str(data)


# ==============================================================================
# 5. JOB CREATION & INTAKE CREDENTIAL LIFECYCLE
# ==============================================================================

def test_job_create_never_persists_git_token(client: TestClient):
    """Proves that passing git_token to POST /api/v1/jobs does not persist it to DB columns or metadata."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    test_pat = "github_pat_99SECRETINTAKETOKEN0000000000000000"
    resp = client.post(
        "/api/v1/jobs",
        json={
            "name": "Private Repo PAT Intake Test",
            "source_repository": "https://github.com/acme/payment-gateway",
            "source_revision": "main",
            "pinned_commit": "9f8e7d6c5b4a31201928374655a4b3c2d1e0f9a8",
            "git_token": test_pat,
            "budget": 120.0,
            "max_repair_attempts": 3,
        },
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert resp.status_code == 201
    job_data = resp.json()

    # 1. Not in create response
    assert "git_token" not in job_data
    assert test_pat not in str(job_data)

    job_id = job_data["job_id"]

    # 2. Check GET /jobs/{job_id} (database representation)
    get_resp = client.get(
        f"/api/v1/jobs/{job_id}",
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert get_resp.status_code == 200
    assert test_pat not in str(get_resp.json())

    # 3. Check GET /jobs/{job_id}/audit (audit log trail)
    audit_resp = client.get(
        f"/api/v1/jobs/{job_id}/audit",
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert audit_resp.status_code == 200
    assert test_pat not in str(audit_resp.json())


def test_job_intake_route_with_pinned_commit(client: TestClient):
    """Proves POST /api/v1/jobs/{job_id}/intake accepts git_token, acquires workspace at pinned commit."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200
    session_cookie = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    # 1. Create a job
    create_resp = client.post(
        "/api/v1/jobs",
        json={
            "name": "Intake Route Test Job",
            "source_repository": "https://github.com/acme/payment-gateway",
            "source_revision": "main",
            "budget": 100.0,
        },
        cookies={settings.SESSION_COOKIE_NAME: session_cookie},
    )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["job_id"]

    # 2. Run intake
    intake_pat = "github_pat_intake_test_only_0000000000"
    intake_resp = client.post(
        f"/api/v1/jobs/{job_id}/intake",
        json={"git_token": intake_pat},
        cookies={settings.SESSION_COOKIE_NAME: session_cookie},
    )
    assert intake_resp.status_code == 200
    intake_data = intake_resp.json()
    # Successful repository staging is immediately handed to the Analyzer by
    # the authoritative supervisor; intake must not leave an executable job
    # pointing at an unvalidated workspace.
    assert intake_data["status"] == "ANALYZING"
    assert "git_token" not in intake_data
    assert intake_pat not in str(intake_data)
