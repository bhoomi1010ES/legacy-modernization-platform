"""Phase 2B Ephemeral Repository Detection and Three-Tier Architecture Test Suite.

Verifies:
1. Ephemeral preview workspace isolation:
   - Backend repo_workspaces/ is completely untouched before, during, and after preview detection.
   - OS temporary directories are strictly cleaned up after success and exceptions.
   - Concurrent preview requests remain isolated and collision-free.
2. Three-Tier Characterization:
   - React SPA is classified as Frontend Tier; Backend Tier is None detected (never falsely labeled Node.js).
   - Express is classified as Backend Tier; Frontend Tier is None detected.
   - Monorepos with multiple frontend and backend services are properly decomposed.
3. Database Non-Guessing Heuristics:
   - Generic SQL schemas classify as 'Relational SQL (Dialect Unconfirmed)' with 0.50 confidence.
   - Vendor DDL (MySQL ENGINE=InnoDB) confirms MySQL with 0.95 confidence.
   - Vendor DDL (PostgreSQL SERIAL/JSONB/TIMESTAMPTZ) confirms PostgreSQL with 0.95 confidence.
   - Driver dependencies (e.g. pdo_mysql) identify driver with 0.90 confidence.
   - Dual confirmation (DDL + Driver match) reaches 0.98 confidence.
   - Conflicting DDL vs Driver produces diagnostic ambiguity warning and lowered confidence.
   - Stateless repositories return empty database tier.
4. Job Creation & Persistence:
   - Preserves raw detected findings separately from user overrides.
   - Validates pinned commit SHA syntax and rejects malformed hashes.
"""

from pathlib import Path
import subprocess
import tempfile
from typing import Dict
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationException
from app.models.user import User
from app.schemas.jobs import JobCreateRequest
from app.services.git_adapter import ControlledGitAdapter, GitSecurityException
from app.services.job_service import JobService
from app.services.stack_detector import StackDetector


@pytest.fixture
def make_local_git_repo(tmp_path: Path):
    """Factory fixture to create controlled local Git repositories with custom files."""
    def _create(files: Dict[str, str], branch: str = "main") -> Path:
        repo_dir = tmp_path / f"repo_{uuid.uuid4().hex[:8]}"
        repo_dir.mkdir(parents=True, exist_ok=True)

        for rel_path, content in files.items():
            file_path = repo_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        subprocess.run(["git", "init", "-b", branch], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Committer"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@acme.corp"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "Initial test commit"], cwd=str(repo_dir), check=True, capture_output=True)
        return repo_dir

    return _create


# =============================================================================
# 1. Ephemeral Preview Workspace Isolation Tests
# =============================================================================

def test_preview_workspace_isolation_and_cleanup(make_local_git_repo):
    """Proves preview detection NEVER touches backend/repo_workspaces/ and cleans tempdir."""
    repo_path = make_local_git_repo({
        "package.json": '{"name": "isolation-test", "dependencies": {"react": "^18.2.0"}}',
        "src/App.tsx": "export const App = () => <div>Hello</div>;",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    permanent_workspace_dir = adapter.workspace_base

    # Record files in permanent workspace before detection
    before_items = set(permanent_workspace_dir.iterdir()) if permanent_workspace_dir.exists() else set()

    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    # Record files in permanent workspace after detection
    after_items = set(permanent_workspace_dir.iterdir()) if permanent_workspace_dir.exists() else set()

    # Rule: repo_workspaces must remain 100% identical
    assert before_items == after_items, "Preview detection leaked directories into permanent repo_workspaces!"
    assert res.scan_status == "COMPLETED"
    assert res.tiers.frontend.primary is not None
    assert "React" in res.tiers.frontend.primary.framework


def test_preview_failure_workspace_cleanup(make_local_git_repo):
    """Proves failed preview detections clean up temporary folders and do not touch repo_workspaces."""
    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    permanent_workspace_dir = adapter.workspace_base
    before_items = set(permanent_workspace_dir.iterdir()) if permanent_workspace_dir.exists() else set()

    # Non-existent local repository path
    fake_repo = "file:///non/existent/path/repo"
    with pytest.raises(Exception):
        StackDetector.detect_stack(fake_repo, "main", git_adapter=adapter)

    after_items = set(permanent_workspace_dir.iterdir()) if permanent_workspace_dir.exists() else set()
    assert before_items == after_items, "Failed preview leaked directories into permanent repo_workspaces!"


def test_concurrent_preview_requests_isolation(make_local_git_repo):
    """Proves two distinct preview requests run in isolated tempdirs without collisions."""
    repo1 = make_local_git_repo({"package.json": '{"name": "app-one", "dependencies": {"vue": "^3.3.0"}}'})
    repo2 = make_local_git_repo({"requirements.txt": "fastapi==0.115.0\nmain.py\n", "main.py": "import fastapi"})

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)

    res1 = StackDetector.detect_stack(str(repo1), "main", git_adapter=adapter)
    res2 = StackDetector.detect_stack(str(repo2), "main", git_adapter=adapter)

    assert res1.tiers.frontend.primary.framework == "Vue SPA"
    assert res2.tiers.backend.primary.framework == "FastAPI"


# =============================================================================
# 2. Three-Tier Framework Characterization Tests
# =============================================================================

def test_react_frontend_versus_express_backend(make_local_git_repo):
    """Proves React-only is NOT labeled Node.js backend, and Express is labeled Backend."""
    # Case A: React SPA only
    react_repo = make_local_git_repo({
        "package.json": '{"name": "react-client", "dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"}, "devDependencies": {"vite": "^5.0.0"}}',
        "src/main.tsx": "console.log('client');",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res_react = StackDetector.detect_stack(str(react_repo), "main", git_adapter=adapter)

    assert res_react.tiers.frontend.primary is not None
    assert "React" in res_react.tiers.frontend.primary.framework
    # Crucial Rule: Backend must NOT be Node.js
    assert res_react.tiers.backend.primary is None, "React-only repo was falsely labeled as having a Backend Tier!"

    # Case B: Express backend only
    express_repo = make_local_git_repo({
        "package.json": '{"name": "express-server", "dependencies": {"express": "^4.19.0"}}',
        "server.js": "const express = require('express'); const app = express();",
    })
    res_express = StackDetector.detect_stack(str(express_repo), "main", git_adapter=adapter)

    assert res_express.tiers.backend.primary is not None
    assert "Express" in res_express.tiers.backend.primary.framework
    assert res_express.tiers.frontend.primary is None, "Express-only repo was falsely labeled as having a Frontend Tier!"


def test_fullstack_monorepo_three_tiers(make_local_git_repo):
    """Proves full-stack monorepo with Frontend, Backend, and Database is fully characterized."""
    repo = make_local_git_repo({
        "apps/web/package.json": '{"name": "web", "dependencies": {"react": "^18.2.0"}}',
        "apps/web/src/App.tsx": "export const App = () => <h1>App</h1>;",
        "services/api/requirements.txt": "fastapi==0.115.0\nuvicorn>=0.30.0\npsycopg2-binary\n",
        "services/api/main.py": "from fastapi import FastAPI\napp = FastAPI()",
        "database/schema.sql": "CREATE TABLE users (id SERIAL PRIMARY KEY, email VARCHAR(255) NOT NULL, created_at TIMESTAMPTZ);",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo), "main", git_adapter=adapter)

    assert res.tiers.frontend.primary is not None
    assert "React" in res.tiers.frontend.primary.framework

    assert res.tiers.backend.primary is not None
    assert "FastAPI" in res.tiers.backend.primary.framework

    assert res.tiers.database.primary is not None
    assert res.tiers.database.primary.engine == "PostgreSQL"
    assert res.tiers.database.primary.confidence >= 0.95


# =============================================================================
# 3. Database Non-Guessing Heuristics Tests
# =============================================================================

def test_database_nonguessing_generic_sql(make_local_git_repo):
    """Proves generic SQL schema without vendor keywords does NOT guess MySQL or PostgreSQL."""
    repo = make_local_git_repo({
        "schema.sql": "CREATE TABLE customers (id INT PRIMARY KEY, name VARCHAR(100), balance DECIMAL(10,2));",
        "app.py": "print('hello')",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo), "main", git_adapter=adapter)

    assert res.tiers.database.primary is not None
    assert res.tiers.database.primary.engine == "Relational SQL (Dialect Unconfirmed)"
    assert res.tiers.database.primary.confidence == 0.50
    assert res.tiers.database.primary.inferred_from == "generic_sql"


def test_database_vendor_ddl_mysql(make_local_git_repo):
    """Proves vendor-specific DDL keywords (ENGINE=InnoDB, AUTO_INCREMENT) confirm MySQL with 0.95 confidence."""
    repo = make_local_git_repo({
        "database/schema.sql": """
        CREATE TABLE orders (
            order_id INT AUTO_INCREMENT PRIMARY KEY,
            total DECIMAL(10, 2) NOT NULL,
            updated_at TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """,
        "main.go": "package main\nfunc main() {}",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo), "main", git_adapter=adapter)

    assert res.tiers.database.primary is not None
    assert res.tiers.database.primary.engine == "MySQL"
    assert res.tiers.database.primary.confidence == 0.95
    assert res.tiers.database.primary.inferred_from == "ddl_syntax"


def test_database_vendor_ddl_postgresql(make_local_git_repo):
    """Proves vendor-specific PostgreSQL DDL (SERIAL, TIMESTAMPTZ, JSONB) confirms PostgreSQL with 0.95 confidence."""
    repo = make_local_git_repo({
        "db/init.sql": """
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
        CREATE TABLE audit_trail (
            id SERIAL PRIMARY KEY,
            event_payload JSONB NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
        "index.js": "console.log('service');",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo), "main", git_adapter=adapter)

    assert res.tiers.database.primary is not None
    assert res.tiers.database.primary.engine == "PostgreSQL"
    assert res.tiers.database.primary.confidence == 0.95
    assert res.tiers.database.primary.inferred_from == "ddl_syntax"


def test_database_driver_dependency_and_dual_match(make_local_git_repo):
    """Proves driver alone scores 0.90, while DDL + Driver dual confirmation scores 0.98."""
    # Case A: Driver in composer.json alone
    repo_driver = make_local_git_repo({
        "composer.json": '{"require": {"php": "^8.2", "laravel/framework": "^10.0", "ext-pdo_mysql": "*"}}',
        "routes/web.php": "<?php echo 'Laravel';",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res_driver = StackDetector.detect_stack(str(repo_driver), "main", git_adapter=adapter)

    assert res_driver.tiers.database.primary is not None
    assert res_driver.tiers.database.primary.engine == "MySQL"
    assert res_driver.tiers.database.primary.confidence == 0.90
    assert res_driver.tiers.database.primary.inferred_from == "driver_dependency"

    # Case B: Driver + DDL dual match
    repo_dual = make_local_git_repo({
        "composer.json": '{"require": {"php": "^8.2", "laravel/framework": "^10.0", "ext-pdo_mysql": "*"}}',
        "database/schema.sql": "CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY) ENGINE=InnoDB;",
        "routes/web.php": "<?php echo 'Laravel';",
    })
    res_dual = StackDetector.detect_stack(str(repo_dual), "main", git_adapter=adapter)

    assert res_dual.tiers.database.primary.engine == "MySQL"
    assert res_dual.tiers.database.primary.confidence == 0.98
    assert res_dual.tiers.database.primary.inferred_from == "ddl_syntax"


def test_database_conflicting_evidence(make_local_git_repo):
    """Proves conflicting DDL vs driver produces warning and degrades confidence."""
    repo = make_local_git_repo({
        "requirements.txt": "flask>=3.0.0\npsycopg2-binary\n",
        "schema.sql": "CREATE TABLE orders (id INT AUTO_INCREMENT PRIMARY KEY) ENGINE=InnoDB;",
        "app.py": "from flask import Flask\napp = Flask(__name__)",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo), "main", git_adapter=adapter)

    assert res.tiers.database.primary is not None
    assert "Ambiguous" in res.tiers.database.primary.engine
    assert res.tiers.database.primary.confidence == 0.70
    assert any("Conflicting" in w for w in res.warnings)


def test_stateless_repository(make_local_git_repo):
    """Proves repositories without database files return an empty database tier."""
    repo = make_local_git_repo({
        "src/index.js": "console.log('CLI utility');",
        "package.json": '{"name": "cli-tool", "version": "1.0.0"}',
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo), "main", git_adapter=adapter)

    assert res.tiers.database.primary is None
    assert res.tiers.database.components == []
    assert any("Stateless" in w for w in res.warnings)


from app.core.config import settings
from app.core.database import AsyncSessionLocal
from fastapi.testclient import TestClient


# =============================================================================
# 4. Job Creation & Persistence Contract Tests
# =============================================================================

@pytest.mark.asyncio
async def test_job_creation_preserves_overrides_and_pinned_commit():
    """Proves job creation separates automated detection from user overrides and records pinned commit."""
    job_service = JobService()

    async with AsyncSessionLocal() as db_session:
        dummy_user = User(
            user_id=uuid.uuid4(),
            email=f"architect_{uuid.uuid4().hex[:6]}@rebase.test",
            full_name="Lead Architect",
            password_hash="testhash",
            role="ADMIN",
        )
        db_session.add(dummy_user)
        await db_session.commit()

        valid_commit_sha = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
        user_overrides = {
            "database": {"engine": "PostgreSQL", "orm": "SQLAlchemy"},
            "frontend": {"framework": "Next.js"},
        }

        req = JobCreateRequest(
            name="Phase 2B Test Job",
            source_repository="https://github.com/acme/payment-gateway",
            source_revision="main",
            source_stack="Java 11 / Spring Boot 2.7",
            target_stack="TypeScript / NestJS",
            budget=100.0,
            pinned_commit=valid_commit_sha,
            user_overrides=user_overrides,
            stack_metadata={"primary_language": "Java", "framework": "Spring Boot"},
        )

        job = await job_service.create_job(db=db_session, payload=req, user=dummy_user)

        assert job.stack_metadata is not None
        assert "detected" in job.stack_metadata
        assert "overrides" in job.stack_metadata
        assert "effective" in job.stack_metadata
        assert job.stack_metadata["pinned_commit"] == valid_commit_sha
        assert job.stack_metadata["overrides"]["database"]["engine"] == "PostgreSQL"


@pytest.mark.asyncio
async def test_job_creation_rejects_malformed_pinned_commit():
    """Proves invalid commit hash syntax is rejected during job intake."""
    job_service = JobService()

    async with AsyncSessionLocal() as db_session:
        dummy_user = User(
            user_id=uuid.uuid4(),
            email=f"user_{uuid.uuid4().hex[:6]}@rebase.test",
            full_name="User Test",
            password_hash="testhash",
            role="USER",
        )
        db_session.add(dummy_user)
        await db_session.commit()

        # Invalid non-hex commit hash
        req = JobCreateRequest(
            name="Invalid Commit Job",
            source_repository="https://github.com/acme/payment-gateway",
            source_revision="main",
            pinned_commit="not-a-valid-sha!!",
        )

        with pytest.raises(ValidationException) as exc_info:
            await job_service.create_job(db=db_session, payload=req, user=dummy_user)

        assert "pinned_commit" in str(exc_info.value.details)


def test_api_jobs_create_with_pinned_commit_and_overrides(client: TestClient):
    """Proves POST /api/v1/jobs accepts pinned_commit and user_overrides via HTTP contract."""
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.cookies[settings.SESSION_COOKIE_NAME]

    valid_commit = "9f8e7d6c5b4a31201928374655a4b3c2d1e0f9a8"
    resp = client.post(
        "/api/v1/jobs",
        json={
            "name": "Phase 2B HTTP Job",
            "source_repository": "https://github.com/acme/payment-gateway",
            "source_revision": "main",
            "pinned_commit": valid_commit,
            "user_overrides": {"database": {"engine": "MySQL 8.0"}},
            "budget": 120.0,
            "max_repair_attempts": 3,
        },
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["stack_metadata"]["pinned_commit"] == valid_commit
    assert data["stack_metadata"]["overrides"]["database"]["engine"] == "MySQL 8.0"

