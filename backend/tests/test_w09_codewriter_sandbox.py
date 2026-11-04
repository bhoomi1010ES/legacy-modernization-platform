"""Focused W09 regressions for ChangeSet paths and model request traces."""

import pytest
import hashlib
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

from app.services import phase6_sandbox, phase6_workspace, phase7_engine
from app.services.code_writer import CodeWriterService
from app.services.model_gateway import (
    FakeModelProvider,
    ModelGateway,
    ModelGatewayError,
    RealModelBudgetTracker,
    TransientModelError,
)


@pytest.mark.parametrize(
    "path",
    [
        "../escape.py",
        "/tmp/escape.py",
        "C:/Windows/win.ini",
        "modern/../outside.py",
        "modern/.git/config",
        "modern/.control",
        "modern/CON.txt",
        "modern\\module.py",
        "modern//module.py",
    ],
)
def test_changeset_path_policy_rejects_escape_and_control_paths(tmp_path, path):
    with pytest.raises(ValueError):
        phase6_workspace.safe_target(tmp_path, path, "modern")


@pytest.mark.anyio
async def test_apply_changes_rejects_out_of_scope_instead_of_relocating(tmp_path):
    (tmp_path / "modern").mkdir()
    with pytest.raises(ValueError, match="outside every approved module target"):
        await phase6_workspace.apply_changes(
            tmp_path, {"outside/escape.py": "malicious"}, "modern"
        )
    assert not (tmp_path / "modern" / "outside" / "escape.py").exists()
    assert not (tmp_path / "outside" / "escape.py").exists()


@pytest.mark.anyio
async def test_apply_changes_targets_new_output_workspace_without_source_mutation(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
    (repo / "modern").mkdir()
    (repo / "modern" / "baseline.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "modern/baseline.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "fixture source baseline"], check=True, capture_output=True)
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(phase6_workspace, "ROOT", tmp_path / "converted-output")
    output, branch = await phase6_workspace.prepare(
        repo, "job-fixture", "module-fixture", "attempt-fixture", 1, base
    )
    assert output != repo and output.is_dir()

    result = await phase6_workspace.apply_changes(
        output, {"modern/generated.py": "value = 2\n"}, "modern"
    )

    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    output_head = subprocess.check_output(["git", "-C", str(output), "rev-parse", "HEAD"], text=True).strip()
    staged = subprocess.check_output(["git", "-C", str(output), "diff", "--cached", "--name-only"], text=True)
    source_status = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
    assert head == base
    assert output_head == base
    assert not source_status
    assert not (repo / "modern" / "generated.py").exists()
    assert (output / "modern" / "generated.py").read_text(encoding="utf-8") == "value = 2\n"
    assert branch.startswith("job/job-fixture/module/module-fixture/attempt/")
    assert result["base_sha"] == base
    assert result["diff_hash"] == hashlib.sha256(result["diff"].encode()).hexdigest()
    assert staged.splitlines() == ["modern/generated.py"]
    assert result["candidate_hash"] == await phase6_workspace.git(output, "write-tree")
    assert await phase6_workspace.git(output, "rev-parse", "HEAD") == base
    assert await phase6_workspace.git(output, "rev-list", "--count", "HEAD") == "1"


def test_static_html_presence_cannot_claim_behavioral_equivalence():
    from app.services.phase5_engine import digest

    case = {
        "test_case_id": "case-web-1",
        "expected": {"route": "/checkout", "form": "submits"},
        "side_effects": {"network_requests": 1},
        "normalization": [],
    }
    observed = {
        "checks": [],
        "observations": [{
            "test_case_id": "case-web-1", "command": ["browser", "run"],
            "exit_code": 0, "duration_ms": 1, "stdout": '{"output":{"route":"/checkout","form":"broken"},"side_effects":{"network_requests":0}}',
        }],
        "source_unchanged": True,
    }
    result = phase6_sandbox.assess(observed, [case], [], "fixture", files={"index.html": "<form></form>"})
    assert result["cases"][0]["status"] == "FAIL"
    assert result["passed"] is False


def test_chunked_provider_requests_share_the_attempt_reservation_ceiling():
    writer = CodeWriterService()
    context = {"cost_reservation": 0.12}
    assert writer._request_cost_cap(context, 1) == pytest.approx(0.12)
    # Four source files produce two fallback chunks plus the initial request.
    assert writer._request_cost_cap(context, 4) == pytest.approx(0.04)


def test_build_success_does_not_mask_failed_unit_or_critical_security_check():
    from app.services.phase5_engine import digest

    specs = [
        {"category": "build", "command": ["npm", "run", "build"]},
        {"category": "unit", "command": ["npm", "test"]},
        {"category": "static", "command": ["npm", "run", "lint"]},
        {"category": "security", "command": ["npm", "run", "security"]},
    ]
    data = {
        "checks": [
            {"category": item["category"], "command": item["command"], "duration_ms": 1, "exit_code": (1 if item["category"] in {"unit", "security"} else 0), "started_at": "2026-01-01T00:00:00+00:00", "finished_at": "2026-01-01T00:00:01+00:00", "logs_hash": "sha256:test"}
            for item in specs
        ],
        "observations": [{"test_case_id": "case-1", "command": ["python", "/adapter.py"], "exit_code": 0, "duration_ms": 1, "stdout": '{"output":1,"side_effects":{}}'}],
        "source_unchanged": True,
    }
    case = {"test_case_id": "case-1", "expected": 1, "side_effects": {}, "normalization": []}
    result = phase6_sandbox.assess(data, [case], specs, "fixture")
    assert result["checks"][0]["status"] == "PASS"
    assert result["checks"][1]["status"] == "FAIL"
    assert result["checks"][3]["status"] == "FAIL"
    assert result["passed"] is False


def test_missing_syft_is_blocked_not_an_empty_clean_sbom(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PHASE7_SBOM_TOOL", "syft")
    result = phase7_engine.sbom_evidence({"checks": []}, {"package.json": "{}"})
    assert result["status"] == "BLOCKED"
    assert result["status"] != "GENERATED"


def test_delivery_zip_contains_project_bytes_but_excludes_controls_and_secrets(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('safe')\n", encoding="utf-8")
    (tmp_path / "src" / "logo.bin").write_bytes(b"\x00\x01asset")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=must-not-ship\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("internal", encoding="utf-8")
    (tmp_path / ".rebase_workspace.json").write_text("internal", encoding="utf-8")
    (tmp_path / ".npmrc").write_text("//registry.example/:_authToken=secret", encoding="utf-8")
    (tmp_path / "signing.pem").write_text("PRIVATE KEY", encoding="utf-8")

    archive, manifest_files = phase7_engine.package_project(tmp_path)

    with zipfile.ZipFile(BytesIO(archive)) as zf:
        assert zf.testzip() is None
        assert set(zf.namelist()) == {"src/app.py", "src/logo.bin"}
        assert zf.read("src/logo.bin") == b"\x00\x01asset"
    assert manifest_files == ["src/app.py", "src/logo.bin"]
    assert hashlib.sha256(archive).hexdigest()


def test_delivery_zip_rejects_symlinks(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("do not package", encoding="utf-8")
    try:
        (tmp_path / "escape.txt").symlink_to(outside)
    except OSError as error:
        pytest.skip(f"Symlink creation is unavailable on this Windows worker: {error}")
    with pytest.raises(ValueError, match="symlink"):
        phase7_engine.package_project(tmp_path)


@pytest.mark.anyio
async def test_gateway_reuses_idempotency_key_and_records_prompt_and_actual_model():
    provider = FakeModelProvider(
        [
            TransientModelError("retry"),
            {
                "action": "final",
                "output": {"content": "ok"},
                "provider_metadata": {"model": "actual-model-build-17"},
                "usage": {"input_tokens": 2, "output_tokens": 1, "cost_usd": 0},
            },
        ]
    )
    gateway = ModelGateway(
        {"test": provider}, {"test": {"approved"}}, max_retries=1
    )
    result = await gateway.complete(
        provider="test",
        model="approved",
        request={"prompt": "bounded", "request_id": "local-w09-1", "prompt_revision": "r7"},
    )
    assert provider.requests[0]["_gateway_request_id"] == provider.requests[1]["_gateway_request_id"]
    assert result.response.provider_metadata["request_id"] == "local-w09-1"
    assert result.response.provider_metadata["prompt_revision"] == "r7"
    assert result.response.provider_metadata["actual_model"] == "actual-model-build-17"
    assert result.attempts == 2


@pytest.mark.anyio
async def test_real_lane_reserves_before_call_and_reconciles_cost(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "REAL_MODEL_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MAX_BUDGET_USD", 0.1)
    tracker = RealModelBudgetTracker.get_tracker()
    tracker.reset()
    provider = FakeModelProvider(
        [{"action": "final", "output": {"content": "ok"}, "usage": {"input_tokens": 8, "output_tokens": 4, "cost_usd": 0.075}}]
    )
    gateway = ModelGateway({"openai": provider}, {"openai": {"bounded-test-model"}})
    result = await gateway.complete(
        provider="openai",
        model="bounded-test-model",
        request={"prompt": "bounded unit fixture"},
        max_cost_usd=0.08,
    )
    assert result.response.provider_metadata["cumulative_spend_usd"] == pytest.approx(0.075)
    assert tracker.reserved_usd == 0
    with pytest.raises(ModelGatewayError, match="reserve"):
        await gateway.complete(
            provider="openai",
            model="bounded-test-model",
            request={"prompt": "must not dispatch"},
            max_cost_usd=0.03,
        )
    assert len(provider.requests) == 1
    tracker.reset()


@pytest.mark.anyio
async def test_durable_gateway_ledger_survives_reinstantiation_and_blocks_duplicate_charge(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models.model_gateway import ModelGatewayBudget, ModelGatewayRequest
    from app.services import model_request_ledger as ledger_module

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ModelGatewayBudget.__table__.create)
        await connection.run_sync(ModelGatewayRequest.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ledger_module, "AsyncSessionLocal", session_factory)
    async with session_factory() as session:
        async with session.begin():
            session.add(ModelGatewayBudget(budget_id=1, ceiling_usd=0.1, reserved_usd=0, spent_usd=0))

    ledger = ledger_module.PersistentModelRequestLedger()
    await ledger.reserve(
        request_id="durable-request-1", provider="openai", model="approved",
        prompt_revision="r1", amount_usd=0.08, ceiling_usd=0.1,
    )
    await ledger.begin_attempt("durable-request-1")
    total = await ledger.complete(
        "durable-request-1", actual_model="approved-2026", provider_request_id="provider-1",
        input_tokens=8, output_tokens=4, estimated_cost_usd=0.075,
        billed_cost_usd=0.075, charged_cost_usd=0.075,
    )
    assert total == pytest.approx(0.075)

    # A newly constructed gateway ledger sees the committed request and cannot
    # send it again after an application-process restart.
    restarted_ledger = ledger_module.PersistentModelRequestLedger()
    with pytest.raises(ModelGatewayError, match="duplicate dispatch blocked"):
        await restarted_ledger.reserve(
            request_id="durable-request-1", provider="openai", model="approved",
            prompt_revision="r1", amount_usd=0.08, ceiling_usd=0.1,
        )
    async with session_factory() as session:
        budget = await session.get(ModelGatewayBudget, 1)
        row = await session.get(ModelGatewayRequest, "durable-request-1")
        assert float(budget.reserved_usd) == pytest.approx(0)
        assert float(budget.spent_usd) == pytest.approx(0.075)
        assert row.status == "COMPLETED"
        assert row.provider_request_id == "provider-1"
        assert row.input_tokens == 8 and row.output_tokens == 4

    await restarted_ledger.reserve(
        request_id="durable-request-ambiguous", provider="openai", model="approved",
        prompt_revision="r1", amount_usd=0.02, ceiling_usd=0.1,
    )
    await restarted_ledger.begin_attempt("durable-request-ambiguous")
    await restarted_ledger.fail("durable-request-ambiguous", "TimeoutError", ambiguous=True)
    with pytest.raises(ModelGatewayError, match="Persistent real-model budget"):
        await restarted_ledger.reserve(
            request_id="request-over-ceiling", provider="openai", model="approved",
            prompt_revision="r1", amount_usd=0.01, ceiling_usd=0.1,
        )
    async with session_factory() as session:
        budget = await session.get(ModelGatewayBudget, 1)
        row = await session.get(ModelGatewayRequest, "durable-request-ambiguous")
        assert float(budget.reserved_usd) == pytest.approx(0.02)
        assert row.status == "UNKNOWN"
    await engine.dispose()


@pytest.mark.anyio
async def test_paid_gateway_dispatch_is_persisted_before_provider_call(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.config import settings
    from app.models.model_gateway import ModelGatewayBudget, ModelGatewayRequest
    from app.schemas.agent_runtime import ModelResponse
    from app.services import model_request_ledger as ledger_module

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ModelGatewayBudget.__table__.create)
        await connection.run_sync(ModelGatewayRequest.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ledger_module, "AsyncSessionLocal", session_factory)
    async with session_factory() as session:
        async with session.begin():
            session.add(ModelGatewayBudget(budget_id=1, ceiling_usd=0.1, reserved_usd=0, spent_usd=0))
    monkeypatch.setattr(settings, "REAL_MODEL_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MAX_BUDGET_USD", 0.1)

    class PaidProviderFixture:
        def __init__(self):
            self.calls = 0

        async def complete(self, *, model, request):
            self.calls += 1
            return ModelResponse(
                action="final", output={"content": "bounded"},
                provider_request_id="provider-charge-1",
                provider_metadata={"model": "approved-model-v2"},
                usage={"input_tokens": 2, "output_tokens": 1, "cost_usd": 0.04,
                       "estimated_cost": 0.04, "billed_cost": 0.04},
            )

    provider = PaidProviderFixture()
    gateway = ModelGateway({"openai": provider}, {"openai": {"approved-model"}})
    result = await gateway.complete(
        provider="openai", model="approved-model",
        request={"request_id": "persist-before-dispatch", "prompt_revision": "r9",
                 "prompt": "bounded", "ledger_context": {"job_id": None, "run_id": None}},
        max_cost_usd=0.08,
    )
    assert result.response.provider_metadata["cumulative_spend_usd"] == pytest.approx(0.04)
    assert provider.calls == 1
    with pytest.raises(ModelGatewayError, match="duplicate dispatch blocked"):
        await gateway.complete(
            provider="openai", model="approved-model",
            request={"request_id": "persist-before-dispatch", "prompt_revision": "r9", "prompt": "bounded"},
            max_cost_usd=0.08,
        )
    assert provider.calls == 1
    async with session_factory() as session:
        row = await session.get(ModelGatewayRequest, "persist-before-dispatch")
        budget = await session.get(ModelGatewayBudget, 1)
        assert row.status == "COMPLETED"
        assert row.provider_request_id == "provider-charge-1"
        assert row.actual_model == "approved-model-v2"
        assert row.prompt_revision == "r9"
        assert float(row.reserved_usd) == pytest.approx(0.08)
        assert float(row.billed_cost_usd) == pytest.approx(0.04)
        assert float(budget.reserved_usd) == pytest.approx(0)
        assert float(budget.spent_usd) == pytest.approx(0.04)

    class MissingUsageProvider:
        async def complete(self, *, model, request):
            return ModelResponse(
                action="final", output={"content": "unmetered"},
                provider_metadata={"model": model, "usage_reported": False},
            )

    missing_gateway = ModelGateway(
        {"openai": MissingUsageProvider()}, {"openai": {"approved-model"}}
    )
    with pytest.raises(ModelGatewayError, match="no usage"):
        await missing_gateway.complete(
            provider="openai", model="approved-model",
            request={"request_id": "missing-usage-request", "prompt_revision": "r9", "prompt": "bounded"},
            max_cost_usd=0.05,
        )
    async with session_factory() as session:
        row = await session.get(ModelGatewayRequest, "missing-usage-request")
        budget = await session.get(ModelGatewayBudget, 1)
        assert row.status == "UNKNOWN"
        assert float(budget.reserved_usd) == pytest.approx(0.05)
    await engine.dispose()


@pytest.mark.anyio
async def test_unverified_runtime_setting_cannot_claim_isolation(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SANDBOX_RUNTIME", "docker-unverified")
    with pytest.raises(ValueError, match="unverified"):
        await phase6_sandbox.verified_runtime_args()


@pytest.mark.anyio
async def test_phase5_docker_unavailable_never_executes_adapter_on_host(monkeypatch):
    import asyncio
    from app.core.config import settings
    from app.schemas.phase5 import Scenario
    from app.services import phase5_engine
    from unittest.mock import AsyncMock

    monkeypatch.setattr(settings, "PHASE5_LEGACY_IMAGE", "fixture@sha256:" + "a" * 64)
    monkeypatch.setattr(settings, "PHASE5_LEGACY_COMMAND_JSON", '["python", "/adapter.py"]')
    monkeypatch.setenv("PHASE5_LEGACY_IMAGE", "fixture@sha256:" + "a" * 64)
    monkeypatch.setenv("PHASE5_LEGACY_COMMAND_JSON", '["python", "/adapter.py"]')
    monkeypatch.setattr(phase6_sandbox, "verified_runtime_args", AsyncMock(return_value=[]))

    async def docker_missing(*args, **kwargs):
        raise FileNotFoundError("docker")

    async def host_execution_forbidden(*args, **kwargs):
        raise AssertionError("Uploaded adapter ran on the API host")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", docker_missing)
    from app.core import subprocesses

    monkeypatch.setattr(subprocesses, "run_subprocess_async", host_execution_forbidden)
    result = await phase5_engine.replay(
        Scenario(name="hostile", module="m", interface="GET", behavior="probe")
    )
    assert result["available"] is False
    assert result["execution_mode"] == "UNAVAILABLE"
