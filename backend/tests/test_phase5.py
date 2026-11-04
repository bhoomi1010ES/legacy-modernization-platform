"""Phase 5 invariants using isolated in-memory databases and deterministic legacy adapters."""

import json
import os
import uuid
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base
from app.models.artifact import Artifact
from app.models.job import Job, JobMembership
from app.models.module import Module
from app.models.user import User
from app.models.test_case import TestCase as Case, TestResult as Result
from app.models.workflow import WorkflowGate
from app.schemas.phase5 import (
    CaptureRequest,
    FreezeRequest,
    NormalizationRule,
    Scenario,
    Table,
    ValidationRequest,
)
from app.schemas.gates import DecisionOutcome, GateDecisionRequest
from app.core.errors import ConflictException, NotFoundException
from app.services import phase5_service as service
from app.services.phase5_engine import (
    canonical,
    coverage,
    digest,
    migration_plan,
    normalize,
    replay,
    validate_migration,
)
from app.services.gate_service import GateService


def rule(kind="timestamp", path="/time", **kw):
    return NormalizationRule(
        path=path, kind=kind, justification="Observed runtime nondeterminism", **kw
    )


def test_golden_detects_meaningful_change():
    left = {"time": "2026-01-01T00:00:00Z", "amount": 10}
    right = {"time": "2026-01-02T00:00:00Z", "amount": 11}
    assert normalize(left, [rule()]) != normalize(right, [rule()])
    right["amount"] = 10
    assert normalize(left, [rule()]) == normalize(right, [rule()])
    assert left["time"] == "2026-01-01T00:00:00Z"
    assert digest(left) == digest(json.loads(canonical(left)))


def test_normalization_rejects_overreach_and_logs(caplog):
    with pytest.raises(ValueError):
        normalize({"time": 42}, [rule()])
    assert "phase5.normalize failed" in caplog.text
    with pytest.raises(ValueError):
        normalize({"items": [2, 1]}, [rule("unordered", "/items")])
    assert normalize(
        {"items": [2, 1]}, [rule("unordered", "/items", contract_allows=True)]
    ) == {"items": [1, 2]}
    with pytest.raises(KeyError):
        normalize({}, [rule()])


def test_coverage_includes_untested_modules_interfaces_and_limitations():
    result = coverage(
        ["orders", "billing"],
        ["GET orders", "POST bills"],
        [
            {
                "module": "orders",
                "interface": "GET orders",
                "behavior": "empty orders",
                "outcome": "PASSED",
            }
        ],
    )
    assert (
        "billing" in result["untested_paths"]
        and "POST bills" in result["untested_paths"]
    )
    assert result["percent"] < 100 and result["limitations"]


def tables():
    return [
        Table.model_validate(
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "id",
                        "type": "INTEGER",
                        "primary_key": True,
                        "nullable": False,
                    },
                    {
                        "name": "name",
                        "type": "TEXT",
                        "nullable": False,
                        "max_length": 5,
                        "unique": True,
                    },
                ],
            }
        ),
        Table.model_validate(
            {
                "name": "orders",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {
                        "name": "customer_id",
                        "type": "INTEGER",
                        "references_table": "customers",
                        "references_column": "id",
                    },
                ],
            }
        ),
    ]


def test_schema_diff_static_sql_and_upgrade_rollback_counts():
    source = tables()
    target = [t.model_copy(deep=True) for t in source]
    target[0].columns[1].max_length = 10
    plan = migration_plan(source, target)
    assert plan["differences"][0]["column"] == "name"
    assert "REFERENCES" in plan["upgrade_sql"] and "DROP TABLE" in plan["rollback_sql"]
    result = validate_migration(
        plan,
        ValidationRequest(
            tables=[
                {"name": "customers", "rows": [{"id": 1, "name": "Amy"}]},
                {"name": "orders", "rows": [{"id": 2, "customer_id": 1}]},
            ]
        ),
    )
    assert result["passed"] and result["rollback_verified"]
    assert result["counts"]["customers"] == {
        "source": 1,
        "target": 1,
        "reconciled": True,
    }


@pytest.mark.parametrize(
    "rows",
    [
        [{"id": 1, "name": None}],
        [{"id": 1, "name": "Amy"}, {"id": 1, "name": "Bob"}],
        [{"id": 1, "name": "too long"}],
        [{"id": "1", "name": "Amy"}],
    ],
)
def test_mapping_rejects_null_duplicate_truncation_implicit_cast(rows):
    result = validate_migration(
        migration_plan(tables(), []),
        ValidationRequest(tables=[{"name": "customers", "rows": rows}]),
    )
    assert not result["passed"] and result["errors"] and result["rollback_verified"]


def test_referential_integrity_and_empty_sample_warning():
    plan = migration_plan(tables(), [])
    result = validate_migration(
        plan,
        ValidationRequest(
            tables=[{"name": "orders", "rows": [{"id": 2, "customer_id": 99}]}]
        ),
    )
    assert not result["passed"]
    assert validate_migration(plan, ValidationRequest())["limitations"]
    oversized = validate_migration(
        plan,
        ValidationRequest(
            tables=[{"name": "customers", "rows": [{"id": 2**80, "name": "Amy"}]}]
        ),
    )
    assert not oversized["passed"] and oversized["errors"]


def test_no_connection_urls_production_scope_or_arbitrary_sql():
    for payload in (
        {"scope": "production"},
        {"database_url": "postgres://prod"},
        {"sql": "DROP TABLE anything"},
    ):
        with pytest.raises(ValidationError):
            ValidationRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        Table.model_validate({"name": 'x"; DROP TABLE users', "columns": []})


@pytest.mark.asyncio
async def test_sandbox_unavailable_is_not_a_pass(monkeypatch):
    monkeypatch.setenv("PHASE5_LEGACY_IMAGE", "")
    from app.core.config import settings
    monkeypatch.setattr(settings, "PHASE5_LEGACY_IMAGE", "")
    result = await replay(
        Scenario(name="orders", module="orders", interface="GET", behavior="empty")
    )
    assert result["available"] is False


@pytest_asyncio.fixture
async def isolated(monkeypatch):
    from app.core.storage import StorageAdapter

    class MemoryStorage(StorageAdapter):
        objects = {}

        async def put_object(self, key, data, media_type="application/json"):
            self.objects[key] = data
            return self.compute_sha256(data), len(data)

        async def get_object(self, key):
            return self.objects[key]

        async def object_exists(self, key):
            return key in self.objects

        async def delete_object(self, key):
            return self.objects.pop(key, None) is not None

    storage = MemoryStorage()
    monkeypatch.setattr(service, "get_storage_adapter", lambda: storage)
    from app.services.artifact_service import artifact_service

    monkeypatch.setattr(artifact_service, "storage", storage)
    monkeypatch.setattr(
        "app.services.continuous_pipeline.continuous_pipeline_service.trigger_continuous_pipeline",
        lambda *a, **k: None,
    )
    # This fixture explicitly drives the workflow with its own in-memory session.
    # Gate approval must not start another runner on the global test database.
    monkeypatch.setattr('app.services.supervisor_service.supervisor_service.schedule_drive',lambda *a,**k:None)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        owner = User(
            email="reviewer@example.test",
            full_name="Reviewer",
            password_hash="unused",
            role="SUPER_ADMIN",
        )
        db.add(owner)
        await db.flush()
        job = Job(
            name="phase5 isolated",
            source_repository="fixture",
            owner_user_id=owner.user_id,
            status="CHARACTERIZING",
            active_node="characterization",
        )
        db.add(job)
        await db.flush()
        db.add(JobMembership(job_id=job.job_id,user_id=owner.user_id,role_id='SUPER_ADMIN'))
        db.add(
            Module(
                job_id=job.job_id,
                name="untested",
                legacy_path="src",
                target_path="target",
            )
        )
        db.add(
            WorkflowGate(
                job_id=job.job_id,
                gate_type="G1",
                version=1,
                status="APPROVED",
                artifact_hashes={},
                artifact_ids=[],
            )
        )
        await db.commit()
        yield db, job, owner, storage
    await engine.dispose()


async def captured(isolated, monkeypatch, key="capture", expected=3):
    db, job, owner, _ = isolated
    monkeypatch.setattr(
        service,
        "replay",
        AsyncMock(
            return_value={"available": True, "output": 3, "side_effects": {"count": 1}}
        ),
    )
    return await service.capture(
        db,
        job,
        CaptureRequest(
            idempotency_key=key,
            scenarios=[
                Scenario(
                    name="add",
                    module="calc",
                    interface="add",
                    behavior="adds values",
                    inputs={"x": 1, "y": 2},
                    expected=expected,
                )
            ],
            tables=tables(),
        ),
        str(owner.user_id),
    )


@pytest.mark.asyncio
async def test_capture_baseline_persistence_hash_idempotency_and_redaction(
    isolated, monkeypatch
):
    first = await captured(isolated, monkeypatch)
    second = await captured(isolated, monkeypatch)
    assert first["suite_id"] == second["suite_id"] and first["version"] == 1
    assert first["cases"][0]["outcome"] == "PASSED"
    assert "untested" in first["coverage"]["untested_paths"]
    db, job, owner, storage = isolated
    # Read-only idempotent retries remain valid after the workflow is paused.
    job.status = "PAUSED"
    await db.commit()
    paused_retry = await captured(isolated, monkeypatch)
    assert paused_retry["suite_id"] == first["suite_id"]
    with pytest.raises(ConflictException):
        await service.capture(
            db, job, CaptureRequest(idempotency_key="capture"), str(owner.user_id)
        )


@pytest.mark.asyncio
async def test_g2_approve_hash_stable_and_revision_invalidates_downstream(
    isolated, monkeypatch
):
    baseline = await captured(isolated, monkeypatch)
    db, job, owner, storage = isolated
    frozen = await service.freeze(
        db,
        job,
        FreezeRequest(
            suite_id=baseline["suite_id"], content_hash=baseline["content_hash"]
        ),
    )
    gate = await db.get(WorkflowGate, uuid.UUID(frozen["gate_id"]))
    await service.validate_plan(
        db,
        job,
        ValidationRequest(
            tables=[{"name": "customers", "rows": [{"id": 1, "name": "Amy"}]}]
        ),
        str(owner.user_id),
    )
    await GateService().decide(
        db,
        gate.gate_id,
        GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Reviewed golden behavior and known coverage gaps",
            artifact_hashes=gate.artifact_hashes,
        ),
        actor_id=owner.user_id,
        actor_role="SUPER_ADMIN",
    )
    assert (await service.report(db, job.job_id))["status"] == "FROZEN"
    case = await db.get(Case, uuid.UUID(baseline["cases"][0]["test_case_id"]))
    assert case.is_frozen
    db.add(
        WorkflowGate(
            job_id=job.job_id,
            gate_type="G3",
            version=1,
            status="APPROVED",
            artifact_ids=[],
            artifact_hashes={},
        )
    )
    await db.commit()
    revised = await captured(isolated, monkeypatch, key="revision")
    assert revised["version"] == 2 and revised["suite_id"] != baseline["suite_id"]
    assert (
        await service.report(
            db, job.job_id, await db.get(Artifact, uuid.UUID(baseline["suite_id"]))
        )
    )["content_hash"] == baseline["content_hash"]
    assert (await db.get(WorkflowGate, gate.gate_id)).status == "INVALIDATED"
    assert all(
        r.invalidated
        for r in (
            await db.execute(
                select(Result).where(Result.test_case_id == case.test_case_id)
            )
        ).scalars()
    )


@pytest.mark.asyncio
async def test_g2_reject_requires_new_version_and_stale_hash_conflicts(
    isolated, monkeypatch
):
    baseline = await captured(isolated, monkeypatch)
    db, job, owner, _ = isolated
    frozen = await service.freeze(
        db,
        job,
        FreezeRequest(
            suite_id=baseline["suite_id"], content_hash=baseline["content_hash"]
        ),
    )
    gate = await db.get(WorkflowGate, uuid.UUID(frozen["gate_id"]))
    await GateService().decide(
        db,
        gate.gate_id,
        GateDecisionRequest(
            decision=DecisionOutcome.REJECTED,
            rationale="Missing edge case needs additional capture",
            artifact_hashes=gate.artifact_hashes,
        ),
        actor_id=owner.user_id,
        actor_role="SUPER_ADMIN",
    )
    assert job.status == "CHARACTERIZING"
    revised = await captured(isolated, monkeypatch, key="revision")
    assert revised["version"] == 2
    with pytest.raises(ConflictException):
        await service.freeze(
            db,
            job,
            FreezeRequest(
                suite_id=baseline["suite_id"], content_hash=baseline["content_hash"]
            ),
        )


@pytest.mark.asyncio
async def test_meaningful_baseline_failure_blocks_freeze(isolated, monkeypatch):
    baseline = await captured(isolated, monkeypatch, expected=99)
    db, job, owner, _ = isolated
    assert baseline["cases"][0]["outcome"] == "FAILED"
    with pytest.raises(ConflictException):
        await service.freeze(
            db,
            job,
            FreezeRequest(
                suite_id=baseline["suite_id"], content_hash=baseline["content_hash"]
            ),
        )


@pytest.mark.asyncio
async def test_discovery_does_not_invent_vectors_or_cost(isolated, monkeypatch):
    db, job, owner, _ = isolated
    baseline = await service.capture(
        db, job, CaptureRequest(idempotency_key="discovery"), str(owner.user_id)
    )
    assert not baseline["runtime_available"] and baseline["cases"] == []
    assert baseline["coverage"]["percent"] == 0 and job.budget_used_usd == 0


@pytest.mark.asyncio
async def test_api_auth_job_isolation_and_all_phase5_endpoints(isolated, monkeypatch):
    import httpx
    from app.main import app
    from app.api.deps import get_current_user_and_permissions
    from app.core.database import get_db
    from app.models.role import Role

    db, job, owner, storage = isolated

    async def session_override():
        yield db

    async def auth_override():
        return owner, []

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_current_user_and_permissions] = auth_override
    monkeypatch.setattr(
        service,
        "replay",
        AsyncMock(
            return_value={"available": True, "output": {"count": 0}, "side_effects": {}}
        ),
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            base = f"/api/v1/jobs/{job.job_id}"
            response = await client.post(
                base + "/characterization-runs",
                json={
                    "idempotency_key": "api",
                    "scenarios": [
                        {
                            "name": "empty",
                            "module": "orders",
                            "interface": "GET orders",
                            "behavior": "empty list",
                            "inputs": {
                                "password": "fixture-secret",
                                "email": "test@example.test",
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 201, response.text
            report = response.json()
            assert report["cases"][0]["fixtures"]["password"] != "fixture-secret"
            for endpoint in (
                "test-cases",
                "characterization-report",
                "schema-analysis",
                "data-migration-plan",
            ):
                assert (await client.get(base + "/" + endpoint)).status_code == 200
            case_id = report["cases"][0]["test_case_id"]
            assert (
                await client.get(f"/api/v1/test-cases/{case_id}")
            ).status_code == 200
            response = await client.post(
                base + "/g2/freeze",
                json={
                    "suite_id": report["suite_id"],
                    "content_hash": report["content_hash"],
                },
            )
            assert response.status_code == 200, response.text
            assert (
                await client.post(
                    base + "/data-migration-plan/validate", json={"scope": "production"}
                )
            ).status_code == 422
            assert (
                await client.post(
                    base + "/data-migration-plan/validate", json={"tables": []}
                )
            ).status_code == 200
            # A valid authenticated user without membership sees neither job nor test evidence.
            outsider = User(
                email="outsider@example.test",
                full_name="Outsider",
                password_hash="unused",
                role="VIEWER",
            )
            db.add(outsider)
            await db.commit()

            async def outsider_auth():
                return outsider, []

            app.dependency_overrides[get_current_user_and_permissions] = outsider_auth
            assert (
                await client.get(base + "/characterization-report")
            ).status_code == 404
            assert (
                await client.get(f"/api/v1/test-cases/{case_id}")
            ).status_code == 404
            db.add(Role(role_id="VIEWER", name="Viewer", permissions=[]))
            db.add(
                JobMembership(
                    job_id=job.job_id, user_id=outsider.user_id, role_id="VIEWER"
                )
            )
            await db.commit()
            assert (
                await client.get(base + "/characterization-report")
            ).status_code == 200
            assert (
                await client.post(
                    base + "/characterization-runs",
                    json={"idempotency_key": "forbidden"},
                )
            ).status_code == 201
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_nondeterministic_side_effects_fail_and_unavailable_cannot_approve(
    isolated, monkeypatch
):
    db, job, owner, _ = isolated
    monkeypatch.setattr(
        service,
        "replay",
        AsyncMock(
            side_effect=[
                {"available": True, "output": 1, "side_effects": {"writes": 1}},
                {"available": True, "output": 1, "side_effects": {"writes": 2}},
            ]
        ),
    )
    report = await service.capture(
        db,
        job,
        CaptureRequest(
            idempotency_key="unstable",
            scenarios=[
                Scenario(
                    name="unstable",
                    module="m",
                    interface="i",
                    behavior="unstable side effects",
                )
            ],
        ),
        str(owner.user_id),
    )
    assert report["cases"][0]["outcome"] == "NON_REPRODUCIBLE"
    report = await service.capture(
        db, job, CaptureRequest(idempotency_key="missing"), str(owner.user_id)
    )
    frozen = await service.freeze(
        db,
        job,
        FreezeRequest(suite_id=report["suite_id"], content_hash=report["content_hash"]),
    )
    gate = await db.get(WorkflowGate, uuid.UUID(frozen["gate_id"]))
    with pytest.raises(ConflictException, match="at least one observed"):
        await service.decide_g2(db, gate, True)


@pytest.mark.asyncio
async def test_artifact_corruption_fails_integrity(isolated, monkeypatch):
    baseline = await captured(isolated, monkeypatch)
    db, job, _, storage = isolated
    artifact = await service.latest(db, job.job_id)
    storage.objects[artifact.storage_path] = b'{"tampered":true}'
    with pytest.raises(ConflictException, match="integrity"):
        await service.report(db, job.job_id)


def test_source_schema_discovery_is_scoped_and_reports_limits(tmp_path, monkeypatch):
    import app.services.phase5_engine as engine
    monkeypatch.setattr(
        "app.services.phase6_sandbox.verified_runtime_args",
        AsyncMock(return_value=[]),
    )

    fake_module = tmp_path / "backend" / "app" / "services" / "phase5_engine.py"
    monkeypatch.setattr(engine, "__file__", str(fake_module))
    workspace = tmp_path / "backend" / "repo_workspaces" / "job_fixture"
    workspace.mkdir(parents=True)
    (workspace / "schema.sql").write_text(
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name VARCHAR(5) NOT NULL UNIQUE); DELETE FROM customers;",
        encoding="utf-8",
    )
    discovered, notes = engine.discover_schema(
        "fixture", ["schema.sql", "../../outside.sql"]
    )
    assert discovered[0].name == "customers"
    assert discovered[0].columns[1].unique and discovered[0].columns[1].max_length == 5
    assert notes and any("Unparsed" in n for n in notes)


@pytest.mark.asyncio
async def test_sandbox_command_is_restricted_and_evidence_is_validated(monkeypatch):
    from types import SimpleNamespace
    import app.services.phase5_engine as engine
    from app.services import sandbox_client,phase6_workspace
    calls=[]
    monkeypatch.setattr(phase6_workspace,'file_snapshot',AsyncMock(return_value={'legacy.py':'value=1'}))
    async def pinned_git(_repo, *args):
        if args == ('rev-parse', 'HEAD'): return 'a' * 40
        if args == ('status', '--porcelain', '--untracked-files=no'): return ''
        return 'legacy.py\x00'
    monkeypatch.setattr(phase6_workspace, 'git', pinned_git)
    async def execute(execution,binding):
        calls.append((execution,binding))
        return {'execution_purpose':'VERIFICATION','execution':{'exit_code':0,'worker_id':'unit-controller-container','cleanup':{'container_absent':True},
            'observation':{'source_unchanged':True,'observations':[{'exit_code':0,'stdout':'{"output":{"count":0},"side_effects":{}}'}]}},
            'image_scan':{'status':'PASS'},'attestation':{'synthetic_unit_test_only':True}}
    monkeypatch.setattr(sandbox_client,'execute',execute)
    result=await engine.replay(Scenario(name='empty',module='orders',interface='GET',behavior='empty list'),
        '/unit-workspace',SimpleNamespace(job_id=uuid.uuid4()))
    assert result['available'] and result['output']=={'count':0}
    execution,binding=calls[0]
    assert execution['checks']==[] and execution['files']=={'legacy.py':'value=1'}
    assert execution['source_provenance']['source_commit']=='a'*40
    assert execution['source_provenance']['source_snapshot_sha256']
    assert set(binding)>={'request_id','job_id','attempt_id','candidate_hash','suite_hash'}
    assert all('expected' not in case for case in execution['cases'])


@pytest.mark.asyncio
async def test_adapter_unobserved_reason_is_preserved_for_g2_row(monkeypatch):
    from types import SimpleNamespace
    import app.services.phase5_engine as engine
    from app.services import sandbox_client, phase6_workspace
    monkeypatch.setattr(phase6_workspace, 'file_snapshot', AsyncMock(return_value={'legacy.py': 'value=1'}))
    async def pinned_git(_repo, *args):
        if args == ('rev-parse', 'HEAD'): return 'b' * 40
        if args == ('status', '--porcelain', '--untracked-files=no'): return ''
        return 'legacy.py\x00'
    monkeypatch.setattr(phase6_workspace, 'git', pinned_git)
    async def execute(_execution, _binding):
        return {'execution_purpose': 'VERIFICATION', 'execution': {
            'exit_code': 0, 'worker_id': 'unit-controller-container',
            'cleanup': {'container_absent': True},
            'observation': {'source_unchanged': True, 'observations': [{
                'exit_code': 78, 'stderr': 'UNOBSERVED: browser/DOM runtime is not installed',
            }]},
        }, 'image_scan': {'status': 'PASS'}, 'attestation': {}}
    monkeypatch.setattr(sandbox_client, 'execute', execute)
    result = await engine.replay(Scenario(name='frontend', module='frontend', interface='/', behavior='browser flow'),
                                '/unit-workspace', SimpleNamespace(job_id=uuid.uuid4()))
    assert result['available'] is False
    assert result['reason'] == 'ADAPTER_EXIT: UNOBSERVED: browser/DOM runtime is not installed'


@pytest.mark.parametrize("path", ["/bad~2escape", "/items/*", "/items/../value"])
def test_malformed_and_wildcard_pointers_rejected(path):
    with pytest.raises(ValidationError):
        rule(path=path)


@pytest.mark.parametrize("index", ["-1", "01", "+1"])
def test_noncanonical_array_indices_cannot_normalize_a_different_field(index):
    with pytest.raises(ValueError):
        normalize({"items": ["2026-01-01T00:00:00Z"]}, [rule(path=f"/items/{index}")])


def test_blank_normalization_reason_and_unsafe_controls_are_rejected():
    with pytest.raises(ValidationError):
        NormalizationRule(path="/time", kind="timestamp", justification=" " * 20)
    for inputs in (
        {"command": "sh"},
        {"adapter_command": ["sh"]},
        {"database_url": "postgresql://production"},
        {"host_mount": "/host"},
        {"password": "real-production-credential"},
        {"nested": {"dsn": "private"}},
    ):
        with pytest.raises(ValidationError):
            CaptureRequest(
                idempotency_key="unsafe",
                scenarios=[
                    Scenario(
                        name="n", module="m", interface="i", behavior="b", inputs=inputs
                    )
                ],
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stdout,stderr,code,reason",
    [
        (
            b'{"output":1,"side_effects":{},"available":true}',
            b"",
            0,
            "INVALID_ADAPTER_EVIDENCE",
        ),
        (
            b'{"output":1,"output":2,"side_effects":{}}',
            b"",
            0,
            "INVALID_ADAPTER_EVIDENCE",
        ),
        (b'{"output":NaN,"side_effects":{}}', b"", 0, "INVALID_ADAPTER_EVIDENCE"),
        (b"not JSON", b"", 0, "INVALID_ADAPTER_EVIDENCE"),
        (b"{}", b"", 0, "INVALID_ADAPTER_EVIDENCE"),
        (b"", b"failed to connect to Docker daemon", 1, "DOCKER_UNAVAILABLE"),
        (b"", b"No such image", 1, "IMAGE_UNAVAILABLE"),
        (b"", b"legacy failure", 7, "ADAPTER_EXIT"),
    ],
)
async def test_adapter_contract_and_precise_failure_reasons(monkeypatch,stdout,stderr,code,reason):
    from types import SimpleNamespace
    from app.services import sandbox_client,phase6_workspace
    monkeypatch.setattr(phase6_workspace,'file_snapshot',AsyncMock(return_value={}))
    async def execute(execution,binding):
        if reason in {'DOCKER_UNAVAILABLE','IMAGE_UNAVAILABLE'}:
            raise ValueError(reason+': signed controller failure fixture')
        return {'execution_purpose':'VERIFICATION','execution':{'exit_code':0,'worker_id':'synthetic-unit-container','cleanup':{'container_absent':True},
            'observation':{'source_unchanged':True,'observations':[{'exit_code':code,'stdout':stdout.decode(),'stderr':stderr.decode()}]}},
            'image_scan':{'status':'PASS'},'attestation':{'synthetic_unit_test_only':True}}
    monkeypatch.setattr(sandbox_client,'execute',execute)
    result=await replay(Scenario(name='n',module='m',interface='i',behavior='b'),'/unit-workspace',SimpleNamespace(job_id=uuid.uuid4()))
    assert not result['available'] and result['reason'].startswith(reason)


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["PENDING", "REJECTED", "APPROVED"])
async def test_g2_to_phase6_canonical_exit_proof(isolated, monkeypatch, decision):
    from app.services.supervisor_service import supervisor_service
    from app.services.supervisor_router import supervisor_router, SupervisorAction
    from app.models.audit import AuditEvent

    baseline = await captured(isolated, monkeypatch)
    db, job, owner, storage = isolated
    await service.validate_plan(
        db,
        job,
        ValidationRequest(
            tables=[{"name": "customers", "rows": [{"id": 1, "name": "Amy"}]}]
        ),
        str(owner.user_id),
    )
    review = await service.freeze(
        db,
        job,
        FreezeRequest(
            suite_id=baseline["suite_id"], content_hash=baseline["content_hash"]
        ),
    )
    gate = await db.get(WorkflowGate, uuid.UUID(review["gate_id"]))
    assert job.status == "AWAITING_GATE_G2" and gate.status == "PENDING"
    if decision != "PENDING":
        await GateService().decide(
            db,
            gate.gate_id,
            GateDecisionRequest(
                decision=DecisionOutcome(decision),
                rationale="Human reviewed baseline, schema data and limitations",
                artifact_hashes=gate.artifact_hashes,
                idempotency_key=f"exit-{decision}",
            ),
            actor_id=owner.user_id,
            actor_role="SUPER_ADMIN",
        )
    if decision == "APPROVED":
        assert job.status == "PLANNING"
        assert await supervisor_service.require_planning_eligibility(db, job) is gate
        route = await supervisor_router.evaluate_next_action(db, job)
        assert (
            route.action == SupervisorAction.EXECUTE
            and route.agent_id == "PlannerCoordinator"
        )
        assert (await service.report(db, job.job_id))["status"] == "FROZEN"
        assert (
            await db.get(Case, uuid.UUID(baseline["cases"][0]["test_case_id"]))
        ).is_frozen
        assert await service.read_payload(
            await service.latest(db, job.job_id, "SCHEMA_MIGRATION_PLAN")
        )
    else:
        with pytest.raises(ConflictException):
            await supervisor_service.require_planning_eligibility(db, job)
        assert job.status == (
            "CHARACTERIZING" if decision == "REJECTED" else "AWAITING_GATE_G2"
        )
        if decision == "REJECTED":
            revision = await captured(isolated, monkeypatch, key="after-rejection")
            assert revision["version"] == 2
    events = list(
        (
            await db.execute(select(AuditEvent).where(AuditEvent.job_id == job.job_id))
        ).scalars()
    )
    assert any(e.event_type == "BASELINE_REVISION_RECORDED" for e in events)
    if decision != "PENDING":
        assert any(e.event_type == "GATE_DECIDED" for e in events)


@pytest.mark.asyncio
async def test_empty_data_samples_cannot_satisfy_g2(isolated, monkeypatch):
    baseline = await captured(isolated, monkeypatch)
    db, job, owner, _ = isolated
    await service.validate_plan(db, job, ValidationRequest(), str(owner.user_id))
    review = await service.freeze(
        db,
        job,
        FreezeRequest(
            suite_id=baseline["suite_id"], content_hash=baseline["content_hash"]
        ),
    )
    gate = await db.get(WorkflowGate, uuid.UUID(review["gate_id"]))
    with pytest.raises(ConflictException, match="disposable sample"):
        await service.decide_g2(db, gate, True)


@pytest.mark.asyncio
async def test_stale_approved_g2_replay_and_planning_are_blocked(isolated, monkeypatch):
    from app.services.supervisor_service import supervisor_service

    baseline = await captured(isolated, monkeypatch)
    db, job, owner, _ = isolated
    await service.validate_plan(
        db,
        job,
        ValidationRequest(
            tables=[{"name": "customers", "rows": [{"id": 1, "name": "Amy"}]}]
        ),
        str(owner.user_id),
    )
    review = await service.freeze(
        db,
        job,
        FreezeRequest(
            suite_id=baseline["suite_id"], content_hash=baseline["content_hash"]
        ),
    )
    gate = await db.get(WorkflowGate, uuid.UUID(review["gate_id"]))
    payload = GateDecisionRequest(
        decision=DecisionOutcome.APPROVED,
        rationale="Human reviewed current baseline and schema",
        artifact_hashes=gate.artifact_hashes,
        idempotency_key="stale-approval",
    )
    await GateService().decide(
        db, gate.gate_id, payload, actor_id=owner.user_id, actor_role="SUPER_ADMIN"
    )
    await captured(isolated, monkeypatch, key="revised-again")
    with pytest.raises(ConflictException, match="stale approval"):
        await GateService().decide(
            db, gate.gate_id, payload, actor_id=owner.user_id, actor_role="SUPER_ADMIN"
        )
    with pytest.raises(ConflictException):
        await supervisor_service.require_planning_eligibility(db, job)


@pytest.mark.asyncio
async def test_expected_null_differs_from_observation_only_request_identity(
    isolated, monkeypatch
):
    db, job, owner, _ = isolated
    scenario = {"name": "n", "module": "m", "interface": "i", "behavior": "b"}
    monkeypatch.setattr(
        service,
        "replay",
        AsyncMock(return_value={"available": True, "output": None, "side_effects": {}}),
    )
    await service.capture(
        db,
        job,
        CaptureRequest(idempotency_key="identity", scenarios=[Scenario(**scenario)]),
        str(owner.user_id),
    )
    with pytest.raises(ConflictException):
        await service.capture(
            db,
            job,
            CaptureRequest(
                idempotency_key="identity",
                scenarios=[Scenario(**scenario, expected=None)],
            ),
            str(owner.user_id),
        )


def test_unsupported_composite_semantics_are_review_required():
    composite = [
        Table.model_validate(
            {
                "name": "pairs",
                "columns": [
                    {"name": "left", "primary_key": True},
                    {"name": "right", "primary_key": True},
                ],
            }
        )
    ]
    plan = migration_plan(composite, [])
    assert plan["status"] == "REVIEW_REQUIRED"
    result = validate_migration(plan, ValidationRequest())
    assert result["status"] == "REVIEW_REQUIRED" and not result["passed"]


def test_phase5_does_not_write_workflow_state_or_approve_gates():
    import inspect

    source = inspect.getsource(service)
    assert "job.status =" not in source and "job.status," not in source
    assert "checkpointer.save" not in source and "WorkflowGate(" not in source
    assert "DecisionOutcome.APPROVED" not in source


def test_phase4_manifest_parser_rejects_xml_entity_expansion():
    from app.services.stack_detector import StackDetector
    from types import SimpleNamespace

    inventory = SimpleNamespace(warnings=[])
    manifest = SimpleNamespace(relative_path="pom.xml")
    malicious = '<!DOCTYPE project [<!ENTITY x "expansion">]><project>&x;</project>'
    assert StackDetector._parse_pom_xml(malicious, manifest, inventory) is None
    assert inventory.warnings


@pytest.mark.asyncio
async def test_adapter_timeout_cleans_up_named_container_without_weakening_policy(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.services import sandbox_client,phase6_workspace
    spawn=AsyncMock(side_effect=AssertionError('The API must not launch Docker or execute customer code'))
    monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
    monkeypatch.setattr(phase6_workspace,'file_snapshot',AsyncMock(return_value={}))
    monkeypatch.setattr(sandbox_client,'execute',AsyncMock(side_effect=TimeoutError('Independent controller deadline')))
    result=await replay(Scenario(name='slow',module='m',interface='i',behavior='slow adapter'),'/unit-workspace',SimpleNamespace(job_id=uuid.uuid4()))
    assert not result['available'] and result['reason'].startswith('ADAPTER_TIMEOUT')
    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_adapter_output_size_is_bounded():
    import asyncio
    from app.services.phase5_engine import read_bounded

    stream = asyncio.StreamReader()
    stream.feed_data(b"x" * 1048577)
    stream.feed_eof()
    with pytest.raises(ValueError, match="1 MiB"):
        await read_bounded(stream)


@pytest.mark.asyncio
async def test_real_legacy_environment_acceptance(isolated):
    """Opt-in real configured adapter path; never mocked or counted as PASS without execution."""
    from app.core.config import settings
    from app.services.supervisor_service import supervisor_service

    default_image = "phase5-legacy-fixture@sha256:c4b08a30ed93afecac971193131d4dadcbea7d112915749b7864a38676d481fb"
    default_cmd = '["python", "/adapter.py"]'
    default_scenario = json.dumps({
        "name": "process_deposit",
        "module": "account_service",
        "interface": "process_transaction",
        "behavior": "deposit funds into active corporate account",
        "inputs": {"account_id": 101, "amount": 250.0, "transaction_type": "DEPOSIT"},
        "expected": {
            "account_id": 101,
            "account_number": "ACC-101-CORP",
            "currency": "INR",
            "new_balance": 1250.0,
            "status": "SUCCESS",
        },
    })
    image = os.getenv("PHASE5_LEGACY_IMAGE") or settings.PHASE5_LEGACY_IMAGE or default_image
    command = os.getenv("PHASE5_LEGACY_COMMAND_JSON") or settings.PHASE5_LEGACY_COMMAND_JSON or default_cmd
    scenario_json = os.getenv("PHASE5_ACCEPTANCE_SCENARIO_JSON") or default_scenario

    db, job, owner, storage = isolated
    baseline = await service.capture(
        db,
        job,
        CaptureRequest(
            idempotency_key="real-environment",
            scenarios=[Scenario.model_validate(json.loads(scenario_json))],
        ),
        str(owner.user_id),
    )
    assert baseline["runtime_available"], f"REAL LEGACY ACCEPTANCE FAILED: {baseline['cases'][0].get('limitation')}"
    assert baseline["execution_mode"] == "REAL_CONTAINER"
    assert baseline["cases"][0]["outcome"] == "PASSED"
    assert baseline["cases"][0]["execution_mode"] == "REAL_CONTAINER"
    assert baseline["cases"][0]["reproducibility"] == "DETERMINISTIC"
    assert baseline["cases"][0]["exit_status"] == 0
    assert baseline["cases"][0]["duration_ms"] is not None and baseline["cases"][0]["duration_ms"] >= 0
    artifact = await service.latest(db, job.job_id)
    import hashlib

    assert (
        hashlib.sha256(storage.objects[artifact.storage_path]).hexdigest()
        == baseline["content_hash"]
    )
    review = await service.freeze(
        db,
        job,
        FreezeRequest(
            suite_id=baseline["suite_id"], content_hash=baseline["content_hash"]
        ),
    )
    gate = await db.get(WorkflowGate, uuid.UUID(review["gate_id"]))
    import httpx
    from app.main import app
    from app.core.database import get_db
    from app.api.deps import get_current_user_and_permissions

    async def acceptance_session():
        yield db

    async def acceptance_reviewer():
        return owner, []

    app.dependency_overrides[get_db] = acceptance_session
    app.dependency_overrides[get_current_user_and_permissions] = acceptance_reviewer
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                f"/api/v1/gates/{gate.gate_id}/decision",
                json={
                    "decision": "APPROVED",
                    "rationale": "Human acceptance test reviewer validated real legacy replay",
                    "artifact_hashes": gate.artifact_hashes,
                },
            )
            assert response.status_code == 200, response.text
    finally:
        app.dependency_overrides.clear()
    assert await supervisor_service.require_planning_eligibility(db, job)


@pytest.mark.asyncio
async def test_all_eight_api_authentication_permissions_and_cross_job_idor(
    isolated, monkeypatch
):
    import httpx
    from app.main import app
    from app.api.deps import get_current_user_and_permissions
    from app.core.database import get_db
    from app.models.role import Role

    baseline = await captured(isolated, monkeypatch)
    db, job, owner, _ = isolated
    other = Job(
        name="other private job",
        source_repository="private",
        owner_user_id=owner.user_id,
    )
    db.add(other)
    viewer = User(
        email="member@example.test",
        full_name="Member",
        password_hash="unused",
        role="VIEWER",
    )
    db.add(viewer)
    db.add(Role(role_id="VIEWER", name="Viewer", permissions=[]))
    await db.flush()
    db.add(JobMembership(job_id=job.job_id, user_id=viewer.user_id, role_id="VIEWER"))
    other_case = Case(
        job_id=other.job_id,
        name="private evidence",
        test_layer="UNIT",
        fixture_payload={"private": True},
    )
    db.add(other_case)
    await db.commit()
    job_id, other_id = str(job.job_id), str(other.job_id)
    case_id = baseline["cases"][0]["test_case_id"]

    async def session_override():
        yield db

    async def viewer_auth():
        await db.refresh(viewer)
        return viewer, []

    app.dependency_overrides[get_db] = session_override
    specs = [
        ("POST", "characterization-runs", {"idempotency_key": "auth"}, False),
        ("GET", "test-cases", None, True),
        ("GET", f"case:{case_id}", None, True),
        ("GET", "characterization-report", None, True),
        (
            "POST",
            "g2/freeze",
            {
                "suite_id": baseline["suite_id"],
                "content_hash": baseline["content_hash"],
            },
            False,
        ),
        ("GET", "schema-analysis", None, True),
        ("GET", "data-migration-plan", None, True),
        ("POST", "data-migration-plan/validate", {"tables": []}, False),
    ]
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            for method, endpoint, body, readable in specs:
                own_path = (
                    f"/api/v1/test-cases/{case_id}"
                    if endpoint.startswith("case:")
                    else f"/api/v1/jobs/{job_id}/{endpoint}"
                )
                kwargs = {"json": body} if body is not None else {}
                response = await client.request(method, own_path, **kwargs)
                assert response.status_code == 401, (endpoint, response.text)
            app.dependency_overrides[get_current_user_and_permissions] = viewer_auth
            for method, endpoint, body, readable in specs:
                own_path = (
                    f"/api/v1/test-cases/{case_id}"
                    if endpoint.startswith("case:")
                    else f"/api/v1/jobs/{job_id}/{endpoint}"
                )
                other_path = (
                    f"/api/v1/test-cases/{other_case.test_case_id}"
                    if endpoint.startswith("case:")
                    else f"/api/v1/jobs/{other_id}/{endpoint}"
                )
                kwargs = {"json": body} if body is not None else {}
                response = await client.request(method, own_path, **kwargs)
                expected_code=201 if endpoint=='characterization-runs' else 409 if endpoint=='g2/freeze' else 200
                assert response.status_code == expected_code, (
                    endpoint,
                    response.text,
                )
                assert (
                    await client.request(method, other_path, **kwargs)
                ).status_code == 404
    finally:
        app.dependency_overrides.clear()
