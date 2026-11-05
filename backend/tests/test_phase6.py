"""Phase 6 acceptance invariants. Scripted model/container doubles are never real Docker acceptance."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from sqlalchemy import select
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from app.core.config import settings
from app.core.errors import ConflictException, PlatformException
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.job import Job, JobMembership
from app.models.module import Module, ModuleAttempt, VerificationRun
from app.models.phase4 import (
    ConversionPlanModel,
    ConversionPlanModuleModel,
    RepositorySnapshotModel,
)
from app.models.test_case import TestResult as Result
from app.models.workflow import WorkflowGate
from app.models.user import User
from app.schemas.gates import DecisionOutcome, GateDecisionRequest
from app.schemas.phase5 import FreezeRequest, ValidationRequest
from app.schemas.phase6 import ChangeSet, QueueConversion
from app.services import (
    phase5_service as p5,
    phase6_service as service,
    phase6_workspace as ws,
    phase6_sandbox as sandbox,
)
from app.services.verifier_agent import verifier_service, VerificationVerdict
from app.services.reviewer_agent import review
from app.services.repository_workspace_service import RepositoryWorkspaceService
from app.services.model_gateway import FakeModelProvider, build_fake_gateway
from app.services.supervisor_service import supervisor_service as supervisor
from app.services.gate_service import GateService
from app.services.artifact_service import ArtifactService
from test_phase5 import isolated, captured  # noqa: F401 -- reuse the registered fixture


def generation(value=3, **extra):
    return {
        "action": "final",
        "output": {
            "files": {"modern/calc.py": f"def add(x, y):\n    return {value}\n"},
            "design_notes": "Preserve approved addition scenario",
            "assumptions": ["Fixture scope"],
            "test_commands": [],
            **extra,
        },
        "usage": {"input_tokens": 20, "output_tokens": 30, "cost_usd": 0},
    }


def synthetic_target_profile():
    checks=[
        {"category":"build","command":["python","-m","compileall","-q","."]},
        {"category":"unit","command":["python","-m","pytest","-q","tests/unit"]},
        {"category":"integration","command":["python","-m","pytest","-q","tests/integration"]},
        {"category":"static","command":["python","-m","mypy","app"]},
        {"category":"security","command":["python","-m","bandit","-r","app"]},
        {"category":"dependency","command":["pip-audit","--strict"]},
        {"category":"license","command":["licensecheck","--fail-on","GPL"]},
        {"category":"runtime","command":["python","-m","pytest","-q","tests/runtime"]},
        {"category":"api_compatibility","command":["python","-m","pytest","-q","tests/api_compatibility"]},
    ]
    system_checks=[
        {"category":"build","command":["python","-m","compileall","-q","."]},
        {"category":"unit","command":["python","-m","pytest","-q","tests/unit"]},
        {"category":"integration","command":["python","-m","pytest","-q","tests/integration"]},
        {"category":"static","command":["python","-m","mypy","app"]},
        {"category":"security","command":["python","-m","bandit","-r","app"]},
        {"category":"dependency","command":["pip-audit","--strict"]},
        {"category":"license","command":["licensecheck","--fail-on","GPL"]},
        {"category":"runtime","command":["python","-m","pytest","-q","tests/runtime"]},
        {"category":"api_compatibility","command":["python","-m","pytest","-q","tests/api_compatibility"]},
        {"category":"schema","command":["python","-m","pytest","-q","tests/schema"]},
    ]
    return {"version":"synthetic-python-v1","image":settings.PHASE6_SANDBOX_IMAGE,
        "runtime":"docker-rootless","timeout":120,
        "adapter":json.loads(settings.PHASE6_TARGET_COMMAND_JSON),
        "checks":checks,"system_checks":system_checks}


@pytest_asyncio.fixture
async def ready(
    isolated, monkeypatch, tmp_path  # noqa: F811 -- imported pytest fixture
):  # noqa: F811 -- pytest fixture dependency
    db, job, owner, storage = isolated
    monkeypatch.setattr(settings,"PHASE6_TARGET_PROFILES_JSON",json.dumps({"TypeScript / NestJS":synthetic_target_profile()}))
    baseline = await captured(isolated, monkeypatch)
    reviewer = User(
        email="phase6-reviewer@example.test",
        full_name="Phase 6 Reviewer",
        password_hash="unused",
        role="SUPER_ADMIN",
    )
    db.add(reviewer)
    await db.flush()
    frozen = await p5.freeze(
        db,
        job,
        FreezeRequest(
            suite_id=baseline["suite_id"], content_hash=baseline["content_hash"]
        ),
    )
    await p5.validate_plan(
        db,
        job,
        ValidationRequest(
            tables=[{"name": "customers", "rows": [{"id": 1, "name": "Amy"}]}]
        ),
        str(owner.user_id),
    )
    gate = await db.get(WorkflowGate, uuid.UUID(frozen["gate_id"]))
    await GateService().decide(
        db,
        gate.gate_id,
        GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Human approved observed characterization and schema evidence",
            artifact_hashes=gate.artifact_hashes,
        ),
        actor_id=reviewer.user_id,
        actor_role="SUPER_ADMIN",
    )
    monkeypatch.setattr(
        "app.services.artifact_service.get_storage_adapter", lambda: storage
    )
    plan = await ArtifactService(storage).create_artifact(
        db,
        job.job_id,
        "CONVERSION_PLAN",
        1,
        json.dumps(
            {
                "modules": [
                    {
                        "module_id": "calc",
                        "source_scope": ["legacy"],
                        "target_scope": ["modern"],
                        "dependencies": [],
                        "responsibility": "Preserve calculator behavior",
                    }
                ]
            }
        ).encode(),
        "Planner",
    )
    db_plan = ConversionPlanModel(
        plan_id=uuid.uuid4(),
        job_id=job.job_id,
        version=1,
        blueprint_version=1,
        validation_status="VALID",
        is_valid_dag=True,
        content_hash=plan.content_hash,
    )
    db.add(db_plan)
    db.add(ConversionPlanModuleModel(
        plan_id=db_plan.plan_id,
        module_id="calc",
        responsibility="Preserve calculator behavior",
        wave_number=1,
        risk="LOW",
    ))
    db.add(
        WorkflowGate(
            job_id=job.job_id,
            gate_type="G3",
            version=1,
            status="APPROVED",
            artifact_ids=[str(plan.artifact_id)],
            artifact_hashes={str(plan.artifact_id): plan.content_hash},
        )
    )
    module = await db.scalar(select(Module).where(Module.job_id == job.job_id))
    module.name, module.legacy_path, module.target_path = "calc", "legacy", "modern"
    module.plan_hash = plan.content_hash
    approval_hashes = {}
    for gate_type in ("G1", "G2"):
        upstream_gate = await db.scalar(
            select(WorkflowGate).where(
                WorkflowGate.job_id == job.job_id,
                WorkflowGate.gate_type == gate_type,
                WorkflowGate.status == "APPROVED",
            ).order_by(WorkflowGate.version.desc()).limit(1)
        )
        encoded = json.dumps(
            {
                "gate_id": str(upstream_gate.gate_id),
                "version": upstream_gate.version,
                "artifact_hashes": upstream_gate.artifact_hashes or {},
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        approval_hashes[f"{gate_type.lower()}_approval_hash"] = hashlib.sha256(
            encoded.encode()
        ).hexdigest()
    module.upstream_approval_hashes = approval_hashes
    job.status, job.active_node = "CONVERTING", "conversion"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "legacy").mkdir()
    (repo / "legacy" / "calc.py").write_text(
        "def add(x, y):\n    return x + y\n", encoding="utf-8"
    )
    await ws.git(repo, "init")
    await ws.git(repo, "add", ".")
    await ws.git(repo, "commit", "-m", "Trusted Phase 6 fixture")
    commit = await ws.git(repo, "rev-parse", "HEAD")
    module.integration_base_sha = commit
    job.source_repository = str(repo)
    db.add(
        RepositorySnapshotModel(
            job_id=job.job_id,
            source_ref="fixture",
            commit_sha=commit,
            content_hash="fixture",
            inventory_hash="fixture",
        )
    )
    await db.commit()
    workspace_service = RepositoryWorkspaceService(
        workspace_root=tmp_path / "authoritative_workspaces"
    )
    monkeypatch.setattr(
        "app.services.repository_workspace_service.repository_workspace_service",
        workspace_service,
    )
    monkeypatch.setattr(service, "repository_workspace_service", workspace_service)
    monkeypatch.setattr(ws, "repository_workspace_service", workspace_service)
    repo, _ = await workspace_service.stage_repository(
        db, job, pinned_commit=commit
    )
    monkeypatch.setattr(ws, "ROOT", tmp_path / "worktrees")
    monkeypatch.setattr(settings, "PHASE6_MODEL_PROVIDER", "fake")
    monkeypatch.setattr(settings, "PHASE6_MODEL_IDENTIFIER", "fake-model-v1")
    return db, job, owner, storage, module, repo


async def queued(ready, key="one", **kwargs):
    db, job, owner, _, module, _ = ready
    return await supervisor.queue_module_conversion(
        db, job, module, key, str(owner.user_id), **kwargs
    )


@pytest.fixture
def trusted_executor(monkeypatch, tmp_path):
    """Actual Python subprocess checks on generated *trusted fixtures*, not a sandbox substitute."""
    calls = []
    monkeypatch.setattr(settings,'SANDBOX_ATTESTATION_KEY','synthetic-unit-test-key-'+('x'*32))
    async def execute(files, cases, baseline_hash, *, binding=None, frozen_profile=None, system_checks=None):
        calls.append((files, cases, baseline_hash))
        root = tmp_path / ("fixture-check-" + uuid.uuid4().hex)
        root.mkdir()
        target = root / "calc.py"
        target.write_text(files["modern/calc.py"], encoding="utf-8")
        subprocess.run([sys.executable, "-m", "compileall", "-q", str(root)], check=True, capture_output=True, text=True, timeout=10)
        observations = []
        for case in cases:
            command = [
                sys.executable,
                "-c",
                "import json,runpy,sys; f=runpy.run_path(sys.argv[1]); print(json.dumps({'output':f['add'](1,2),'side_effects':{'count':1}}))",
                str(target),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            observations.append(
                {
                    "test_case_id": case["test_case_id"],
                    "command": command,
                    "exit_code": result.returncode,
                    "duration_ms": 1.0,
                    "stdout": result.stdout,
                }
            )
        # Compile output is only compile evidence. The synthetic fixture unit
        # result below follows a separate actual assertion of its known contract.
        unit=subprocess.run([sys.executable,'-c',
            "import runpy,sys; f=runpy.run_path(sys.argv[1]); assert f['add'](1,2)==3",str(target)],
            capture_output=True,text=True,timeout=10)
        raw=[]
        for spec in frozen_profile['checks']:
            result=unit if spec['category']=='unit' else SimpleNamespace(returncode=0,stdout='',stderr='')
            raw.append({**spec,'status':'PASS' if result.returncode==0 else 'FAIL','exit_code':result.returncode,
                'duration_ms':1.0,'stdout':result.stdout,'stderr':result.stderr})
        from tests.fixtures.sandbox_evidence import synthetic_result
        return synthetic_result(files,cases,raw,binding,frozen_profile,observations)

    monkeypatch.setattr(sandbox, "execute", execute)
    return calls


@pytest.mark.asyncio
async def test_synthetic_fixture_generation_execution_review_and_history(
    ready, trusted_executor
):
    db, job, _, storage, module, _ = ready
    attempt = await queued(ready)
    assert attempt.status == "QUEUED" and module.status == "LEASED"
    gateway = build_fake_gateway(FakeModelProvider([generation()]))
    await service.execute_attempt(db, attempt.attempt_id, gateway=gateway)
    assert attempt.status == module.status == "VERIFIED"
    evidence = (await service.detail(db, attempt))["evidence"]
    detail = await service.detail(db, attempt)
    verifier_evidence = detail["verification_run"]
    durable_run = await db.get(VerificationRun, uuid.UUID(verifier_evidence["verification_run_id"]))
    assert verifier_evidence["status"] == "PASS"
    assert verifier_evidence["profile_version"] == "synthetic-python-v1"
    assert verifier_evidence["candidate_hash"] == evidence["verification"]["candidate_hash"]
    assert verifier_evidence["suite_hash"] == evidence["verification"]["suite_hash"]
    assert durable_run.started_at and durable_run.finished_at and durable_run.evidence_hash
    assert durable_run.worker_id == 'synthetic-unit-verifier'
    assert durable_run.worker_id != (await db.get(AgentRun,durable_run.agent_run_id)).task_payload['codewriter_worker_id']
    assert detail["verification_run"]["agent_run_id"]
    assert len(evidence["checks"]) == 9 and all(
        item["tool_name"] == "SYNTHETIC_UNIT_TEST_ONLY"
        for item in evidence["checks"]
    ) and evidence["review"]["status"] == "PASS"
    assert (
        evidence["source_commit"]
        and evidence["diff"]
        and evidence["changed_files"] == ["modern/calc.py"]
    )
    assert len(trusted_executor) == 1 and len(trusted_executor[0][1]) == 1
    assert (
        len(
            (
                await db.execute(
                    select(Result).where(Result.attempt_id == attempt.attempt_id)
                )
            )
            .scalars()
            .all()
        )
        == 1
    )
    await supervisor.require_integration_eligibility(db, job)
    artifact = await db.get(Artifact, uuid.UUID(evidence["code_artifact_id"]))
    storage.objects[artifact.storage_path] = b"tampered"
    with pytest.raises(ConflictException):
        await service.detail(db, attempt)


@pytest.mark.asyncio
async def test_capture_idempotency_conflict_and_no_duplicate_attempt(ready):
    db, *_ = ready
    first, second = await queued(ready), await queued(ready)
    assert first.attempt_id == second.attempt_id
    assert len((await db.execute(select(ModuleAttempt))).scalars().all()) == 1
    with pytest.raises(ConflictException):
        await queued(ready, "one", rationale="Different request identity")


@pytest.mark.asyncio
async def test_sandbox_unavailable_never_verified_or_integrated(ready, monkeypatch):
    db, job, _, _, module, _ = ready
    monkeypatch.setattr(
        sandbox,
        "execute",
        AsyncMock(
            return_value={
                "available": False,
                "reason": "Docker daemon unavailable",
                "checks": [],
                "cases": [],
            }
        ),
    )
    attempt = await queued(ready)
    await service.execute_attempt(
        db,
        attempt.attempt_id,
        gateway=build_fake_gateway(FakeModelProvider([generation()])),
    )
    assert module.status == attempt.status == "BLOCKED"
    assert "Docker daemon" in attempt.failure_reason


@pytest.mark.asyncio
async def test_expired_api_verifier_lease_is_terminalized_and_cannot_be_reused(ready):
    from datetime import timedelta
    from app.models.base import utc_now

    db, job, _, _, module, _ = ready
    attempt = await queued(ready)
    writer = await db.get(AgentRun, attempt.agent_run_id)
    writer.status = "RUNNING"
    writer.task_payload = {**writer.task_payload, "phase": 6}
    attempt.status = "VERIFYING"
    module.status = "RUNNING"
    module.lease_owner = "expired-api-worker"
    module.lease_expires_at = utc_now() - timedelta(seconds=1)
    verifier = AgentRun(
        job_id=job.job_id,
        agent_name="Verifier",
        task_id="recovery-fixture-" + uuid.uuid4().hex,
        model_provider="system",
        model_identifier="target-stack-v3",
        status="RUNNING",
        task_payload={"controller_request_id": uuid.uuid4().hex},
    )
    db.add(verifier)
    await db.flush()
    record = VerificationRun(
        attempt_id=attempt.attempt_id,
        agent_run_id=verifier.run_id,
        candidate_hash="a" * 64,
        suite_hash="b" * 64,
        profile_version="target-stack-v3",
        profile_digest="c" * 64,
        input_hash="d" * 64,
        status="RUNNING",
        evidence={},
    )
    db.add(record)
    await db.commit()

    from app.services.dependency_scheduler import dependency_scheduler
    assert await dependency_scheduler.reconcile_stale_leases(db, job.job_id) == 1
    await db.refresh(attempt)
    await db.refresh(record)
    await db.refresh(verifier)
    assert attempt.status == "BLOCKED"
    assert record.status == "BLOCKED" and record.finished_at and record.evidence_hash
    assert record.evidence_hash == p5.digest(record.evidence)
    assert "new independent VerificationRun" in record.evidence["reason"]
    assert verifier.status == "FAILED"
    assert (
        await verifier_service.verify_module(db, job, module)
    ).verdict == VerificationVerdict.REJECT
    with pytest.raises(ConflictException):
        await supervisor.require_integration_eligibility(db, job)


@pytest.mark.asyncio
async def test_repair_resolved_reruns_frozen_suite_and_invalidates_old(
    ready, trusted_executor
):
    db, _, _, _, module, _ = ready
    first = await queued(ready)
    gateway = build_fake_gateway(FakeModelProvider([generation(4), generation(3)]))
    await service.execute_attempt(db, first.attempt_id, gateway=gateway)
    assert first.status == "REPAIR_REQUIRED"
    second = await queued(
        ready,
        "repair",
        previous=first,
        rationale="Repair the recorded addition behavioral regression",
    )
    old = await db.scalar(select(Result).where(Result.attempt_id == first.attempt_id))
    assert old.invalidated
    await service.execute_attempt(db, second.attempt_id, gateway=gateway)
    assert (
        module.status == second.status == "VERIFIED"
        and first.status == "REPAIR_REQUIRED"
    )
    assert second.git_branch != first.git_branch and len(trusted_executor) == 2
    assert trusted_executor[0][1] == trusted_executor[1][1]
    assert (await service.detail(db, second))["evidence"]["repair_feedback"]["results"][
        0
    ]["status"] == "FAIL"


@pytest.mark.asyncio
async def test_repeated_failure_and_maximum_escalation(ready, trusted_executor):
    db, job, *_ = ready
    first = await queued(ready)
    gateway = build_fake_gateway(FakeModelProvider([generation(4), generation(4)]))
    await service.execute_attempt(db, first.attempt_id, gateway=gateway)
    second = await queued(
        ready,
        "repair",
        previous=first,
        rationale="Repair exact failed frozen characterization case",
    )
    await service.execute_attempt(db, second.attempt_id, gateway=gateway)
    assert second.status == "WAITING_FOR_HUMAN"
    with pytest.raises(ConflictException):
        await queued(
            ready,
            "again",
            previous=second,
            rationale="A third automatic repeat must not be scheduled",
        )
    job.max_repair_attempts = 1
    with pytest.raises(ConflictException):
        await queued(
            ready,
            "over-limit",
            previous=second,
            rationale="Exceeds maximum attempt policy",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("gate_type", ["G1", "G2", "G3"])
async def test_pending_rejected_or_stale_gates_block_conversion(ready, gate_type):
    db, job, *_ = ready
    gate = await db.scalar(
        select(WorkflowGate).where(
            WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == gate_type
        )
    )
    gate.status = "REJECTED"
    await db.commit()
    with pytest.raises(ConflictException):
        await queued(ready)


@pytest.mark.asyncio
async def test_dependency_order_target_conflicts_and_branch_isolation(ready):
    db, job, _, _, module, repo = ready
    child = Module(
        job_id=job.job_id,
        name="child",
        legacy_path="legacy",
        target_path="child",
        dependency_module_ids=[str(module.module_id)],
    )
    db.add(child)
    await db.commit()
    with pytest.raises(ConflictException):
        await supervisor.queue_module_conversion(
            db, job, child, "blocked", "Supervisor"
        )
    first = await queued(ready)
    path1, branch1 = await ws.prepare(
        repo,
        str(job.job_id),
        str(module.module_id),
        str(first.attempt_id),
        1,
        await ws.git(repo, "rev-parse", "HEAD"),
    )
    path2, branch2 = await ws.prepare(
        repo,
        str(job.job_id),
        str(child.module_id),
        str(uuid.uuid4()),
        1,
        await ws.git(repo, "rev-parse", "HEAD"),
    )
    assert path1 != path2 and branch1 != branch2
    await ws.apply_changes(
        path1, {"modern/calc.py": "def add(x,y):\n    return x+y\n"}, "modern"
    )
    assert not (path2 / "modern/calc.py").exists()
    child.target_path = "modern/sub"
    await db.commit()
    with pytest.raises(ConflictException):
        await supervisor.queue_module_conversion(
            db, job, child, "conflict", "Supervisor"
        )


@pytest.mark.parametrize(
    "path",
    [
        "../escape.py",
        "/etc/passwd",
        "modern/../../outside",
        "modern/tests/test_calc.py",
        "modern/.env",
        "another/calc.py",
        "modern\\calc.py",
        "modern/.git/hooks/x",
        "modern/a.spec.ts",
    ],
)
def test_codewriter_scope_rejects_unsafe_paths(tmp_path, path):
    with pytest.raises(ValueError):
        ws.safe_target(tmp_path, path, "modern")


def test_reviewer_security_severity_contract_and_evidence():
    report = review(
        {"modern/calc.py": "def add(x,y):\n    return eval(x)\n"},
        [{"symbol": "required_api"}],
        "b" * 64,
    )
    assert report["status"] == "REJECTED"
    assert {f["severity"] for f in report["findings"]} == {"CRITICAL", "HIGH"}
    assert all(f["evidence_ref"] == "b" * 64 for f in report["findings"])


@pytest.mark.parametrize(
    "command",
    [
        ["sh", "-c", "echo pass"],
        ["python", "-c", "exec('x')"],
        ["npm", "install"],
        ["pytest", ";curl"],
        ["python", "-m", "pip", "install", "x"],
    ],
)
def test_unsafe_command_blocking(command):
    assert not sandbox.approved_command(command)


def test_codewriter_cannot_supply_verdict_or_arbitrary_api_commands():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChangeSet.model_validate(generation(verified=True)["output"])
    with pytest.raises(ValidationError):
        QueueConversion.model_validate({"idempotency_key": "x", "command": ["sh"]})


@pytest.mark.asyncio
async def test_stale_baseline_after_queue_fails_closed(ready):
    db, job, *_ = ready
    attempt = await queued(ready)
    gate = await db.scalar(
        select(WorkflowGate).where(
            WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G2"
        )
    )
    gate.status = "INVALIDATED"
    await db.commit()
    await service.execute_attempt(db, attempt.attempt_id)
    assert attempt.status == "BLOCKED"


@pytest.mark.asyncio
async def test_missing_model_configuration_is_blocked(ready, monkeypatch):
    db, *_ = ready
    monkeypatch.setattr(settings, "PHASE6_MODEL_PROVIDER", "")
    attempt = await queued(ready)
    await service.execute_attempt(db, attempt.attempt_id)
    assert attempt.status == "BLOCKED"
    assert "not configured" in attempt.failure_reason


@pytest.mark.asyncio
async def test_api_auth_idor_read_repair_and_waiver_permissions(ready, monkeypatch):
    from app.api.v1.phase6 import router
    from app.api.deps import get_current_user_and_permissions
    from app.core.database import get_db

    db, job, owner, _, module, _ = ready
    attempt = await queued(ready)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    @app.exception_handler(PlatformException)
    async def platform_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code})

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (
            await client.get(f"/api/v1/module-attempts/{attempt.attempt_id}")
        ).status_code == 401
        outsider = User(
            email="outsider@phase6.test",
            password_hash="unused",
            full_name="Outside",
            role="DEVELOPER",
        )
        db.add(outsider)
        await db.commit()
        app.dependency_overrides[get_current_user_and_permissions] = lambda: (
            outsider,
            [],
        )
        for suffix in ("", "/diff", "/test-results", "/review"):
            assert (
                await client.get(
                    f"/api/v1/module-attempts/{attempt.attempt_id}{suffix}"
                )
            ).status_code == 404
        db.add(
            JobMembership(job_id=job.job_id, user_id=outsider.user_id, role_id="VIEWER")
        )
        await db.commit()
        for suffix in ("", "/diff", "/test-results", "/review"):
            assert (
                await client.get(
                    f"/api/v1/module-attempts/{attempt.attempt_id}{suffix}"
                )
            ).status_code == 200
        assert (await client.get(f"/api/v1/jobs/{job.job_id}/module-attempts")).json()[
            "allowed_actions"
        ] == []
        assert (
            await client.post(
                f"/api/v1/module-attempts/{attempt.attempt_id}/repair",
                json={
                    "idempotency_key": "r",
                    "rationale": "A legitimate repair request rationale",
                },
            )
        ).status_code == 403
        assert (
            await client.post(
                f"/api/v1/module-attempts/{attempt.attempt_id}/waivers",
                json={
                    "finding_id": "x",
                    "rationale": "A legitimate waiver request rationale",
                },
            )
        ).status_code == 403
        foreign = Job(
            name="foreign", source_repository="fixture", owner_user_id=owner.user_id
        )
        db.add(foreign)
        await db.commit()
        app.dependency_overrides[get_current_user_and_permissions] = lambda: (owner, [])
        assert (
            await client.post(
                f"/api/v1/jobs/{foreign.job_id}/modules/{module.module_id}/conversion-runs",
                json={"idempotency_key": "foreign"},
            )
        ).status_code == 404


@pytest.mark.asyncio
async def test_sandbox_flags_timeout_cleanup_and_output_bounds(monkeypatch):
    from app.services import sandbox_controller as controller
    calls=[]
    image='sha256:'+'a'*64
    config={'Runtime':'runc','NetworkMode':'none','ReadonlyRootfs':True,'Memory':268435456,'NanoCpus':1000000000,
        'PidsLimit':64,'CapDrop':['ALL'],'SecurityOpt':['apparmor=docker-default','no-new-privileges'],'Binds':None}
    info={'Image':image,'Id':'unit-container','Config':{'User':'65534:65534'},'HostConfig':config,'Mounts':[]}
    def docker(*args,**kwargs):
        calls.append(args)
        if args[0]=='create':return SimpleNamespace(returncode=0,stdout='unit-container',stderr='')
        if args[0]=='start':raise TimeoutError('Execution deadline exceeded')
        if args[0]=='inspect':return SimpleNamespace(returncode=1 if any(c[0]=='rm' for c in calls) else 0,stdout=json.dumps([info]),stderr='')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(controller,'docker',docker)
    monkeypatch.setattr(controller,'runtime_evidence',lambda runtime:{'selected_runtime':'runc'})
    result=controller.execute_container({'request_id':'unit','job_id':'job','attempt_id':'attempt','_controller_id':'controller',
        'execution':{'image':image,'timeout':5,'runtime':'docker-rootless'}},'trusted unit fixture',{},'verify')
    assert 'deadline' in result['error'].lower()
    assert result['cleanup']['container_absent'] is True
    flags=calls[0]
    for flag in ('--pull=never','--network=none','--read-only','--memory=256m','--cpus=1','--pids-limit=64','--cap-drop=ALL','--user=65534:65534'):
        assert flag in flags
    assert '-v' not in flags and '--mount' not in flags
    assert calls[-2]==('rm','--force','rebase-unit-verify')


@pytest.mark.asyncio
async def test_supervisor_pool_exits_only_after_independent_execution(
    ready, trusted_executor, monkeypatch
):
    from app.services.code_writer import code_writer_service

    db, job, *_ = ready
    job.max_parallel_tasks = 1
    await db.commit()
    original = code_writer_service.generate
    gateway = build_fake_gateway(FakeModelProvider([generation()]))

    async def scripted(context, sources, **kwargs):
        return await original(context, sources, gateway=gateway)

    monkeypatch.setattr(code_writer_service, "generate", scripted)
    await supervisor.run_phase6_pool(db, job)
    await db.refresh(job)
    assert job.status == "INTEGRATING"
    assert trusted_executor


@pytest.mark.asyncio
async def test_all_post_apis_use_backend_authority_and_waiver_never_self_verifies(
    ready, trusted_executor, monkeypatch
):
    from app.api.v1.phase6 import router
    from app.api.deps import get_current_user_and_permissions
    from app.core.database import get_db

    db, job, owner, _, module, _ = ready
    monkeypatch.setattr("app.api.v1.phase6.resume_pool", AsyncMock())
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_and_permissions] = lambda: (owner, [])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        url = f"/api/v1/jobs/{job.job_id}/modules/{module.module_id}/conversion-runs"
        response = await client.post(url, json={"idempotency_key": "api-queue"})
        assert response.status_code == 202
        attempt_id = response.json()["attempt_id"]
        assert (await client.post(url, json={"idempotency_key": "api-queue"})).json()[
            "attempt_id"
        ] == attempt_id
        output = generation()
        output["output"]["files"]["modern/calc.py"] += "# TODO manual review needed\n"
        await service.execute_attempt(
            db,
            uuid.UUID(attempt_id),
            gateway=build_fake_gateway(FakeModelProvider([output])),
        )
        attempt = await db.get(ModuleAttempt, uuid.UUID(attempt_id))
        assert attempt.status == "REPAIR_REQUIRED"
        finding = (
            await client.get(f"/api/v1/module-attempts/{attempt_id}/review")
        ).json()["findings"][0]
        response = await client.post(
            f"/api/v1/module-attempts/{attempt_id}/waivers",
            json={
                "finding_id": finding["finding_id"],
                "rationale": "Human review requested for the exact recorded finding",
            },
        )
        assert response.status_code == 202 and response.json()["applied"] is False
        assert module.status == "REPAIR_REQUIRED"
        response = await client.post(
            f"/api/v1/module-attempts/{attempt_id}/repair",
            json={
                "idempotency_key": "api-repair",
                "rationale": "Remove incomplete implementation marker and rerun all checks",
            },
        )
        assert response.status_code == 202 and response.json()["attempt_number"] == 2
        assert response.json()["attempt_id"] != attempt_id


@pytest.mark.asyncio
async def test_deadline_and_output_overflow_remove_the_actual_named_container(monkeypatch):
    from app.services import sandbox_controller as controller
    for error in (TimeoutError('Execution deadline exceeded'),ValueError('Docker output exceeded bounded evidence limit')):
        calls=[]
        def docker(*args,**kwargs):
            calls.append(args)
            if args[0]=='start':raise error
            if args[0]=='inspect':return SimpleNamespace(returncode=1 if any(c[0]=='rm' for c in calls) else 0,stdout='[{}]',stderr='')
            return SimpleNamespace(returncode=0,stdout='unit-container',stderr='')
        monkeypatch.setattr(controller,'docker',docker)
        monkeypatch.setattr(controller,'runtime_evidence',lambda runtime:{'selected_runtime':'runc'})
        monkeypatch.setattr(controller,'inspected_configuration',lambda *args:{})
        # The inspect double needs the immutable identity fields, while policy
        # flags and their effective values are checked in the companion test.
        def inspect_docker(*args,**kwargs):
            result=docker(*args,**kwargs)
            if args[0]=='inspect' and result.returncode==0:result.stdout=json.dumps([{'Id':'unit-container','Image':'sha256:'+'a'*64,'Config':{'User':'65534:65534'}}])
            return result
        monkeypatch.setattr(controller,'docker',inspect_docker)
        result=controller.execute_container({'request_id':'bounded','job_id':'job','attempt_id':'attempt','_controller_id':'controller',
            'execution':{'image':'sha256:'+'a'*64,'timeout':5,'runtime':'docker-rootless'}},'trusted unit fixture',{},'verify')
        assert type(error).__name__ in result['error']
        assert result['cleanup']['container_absent'] is True
        assert calls[-2]==('rm','--force','rebase-bounded-verify')


@pytest.mark.asyncio
async def test_real_docker_acceptance_when_explicitly_configured():
    if os.getenv("PHASE6_RUN_REAL_ACCEPTANCE") != "1":
        pytest.skip(
            "Real Docker/model/target adapter acceptance requires explicit configured fixture"
        )
    check_docker = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if check_docker.returncode != 0:
        pytest.skip("Docker daemon is not running on development host")
    sandbox.configuration("python-fastapi")
    result = await sandbox.execute(
        {"modern/calc.py": "def add(x,y):\n    return x+y\n"},
        [
            {
                "test_case_id": "fixture",
                "name": "add",
                "fixtures": {"x": 1, "y": 2},
                "expected": 3,
                "side_effects": {"count": 1},
                "normalization": [],
            }
        ],
        "fixture",
    )
    assert result["available"] and result["passed"]


@pytest.mark.asyncio
async def test_transitive_dependency_changes_are_hydrated_and_stale_plans_rejected(
    ready,
):
    db, job, _, storage, module, repo = ready
    current = await supervisor.require_conversion_eligibility(db, job)
    child = Module(
        job_id=job.job_id,
        name="dependency-child",
        legacy_path="legacy",
        target_path="dependency_b",
    )
    db.add(child)
    await db.commit()
    base = {
        "baseline_hash": current["baseline_hash"],
        "plan_hash": current["plan_hash"],
    }
    first = await ArtifactService(storage).create_artifact(
        db,
        job.job_id,
        "CONVERTED_MODULE",
        1,
        p5.canonical(
            {
                **base,
                "files": {"dependency_a/a.py": "value = 1\n"},
                "allowed_target": "dependency_a",
                "dependency_evidence": [],
            }
        ),
        "CodeWriter",
        module_id=module.module_id,
    )
    first_ref = {
        "artifact_id": str(first.artifact_id),
        "content_hash": first.content_hash,
        "module_id": str(module.module_id),
    }
    second = await ArtifactService(storage).create_artifact(
        db,
        job.job_id,
        "CONVERTED_MODULE",
        2,
        p5.canonical(
            {
                **base,
                "files": {"dependency_b/b.py": "value = 2\n"},
                "allowed_target": "dependency_b",
                "dependency_evidence": [first_ref],
            }
        ),
        "CodeWriter",
        module_id=child.module_id,
    )
    second_ref = {
        "artifact_id": str(second.artifact_id),
        "content_hash": second.content_hash,
        "module_id": str(child.module_id),
    }
    worktree, _ = await ws.prepare(
        repo,
        str(job.job_id),
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        1,
        await ws.git(repo, "rev-parse", "HEAD"),
    )
    await service.hydrate_dependencies(
        db,
        worktree,
        [second_ref],
        job.job_id,
        current["baseline_hash"],
        current["plan_hash"],
    )
    assert (worktree / "dependency_a/a.py").exists() and (
        worktree / "dependency_b/b.py"
    ).exists()
    assert not (repo / "dependency_a/a.py").exists()
    with pytest.raises(ConflictException):
        await service.hydrate_dependencies(
            db,
            worktree,
            [second_ref],
            job.job_id,
            current["baseline_hash"],
            "stale-plan",
        )
