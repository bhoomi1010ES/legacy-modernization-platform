"""Phase 1 Controlled Git Adapter, SSRF Protection, and Zero-Execution Tests."""

import os
import subprocess
import pytest
from pathlib import Path

from app.core.errors import ConflictException
from app.services.git_adapter import ControlledGitAdapter, GitOperationException, GitSecurityException


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Initializes a temporary local Git repository for integration testing."""
    repo_dir = tmp_path / "sample_origin_repo"
    repo_dir.mkdir(parents=True)

    # Init repo safely
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Committer"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@acme.corp"], cwd=str(repo_dir), check=True)

    # Initial commit
    file1 = repo_dir / "LegacyApplication.java"
    file1.write_text("public class LegacyApplication { public static void main(String[] args) {} }")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial legacy commit"], cwd=str(repo_dir), check=True)

    return repo_dir


def test_git_ssrf_and_protocol_allowlist_validation():
    """Proves Git adapter rejects forbidden protocols and SSRF destinations."""
    # Production-mode adapter (rejects private/local IPs)
    adapter = ControlledGitAdapter(allow_local_repos_for_test=False)

    # 1. Reject invalid / malicious schemes
    with pytest.raises(GitSecurityException) as exc:
        adapter.validate_source_url("ftp://github.com/acme/repo.git")
    assert "protocol 'ftp' is not allowed" in str(exc.value).lower()

    # 2. Reject shell injection attempts in URL
    with pytest.raises(GitSecurityException) as exc:
        adapter.validate_source_url("https://github.com/acme/repo.git; rm -rf /")
    assert "dangerous control characters" in str(exc.value).lower()

    # 3. Reject loopback / SSRF IP destinations
    with pytest.raises(GitSecurityException) as exc:
        adapter.validate_source_url("https://127.0.0.1/evil/repo.git")
    assert "ssrf violation" in str(exc.value).lower()

    # 4. Reject private RFC 1918 range
    with pytest.raises(GitSecurityException) as exc:
        adapter.validate_source_url("https://192.168.1.50/internal.git")
    assert "ssrf violation" in str(exc.value).lower()


def test_git_clone_branch_diff_workflow(tmp_path: Path, temp_git_repo: Path):
    """Proves controlled clone, commit metadata inspection, safe branch creation, and diffs."""
    adapter = ControlledGitAdapter(
        workspace_base=str(tmp_path / "workspaces"),
        allow_local_repos_for_test=True,
    )

    job_id = "test-job-001"
    repo_url = str(temp_git_repo)

    # 1. Clone repository into controlled job workspace
    workspace, commit_hash = adapter.clone_repository(job_id=job_id, repo_url=repo_url)
    assert workspace.exists()
    assert len(commit_hash) == 40

    # 2. Inspect commit metadata
    metadata = adapter.get_commit_metadata(job_id=job_id)
    assert metadata["commit_hash"] == commit_hash
    assert "Test Committer" in metadata["author"]
    assert metadata["message"] == "Initial legacy commit"

    # 3. Create safe module branch: job/{job_id}/{module_slug}
    branch_name = adapter.create_module_branch(job_id=job_id, module_slug="auth-module")
    assert branch_name == "job/test-job-001/auth-module"

    # 4. Verify protected branch policy
    with pytest.raises(ConflictException):
        adapter.verify_branch_is_not_protected("main")

    with pytest.raises(ConflictException):
        adapter.verify_branch_is_not_protected("master")

    # Safe branch is permitted
    adapter.verify_branch_is_not_protected(branch_name)

    # 5. Clean up workspace
    adapter.cleanup_workspace(job_id=job_id)
    assert not workspace.exists()
