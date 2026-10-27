"""Tests for Phase 4 Intake Agent, Safe Archive Ingestion, and Repository Inventory."""

import io
import os
import shutil
import tempfile
import zipfile
import pytest
from app.services.intake_agent import IntakeAgent, IntakeSecurityError
from app.services.evidence_service import EvidenceService
from app.schemas.phase4 import ConfidenceLevel, EvidenceType


@pytest.fixture
def sample_repo_dir():
    """Creates a temporary sample repository directory."""
    temp_dir = tempfile.mkdtemp(prefix="test_repo_")
    try:
        # Create src
        src_dir = os.path.join(temp_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        with open(os.path.join(src_dir, "main.py"), "w", encoding="utf-8") as f:
            f.write("def run():\n    print('Hello World')\n\nif __name__ == '__main__':\n    run()\n")

        with open(os.path.join(src_dir, "service.py"), "w", encoding="utf-8") as f:
            f.write("class UserService:\n    def get_user(self, uid):\n        return {'id': uid}\n")

        # Create tests
        test_dir = os.path.join(temp_dir, "tests")
        os.makedirs(test_dir, exist_ok=True)
        with open(os.path.join(test_dir, "test_main.py"), "w", encoding="utf-8") as f:
            f.write("def test_dummy():\n    assert True\n")

        # Create config and manifest
        with open(os.path.join(temp_dir, "requirements.txt"), "w", encoding="utf-8") as f:
            f.write("fastapi>=0.100.0\nuvicorn>=0.22.0\n")

        with open(os.path.join(temp_dir, ".env.example"), "w", encoding="utf-8") as f:
            f.write("DATABASE_URL=sqlite:///./app.db\nSECRET_KEY=redacted_demo_key\n")

        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestIntakeAndInventory:
    """Intake Agent unit and security tests."""

    def test_safe_local_inventory_generation(self, sample_repo_dir):
        """Valid local intake generates deterministic inventory and metadata."""
        agent = IntakeAgent()
        file_items, dirs, inv_hash = agent.build_inventory(sample_repo_dir)

        assert len(file_items) >= 4
        assert len(dirs) >= 2
        assert len(inv_hash) == 64  # SHA-256

        # Invariant: Re-running on unchanged directory produces the exact same hash
        file_items_2, dirs_2, inv_hash_2 = agent.build_inventory(sample_repo_dir)
        assert inv_hash == inv_hash_2
        assert len(file_items) == len(file_items_2)

        paths = [f.path for f in file_items]
        assert "src/main.py" in paths
        assert "src/service.py" in paths
        assert "tests/test_main.py" in paths
        assert "requirements.txt" in paths

    def test_safe_archive_extraction(self, sample_repo_dir):
        """Valid zip archive extracts safely without traversal."""
        agent = IntakeAgent()
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("module/app.py", "print('App running')")
            zf.writestr("module/config.json", '{"env": "test"}')

        zip_bytes = zip_buf.getvalue()
        target_dir = tempfile.mkdtemp(prefix="extract_target_")
        try:
            agent.extract_archive_safely(zip_bytes, target_dir)
            assert os.path.exists(os.path.join(target_dir, "module", "app.py"))
            assert os.path.exists(os.path.join(target_dir, "module", "config.json"))
        finally:
            shutil.rmtree(target_dir, ignore_errors=True)

    def test_reject_zipslip_path_traversal(self):
        """Archive with relative path traversal (../) must be strictly rejected."""
        agent = IntakeAgent()
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("../evil.py", "import os; os.system('echo hacked')")

        zip_bytes = zip_buf.getvalue()
        target_dir = tempfile.mkdtemp(prefix="extract_evil_")
        try:
            with pytest.raises(IntakeSecurityError) as exc_info:
                agent.extract_archive_safely(zip_bytes, target_dir)
            assert "path traversal" in str(exc_info.value).lower()
        finally:
            shutil.rmtree(target_dir, ignore_errors=True)

    def test_reject_absolute_path_in_archive(self):
        """Archive with absolute filesystem path must be rejected."""
        agent = IntakeAgent()
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Zip archives can store Windows or POSIX absolute paths
            zf.writestr("/etc/passwd", "root:x:0:0:::")

        zip_bytes = zip_buf.getvalue()
        target_dir = tempfile.mkdtemp(prefix="extract_abs_")
        try:
            with pytest.raises(IntakeSecurityError) as exc_info:
                agent.extract_archive_safely(zip_bytes, target_dir)
            assert "absolute" in str(exc_info.value).lower() or "traversal" in str(exc_info.value).lower()
        finally:
            shutil.rmtree(target_dir, ignore_errors=True)

    def test_reject_oversized_archive_uncompressed(self):
        """Archive with compressed bomb exceeding size limits must be rejected."""
        agent = IntakeAgent(max_archive_bytes=1000)
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # 50KB uncompressed data
            zf.writestr("big.txt", "A" * 50000)

        zip_bytes = zip_buf.getvalue()
        target_dir = tempfile.mkdtemp(prefix="extract_bomb_")
        try:
            with pytest.raises(IntakeSecurityError) as exc_info:
                agent.extract_archive_safely(zip_bytes, target_dir)
            assert "maximum allowed" in str(exc_info.value).lower()
        finally:
            shutil.rmtree(target_dir, ignore_errors=True)

    def test_evidence_service_sanitization_and_hashing(self):
        """EvidenceService redacts secrets and generates valid hashes."""
        ev_service = EvidenceService()
        raw_snippet = "API_KEY = 'AKIAIOSFODNN7EXAMPLE'\nDATABASE_PASSWORD = 'supersecretpass'"

        evidence = ev_service.create_evidence(
            source_artifact="snap_12345",
            source_path="config/settings.py",
            source_location="L1-L2",
            evidence_type=EvidenceType.CONFIG_KEY,
            evidence_excerpt=raw_snippet,
            confidence=ConfidenceLevel.CONFIRMED,
            agent_name="analyzer_config",
        )

        assert evidence.evidence_id.startswith("ev_")
        assert evidence.content_hash is not None
        assert len(evidence.content_hash) == 64
        # Assert secret redaction in excerpt
        assert "supersecretpass" not in (evidence.evidence_excerpt or "")
        assert "[REDACTED" in (evidence.evidence_excerpt or "")
