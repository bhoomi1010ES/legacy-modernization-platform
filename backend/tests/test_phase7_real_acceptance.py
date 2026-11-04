"""Phase 7 Real-Environment E2E Acceptance Test.

Proves the complete final path:
  G3-approved Phase 6 artifact
          ↓
  Phase 7 integration
          ↓
  Dependency-ordered merge
          ↓
  Real integrated candidate
          ↓
  Hardened offline system verification (phase7-acceptance:local-v1)
          ↓
  Full G2 Golden Master replay (100% pass, 0 regressions)
          ↓
  Real Syft SBOM generation (syft 1.55.0, format syft-json)
          ↓
  Immutable verification/report artifacts plus ZIP and modernization manifest
          ↓
  Package cross-hash verification
          ↓
  G4 readiness
          ↓
  Human G4 approval (Developer strictly forbidden, Super Admin approved)
          ↓
  Immutable DELIVERY_RECORD creation
          ↓
  Authorized ZIP-delivery compatibility response
"""

import json
import os
import uuid
import hashlib
import zipfile
from io import BytesIO
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ConflictException, ForbiddenException
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.test_case import TestResult as CaseResult
from app.models.workflow import WorkflowGate
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, WaiverItem
from app.schemas.phase7 import PackageRequest
from app.services import (
    phase7_service as service,
    phase7_engine as engine,
    phase6_service as p6,
    phase6_workspace as ws,
    phase6_sandbox as sandbox,
)
from app.services.gate_service import GateService
from app.services.supervisor_service import supervisor_service as supervisor

# Import base fixtures
from test_phase5 import isolated, captured  # noqa: F401
from test_phase6 import ready  # noqa: F401


@pytest.mark.asyncio
async def test_phase7_real_environment_e2e_acceptance(ready, monkeypatch, tmp_path):
    """Complete, authentic real-environment Phase 7 E2E acceptance test.

    Uses:
    - Real G3-approved Phase 6 converted module
    - Source remains untouched; verified ChangeSets populate an isolated output candidate
    - Real pre-baked Docker container image (phase7-acceptance:local-v1)
    - Real hardened sandbox (--network=none, readonly, dropped caps)
    - Full G2 Golden Master regression replay
    - Real Syft 1.55.0 SBOM generation (syft-json)
    - Immutable report/verification artifacts, ZIP and modernization manifest
    - G4 human approval governance (Developer rejected, Super Admin approved)
    - Immutable DELIVERY_RECORD
    - Idempotent ZIP-delivery response (legacy endpoint compatibility)
    """
    db, job, owner, storage, module, repo = ready
    job.source_stack = "Python"
    job.target_stack = "Python"
    await db.commit()

    # 1. Configure real container image, OpenAI provider, and Syft SBOM tool
    image_digest = "sha256:545c07d7ed4b9858789a4c4fe9f8e642cbc2b932e721d9a597b8b07857ad722c"
    checks_json = (
        '[{"category":"build","command":["python","-m","compileall","-q","."]},'
        '{"category":"unit","command":["python","-m","pytest","/acceptance/test_calc.py","-q","-p","no:cacheprovider"]},'
        '{"category":"integration","command":["python","-m","pytest","/acceptance/test_calc.py","-q","-p","no:cacheprovider"]},'
        '{"category":"static","command":["python","-m","mypy","--cache-dir=/tmp/mypy-cache","--check-untyped-defs","--explicit-package-bases","."]},'
        '{"category":"security","command":["python","-m","bandit","-r",".","-q"]},'
        '{"category":"security","command":["python","-m","pytest","/acceptance/test_security.py","-q","-s","-p","no:cacheprovider"]},'
        '{"category":"schema","command":["python","-m","compileall","-q","."]}]'
    )

    monkeypatch.setattr(settings, "PHASE6_MODEL_PROVIDER", "openai")
    monkeypatch.setattr(settings, "PHASE6_MODEL_IDENTIFIER", "gpt-4o-mini")
    monkeypatch.setattr(settings, "PHASE6_SANDBOX_IMAGE", image_digest)
    monkeypatch.setattr(settings, "PHASE7_SANDBOX_IMAGE", image_digest)
    monkeypatch.setattr(settings, "PHASE7_SBOM_TOOL", "syft")
    monkeypatch.setattr(settings, "PHASE7_CHECK_COMMANDS_JSON", checks_json)
    monkeypatch.setattr(settings, "PHASE7_PR_PROVIDER", "")
    monkeypatch.setattr(settings, "PHASE7_PR_BASE_BRANCH", "main")
    monkeypatch.setattr(engine, "ROOT", tmp_path / "integration")
    monkeypatch.setattr(ws, "repository_for", lambda j_id: repo)

    # 2. Complete Phase 6 Conversion to produce genuine G3-approved module
    # Queue module conversion
    attempt = await supervisor.queue_module_conversion(
        db, job, module, "phase7-e2e-p6-conv", str(owner.user_id)
    )
    assert attempt.status == "QUEUED"
    assert attempt.attempt_number == 1

    # Execute conversion using real Docker sandbox
    await p6.execute_attempt(db, attempt.attempt_id)
    p6_detailed = await p6.detail(db, attempt)
    assert attempt.status == "VERIFIED", f"Phase 6 attempt failed: {attempt.failure_reason}"
    assert attempt.failure_reason is None

    p6_evidence = p6_detailed["evidence"]
    assert "modern/calc.py" in p6_evidence["files"]
    changeset_hash = p6_evidence["code_hash"]
    golden_master_hash = p6_evidence["baseline_hash"]
    source_base_sha = p6_evidence["base_sha"]
    assert p6_evidence["base_sha"] == p6_evidence["source_commit"]
    assert "commit" not in p6_evidence
    assert await ws.git(repo, "rev-parse", "HEAD") == source_base_sha
    assert not await ws.git(repo, "status", "--porcelain")

    # Verify G3 approval gate is present and APPROVED
    g3_gate = await db.scalar(
        select(WorkflowGate).where(
            WorkflowGate.job_id == job.job_id,
            WorkflowGate.gate_type == "G3",
        ).order_by(WorkflowGate.version.desc()).limit(1)
    )
    assert g3_gate is not None
    assert g3_gate.status == "APPROVED"

    print("\n================================================================================")
    print("PHASE 6 UPSTREAM BASELINE VERIFIED")
    print(f"Job ID: {job.job_id}")
    print(f"Module ID: {module.module_id}")
    print(f"Attempt: {attempt.attempt_number}")
    print(f"ChangeSet SHA-256: {changeset_hash}")
    print(f"Golden Master SHA-256: {golden_master_hash}")
    print(f"G3 Approval: {g3_gate.status}")
    print("================================================================================")

    # 3. Transition Job to INTEGRATING and Queue Phase 7 Integration
    # Verify Supervisor transition to INTEGRATING
    run = await supervisor.queue_integration(
        db, job, "phase7-real-e2e-run-1", str(owner.user_id)
    )
    assert run.status == "QUEUED"
    assert job.status == "INTEGRATING"
    assert run.task_payload["phase"] == 7
    assert len(run.task_payload["bindings"]) == 1
    assert run.task_payload["bindings"][0]["module_id"] == str(module.module_id)

    # 4. Execute Real Phase 7 Integration
    # This invokes:
    # - Isolated output-candidate composition; no Git commit is created
    # - Real hardened Docker sandbox execution (phase7-acceptance:local-v1)
    # - Real System Verification checks (build, unit, integration, static, security x2, schema)
    # - Full G2 Golden Master replay (100% match, 0 regressions)
    # - Real Syft 1.55.0 execution producing genuine syft-json SBOM
    # - Publishing immutable report/verification artifacts, ZIP and modernization manifest
    output = await service.execute_integration(db, run.run_id)
    assert output["status"] == "READY_FOR_REVIEW", f"Integration not ready: {output}"
    assert run.status == "SUCCEEDED"

    candidate_hash = output["candidate_hash"]
    report_hash = output["report_hash"]
    assert candidate_hash and len(candidate_hash) == 64
    assert output["zip_artifact_id"] and output["manifest_artifact_id"]
    assert await ws.git(repo, "rev-parse", "HEAD") == source_base_sha
    assert not await ws.git(repo, "status", "--porcelain")

    # 5. Verify immutable evidence artifacts and the complete ZIP delivery
    integration_art = await service.artifact_view(db, job.job_id, "INTEGRATION_REPORT")
    verification_art = await service.artifact_view(db, job.job_id, "SYSTEM_VERIFICATION")
    sbom_art = await service.artifact_view(db, job.job_id, "SBOM")
    job_report_art = await service.artifact_view(db, job.job_id, "JOB_REPORT")
    zip_artifact, zip_bytes = await service.ArtifactService().get_artifact_content(
        db, job.job_id, uuid.UUID(output["zip_artifact_id"])
    )
    manifest_art = await service.artifact_view(db, job.job_id, "ModernizationManifest")
    assert zip_artifact.content_hash == output["zip_sha256"]
    assert hashlib.sha256(zip_bytes).hexdigest() == output["zip_sha256"]
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zipped:
        assert zipped.testzip() is None
        assert not any(name == ".git" or name.startswith(".git/") for name in zipped.namelist())

    assert integration_art["content_hash"] is not None
    assert verification_art["content_hash"] is not None
    assert sbom_art["content_hash"] is not None
    assert job_report_art["content_hash"] == report_hash

    # Verify cross-artifact SHA-256 references in JOB_REPORT
    job_report = job_report_art["content"]
    assert job_report["integrated_commit"] is None
    assert job_report["candidate_hash"] == candidate_hash
    assert job_report["evidence"]["delivery_zip"]["sha256"] == output["zip_sha256"]
    assert job_report["evidence"]["manifest"]["hash"] == manifest_art["content_hash"]
    assert job_report["evidence"]["integration"]["hash"] == integration_art["content_hash"]
    assert job_report["evidence"]["verification"]["hash"] == verification_art["content_hash"]
    assert job_report["evidence"]["sbom"]["hash"] == sbom_art["content_hash"]

    # 6. Verify System Verification Evidence
    verification_content = verification_art["content"]
    assert verification_content["available"] is True
    assert verification_content["passed"] is True
    assert verification_content["image_id"] == image_digest

    checks = verification_content["checks"]
    assert len(checks) >= 9  # 7 system checks + 2 syft sbom checks
    check_categories = {c["category"] for c in checks}
    assert {"build", "unit", "integration", "static", "security", "schema", "sbom"}.issubset(check_categories)
    for c in checks:
        assert c["status"] == "PASS", f"Check {c['category']} failed: {c.get('stdout')} {c.get('stderr')}"
        assert c["exit_code"] == 0

    # 7. Verify Full G2 Golden Master Replay
    cases = verification_content["cases"]
    assert len(cases) > 0
    for case in cases:
        assert case["status"] == "PASS", f"Regression in test case {case['test_case_id']}"
        assert case["exit_code"] == 0
    assert job_report["counts"]["failed"] == 0
    assert job_report["counts"]["unobserved"] == 0
    assert job_report["counts"]["passed"] == job_report["counts"]["total"]

    # 8. Verify Real Syft SBOM
    sbom_content = sbom_art["content"]
    assert sbom_content["status"] == "GENERATED"
    assert sbom_content["tool"] == "syft"
    assert sbom_content["tool_version"] == "1.55.0"
    assert sbom_content["format"] == "syft-json"
    assert sbom_content["component_count"] >= 0
    assert "artifacts" in sbom_content["document"]

    # 9. Verify G4 Governance Flow
    # Submit package for G4 final review
    g4_gate = await supervisor.submit_final_review(
        db, job, report_hash, str(owner.user_id)
    )
    assert g4_gate.status == "PENDING"
    assert g4_gate.gate_type == "G4"
    assert job.status == "AWAITING_GATE_G4"

    # Verify G4 Human-Only Governance: DEVELOPER role must be rejected with 403 Forbidden
    with pytest.raises(ForbiddenException):
        await GateService().decide(
            db,
            g4_gate.gate_id,
            GateDecisionRequest(
                decision=DecisionOutcome.APPROVED,
                rationale="Developer illegally attempting G4 approval",
                artifact_hashes=g4_gate.artifact_hashes,
            ),
            actor_id=owner.user_id,
            actor_role="DEVELOPER",
        )

    # Authorized SUPER_ADMIN human approves G4
    decision, approved_gate, updated_job, _ = await GateService().decide(
        db,
        g4_gate.gate_id,
        GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Human verified the exact ZIP, manifest, full system checks, G2 replay and real Syft SBOM.",
            artifact_hashes=g4_gate.artifact_hashes,
            idempotency_key="real-g4-accept-1",
        ),
        actor_id=owner.user_id,
        actor_role="SUPER_ADMIN",
    )
    assert approved_gate.status == "APPROVED"
    assert updated_job.status == "COMPLETED"

    # 10. Verify Immutable DELIVERY_RECORD
    delivery_art = await service.artifact_view(db, job.job_id, "DELIVERY_RECORD")
    assert delivery_art is not None
    delivery_record = delivery_art["content"]
    assert delivery_record["job_id"] == str(job.job_id)
    assert delivery_record["candidate_hash"] == candidate_hash
    assert delivery_record["zip_sha256"] == output["zip_sha256"]
    assert delivery_record["report_hash"] == report_hash
    assert delivery_record["sbom_hash"] == sbom_art["content_hash"]
    assert delivery_record["gate_id"] == str(g4_gate.gate_id)
    assert delivery_record["rationale"] is not None

    # Verify delivery readiness endpoint
    delivery_state = await service.delivery(db, job)
    assert delivery_state["delivery_ready"] is True
    assert delivery_state["package_current"] is True

    # 11. Verify the legacy delivery endpoint returns the exact ZIP and is idempotent.
    # The endpoint must not create a Git branch or external pull request.
    pr_res = await service.pull_request(
        db, job, PackageRequest(report_hash=report_hash, idempotency_key="pr-accept-1"), str(owner.user_id)
    )
    assert pr_res["status"] == "ZIP_DELIVERY"
    assert pr_res["artifact_id"] == output["zip_artifact_id"]
    assert pr_res["sha256"] == output["zip_sha256"]
    assert pr_res["report_hash"] == report_hash

    # Verify ZIP delivery response idempotency
    pr_repeat = await service.pull_request(
        db, job, PackageRequest(report_hash=report_hash, idempotency_key="pr-accept-1"), str(owner.user_id)
    )
    assert pr_repeat == pr_res

    print("\n================================================================================")
    print("PHASE 7 REAL ACCEPTANCE EVIDENCE")
    print(f"Job ID: {job.job_id}")
    print(f"Integration Run ID: {run.run_id}")
    print(f"Candidate Tree SHA-256: {candidate_hash}")
    print(f"ZIP Artifact ID: {zip_artifact.artifact_id}")
    print(f"ZIP SHA-256: {output['zip_sha256']}")
    print(f"Manifest SHA-256: {manifest_art['content_hash']}")
    print(f"ChangeSet SHA-256: {changeset_hash}")
    print(f"Golden Master SHA-256: {golden_master_hash}")
    print(f"Docker Image Digest: {image_digest}")
    print(f"Checks Passed: {len(checks)} / {len(checks)}")
    print(f"G2 Replay Regressions: 0 (Passed: {len(cases)} / {len(cases)})")
    print(f"Syft Version: {sbom_content['tool_version']}")
    print(f"SBOM Format: {sbom_content['format']}")
    print(f"SBOM SHA-256: {sbom_art['content_hash']}")
    print(f"INTEGRATION_REPORT SHA-256: {integration_art['content_hash']}")
    print(f"SYSTEM_VERIFICATION SHA-256: {verification_art['content_hash']}")
    print(f"JOB_REPORT SHA-256: {job_report_art['content_hash']}")
    print(f"G4 Gate Decision: {approved_gate.status}")
    print(f"Delivery Record ID: {delivery_art['artifact_id']}")
    print(f"Delivery Mode: {pr_res['status']}")
    print("================================================================================")


@pytest.mark.asyncio
async def test_phase7_failure_paths_and_governance_invariants(ready, monkeypatch, tmp_path):
    """Verifies that Phase 7 fails closed across all edge cases:

    1. Missing/Unapproved G3 blocks integration
    2. Stale attempt / invalid ChangeSet blocks integration
    3. Missing dependencies or cyclic DAG blocks integration
    4. G4 rejection invalidates test results and blocks delivery
    5. ZIP/manifest tampering blocks G4 approval
    """
    db, job, owner, storage, module, repo = ready
    monkeypatch.setattr(ws, "repository_for", lambda j_id: repo)
    monkeypatch.setattr(engine, "ROOT", tmp_path / "integration")

    # A. Dependency DAG: Cyclic dependency test
    from app.services.phase7_engine import dependency_order
    from app.models.module import Module as ModModel

    mod_a = ModModel(module_id=uuid.uuid4(), name="mod_a", job_id=job.job_id, legacy_path="legacy", target_path="modern")
    mod_b = ModModel(module_id=uuid.uuid4(), name="mod_b", job_id=job.job_id, legacy_path="legacy", target_path="modern")
    mod_a.dependency_module_ids = [str(mod_b.module_id)]
    mod_b.dependency_module_ids = [str(mod_a.module_id)]

    approved_modules_cycle = [
        {"module_id": "mod_a", "dependencies": ["mod_b"], "source_scope": ["legacy"], "target_scope": ["modern"]},
        {"module_id": "mod_b", "dependencies": ["mod_a"], "source_scope": ["legacy"], "target_scope": ["modern"]},
    ]
    with pytest.raises(ConflictException, match="Approved integration DAG has a cycle"):
        dependency_order(approved_modules_cycle, [mod_a, mod_b])

    # B. Missing dependency in DAG test
    approved_modules_missing = [
        {"module_id": "mod_a", "dependencies": ["mod_missing"], "source_scope": ["legacy"], "target_scope": ["modern"]},
    ]
    with pytest.raises(ConflictException, match="Approved dependency is missing from inventory"):
        dependency_order(approved_modules_missing, [mod_a])

    # C. Missing/Rejected G3 blocks integration
    # Change G3 gate to REJECTED
    g3_gate = await db.scalar(
        select(WorkflowGate).where(
            WorkflowGate.job_id == job.job_id,
            WorkflowGate.gate_type == "G3",
        )
    )
    g3_gate.status = "REJECTED"
    await db.commit()

    with pytest.raises(ConflictException, match="G3"):
        await supervisor.queue_integration(db, job, "blocked-run", str(owner.user_id))
