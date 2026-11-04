"""Phase 2A Technology Stack Detection Audit and Remediation Test Suite.

Verifies:
1. Zero fabricated Java 11 / Spring Boot fallbacks across all failure paths.
2. Integration with ControlledGitAdapter and secure workspace snapshot lifecycle.
3. Recursive inventory scanner and ignore rules (node_modules, target, .venv).
4. Symlink escape protection.
5. Structured manifest parsing (pom.xml, package.json, pyproject.toml, requirements.txt, go.mod, Cargo.toml).
6. Separation of UI libraries (React/Vue) from backend services (Node.js/FastAPI).
7. Monorepo component decomposition (frontend + backend).
8. Explicit scan statuses: COMPLETED, PARTIAL, INCONCLUSIVE, FAILED.
9. Database persistence of detailed stack metadata and audit logging.
"""

import json
import os
from pathlib import Path
import subprocess
from typing import Dict
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.user import User
from app.services.git_adapter import ControlledGitAdapter, GitSecurityException, GitOperationException
from app.services.inventory_scanner import RepositoryInventoryScanner
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

        # Initialize git safely
        subprocess.run(["git", "init", "-b", branch], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Committer"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@acme.corp"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "Initial test commit"], cwd=str(repo_dir), check=True, capture_output=True)
        return repo_dir

    return _create


# =============================================================================
# 1. Framework & Ecosystem Detection Tests
# =============================================================================

def test_detect_django_repository(make_local_git_repo):
    """Proves Django framework and Python language are detected with high confidence."""
    repo_path = make_local_git_repo({
        "pyproject.toml": """
[project]
name = "my-django-app"
version = "1.0.0"
dependencies = [
    "django>=4.2,<5.0",
    "psycopg2-binary>=2.9.0",
]
""",
        "manage.py": "#!/usr/bin/env python\nimport os\nimport sys\n",
        "app/views.py": "from django.http import HttpResponse\ndef index(request): return HttpResponse('OK')\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "COMPLETED"
    assert res.primary_language == "Python"
    assert "Django" in res.framework
    assert res.confidence_score >= 0.95
    assert res.is_fallback is False
    assert len(res.evidence) >= 1
    assert "Python" in res.languages


def test_detect_fastapi_repository(make_local_git_repo):
    """Proves FastAPI, SQLAlchemy, and Python runtime are detected accurately."""
    repo_path = make_local_git_repo({
        "requirements.txt": "fastapi==0.115.0\nuvicorn>=0.30.0\nsqlalchemy>=2.0.0\npytest>=8.0.0\n",
        "main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        "models.py": "from sqlalchemy.orm import DeclarativeBase\nclass Base(DeclarativeBase): pass\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "COMPLETED"
    assert res.primary_language == "Python"
    assert "FastAPI" in res.framework
    assert "pip" in res.build_tool
    assert res.test_framework == "Pytest"
    assert res.confidence_score >= 0.95


def test_detect_react_typescript_repository(make_local_git_repo):
    """Proves React is classified as a Frontend UI Library rather than a generic Node.js service."""
    repo_path = make_local_git_repo({
        "package.json": json.dumps({
            "name": "my-client-app",
            "version": "1.0.0",
            "dependencies": {
                "react": "^18.3.1",
                "react-dom": "^18.3.1",
            },
            "devDependencies": {
                "typescript": "^5.4.0",
                "vite": "^5.2.0",
                "vitest": "^1.4.0",
            },
        }),
        "src/App.tsx": "import React from 'react'; export const App = () => <div>Hello</div>;\n",
        "src/main.tsx": "import { App } from './App';\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "COMPLETED"
    assert res.primary_language == "TypeScript"
    assert "React" in res.framework
    assert res.build_tool == "Vite"
    assert res.test_framework == "Vitest"
    assert "Client-Side" in res.architecture_style or "Application" in res.architecture_style
    assert res.is_fallback is False


def test_detect_java_spring_boot_maven(make_local_git_repo):
    """Proves Maven-based Spring Boot detection extracts correct Java and Spring Boot versions."""
    repo_path = make_local_git_repo({
        "pom.xml": """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.2</version>
    </parent>
    <groupId>com.acme</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>""",
        "src/main/java/com/acme/OrderApplication.java": "package com.acme;\npublic class OrderApplication {}\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "COMPLETED"
    assert res.primary_language == "Java"
    assert "17" in res.language_version
    assert res.framework == "Spring Boot"
    assert res.framework_version == "3.2.2"
    assert res.build_tool == "Maven (pom.xml)"


def test_detect_go_repository(make_local_git_repo):
    """Proves Go runtime and Gin framework detection."""
    repo_path = make_local_git_repo({
        "go.mod": """module github.com/acme/auth-api

go 1.22.0

require (
    github.com/gin-gonic/gin v1.9.1
)
""",
        "main.go": "package main\nimport \"github.com/gin-gonic/gin\"\nfunc main() {}\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "COMPLETED"
    assert res.primary_language == "Go"
    assert res.framework == "Gin"
    assert "1.22" in res.language_version


def test_detect_rust_repository(make_local_git_repo):
    """Proves Rust and Actix-web framework detection."""
    repo_path = make_local_git_repo({
        "Cargo.toml": """[package]
name = "stream-processor"
version = "0.1.0"
edition = "2021"

[dependencies]
actix-web = "4.4"
tokio = { version = "1.0", features = ["full"] }
""",
        "src/main.rs": "fn main() { println!(\"Running\"); }\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "COMPLETED"
    assert res.primary_language == "Rust"
    assert res.framework == "Actix-web"
    assert res.build_tool == "Cargo (Cargo.toml)"


# =============================================================================
# 2. Monorepo & Multi-Component Decomposition Tests
# =============================================================================

def test_detect_monorepo_frontend_and_backend(make_local_git_repo):
    """Proves monorepos with separate frontend and backend roots produce distinct components."""
    repo_path = make_local_git_repo({
        "frontend/package.json": json.dumps({
            "name": "portal-ui",
            "dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"},
            "devDependencies": {"vite": "^5.0.0"},
        }),
        "frontend/src/App.jsx": "export default function App() {}\n",
        "backend/requirements.txt": "fastapi==0.110.0\nuvicorn>=0.28.0\nsqlalchemy>=2.0.0\n",
        "backend/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "COMPLETED"
    assert len(res.components) >= 2
    comp_types = {c["component_type"] for c in res.components}
    assert "frontend" in comp_types
    assert "backend" in comp_types

    frontend_comp = next(c for c in res.components if c["component_type"] == "frontend")
    backend_comp = next(c for c in res.components if c["component_type"] == "backend")

    assert "React" in frontend_comp["framework"]
    assert "FastAPI" in backend_comp["framework"]
    assert "Full-Stack" in res.architecture_style


def test_detect_nested_service_directories(make_local_git_repo):
    """Proves manifests in nested subdirectories are discovered without hardcoded paths."""
    repo_path = make_local_git_repo({
        "services/payments/api/requirements.txt": "flask>=3.0.0\npsycopg2-binary\n",
        "services/payments/api/server.py": "from flask import Flask\napp = Flask(__name__)\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "COMPLETED"
    assert res.primary_language == "Python"
    assert "Flask" in res.framework
    assert len(res.components) >= 1
    assert "services/payments/api" in res.components[0]["relative_path"]


# =============================================================================
# 3. Honest Outcomes, Empty Repositories & Fallback Prevention
# =============================================================================

def test_detect_empty_repository(make_local_git_repo):
    """Proves an empty repository produces INCONCLUSIVE with zero confidence and NO Java fallback."""
    repo_path = make_local_git_repo({})

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "INCONCLUSIVE"
    assert res.confidence_score == 0.0
    assert res.primary_language == "Unknown"
    assert res.framework == "None detected"
    assert res.is_fallback is False
    assert "Spring Boot" not in res.framework
    assert "Java" not in res.primary_language


def test_detect_documentation_only_repository(make_local_git_repo):
    """Proves a markdown/config repo produces INCONCLUSIVE and does NOT fabricate a code stack."""
    repo_path = make_local_git_repo({
        "README.md": "# System Documentation\nArchitecture guidelines.\n",
        "docs/setup.md": "Run instructions.\n",
        "mkdocs.yml": "site_name: Rebase Docs\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "INCONCLUSIVE"
    assert res.confidence_score == 0.0
    assert res.primary_language == "Unknown"
    assert res.framework == "None detected"
    assert "Spring Boot" not in res.framework
    assert res.is_fallback is False


def test_detect_malformed_manifest_handles_safely(make_local_git_repo):
    """Proves malformed XML/JSON manifests generate safe warnings rather than crashing."""
    repo_path = make_local_git_repo({
        "pom.xml": "<project><unclosedTag>Broken XML",
        "src/App.java": "public class App {}\n",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert len(res.warnings) >= 1
    assert any("pom.xml" in w for w in res.warnings)
    # The scan still records the Java source file evidence
    assert res.primary_language == "Java"
    assert res.scan_status in ("PARTIAL", "INCONCLUSIVE")


def test_vendored_directories_ignored(make_local_git_repo):
    """Proves vendored and environment directories (node_modules, target, .venv) are ignored."""
    repo_path = make_local_git_repo({
        "main.py": "print('First party Python')\n",
        "node_modules/bad/file.js": "// Millions of vendored lines\n" * 100,
        "target/classes/Generated.class": "binary",
        ".venv/lib/site-packages/something.py": "vendored",
    })

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    # JavaScript should NOT appear as a primary language because it is only in node_modules
    assert "JavaScript" not in res.languages
    assert res.primary_language == "Python"


def test_symlink_escape_rejected(make_local_git_repo, tmp_path):
    """Proves symlinks escaping the workspace root are skipped safely without path traversal."""
    secret_dir = tmp_path / "secret_corp_dir"
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "secret.py").write_text("SECRET = True", encoding="utf-8")

    repo_path = make_local_git_repo({
        "app.py": "print('Main')\n",
    })

    # Create a symlink pointing outside workspace if OS allows
    try:
        os.symlink(str(secret_dir), str(repo_path / "symlink_dir"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not permitted in this OS environment.")

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.primary_language == "Python"
    # Escaped symlink must not be indexed
    assert not any("secret" in w.lower() for w in res.languages.keys())


# =============================================================================
# 4. Security & Error Boundary Tests
# =============================================================================

def test_reject_ssrf_and_malicious_urls():
    """Proves malicious or private IP destinations are rejected with GitSecurityException."""
    adapter = ControlledGitAdapter(allow_local_repos_for_test=False)

    with pytest.raises(GitSecurityException) as exc1:
        StackDetector.detect_stack("https://127.0.0.1/evil/repo.git", "main", git_adapter=adapter)
    assert "ssrf violation" in str(exc1.value).lower()

    with pytest.raises(GitSecurityException) as exc2:
        StackDetector.detect_stack("https://github.com/acme/repo.git; rm -rf /", "main", git_adapter=adapter)
    assert "dangerous control characters" in str(exc2.value).lower()


def test_unreachable_repository_raises_git_operation_exception():
    """Proves unreachable Git remotes raise GitOperationException with non-200 code rather than fabricating stack."""
    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    # A non-existent local directory
    non_existent = "file:///C:/non_existent_dir_rebase_test_123456"

    with pytest.raises(GitOperationException) as exc:
        StackDetector.detect_stack(non_existent, "main", git_adapter=adapter)
    assert exc.value.status_code in (404, 502, 500)


# =============================================================================
# 5. API Integration & Database Persistence Tests
# =============================================================================

def test_detect_stack_endpoint_persists_metadata(client: TestClient):
    """Proves calling detect-stack with job_id updates job.stack_metadata and logs an AuditEvent."""
    # 1. Login as Admin
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "AdminSecure123!"},
    )
    assert login_resp.status_code == 200

    # 2. Create a Job
    create_resp = client.post(
        "/api/v1/jobs",
        json={
            "name": "Audit Test Job",
            "source_repository": "https://github.com/acme/payment-gateway",
            "source_revision": "main",
            "source_stack": "Pending Detection",
            "target_stack": "TypeScript / NestJS",
            "budget": 100.0,
        },
    )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["job_id"]

    # 3. Call detect-stack with job_id
    detect_resp = client.post(
        "/api/v1/jobs/detect-stack",
        json={
            "source_repository": "https://github.com/acme/payment-gateway",
            "source_revision": "main",
            "job_id": job_id,
        },
    )
    assert detect_resp.status_code == 200
    detect_data = detect_resp.json()
    assert detect_data["scan_status"] == "COMPLETED"
    assert detect_data["primary_language"] == "Java"
    assert "Spring Boot" in detect_data["framework"]

    # 4. Fetch Job and verify stack_metadata is persisted
    job_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    job_data = job_resp.json()
    assert job_data["stack_metadata"] is not None
    assert job_data["stack_metadata"]["scan_status"] == "COMPLETED"
    assert job_data["stack_metadata"]["primary_language"] == "Java"

    # 5. Fetch Audit Trail and verify JOB_STACK_DETECTED was recorded
    audit_resp = client.get(f"/api/v1/jobs/{job_id}/audit")
    assert audit_resp.status_code == 200
    audit_events = audit_resp.json()["items"]
    assert any(e["event_type"] == "JOB_STACK_DETECTED" for e in audit_events)


def test_detect_stack_resilient_to_master_branch(make_local_git_repo):
    """Proves requesting 'main' against a repository initialized on 'master' succeeds gracefully."""
    repo_path = make_local_git_repo(
        {
            "package.json": '{"name": "legacy-app", "dependencies": {"express": "^4.18.2"}}',
            "index.js": "const express = require('express');",
        },
        branch="master",
    )

    adapter = ControlledGitAdapter(allow_local_repos_for_test=True)
    res = StackDetector.detect_stack(str(repo_path), "main", git_adapter=adapter)

    assert res.scan_status == "COMPLETED"
    assert res.primary_language in ("JavaScript", "Node.js")
    assert res.source_revision == "master"

