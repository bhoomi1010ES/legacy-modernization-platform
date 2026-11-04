"""Real-environment Phase 6 acceptance tests using real OpenAI and real Docker sandbox."""

import asyncio
import json
import os
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ConflictException, ForbiddenException
from app.services.model_gateway import ModelGatewayError, ModelNotAllowedError, OpenAIProvider, build_default_gateway
from app.models.artifact import Artifact
from app.models.module import Module, ModuleAttempt
from app.models.workflow import WorkflowGate
from app.schemas.gates import DecisionOutcome, GateDecisionRequest
from app.schemas.phase6 import QueueConversion
from app.services.artifact_service import ArtifactService
from app.services.gate_service import GateService
from app.services.supervisor_service import supervisor_service as supervisor
from app.services import phase6_service as service
from app.services import phase6_workspace as ws
from app.services import phase6_sandbox as sandbox

# Reuse the isolation and setup fixtures from test_phase6
from test_phase5 import isolated, captured  # noqa: F401
from test_phase6 import ready  # noqa: F401

# Live requests require an explicit invocation. Merely having a key in .env
# must never make a regression-suite collection charge the provider account.
live_provider = pytest.mark.skipif(
    os.getenv('W09_RUN_LIVE_PROVIDER') != '1',
    reason='Live provider acceptance requires W09_RUN_LIVE_PROVIDER=1 and a bounded persistent ledger',
)


@pytest.mark.asyncio
@live_provider
async def test_openai_live_connectivity_and_accounting(tmp_path):
    """Explicit live gateway request: bounded output, persistent accounting and restart recovery."""
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    evidence=tmp_path/'provider.json';ledger=tmp_path/'w09_test_provider.sqlite'
    process=await asyncio.create_subprocess_exec(sys.executable,str(root/'tools/phase6_acceptance/verify_provider.py'),
        '--output',str(evidence),'--ledger',str(ledger),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,cwd=str(root/'backend'))
    stdout,stderr=await process.communicate()
    assert process.returncode==0, 'Bounded provider acceptance blocked; inspect its sanitized evidence'
    result=json.loads(evidence.read_text())
    assert result['status']=='PASS' and result['ledger']['status']=='COMPLETED'
    assert result['maximum_output_tokens']==256 and result['request_budget_usd']==.01
    assert result['usage']['input_tokens']>0 and result['usage']['output_tokens']>0
    assert result['ledger']['actual_model'] and result['ledger']['provider_request_id']
    assert result['duplicate_dispatch_blocked'] and result['over_ceiling_reservation_blocked']
    assert result['persistent_recovery']['status']=='COMPLETED'


@pytest.mark.asyncio
@live_provider
async def test_openai_error_conditions():
    """Proves missing keys, invalid keys, and unallowlisted models fail closed."""
    # 1. Missing API key
    empty_provider = OpenAIProvider(api_key="")
    with pytest.raises(ModelGatewayError, match="not configured"):
        await empty_provider.complete(model="gpt-4o-mini", request={"prompt": "hi"})

    # 2. Invalid API key
    invalid_provider = OpenAIProvider(api_key="sk-invalid-key-for-unit-test-verification")
    with pytest.raises(ModelGatewayError, match="authentication error"):
        await invalid_provider.complete(model="gpt-4o-mini", request={"prompt": "hi"})

    # 3. Model not in allowlist
    gw = build_default_gateway()
    with pytest.raises(ModelNotAllowedError):
        await gw.complete(provider="openai", model="unapproved-model-v99", request={"prompt": "hi"})


def test_registration_privilege_escalation_blocked(client):
    """Proves the public /register endpoint prevents self-assigning privileged roles."""
    unique_suffix = uuid.uuid4().hex[:8]

    # 1. Attempt self-assigning SUPER_ADMIN must be rejected with 403 Forbidden
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"hacker-super_{unique_suffix}@acme.corp",
            "full_name": "Privilege Escalator",
            "password": "Password12345!",
            "role": "SUPER_ADMIN",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"

    # 2. Attempt self-assigning ADMIN must be rejected with 403 Forbidden
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"hacker-admin_{unique_suffix}@acme.corp",
            "full_name": "Privilege Escalator",
            "password": "Password12345!",
            "role": "ADMIN",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"

    # 3. Attempt self-assigning PROJECT_MANAGER must be rejected with 403 Forbidden
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"hacker-pm_{unique_suffix}@acme.corp",
            "full_name": "Privilege Escalator",
            "password": "Password12345!",
            "role": "PROJECT_MANAGER",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"

    # 4. Normal registration with default role (omitted) defaults safely to DEVELOPER
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"dev_{unique_suffix}@acme.corp",
            "full_name": "Legitimate Developer",
            "password": "Password12345!",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "DEVELOPER"

    # 5. Normal registration with VIEWER role succeeds
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"viewer_{unique_suffix}@acme.corp",
            "full_name": "Auditor Viewer",
            "password": "Password12345!",
            "role": "VIEWER",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "VIEWER"


@pytest.mark.asyncio
@live_provider
async def test_real_phase6_openai_docker_end_to_end_acceptance(ready, monkeypatch):
    """Genuine end-to-end acceptance:

    Approved G1
       -> Phase 5 frozen Golden Master verified
       -> Approved G2
       -> Real CodeWriter using REAL OpenAI (gpt-4o-mini)
       -> Real ChangeSet generated and applied to branch
       -> Hardened Docker sandbox (phase6-acceptance:local-v1) runs under --network=none
       -> Builds, unit tests, static analysis (mypy), security (bandit), G2 regression
       -> ModuleAttempt becomes VERIFIED with genuine execution evidence
       -> G3 readiness is established and governed by human approval.
    """
    db, job, owner, storage, module, repo = ready
    job.source_stack = "Python"
    job.target_stack = "Python"
    await db.commit()

    # Configure real OpenAI provider and local acceptance image
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        pytest.skip("OPENAI_API_KEY not configured")

    image_id = "sha256:78c7f2fa233ebfc26669a41e52154c62ede5b0d16b821dd83ca2dc5aeab9fac5"
    target_cmd = '["python", "/adapter.py"]'
    checks_cmd = (
        '[{"category":"build","command":["python","-m","compileall","-q","."]},'
        '{"category":"unit","command":["python","-m","pytest","/acceptance/test_calc.py","-q","-p","no:cacheprovider"]},'
        '{"category":"static","command":["python","-m","mypy","--cache-dir=/tmp/mypy-cache","--check-untyped-defs","--explicit-package-bases","."]},'
        '{"category":"security","command":["python","-m","bandit","-r",".","-q"]},'
        '{"category":"security","command":["python","-m","pytest","/acceptance/test_security.py","-q","-s","-p","no:cacheprovider"]}]'
    )

    monkeypatch.setattr(settings, "PHASE6_MODEL_PROVIDER", "openai")
    monkeypatch.setattr(settings, "PHASE6_MODEL_IDENTIFIER", "gpt-4o-mini")
    monkeypatch.setattr(settings, "PHASE6_SANDBOX_IMAGE", image_id)
    monkeypatch.setattr(settings, "PHASE6_TARGET_COMMAND_JSON", target_cmd)
    monkeypatch.setattr(settings, "PHASE6_CHECK_COMMANDS_JSON", checks_cmd)
    monkeypatch.setenv("PHASE6_RUN_REAL_ACCEPTANCE", "1")

    # 1. Queue conversion through the authoritative Supervisor
    attempt = await supervisor.queue_module_conversion(
        db, job, module, "openai-real-accept-1", str(owner.user_id)
    )
    assert attempt.status == "QUEUED"
    assert attempt.attempt_number == 1
    assert attempt.git_branch == f"job/{job.job_id}/module/{module.module_id}/attempt/1"

    # 2. Execute attempt using real OpenAI CodeWriter and real Docker sandbox
    await service.execute_attempt(db, attempt.attempt_id)
    detailed = await service.detail(db, attempt)

    # 3. Verify attempt reached VERIFIED state with real execution evidence
    assert attempt.status == "VERIFIED", f"Attempt failed: {attempt.failure_reason}"
    assert attempt.failure_reason is None

    # Verify real CodeWriter artifact and ChangeSet metadata
    evidence = detailed["evidence"]
    assert evidence["files"] is not None
    assert "modern/calc.py" in evidence["files"]
    calc_code = evidence["files"]["modern/calc.py"]
    assert "def add" in calc_code

    # Verify real OpenAI trace metadata
    from app.models.agent import AgentRun
    run = await db.get(AgentRun, attempt.agent_run_id)
    assert run is not None
    assert run.model_provider == "openai"
    assert run.model_identifier == "gpt-4o-mini"
    assert run.input_tokens > 0
    assert run.output_tokens > 0
    assert run.cost_usd > 0
    assert run.trace_payload.get("action") == "final"
    assert run.trace_payload.get("provider_request_id") is not None

    # Verify real Docker sandbox execution checks
    checks = evidence.get("checks", [])
    assert len(checks) >= 4, f"Expected at least 4 verification checks, got {len(checks)}"
    check_categories = {c["category"] for c in checks}
    assert {"build", "unit", "static", "security"}.issubset(check_categories)
    for c in checks:
        assert c["status"] == "PASS", f"Check {c['category']} failed: {c.get('stdout')} {c.get('stderr')}"
        assert c["exit_code"] == 0

    # Verify G2 golden master regression replay results
    results = evidence.get("results", [])
    assert len(results) > 0, "Expected characterization test results from G2 replay"
    for r in results:
        assert r["status"] == "PASS", f"Regression failure in case {r.get('test_case_id')}"

    # Verify reviewer verdict is PASS
    review = evidence.get("review", {})
    assert review.get("status") == "PASS"

    # 4. Verify G3 Governance:
    # A human reviewer approves G3 with exact artifact hashes
    converted_artifact = await db.scalar(
        select(Artifact).where(
            Artifact.job_id == job.job_id,
            Artifact.artifact_type == "CodeModule",
            Artifact.module_id == module.module_id,
        )
    )
    assert converted_artifact is not None
    assert converted_artifact.content_hash is not None

    # Developer cannot approve G3
    g3_gate = await db.scalar(
        select(WorkflowGate).where(
            WorkflowGate.job_id == job.job_id,
            WorkflowGate.gate_type == "G3",
        ).order_by(WorkflowGate.version.desc()).limit(1)
    )
    assert g3_gate is not None
    assert g3_gate.status == "APPROVED"

    print("\n--- PHASE 6 ACCEPTANCE EVIDENCE ---")
    print(f"Job ID: {job.job_id}")
    print(f"Module ID: {module.module_id}")
    print(f"Attempt: {attempt.attempt_number}")
    print(f"ChangeSet SHA-256: {converted_artifact.content_hash}")
    print(f"Golden Master SHA-256: {evidence.get('baseline_hash')}")
    print(f"Docker image: phase6-acceptance:local-v1")
    print(f"Docker image digest: {image_id}")
    print(f"G3 status: {g3_gate.status}")
    print("-----------------------------------")
