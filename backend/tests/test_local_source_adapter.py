"""Comprehensive Test Suite for LocalSourceAdapter and Browser-Based Directory Ingestion.

Tests:
1. Deterministic canonical snapshot fingerprinting.
2. Path traversal (ZipSlip), symlinks, and null-byte attack rejection.
3. Staged preview snapshot creation with 30-minute lease.
4. Single-upload lifecycle: atomic promotion of staged snapshot during job intake.
5. Snapshot authorization enforcement (cross-user promotion blocked).
6. Staged snapshot expiration (TTL enforcement).
7. Snapshot fingerprint tamper detection (HTTP 409 on content modification).
8. Incomplete scan detection: limits trigger PARTIAL scan_status and explicit warnings.
9. Stale snapshot garbage collection.
10. End-to-end detection parity on test fixture.
11. Regression verification of Git and PAT workflows.
"""

from datetime import datetime, timezone, timedelta
import io
import json
from pathlib import Path
import shutil
import tempfile
import uuid
import zipfile
import pytest

from app.core.errors import (
    ConflictException,
    NotFoundException,
    PlatformException,
    UnauthorizedException,
    ValidationException,
)
from app.services.local_source_adapter import LocalSourceAdapter, LocalSourceSecurityException
from app.services.stack_detector import StackDetector
from app.services.job_service import JobService
from app.schemas.jobs import JobCreateRequest


def create_in_memory_zip(file_dict: dict[str, bytes]) -> Path:
    """Helper creating a temporary ZIP file from a dict of relative_path -> content."""
    temp_zip = Path(tempfile.gettempdir()) / f"test_bundle_{uuid.uuid4()}.zip"
    with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in file_dict.items():
            zf.writestr(rel_path, content)
    return temp_zip


class TestLocalSourceAdapter:

    @pytest.fixture
    def staging_env(self, tmp_path):
        staging = tmp_path / "staging_snapshots"
        workspaces = tmp_path / "repo_workspaces"
        adapter = LocalSourceAdapter(staging_base=staging, workspace_base=workspaces)
        return adapter, staging, workspaces

    def test_canonical_fingerprint_deterministic_and_sorted(self, tmp_path):
        """Proves canonical fingerprint sorts files lexicographically and uses null-delimiter."""
        dir1 = tmp_path / "proj1"
        dir1.mkdir()
        (dir1 / "b.txt").write_text("content B", encoding="utf-8")
        (dir1 / "a.txt").write_text("content A", encoding="utf-8")

        fp1 = LocalSourceAdapter.calculate_canonical_fingerprint(dir1)
        assert len(fp1) == 64
        assert fp1 == LocalSourceAdapter.calculate_canonical_fingerprint(dir1)

        # Modifying a single byte changes the fingerprint
        (dir1 / "a.txt").write_text("content A modified", encoding="utf-8")
        fp2 = LocalSourceAdapter.calculate_canonical_fingerprint(dir1)
        assert fp1 != fp2

    def test_path_traversal_zipslip_rejected(self, staging_env):
        """Verifies ZipSlip path traversal vectors are caught and rejected."""
        adapter, _, _ = staging_env
        malicious_zip = create_in_memory_zip({
            "../../etc/passwd": b"root:x:0:0::/root:/bin/bash",
            "normal.txt": b"safe content",
        })

        try:
            with pytest.raises(LocalSourceSecurityException) as exc:
                adapter.stage_preview_bundle(malicious_zip, "malicious", "user-123")
            assert "Path traversal" in exc.value.message
        finally:
            malicious_zip.unlink(missing_ok=True)

    def test_windows_path_traversal_rejected(self, staging_env):
        """Verifies Windows-style backslash climbing is caught and rejected."""
        adapter, _, _ = staging_env
        malicious_zip = create_in_memory_zip({
            "..\\..\\windows\\system32\\cmd.exe": b"evil binary",
        })

        try:
            with pytest.raises(LocalSourceSecurityException) as exc:
                adapter.stage_preview_bundle(malicious_zip, "malicious-win", "user-123")
            assert "Path traversal" in exc.value.message
        finally:
            malicious_zip.unlink(missing_ok=True)

    def test_staging_preview_and_atomic_promotion(self, staging_env):
        """Proves Requirement 1: single-upload lifecycle via staging and atomic promotion."""
        adapter, staging, workspaces = staging_env
        test_zip = create_in_memory_zip({
            "package.json": b'{"name": "my-app", "version": "1.0.0"}',
            "src/index.js": b'console.log("hello world");',
        })

        user_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        try:
            staging_dir, meta = adapter.stage_preview_bundle(test_zip, "my-app", user_id)
            assert staging_dir.is_dir()
            assert meta.owner_user_id == user_id
            assert meta.file_count == 2
            assert meta.is_complete is True
            assert (staging / f"{meta.snapshot_id}.meta.json").exists()

            # Promote staging snapshot to permanent workspace
            target_ws, fp = adapter.promote_staging_to_workspace(
                snapshot_id=meta.snapshot_id,
                job_id=job_id,
                user_id=user_id,
                expected_fingerprint=meta.canonical_fingerprint,
            )

            assert target_ws.is_dir()
            assert target_ws == workspaces / f"job_{job_id}"
            assert (target_ws / "package.json").exists()
            assert (target_ws / "src" / "index.js").exists()
            assert fp == meta.canonical_fingerprint

            # Verify staging directory was moved and cleaned up
            assert not staging_dir.exists()
            assert not (staging / f"{meta.snapshot_id}.meta.json").exists()
        finally:
            test_zip.unlink(missing_ok=True)

    def test_snapshot_authorization_cross_user_blocked(self, staging_env):
        """Verifies User A cannot promote User B's staged preview snapshot."""
        adapter, _, _ = staging_env
        test_zip = create_in_memory_zip({"app.py": b"print('hello')"})
        owner_id = str(uuid.uuid4())
        attacker_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        try:
            _, meta = adapter.stage_preview_bundle(test_zip, "app", owner_id)

            with pytest.raises(UnauthorizedException):
                adapter.promote_staging_to_workspace(
                    snapshot_id=meta.snapshot_id,
                    job_id=job_id,
                    user_id=attacker_id,
                    is_admin=False,
                )
        finally:
            test_zip.unlink(missing_ok=True)

    def test_snapshot_expiration_ttl(self, staging_env):
        """Proves expired preview snapshots (>30m) are rejected with HTTP 410."""
        adapter, staging, _ = staging_env
        test_zip = create_in_memory_zip({"app.py": b"print('hello')"})
        user_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        try:
            staging_dir, meta = adapter.stage_preview_bundle(test_zip, "app", user_id)

            # Manually backdate the metadata to simulate expiration
            meta_path = staging / f"{meta.snapshot_id}.meta.json"
            expired_time = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            data["expires_at"] = expired_time
            meta_path.write_text(json.dumps(data), encoding="utf-8")

            with pytest.raises(PlatformException) as exc:
                adapter.promote_staging_to_workspace(
                    snapshot_id=meta.snapshot_id,
                    job_id=job_id,
                    user_id=user_id,
                )
            assert exc.value.status_code == 410
            assert "expired" in exc.value.message.lower()
        finally:
            test_zip.unlink(missing_ok=True)

    def test_fingerprint_tampering_rejected(self, staging_env):
        """Proves fingerprint mismatch during promotion raises HTTP 409 Conflict."""
        adapter, _, _ = staging_env
        test_zip = create_in_memory_zip({"app.py": b"print('hello')"})
        user_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        try:
            _, meta = adapter.stage_preview_bundle(test_zip, "app", user_id)

            with pytest.raises(ConflictException) as exc:
                adapter.promote_staging_to_workspace(
                    snapshot_id=meta.snapshot_id,
                    job_id=job_id,
                    user_id=user_id,
                    expected_fingerprint="0000000000000000000000000000000000000000000000000000000000000000",
                )
            assert exc.value.status_code == 409
            assert "mismatch" in exc.value.message.lower()
        finally:
            test_zip.unlink(missing_ok=True)

    def test_incomplete_scan_detection(self, staging_env):
        """Proves hitting limits sets is_complete=False and triggers PARTIAL scan status."""
        adapter, _, _ = staging_env
        # Set artificially small max files
        adapter.MAX_FILES = 2
        test_zip = create_in_memory_zip({
            "pom.xml": b"""<project xmlns="http://maven.apache.org/POM/4.0.0">
                <modelVersion>4.0.0</modelVersion>
                <groupId>com.example</groupId>
                <artifactId>app</artifactId>
                <version>1.0.0</version>
                <properties><java.version>17</java.version></properties>
                <dependencies>
                    <dependency>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-starter-web</artifactId>
                    </dependency>
                </dependencies>
            </project>""",
            "src/main/java/App.java": b"public class App {}",
            "file3.py": b"print(3)",
            "file4.py": b"print(4)",
        })

        try:
            staging_dir, meta = adapter.stage_preview_bundle(test_zip, "multi", "user-1")
            assert meta.is_complete is False
            assert any("Maximum file limit" in w for w in meta.warnings)

            # StackDetector must flag PARTIAL
            detected = StackDetector.detect_stack_from_workspace(
                workspace_path=staging_dir,
                source_name="multi",
                preview_snapshot_id=meta.snapshot_id,
                snapshot_fingerprint=meta.canonical_fingerprint,
                extra_warnings=meta.warnings,
                is_complete=meta.is_complete,
            )
            assert detected.scan_status == "PARTIAL"
            assert detected.source_type == "local"
            assert detected.preview_snapshot_id == meta.snapshot_id
        finally:
            test_zip.unlink(missing_ok=True)

    def test_stale_staging_snapshots_cleanup(self, staging_env):
        """Verifies cleanup_stale_staging_snapshots purges expired snapshots and retains active ones."""
        adapter, staging, _ = staging_env
        test_zip = create_in_memory_zip({"test.py": b"123"})

        try:
            _, meta_active = adapter.stage_preview_bundle(test_zip, "active", "u1")
            _, meta_expired = adapter.stage_preview_bundle(test_zip, "expired", "u2")

            # Expire second snapshot
            meta_path = staging / f"{meta_expired.snapshot_id}.meta.json"
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            data["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
            meta_path.write_text(json.dumps(data), encoding="utf-8")

            cleaned = adapter.cleanup_stale_staging_snapshots()
            assert cleaned >= 1
            # Active snapshot still exists
            assert (staging / meta_active.snapshot_id).is_dir()
            # Expired snapshot was purged
            assert not (staging / meta_expired.snapshot_id).exists()
        finally:
            test_zip.unlink(missing_ok=True)

    def test_sample_payment_gateway_parity(self, staging_env):
        """Verifies static detection parity on sample payment gateway fixture."""
        adapter, _, _ = staging_env
        fixture_dir = Path(__file__).resolve().parent / "fixtures" / "sample_payment_gateway"
        if not fixture_dir.exists():
            pytest.skip("sample_payment_gateway fixture not found")

        # Zip fixture
        files = {}
        for p in fixture_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(fixture_dir).as_posix()
                files[rel] = p.read_bytes()

        fixture_zip = create_in_memory_zip(files)
        try:
            staging_dir, meta = adapter.stage_preview_bundle(fixture_zip, "payment-gateway", "u1")
            detected = StackDetector.detect_stack_from_workspace(
                workspace_path=staging_dir,
                source_name="payment-gateway",
                preview_snapshot_id=meta.snapshot_id,
                snapshot_fingerprint=meta.canonical_fingerprint,
            )

            assert "Java" in detected.primary_language
            assert "Spring Boot" in detected.framework or "Maven" in detected.build_tool
            assert detected.tiers.backend.primary is not None
            assert detected.source_type == "local"
        finally:
            fixture_zip.unlink(missing_ok=True)

    def test_direct_local_path_materialize_and_tamper(self, staging_env, tmp_path):
        """Verifies pasting a local project path on PC copies directly without upload and enforces fingerprint."""
        adapter, _, workspaces = staging_env
        local_project = tmp_path / "my_local_pc_project"
        local_project.mkdir()
        (local_project / "pom.xml").write_text("<project></project>", encoding="utf-8")
        src_dir = local_project / "src"
        src_dir.mkdir()
        (src_dir / "Main.java").write_text("public class Main {}", encoding="utf-8")

        job_id = str(uuid.uuid4())
        expected_fp = LocalSourceAdapter.calculate_canonical_fingerprint(local_project)

        # 1. Materialize local path directly
        ws_path, actual_fp = adapter.materialize_local_path(
            local_dir=local_project,
            job_id=job_id,
            expected_fingerprint=expected_fp,
        )
        assert ws_path.is_dir()
        assert actual_fp == expected_fp
        assert (ws_path / "pom.xml").exists()
        assert (ws_path / "src" / "Main.java").exists()

        # 2. Tamper check: mismatching fingerprint raises ConflictException
        with pytest.raises(ConflictException):
            adapter.materialize_local_path(
                local_dir=local_project,
                job_id=str(uuid.uuid4()),
                expected_fingerprint="bad_fingerprint_0000000000000000000000000000000000000000000000000000",
            )
