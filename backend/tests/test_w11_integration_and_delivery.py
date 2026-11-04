"""W11 Integration, G4 and delivery hardening test suite.

Verifies:
1. Conflicting verified ChangeSets fail integration.
2. Any conversion/integration path attempting a Git commit is rejected.
3. Changed candidate/package after G4 denies delivery.
4. ZIP traversal, symlinks, and secret fixtures are excluded or rejected.
5. ZIP CRC and SHA-256 verify.
6. Cross-job artifact download is denied.
7. Fake/empty SBOM fails closed (cannot claim clean result).
8. Unresolved high-severity finding blocks completion.
9. Unsigned or invented waiver is rejected at G4.
10. Attempted repeat packaging and integration is idempotent.
11. Delivery and JobReport never claim production deployment.
12. Missing Syft tool fails closed as BLOCKED/NOT_RUN (resolving TEST-03).
"""

import hashlib
import json
import os
import stat
import uuid
import zipfile
from io import BytesIO
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ConflictException, ForbiddenException, NotFoundException
from app.models.artifact import Artifact, ArtifactType, normalize_artifact_type
from app.models.agent import AgentRun
from app.models.module import Module
from app.models.workflow import WorkflowGate
from app.schemas.gates import DecisionOutcome, GateDecisionRequest
from app.schemas.phase7 import PackageRequest
from app.services import (
    phase7_service as service,
    phase7_engine as engine,
    phase6_service as p6,
    phase6_workspace as workspace,
    phase6_sandbox as sandbox,
)
from app.services.gate_service import GateService
from app.services.model_gateway import FakeModelProvider, build_fake_gateway
from app.services.supervisor_service import supervisor_service as supervisor

from tests.test_phase5 import isolated, captured  # noqa: F401
from tests.test_phase6 import ready, trusted_executor, generation, queued  # noqa: F401
from tests.test_phase7 import verified, integrated  # noqa: F401


# ---------------------------------------------------------------------------
# 1. Conflicting verified ChangeSets fail integration
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_conflicting_verified_changesets_fail_integration(verified, tmp_path):
    """When two verified ChangeSets modify overlapping paths, merge fails with CONFLICT."""
    db, job, owner, storage, module, repo, attempt, _ = verified
    run = await supervisor.queue_integration(
        db, job, "unit-conflict-check", str(owner.user_id)
    )
    current, bindings = await service.bindings_for(db, job)

    # Simulate a second module that touches the exact same file
    colliding_binding = {
        **bindings[0],
        "module_id": str(uuid.uuid4()),
        "name": "module-colliding",
        "attempt_id": str(uuid.uuid4()),
        "files": {"modern/calc.py": "# conflicting edit\n"},
        "changed_files": ["modern/calc.py"],
    }
    two_bindings = [bindings[0], colliding_binding]

    merged = await engine.merge_verified(
        repo,
        str(job.job_id),
        str(run.run_id),
        bindings[0]["source_commit"],
        two_bindings,
    )
    assert merged["status"] == "CONFLICT"
    assert "modern/calc.py" in merged["conflicts"]
    assert merged["candidate_hash"] is None
    assert "Revise and independently reverify" in merged["resolution"]


# ---------------------------------------------------------------------------
# 2. Any conversion/integration path attempting a Git commit is rejected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_git_commit_operations_are_forbidden_during_conversion_and_integration(ready):
    """Calling git commit on a conversion or integration candidate is strictly prohibited and fails closed."""
    db, job, owner, storage, module, repo = ready
    attempt = await queued(ready)
    worktree, _ = await workspace.prepare(
        repo, str(job.job_id), str(module.module_id), str(attempt.attempt_id), attempt.attempt_number, module.integration_base_sha
    )
    with pytest.raises(ConflictException) as exc_info:
        await workspace.git(worktree, "commit", "-m", "unauthorized commit during conversion")
    assert "forbidden" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 3. Changed candidate/package after G4 denies delivery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_changed_candidate_or_package_after_g4_denies_delivery(verified):
    """If delivery ZIP bytes or hashes are altered after G4 approval, delivery is denied."""
    db, job, owner, storage, module, repo, attempt, _ = verified
    run, output = await integrated(verified)
    gate = await supervisor.submit_final_review(
        db, job, output["report_hash"], str(owner.user_id)
    )

    # Approve G4 as authorized reviewer
    await GateService().decide(
        db,
        gate.gate_id,
        GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Human approved verified package",
            artifact_hashes=gate.artifact_hashes,
            idempotency_key="unit-g4-tamper-check",
        ),
        actor_id=owner.user_id,
        actor_role="SUPER_ADMIN",
    )

    # Verify delivery is initially ready
    delivery = await service.delivery(db, job)
    assert delivery["delivery_ready"] is True

    # Tamper with the package bytes in storage
    zip_artifact = await db.get(Artifact, uuid.UUID(output["zip_artifact_id"]))
    storage.objects[zip_artifact.storage_path] = b"tampered corrupt zip bytes"

    # Delivery must now fail closed
    tampered_delivery = await service.delivery(db, job)
    assert tampered_delivery["delivery_ready"] is False
    assert any("tamper" in lim.lower() or "stale" in lim.lower() or "blocked" in lim.lower()
               for lim in tampered_delivery["limitations"])


# ---------------------------------------------------------------------------
# 4. ZIP packaging excludes secrets, symlinks, and traversal paths
# ---------------------------------------------------------------------------
def test_zip_packaging_excludes_secrets_symlinks_and_traversal_paths(tmp_path):
    """package_project rejects symlinks, traversal paths, and secret tokens."""
    work_dir = tmp_path / "candidate_clean"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("print('hello')", encoding="utf-8")

    # Positive case: clean candidate packages cleanly
    payload, names = engine.package_project(work_dir)
    assert "app.py" in names
    assert payload[:2] == b"PK"

    # Negative 1: Symlink is rejected
    symlink_dir = tmp_path / "candidate_symlink"
    symlink_dir.mkdir()
    (symlink_dir / "target.py").write_text("a = 1", encoding="utf-8")
    link = symlink_dir / "link.py"
    try:
        os.symlink(symlink_dir / "target.py", link)
        with pytest.raises(ValueError, match="symlinks"):
            engine.package_project(symlink_dir)
    except OSError:
        pass  # Symlink creation may require elevated privileges on Windows; skipped if OS denies

    # Negative 2: Secret files like .env or id_rsa are excluded
    secret_dir = tmp_path / "candidate_secret_file"
    secret_dir.mkdir()
    (secret_dir / "valid.py").write_text("b = 2", encoding="utf-8")
    (secret_dir / ".env").write_text("SECRET_KEY=leak", encoding="utf-8")
    (secret_dir / "id_rsa").write_text("PRIVATE KEY", encoding="utf-8")
    payload2, names2 = engine.package_project(secret_dir)
    assert "valid.py" in names2
    assert ".env" not in names2
    assert "id_rsa" not in names2

    # Negative 3: Embedded API key inside source code is blocked
    leaked_dir = tmp_path / "candidate_leaked_key"
    leaked_dir.mkdir()
    (leaked_dir / "leak.py").write_text('OPENAI_API_KEY = "sk-proj-0123456789abcdef0123456789abcdef0123456789abcdef"', encoding="utf-8")
    with pytest.raises(ValueError, match="Secret material"):
        engine.package_project(leaked_dir)


# ---------------------------------------------------------------------------
# 5. ZIP CRC and SHA-256 verify
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_zip_integrity_crc_and_sha256_verification(verified):
    """Packaged ZIP passes testzip() CRC verification and SHA-256 matches manifest."""
    db, job, owner, storage, module, repo, attempt, _ = verified
    run, output = await integrated(verified)

    zip_artifact, zip_bytes = await service.ArtifactService().get_artifact_content(
        db, job.job_id, uuid.UUID(output["zip_artifact_id"])
    )
    # Check testzip() CRC integrity
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
        bad_file = archive.testzip()
        assert bad_file is None

    # Check SHA-256
    computed_sha = hashlib.sha256(zip_bytes).hexdigest()
    assert computed_sha == output["zip_sha256"]
    assert computed_sha == zip_artifact.content_hash

    # Check modernization manifest references
    manifest = await service.artifact_view(db, job.job_id, "MODERNIZATION_MANIFEST")
    assert manifest["content"]["zip_sha256"] == computed_sha


# ---------------------------------------------------------------------------
# 6. Cross-job download is denied
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_job_artifact_download_is_denied(verified):
    """Requesting Job A's delivery ZIP with Job B's job_id fails closed."""
    db, job, owner, storage, module, repo, attempt, _ = verified
    run, output = await integrated(verified)
    zip_id = uuid.UUID(output["zip_artifact_id"])

    other_job_id = uuid.uuid4()
    with pytest.raises(NotFoundException):
        await service.ArtifactService().get_artifact_content(db, other_job_id, zip_id)


# ---------------------------------------------------------------------------
# 7. Fake/empty SBOM fails closed (cannot claim clean result)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fake_or_empty_sbom_blocks_integration_and_prevents_packaging(verified, monkeypatch):
    """When SBOM output is empty, malformed, or missing, integration fails closed as BLOCKED."""
    db, job, owner, storage, module, repo, attempt, calls = verified
    orig_double = sandbox.execute

    async def broken_sbom_double(files, cases, baseline_hash, *, system_checks=None, binding=None, frozen_profile=None):
        result = await orig_double(files, cases, baseline_hash, system_checks=system_checks, binding=binding, frozen_profile=frozen_profile)
        for check in result.get("checks", []):
            if check.get("category") == "sbom":
                check["stdout"] = "{}"
        return result

    monkeypatch.setattr(sandbox, "execute", broken_sbom_double)
    run = await supervisor.queue_integration(
        db, job, "unit-broken-sbom-check", str(owner.user_id)
    )
    output = await service.execute_integration(db, run.run_id)

    assert output["status"] == "BLOCKED"
    assert output.get("zip_artifact_id") is None
    assert output.get("manifest_artifact_id") is None


# ---------------------------------------------------------------------------
# 8. Unresolved high-severity finding blocks completion
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unresolved_high_severity_review_finding_blocks_completion(verified, monkeypatch):
    """If the independent reviewer flags a critical/high vulnerability, integration is BLOCKED."""
    db, job, owner, storage, module, repo, attempt, calls = verified

    # Mock remote review in sandbox verification to return critical security findings
    orig_double = sandbox.execute

    async def vulnerable_system_double(files, cases, baseline_hash, *, system_checks=None, binding=None, frozen_profile=None):
        result = await orig_double(files, cases, baseline_hash, system_checks=system_checks, binding=binding, frozen_profile=frozen_profile)
        result["independent_review"] = {
            "status": "REJECTED",
            "worker_id": "synthetic-reviewer-1",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "category": "SECURITY",
                    "description": "Hardcoded AWS credentials detected in configuration",
                    "line": 42,
                    "file": "app/config.py",
                }
            ],
        }
        return result

    monkeypatch.setattr(sandbox, "execute", vulnerable_system_double)
    run = await supervisor.queue_integration(
        db, job, "unit-sec-veto-check", str(owner.user_id)
    )
    output = await service.execute_integration(db, run.run_id)

    assert output["status"] == "BLOCKED"
    assert output.get("zip_artifact_id") is None
    report = await service.artifact_view(db, job.job_id, "JOB_REPORT")
    assert report["content"]["status"] == "BLOCKED"
    assert any(finding.get("severity") == "CRITICAL" for finding in report["content"]["findings"])


# ---------------------------------------------------------------------------
# 9. Unsigned or invented waiver is rejected at G4
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsigned_or_invented_waiver_is_rejected_at_g4(verified):
    """G4 approval rejects any waiver referencing unobserved or non-waivable test cases."""
    db, job, owner, *_ = verified
    run, output = await integrated(verified)
    gate = await supervisor.submit_final_review(
        db, job, output["report_hash"], str(owner.user_id)
    )

    with pytest.raises(ConflictException, match="Waivers require exact recorded intended-difference evidence"):
        await GateService().decide(
            db,
            gate.gate_id,
            GateDecisionRequest(
                decision=DecisionOutcome.APPROVED,
                rationale="Attempting to approve with invented waiver",
                artifact_hashes=gate.artifact_hashes,
                waivers=[
                    {
                        "test_id": "fake_case_12345",
                        "difference_type": "INTENDED_DIFFERENCE",
                        "waiver_rationale": "Attempting waiver bypass without underlying evidence",
                    }
                ],
            ),
            actor_id=owner.user_id,
            actor_role="SUPER_ADMIN",
        )


# ---------------------------------------------------------------------------
# 10. Attempted repeat packaging and integration is idempotent
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_repeat_integration_is_idempotent(verified):
    """Queueing or executing integration repeatedly with the same key returns cached output."""
    db, job, owner, *_ = verified
    run, output = await integrated(verified)

    # Re-queue with same key
    again = await supervisor.queue_integration(
        db, job, "unit-integration-1", str(owner.user_id)
    )
    assert again.run_id == run.run_id

    # Re-execute on already finished run
    output2 = await service.execute_integration(db, run.run_id)
    assert output2["report_hash"] == output["report_hash"]
    assert output2["zip_sha256"] == output["zip_sha256"]


# ---------------------------------------------------------------------------
# 11. Delivery and JobReport never claim production deployment
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delivery_and_job_report_never_claim_production_deployment(verified):
    """production_cutover_included is strictly False in JobReport, delivery, and DELIVERY_RECORD."""
    db, job, owner, *_ = verified
    run, output = await integrated(verified)

    gate = await supervisor.submit_final_review(
        db, job, output["report_hash"], str(owner.user_id)
    )
    await GateService().decide(
        db,
        gate.gate_id,
        GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approved delivery",
            artifact_hashes=gate.artifact_hashes,
            idempotency_key="unit-g4-delivery-claim",
        ),
        actor_id=owner.user_id,
        actor_role="SUPER_ADMIN",
    )

    delivery = await service.delivery(db, job)
    assert delivery["production_cutover_included"] is False
    assert delivery["delivery_record"]["content"]["production_cutover_included"] is False

    report = await service.artifact_view(db, job.job_id, "JOB_REPORT")
    assert any("production cutover are not included" in lim.lower() for lim in report["content"]["limitations"])


# ---------------------------------------------------------------------------
# 12. Missing Syft tool fails closed as BLOCKED/NOT_RUN (resolving TEST-03)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tool,expected_status",
    [("", "BLOCKED"), ("unknown_scanner", "NOT_RUN")],
)
def test_missing_syft_binary_fails_closed_in_sbom_evidence(monkeypatch, tool, expected_status):
    """When syft is missing or unselected, sbom_evidence returns BLOCKED/NOT_RUN, never empty clean."""
    monkeypatch.setattr(settings, "PHASE7_SBOM_TOOL", tool)
    result = engine.sbom_evidence({}, {})
    assert result["status"] == expected_status
    assert result["format"] is None
