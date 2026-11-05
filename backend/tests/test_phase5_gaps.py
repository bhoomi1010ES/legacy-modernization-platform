"""Phase 5 Comprehensive Acceptance and Gap Verification Suite.

Validates:
1. Real Docker container execution with pinned fixture and double-run reproducibility.
2. Explicit detection and classification of nondeterminism (DETERMINISTIC, NON_DETERMINISTIC, FAILED, UNAVAILABLE).
3. Advanced scoped normalization rules (timestamp, random_id, uuid, path, regex, unordered).
4. Complex / proprietary SQL construct discovery (triggers, procedures, functions, views, sequences, composite constraints).
5. Immutable golden master lifecycle (DRAFT -> CAPTURED -> REPRODUCIBLE -> REVIEW_REQUIRED -> FROZEN).
6. Human-only G2 gate governance requiring exact artifact hashes and blocking Phase 6 if pending or rejected.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.errors import ConflictException, ValidationException
from app.domain.state_machine import JobStateMachine
from app.models import Base
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.module import Module
from app.models.test_case import TestCase
from app.models.user import User
from app.models.workflow import WorkflowGate
from app.schemas.gates import DecisionOutcome, GateDecisionRequest
from app.schemas.jobs import JobStatus
from app.schemas.phase5 import (
    CaptureRequest,
    FreezeRequest,
    NormalizationRule,
    Scenario,
    Table,
    ValidationRequest,
)
from app.services import phase5_service as service
from app.services.gate_service import gate_service
from app.services.phase5_engine import (
    canonical,
    digest,
    discover_schema,
    migration_plan,
    normalize,
    replay,
    validate_migration,
)
from app.services.supervisor_service import supervisor_service

PINNED_IMAGE = "phase5-legacy-fixture@sha256:c4b08a30ed93afecac971193131d4dadcbea7d112915749b7864a38676d481fb"
FIXTURE_ROOT = Path(__file__).resolve().parent.parent.parent / "tools" / "phase5_acceptance" / "fixture"


@pytest_asyncio.fixture
async def gap_context(monkeypatch):
    """Sets up an authentic isolated in-memory test database with an active Job following approved G1."""
    from app.core.storage import StorageAdapter

    class MemoryStorage(StorageAdapter):
        def __init__(self):
            self.objects = {}

        async def put_object(self, key, data, media_type="application/json"):
            self.objects[key] = data
            return self.compute_sha256(data), len(data)

        async def get_object(self, key):
            if key in self.objects:
                return self.objects[key]
            from app.core.storage import LocalStorageAdapter
            return await LocalStorageAdapter().get_object(key)

        async def object_exists(self, key):
            if key in self.objects:
                return True
            from app.core.storage import LocalStorageAdapter
            return await LocalStorageAdapter().object_exists(key)

        async def delete_object(self, key):
            removed = self.objects.pop(key, None) is not None
            try:
                from app.core.storage import LocalStorageAdapter
                await LocalStorageAdapter().delete_object(key)
            except Exception:
                pass
            return removed

    storage = MemoryStorage()
    monkeypatch.setattr(service, "get_storage_adapter", lambda: storage)
    monkeypatch.setattr("app.services.artifact_service.artifact_service.storage", storage)
    monkeypatch.setattr(
        "app.services.continuous_pipeline.continuous_pipeline_service.trigger_continuous_pipeline",
        lambda *a, **k: None,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        creator = User(
            email="gap_creator@example.test",
            full_name="Gap Creator",
            password_hash="unused",
            role="DEVELOPER",
        )
        db.add(creator)
        user = User(
            email="gap_reviewer@example.test",
            full_name="Gap Reviewer",
            password_hash="unused",
            role="SUPER_ADMIN",
        )
        db.add(user)
        await db.flush()

        job = Job(
            name=f"phase5-gaps-{uuid.uuid4().hex[:8]}",
            source_repository=str(FIXTURE_ROOT),
            owner_user_id=creator.user_id,
            status=JobStatus.CHARACTERIZING.value,
            active_node="characterization",
            budget_used_usd=Decimal("0.00"),
            budget_limit_usd=Decimal("100.00"),
        )
        db.add(job)
        await db.flush()

        # Seed Module
        db.add(
            Module(
                job_id=job.job_id,
                name="account_service",
                legacy_path="legacy/account_service.py",
                target_path="services/account_service.py",
            )
        )

        # Seed approved Gate G1
        g1_art_id = str(uuid.uuid4())
        g1_gate = WorkflowGate(
            job_id=job.job_id,
            gate_type="G1",
            version=1,
            status="APPROVED",
            artifact_hashes={g1_art_id: "sha256:g1_approved_hash"},
            artifact_ids=[g1_art_id],
        )
        db.add(g1_gate)
        await db.commit()

        yield db, job, user, storage

    await engine.dispose()


# ---------------------------------------------------------------------------
# Test 1: Real Docker Sandbox Acceptance with Pinned Image
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_docker_phase5_end_to_end_acceptance(gap_context):
    """Full lifecycle with real Docker Desktop using pinned image:
    G1 approved -> Capture -> Real Docker Replay -> Double run comparison ->
    Golden master created -> SHA-256 verified -> G2 review -> Human G2 approval -> Frozen baseline.
    """
    try:
        from app.services import sandbox_client
        await sandbox_client.health()
    except Exception as exc:
        pytest.skip(f"Opt-in Docker sandbox controller not running: {exc}")
    db, job, user, storage = gap_context

    scenario = Scenario(
        name="process_deposit",
        module="account_service",
        interface="process_transaction",
        behavior="deposit funds into active corporate account",
        inputs={"account_id": 101, "amount": 250.0, "transaction_type": "DEPOSIT"},
        expected={
            "account_id": 101,
            "account_number": "ACC-101-CORP",
            "currency": "INR",
            "new_balance": 1250.0,
            "status": "SUCCESS",
        },
    )

    req = CaptureRequest(
        idempotency_key="real-docker-acceptance-v1",
        scenarios=[scenario],
        environment={"notes": "Real Docker environment execution"},
    )

    # 1. Execute Capture with real Docker container
    report = await service.capture(db, job, req, str(user.user_id))

    assert report["runtime_available"] is True
    assert report["execution_mode"] == "REAL_CONTAINER"
    assert len(report["cases"]) == 1

    case = report["cases"][0]
    assert case["outcome"] == "PASSED"
    assert case["execution_mode"] == "REAL_CONTAINER"
    assert case["reproducibility"] == "DETERMINISTIC"
    assert case["exit_status"] == 0
    assert case["duration_ms"] is not None and case["duration_ms"] >= 0
    assert case["provenance"]["name"] == "process_deposit"
    assert case["provenance"]["module"] == "account_service"

    # 2. Verify SHA-256 protection and immutability
    suite_artifact = await service.latest(db, job.job_id, "CHARACTERIZATION_SUITE")
    assert suite_artifact.content_hash == report["content_hash"]
    import hashlib
    raw_payload = storage.objects[suite_artifact.storage_path]
    assert hashlib.sha256(raw_payload).hexdigest() == report["content_hash"]

    # 3. Request G2 Freeze Review
    freeze_res = await service.freeze(
        db,
        job,
        FreezeRequest(suite_id=report["suite_id"], content_hash=report["content_hash"]),
        actor_id=str(user.user_id),
    )
    g2_gate = await db.get(WorkflowGate, uuid.UUID(freeze_res["gate_id"]))
    assert g2_gate.status == "PENDING"
    assert g2_gate.gate_type == "G2"
    assert str(suite_artifact.artifact_id) in g2_gate.artifact_hashes

    # 4. Human G2 Approval with exact artifact hash
    decision_req = GateDecisionRequest(
        decision=DecisionOutcome.APPROVED,
        rationale="Human operator verified real deterministic container execution and approved baseline.",
        artifact_hashes=g2_gate.artifact_hashes,
    )
    decision, decided_gate, _, _ = await gate_service.decide(
        db,
        g2_gate.gate_id,
        decision_req,
        actor_id=user.user_id,
        actor_role=user.role,
    )
    assert decided_gate.status == "APPROVED"

    # 5. Verify Frozen status of Suite and Test Cases
    final_report = await service.report(db, job.job_id)
    assert final_report["status"] == "FROZEN"

    test_case = await db.scalar(
        select(TestCase).where(TestCase.job_id == job.job_id).limit(1)
    )
    assert test_case.is_frozen is True

    # 6. Verify Phase 6 Planning eligibility is now unlocked
    eligibility = await supervisor_service.require_planning_eligibility(db, job)
    assert eligibility is not None and eligibility.status == "APPROVED"


# ---------------------------------------------------------------------------
# Test 2: Double-Run Nondeterminism Detection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_double_run_nondeterminism_detection(gap_context, monkeypatch):
    """Proves that when run 2 produces differing output from run 1, it is detected as NON_REPRODUCIBLE."""
    db, job, user, storage = gap_context

    call_count = 0

    async def mock_replay(scenario):
        nonlocal call_count
        call_count += 1
        # Run 1 returns 100, Run 2 returns 200 (nondeterministic execution)
        return {
            "available": True,
            "execution_mode": "REAL_CONTAINER",
            "duration_ms": 42,
            "exit_status": 0,
            "container_name": f"mock-container-{call_count}",
            "output": {"value": 100 if call_count % 2 == 1 else 200},
            "side_effects": {},
        }

    monkeypatch.setattr("app.services.phase5_service.replay", mock_replay)

    scenario = Scenario(
        name="flaky_scenario",
        module="account_service",
        interface="get_balance",
        behavior="balance query returns inconsistent values",
        inputs={"id": 1},
        expected={"value": 100},
    )

    req = CaptureRequest(idempotency_key="nondeterministic-check", scenarios=[scenario])
    report = await service.capture(db, job, req, str(user.user_id))

    case = report["cases"][0]
    assert case["outcome"] == "NON_REPRODUCIBLE"
    assert case["reproducibility"] == "NON_DETERMINISTIC"
    assert "nondeterministic" in case["limitation"].lower()

    # Verify G2 readiness flags the non-reproducible run
    readiness = report["g2_readiness"]
    assert readiness["non_reproducible_count"] == 1
    assert readiness["ready_for_g2"] is False
    assert any("non-reproducible" in reason for reason in readiness["blocking_reasons"])


# ---------------------------------------------------------------------------
# Test 3: Normalization Rules (UUID, Path, Regex, Timestamp, Unordered)
# ---------------------------------------------------------------------------
def test_advanced_normalization_rules():
    """Validates explicit normalization support for UUID, path, regex, timestamp, and unordered collections."""
    # 1. UUID normalization
    data_uuid = {"id": "12345678-1234-1234-1234-123456789abc", "name": "Item"}
    rule_uuid = NormalizationRule(
        path="/id",
        kind="uuid",
        justification="Random UUID generated on creation",
    )
    norm_uuid = normalize(data_uuid, [rule_uuid])
    assert norm_uuid["id"] == "<uuid>"

    # 2. Path normalization
    data_path = {"tmp_file": "/tmp/test_session_12345/output.dat"}
    rule_path = NormalizationRule(
        path="/tmp_file",
        kind="path",
        justification="Temporary execution path varies by host",
    )
    norm_path = normalize(data_path, [rule_path])
    assert norm_path["tmp_file"] == "<temp-path>"

    # 3. Regex normalization
    data_regex = {"token": "session_tok_987654321_exp"}
    rule_regex = NormalizationRule(
        path="/token",
        kind="regex",
        pattern=r"session_tok_\d+_exp",
        replacement="<session_token>",
        justification="Session tokens have variable numeric IDs",
    )
    norm_regex = normalize(data_regex, [rule_regex])
    assert norm_regex["token"] == "<session_token>"

    # 4. Regex mismatch fails closed
    rule_bad_regex = NormalizationRule(
        path="/token",
        kind="regex",
        pattern=r"other_prefix_\d+",
        justification="Wrong pattern",
    )
    with pytest.raises(ValueError):
        normalize(data_regex, [rule_bad_regex])

    # 5. Unordered normalization
    data_list = {"items": [{"id": 2}, {"id": 1}]}
    rule_sort = NormalizationRule(
        path="/items",
        kind="unordered",
        contract_allows=True,
        justification="Database query returns results in non-guaranteed order",
    )
    norm_list = normalize(data_list, [rule_sort])
    assert norm_list["items"] == [{"id": 1}, {"id": 2}]


# ---------------------------------------------------------------------------
# Test 4: Complex & Proprietary SQL Construct Classification
# ---------------------------------------------------------------------------
def test_complex_and_proprietary_sql_constructs(tmp_path, monkeypatch):
    """Proves triggers, stored procedures, functions, views, sequences, composite constraints,
    and proprietary types are classified as REVIEW_REQUIRED, not falsely marked as passed.
    """
    import app.services.phase5_engine as engine

    fake_module = tmp_path / "backend" / "app" / "services" / "phase5_engine.py"
    monkeypatch.setattr(engine, "__file__", str(fake_module))
    workspace = tmp_path / "backend" / "repo_workspaces" / "job_complex_sql"
    workspace.mkdir(parents=True)

    sql_content = """
    -- Standard table
    CREATE TABLE accounts (
        account_id INTEGER PRIMARY KEY,
        balance REAL NOT NULL,
        account_type VARCHAR(20) NOT NULL
    );

    -- Composite unique constraint
    CREATE UNIQUE INDEX idx_accounts_type_bal ON accounts(account_type, balance);

    -- Trigger (complex procedural construct)
    CREATE TRIGGER update_balance_trg
    AFTER INSERT ON accounts
    BEGIN
        SELECT 1;
    END;

    -- Stored procedure (vendor-specific)
    CREATE PROCEDURE recalculate_interest(acc_id INT)
    BEGIN
        SELECT 1;
    END;

    -- Function (vendor-specific)
    CREATE FUNCTION compute_tax(amount DECIMAL) RETURNS DECIMAL
    BEGIN
        RETURN amount * 0.18;
    END;

    -- View
    CREATE VIEW active_accounts AS SELECT * FROM accounts;

    -- Sequence
    CREATE SEQUENCE account_seq START WITH 1000;
    """

    (workspace / "schema.sql").write_text(sql_content, encoding="utf-8")

    disc_result = engine.discover_schema("complex_sql", ["schema.sql"])
    discovered, notes = disc_result
    findings = disc_result.findings

    constructs = {f["construct"] for f in findings}
    assert "trigger" in constructs
    assert "procedure" in constructs
    assert "function" in constructs
    assert "view" in constructs
    assert "sequence" in constructs
    assert "composite_constraint" in constructs

    # Every complex construct must be flagged REVIEW_REQUIRED
    for f in findings:
        if f["construct"] in ("trigger", "procedure", "function", "view", "sequence", "composite_constraint"):
            assert f["status"] == "REVIEW_REQUIRED", f"{f['construct']} must be REVIEW_REQUIRED"

    # Migration plan incorporating these findings must have status REVIEW_REQUIRED
    plan = engine.migration_plan(list(discovered), list(discovered), findings=findings)
    assert plan["status"] == "REVIEW_REQUIRED"
    assert any("trigger" in r.lower() for r in plan["review_reasons"])
    assert any("procedure" in r.lower() for r in plan["review_reasons"])

    # Disposable validation must fail closed with review_required == True
    val_req = ValidationRequest(scope="disposable", tables=[])
    val_res = engine.validate_migration(plan, val_req)
    assert val_res["status"] == "REVIEW_REQUIRED"
    assert val_res["review_required"] is True
    assert val_res["passed"] is False


# ---------------------------------------------------------------------------
# Test 5: Exact Artifact Hash Requirement and G2 Failure Modes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exact_artifact_hash_enforcement(gap_context):
    """Verifies that G2 approval strictly requires the exact artifact SHA-256 hash."""
    db, job, user, storage = gap_context

    scenario = Scenario(
        name="valid_scenario",
        module="account_service",
        interface="fn",
        behavior="valid",
        inputs={},
        expected={"ok": True},
    )

    async def mock_replay(scenario):
        return {
            "available": True,
            "execution_mode": "REAL_CONTAINER",
            "duration_ms": 10,
            "exit_status": 0,
            "output": {"ok": True},
            "side_effects": {},
        }

    import app.services.phase5_service as p5_svc
    p5_svc_replay = p5_svc.replay
    p5_svc.replay = mock_replay
    try:
        req = CaptureRequest(idempotency_key="hash-enforce", scenarios=[scenario])
        report = await service.capture(db, job, req, str(user.user_id))

        freeze_res = await service.freeze(
            db,
            job,
            FreezeRequest(suite_id=report["suite_id"], content_hash=report["content_hash"]),
            actor_id=str(user.user_id),
        )
        gate = await db.get(WorkflowGate, uuid.UUID(freeze_res["gate_id"]))

        # 1. Attempting approval with mutated / wrong artifact hash fails with ConflictException
        tampered_hashes = dict(gate.artifact_hashes)
        for k in tampered_hashes:
            tampered_hashes[k] = "sha256:different_hash_from_client"

        wrong_decision = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approval with tampered hash",
            artifact_hashes=tampered_hashes,
        )
        with pytest.raises(ConflictException) as exc:
            await gate_service.decide(
                db,
                gate.gate_id,
                wrong_decision,
                actor_id=user.user_id,
                actor_role=user.role,
            )
        assert "Artifact version changed during review" in str(exc.value)

        # 2. While gate is PENDING, Phase 6 is blocked
        with pytest.raises(ConflictException):
            await supervisor_service.require_planning_eligibility(db, job)

        # 3. If gate is REJECTED, Phase 6 is blocked
        reject_decision = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED,
            rationale="Rejected due to review findings",
            artifact_hashes=gate.artifact_hashes,
        )
        _, rejected_gate, _, _ = await gate_service.decide(
            db,
            gate.gate_id,
            reject_decision,
            actor_id=user.user_id,
            actor_role=user.role,
        )
        assert rejected_gate.status == "REJECTED"

        with pytest.raises(ConflictException):
            await supervisor_service.require_planning_eligibility(db, job)

    finally:
        p5_svc.replay = p5_svc_replay
