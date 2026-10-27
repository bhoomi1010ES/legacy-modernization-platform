"""Phase 7 invariants: real isolated Git with labeled model/container unit doubles."""

import json
from types import SimpleNamespace
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ConflictException, ForbiddenException
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.test_case import TestResult as Result
from app.models.workflow import WorkflowGate
from app.schemas.gates import DecisionOutcome, GateDecisionRequest
from app.schemas.phase7 import PackageRequest
from app.services import phase7_service as service, phase7_engine as engine
from app.services import (
    phase6_service as p6,
    phase6_workspace as workspace,
    phase6_sandbox as sandbox,
)
from app.services.gate_service import GateService
from app.services.model_gateway import FakeModelProvider, build_fake_gateway
from app.services.supervisor_service import supervisor_service as supervisor
from test_phase5 import isolated  # noqa: F401 -- imported pytest fixture
from test_phase6 import ready, trusted_executor, generation, queued  # noqa: F401


@pytest_asyncio.fixture
async def verified(ready, trusted_executor, monkeypatch, tmp_path):  # noqa: F811
    db, job, owner, storage, module, repo = ready
    attempt = await queued(ready)
    await p6.execute_attempt(
        db,
        attempt.attempt_id,
        gateway=build_fake_gateway(FakeModelProvider([generation()])),
    )
    assert attempt.status == "VERIFIED"
    monkeypatch.setattr(engine, "ROOT", tmp_path / "integration")
    monkeypatch.setattr(settings, "PHASE7_SBOM_TOOL", "syft")
    monkeypatch.setattr(settings, "PHASE7_PR_PROVIDER", "")
    specs = [
        {"category": category, "command": ["python", "-m", "compileall", "-q", "."]}
        for category in ("build", "unit", "integration", "static", "security", "schema")
    ]
    monkeypatch.setattr(settings, "PHASE7_CHECK_COMMANDS_JSON", json.dumps(specs))
    calls = []

    async def system_double(files, cases, baseline_hash, *, system_checks=None):
        """Labeled container double: no real-system or real-model acceptance claim."""
        calls.append((files, cases, system_checks))
        checks = [
            {
                **spec,
                "status": "PASS",
                "exit_code": 0,
                "duration_ms": 1.0,
                "stdout": "",
                "stderr": "",
                "artifact_hash": "c" * 64,
            }
            for spec in system_checks
        ]
        for check in checks:
            if check["command"] == ["syft", "version", "-o", "json"]:
                check["stdout"] = json.dumps({"version": "unit-syft-1"})
            if check["command"] == ["syft", "scan", "dir:/work", "-o", "syft-json"]:
                check["stdout"] = json.dumps(
                    {
                        "descriptor": {"name": "syft", "version": "unit-syft-1"},
                        "artifacts": [{"name": "unit-fixture", "version": "1"}],
                    }
                )
        return {
            "available": True,
            "passed": True,
            "checks": checks,
            "cases": [
                {
                    "test_case_id": case["test_case_id"],
                    "status": "PASS",
                    "actual": {
                        "output": case["expected"],
                        "side_effects": case["side_effects"],
                    },
                    "command": ["python", "/adapter.py"],
                    "exit_code": 0,
                    "duration_ms": 1.0,
                    "artifact_hash": "c" * 64,
                }
                for case in cases
            ],
            "artifact_hash": "c" * 64,
            "source_unchanged": True,
            "image_id": "sha256:" + "d" * 64,
            "container_name": "labeled-unit-double",
        }

    monkeypatch.setattr(sandbox, "execute", system_double)
    return db, job, owner, storage, module, repo, attempt, calls


async def integrated(verified):
    db, job, owner, *_ = verified
    run = await supervisor.queue_integration(
        db, job, "unit-integration-1", str(owner.user_id)
    )
    output = await service.execute_integration(db, run.run_id)
    assert output["status"] == "READY_FOR_REVIEW", output
    return run, output


@pytest.mark.asyncio
async def test_integration_real_git_exact_commit_report_counts_and_history(verified):
    db, job, owner, storage, module, repo, attempt, calls = verified
    run, output = await integrated(verified)
    assert len(calls) == 1 and {check["category"] for check in calls[0][2]} >= {
        "build",
        "unit",
        "integration",
        "static",
        "security",
        "schema",
        "sbom",
    }
    assert (
        await workspace.git(
            repo,
            "merge-base",
            "--is-ancestor",
            (await p6.detail(db, attempt))["evidence"]["commit"],
            output["commit"],
        )
        == ""
    )
    report = await service.artifact_view(db, job.job_id, "JOB_REPORT")
    assert report["content"]["integrated_commit"] == output["commit"]
    assert report["content"]["counts"] == {
        "total": 1,
        "executed": 1,
        "passed": 1,
        "failed": 0,
        "unobserved": 0,
    }
    assert module.status == "VERIFIED" and job.status == "INTEGRATING"
    assert (
        await db.scalar(
            select(WorkflowGate).where(
                WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G4"
            )
        )
        is None
    )
    again = await supervisor.queue_integration(
        db, job, "unit-integration-1", str(owner.user_id)
    )
    assert again.run_id == run.run_id
    assert (await service.execute_integration(db, run.run_id))["report_hash"] == output[
        "report_hash"
    ]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_g4_exact_human_approval_and_immutable_delivery(verified):
    db, job, owner, *_ = verified
    run, output = await integrated(verified)
    gate = await supervisor.submit_final_review(
        db, job, output["report_hash"], str(owner.user_id)
    )
    assert (
        gate.status == "PENDING"
        and not (await service.delivery(db, job))["delivery_ready"]
    )
    with pytest.raises(ForbiddenException):
        await GateService().decide(
            db,
            gate.gate_id,
            GateDecisionRequest(
                decision=DecisionOutcome.APPROVED,
                rationale="Developer cannot approve delivery",
                artifact_hashes=gate.artifact_hashes,
            ),
            actor_id=owner.user_id,
            actor_role="DEVELOPER",
        )
    decision, _, _, _ = await GateService().decide(
        db,
        gate.gate_id,
        GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Human reviewed exact commit, real evidence in unit fixture and SBOM limitations",
            artifact_hashes=gate.artifact_hashes,
            idempotency_key="unit-approved-g4",
        ),
        actor_id=owner.user_id,
        actor_role="SUPER_ADMIN",
    )
    delivery = await service.delivery(db, job)
    assert job.status == "COMPLETED" and delivery["delivery_ready"]
    assert delivery["delivery_record"]["content"]["commit"] == output["commit"]
    assert (
        delivery["delivery_record"]["content"]["delivered_at"]
        == decision.decided_at.isoformat()
    )
    assert delivery["production_cutover_included"] is False


@pytest.mark.asyncio
async def test_rejection_invalidates_system_results_requires_fresh_version(verified):
    db, job, owner, *_ = verified
    run, output = await integrated(verified)
    gate = await supervisor.submit_final_review(
        db, job, output["report_hash"], str(owner.user_id)
    )
    await GateService().decide(
        db,
        gate.gate_id,
        GateDecisionRequest(
            decision=DecisionOutcome.REJECTED,
            rationale="Human requires fresh integration verification",
            artifact_hashes=gate.artifact_hashes,
        ),
        actor_id=owner.user_id,
        actor_role="SUPER_ADMIN",
    )
    assert job.status == "CONVERTING"
    with pytest.raises(ConflictException):
        await service.validate_package(db, job, output["report_hash"])
    new = await supervisor.queue_integration(
        db, job, "unit-integration-revised", str(owner.user_id)
    )
    revised = await service.execute_integration(db, new.run_id)
    assert revised["status"] == "READY_FOR_REVIEW" and revised["report_version"] == 2
    assert (await service.artifact_view(db, job.job_id, "JOB_REPORT", 1))[
        "content_hash"
    ] == output["report_hash"]


@pytest.mark.parametrize("kind", ["JOB_REPORT", "SBOM", "SYSTEM_VERIFICATION"])
@pytest.mark.asyncio
async def test_final_package_tamper_blocks_g4(verified, kind):
    db, job, owner, storage, *_ = verified
    _, output = await integrated(verified)
    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.job_id == job.job_id, Artifact.artifact_type == kind
        )
    )
    storage.objects[artifact.storage_path] = b"tampered"
    with pytest.raises(ConflictException):
        await supervisor.submit_final_review(
            db, job, output["report_hash"], str(owner.user_id)
        )


@pytest.mark.asyncio
async def test_moved_integration_branch_and_stale_report_blocked(verified):
    db, job, owner, _, _, repo, *_ = verified
    _, output = await integrated(verified)
    with pytest.raises(ConflictException):
        await supervisor.submit_final_review(db, job, "0" * 64, str(owner.user_id))
    base = (await service.artifact_view(db, job.job_id, "JOB_REPORT"))["content"][
        "source_commit"
    ]
    await workspace.git(repo, "update-ref", "refs/heads/" + output["branch"], base)
    with pytest.raises(ConflictException):
        await service.validate_package(db, job, output["report_hash"])


@pytest.mark.asyncio
async def test_unknown_waiver_cannot_override_checks(verified):
    db, job, owner, *_ = verified
    _, output = await integrated(verified)
    gate = await supervisor.submit_final_review(
        db, job, output["report_hash"], str(owner.user_id)
    )
    with pytest.raises(ConflictException):
        await GateService().decide(
            db,
            gate.gate_id,
            GateDecisionRequest(
                decision=DecisionOutcome.APPROVED,
                rationale="Cannot invent missing execution waiver",
                artifact_hashes=gate.artifact_hashes,
                waivers=[
                    {
                        "test_id": "invented",
                        "difference_type": "INTENDED_DIFFERENCE",
                        "waiver_rationale": "Invented evidence is never approval",
                    }
                ],
            ),
            actor_id=owner.user_id,
            actor_role="SUPER_ADMIN",
        )
    assert gate.status == "PENDING" and job.status == "AWAITING_GATE_G4"


@pytest.mark.asyncio
async def test_manual_handoff_not_fake_pr_and_idempotent(verified):
    db, job, owner, *_ = verified
    _, output = await integrated(verified)
    request = PackageRequest(
        idempotency_key="unit-manual-pr", report_hash=output["report_hash"]
    )
    result = await service.pull_request(db, job, request, str(owner.user_id))
    assert result["status"] == "MANUAL_REQUIRED" and not result.get("url")
    assert await service.pull_request(db, job, request, str(owner.user_id)) == result


def test_dependency_order_rejects_missing_and_cyclic_contracts():
    a = SimpleNamespace(module_id="a", name="a", dependency_module_ids=[])
    b = SimpleNamespace(module_id="b", name="b", dependency_module_ids=["a"])
    units = [
        {"module_id": "b", "dependencies": ["a"]},
        {"module_id": "a", "dependencies": []},
    ]
    assert engine.dependency_order(units, [b, a]) == [a, b]
    with pytest.raises(ConflictException):
        engine.dependency_order(
            [{**units[0], "dependencies": ["missing"]}, units[1]], [a, b]
        )
    a.dependency_module_ids = ["b"]
    with pytest.raises(ConflictException):
        engine.dependency_order(
            [units[0], {"module_id": "a", "dependencies": ["b"]}], [a, b]
        )


@pytest.mark.parametrize(
    "tool,status",
    [("", "UNAVAILABLE"), ("unknown", "UNSUPPORTED"), ("syft", "UNAVAILABLE")],
)
def test_sbom_unavailable_or_unsupported_never_claims_standard(
    monkeypatch, tool, status
):
    monkeypatch.setattr(settings, "PHASE7_SBOM_TOOL", tool)
    result = engine.sbom_evidence({}, {})
    assert result["status"] == status and result["format"] is None
