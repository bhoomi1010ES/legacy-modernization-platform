"""Verification test suite for W07: Real Characterizer and Schema/Data Execution (P0/P1).

Covers:
- DATA-01: Truthful SchemaDataAgent without fabricated LLM cost ($18.50) or tokens (8400),
           evidence-driven schema discovery without invented tables (users/orders/items),
           and real PostgreSQL 16 disposable migration validation.
- TEST-05: Real environment tool probes for FeasibilityAgent (missing tools report BLOCKED/MISSING).
- Real static-web characterization: distinguishes BUILD_PASS, DOM_PASS, BEHAVIOR_PASS, NOT_RUN;
  never manufactures fake PASS on missing workspace or failed DOM element assertions.
- Decoupled Characterizer and SchemaData AgentRuns with distinct IDs and artifact refs.
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import shutil
import uuid

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.agent import AgentRun
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job
from app.schemas.jobs import JobStatus
from app.models.user import User
from app.models.workflow import WorkflowGate
from app.schemas.phase5 import CaptureRequest, NormalizationRule, Scenario
from app.services.artifact_service import artifact_service
from app.services.feasibility_agent import FeasibilityAgent
from app.services.phase5_engine import replay_web_static
from app.services.phase5_service import capture
from app.services.schema_data_agent import (
    schema_data_service,
    validate_target_schema_disposable,
)


async def _get_or_create_admin(db) -> User:
    user = await db.scalar(
        select(User).where(User.email == "admin@example.com").limit(1)
    )
    if not user:
        user = User(
            user_id=uuid.uuid4(),
            email="admin@example.com",
            password_hash="argon2id$mocked",
            role="SUPER_ADMIN",
            full_name="Admin User",
            status="ACTIVE",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# 1. DATA-01: Empty Schema Produces NO_SCHEMA_DETECTED without Fabricated Tables
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_schema_produces_no_schema_detected_and_never_fabricates(tmp_path):
    """Evidence-driven discovery: empty repository yields NO_SCHEMA_DETECTED and 0 tables.

    Explicitly verifies that prohibited fake tables (users, orders, items) are NOT present.
    """
    empty_ws = tmp_path / "empty_ws"
    empty_ws.mkdir()

    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)
        job = Job(
            job_id=uuid.uuid4(),
            name=f"test-w07-noschema-{uuid.uuid4().hex[:6]}",
            source_repository=str(empty_ws),
            owner_user_id=admin.user_id,
            status=JobStatus.CHARACTERIZING.value,
            budget_used_usd=Decimal("0.00"),
        )
        db.add(job)
        await db.commit()

        schema_artifact = await schema_data_service.execute_schema_data_analysis(db, job)
        assert schema_artifact is not None
        assert schema_artifact.producing_agent == "SchemaDataAgent"

        # Read artifact payload
        raw_bytes = await artifact_service.storage.get_object(schema_artifact.storage_path)
        payload = json.loads(raw_bytes.decode("utf-8"))

        assert payload["status"] == "NO_SCHEMA_DISCOVERED"
        assert payload["schema_status"] == "NO_SCHEMA_DETECTED"
        assert payload["tables_analyzed_count"] == 0
        assert len(payload["tables"]) == 0

        # DATA-01 Assertion: PROHIBITED synthetic tables were NOT fabricated
        table_names = [t.get("table_name") if isinstance(t, dict) else t for t in payload["tables"]]
        assert "users" not in table_names
        assert "orders" not in table_names
        assert "items" not in table_names


# ---------------------------------------------------------------------------
# 2. DATA-01: Truthful Model Usage - No Fabricated Cost ($18.50) or Tokens
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_truthful_model_usage_no_fabricated_cost_or_tokens(tmp_path):
    """DATA-01 Fix: SchemaDataAgent records truthful deterministic model without $18.50 charge."""
    ws = tmp_path / "ws_budget"
    ws.mkdir()

    initial_budget = Decimal("5.00")
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)
        job = Job(
            job_id=uuid.uuid4(),
            name=f"test-w07-budget-{uuid.uuid4().hex[:6]}",
            source_repository=str(ws),
            owner_user_id=admin.user_id,
            status=JobStatus.CHARACTERIZING.value,
            budget_used_usd=initial_budget,
        )
        db.add(job)
        await db.commit()

        schema_artifact = await schema_data_service.execute_schema_data_analysis(db, job)
        await db.refresh(job)

        # 1. Budget was NOT charged with fabricated $18.50
        assert job.budget_used_usd == initial_budget, "Budget was improperly inflated by SchemaDataAgent!"

        # 2. AgentRun record has truthful model and null/zero costs
        run = await db.scalar(
            select(AgentRun)
            .where(
                AgentRun.job_id == job.job_id,
                AgentRun.agent_name == "SchemaDataAgent",
            )
            .order_by(AgentRun.completed_at.desc())
            .limit(1)
        )
        assert run is not None
        assert run.model_provider == "deterministic_analyzer"
        assert run.model_identifier == "ddl-schema-parser-v1"
        assert run.cost_usd != Decimal("18.50") and run.cost_usd in (None, Decimal("0.0000")), "Fabricated cost_usd found in AgentRun!"
        assert run.input_tokens in (None, 0) and run.input_tokens != 5200, "Fabricated input_tokens found in AgentRun!"
        assert run.output_tokens in (None, 0) and run.output_tokens != 3200, "Fabricated output_tokens found in AgentRun!"
        assert str(schema_artifact.artifact_id) in (run.output_artifact_refs or [])


# ---------------------------------------------------------------------------
# 3. Real Schema Discovery & Disposable Target PostgreSQL 16 Validation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_schema_discovery_and_disposable_postgresql_validation(tmp_path):
    """Discovers real DDL tables and validates migration rehearsal in disposable PostgreSQL 16 schema."""
    from app.services.repository_workspace_service import repository_workspace_service

    test_job_id = uuid.uuid4()
    # Create workspace path matching repository_workspace_service
    ws_dir = repository_workspace_service.get_workspace_path(str(test_job_id))
    ws_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Write real DDL file
        sql_file = ws_dir / "schema.sql"
        sql_file.write_text(
            "CREATE TABLE accounts (\n"
            "    id INT PRIMARY KEY,\n"
            "    account_number VARCHAR(50) NOT NULL,\n"
            "    balance DECIMAL(12, 2) NOT NULL\n"
            ");\n"
            "CREATE TABLE transactions (\n"
            "    id INT PRIMARY KEY,\n"
            "    account_id INT NOT NULL,\n"
            "    amount DECIMAL(12, 2) NOT NULL\n"
            ");\n",
            encoding="utf-8",
        )

        async with AsyncSessionLocal() as db:
            admin = await _get_or_create_admin(db)
            job = Job(
                job_id=test_job_id,
                name=f"test-w07-ddl-{uuid.uuid4().hex[:6]}",
                source_repository=str(ws_dir),
                owner_user_id=admin.user_id,
                status=JobStatus.CHARACTERIZING.value,
                budget_used_usd=Decimal("0.00"),
            )
            db.add(job)
            await db.commit()

            schema_artifact = await schema_data_service.execute_schema_data_analysis(db, job)
            raw_bytes = await artifact_service.storage.get_object(schema_artifact.storage_path)
            payload = json.loads(raw_bytes.decode("utf-8"))

            # Schema analysis matches real tables
            assert payload["status"] == "MAPPED"
            assert payload["tables_analyzed_count"] == 2
            table_names = [t["table_name"] for t in payload["tables"]]
            assert "accounts" in table_names
            assert "transactions" in table_names

            # Disposable PostgreSQL validation passed
            validation = payload.get("disposable_validation", {})
            assert validation.get("passed") is True
            assert validation.get("validation_engine") == "PostgreSQL 16"
            assert validation.get("rollback_verified") is True

            # Audit events verified
            analyzed_audit = await db.scalar(
                select(AuditEvent).where(
                    AuditEvent.job_id == job.job_id,
                    AuditEvent.event_type == "SCHEMA_DATA_ANALYZED",
                )
            )
            assert analyzed_audit is not None
            assert analyzed_audit.payload.get("tables_count") == 2

            validated_audit = await db.scalar(
                select(AuditEvent).where(
                    AuditEvent.job_id == job.job_id,
                    AuditEvent.event_type == "DISPOSABLE_MIGRATION_VALIDATED",
                )
            )
            assert validated_audit is not None
            assert validated_audit.payload.get("validation_engine") == "PostgreSQL 16"
            assert validated_audit.payload.get("rollback_verified") is True
    finally:
        shutil.rmtree(ws_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Disposable Schema Validation Fails on Broken SQL Syntax
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disposable_validation_fails_on_broken_table_name():
    """Disposable validator fails closed if invalid table definition or syntax is provided."""
    broken_tables = [{"table_name": "invalid-table-name;--DROP ALL"}]
    res = await validate_target_schema_disposable(broken_tables)
    assert res["passed"] is False
    assert res["status"] == "FAIL"
    assert len(res["errors"]) > 0


# ---------------------------------------------------------------------------
# 5. Static Web: Missing Workspace Returns NOT_RUN (Never Fabricated PASS)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_static_web_missing_workspace_returns_not_run(tmp_path):
    """Static-web characterizer reports NOT_RUN / UNAVAILABLE when workspace is absent."""
    nonexistent = tmp_path / "does_not_exist"
    scenario = Scenario(
        name="web_home_load",
        module="mod_html",
        interface="static_dom",
        behavior="render_page",
    )
    obs = await replay_web_static(scenario, workspace_path=nonexistent)
    assert obs["available"] is False
    assert obs["execution_mode"] == "UNAVAILABLE"
    assert obs["output"]["status"] == "NOT_RUN"
    assert obs["output"]["evaluation_level"] == "NOT_RUN"


# ---------------------------------------------------------------------------
# 6. Static Web: Multi-level Evaluation (DOM_PASS, BEHAVIOR_PASS, BUILD_PASS)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_static_web_multilevel_evaluation(tmp_path):
    """Distinguishes DOM_PASS, BEHAVIOR_PASS, and BUILD_PASS with real HTML files."""
    web_ws = tmp_path / "static_site"
    web_ws.mkdir()
    index_html = web_ws / "index.html"
    index_html.write_text(
        "<!DOCTYPE html>\n"
        "<html><head><title>Modernization Portal</title></head>\n"
        "<body>\n"
        "  <header id='header-main' class='site-header'>Portal</header>\n"
        "  <main id='app-root' class='container content'></main>\n"
        "</body></html>\n",
        encoding="utf-8",
    )

    # Scenario 1: DOM element assertions match -> DOM_PASS
    scenario_dom = Scenario(
        name="check_dom_elements",
        module="mod_html",
        interface="static_dom",
        behavior="verify_layout",
        inputs={
            "required_ids": ["header-main", "app-root"],
            "required_classes": ["site-header", "container"],
            "expected_title": "Modernization Portal",
        },
    )
    obs_dom = await replay_web_static(scenario_dom, workspace_path=web_ws)
    assert obs_dom["available"] is True
    assert obs_dom["output"]["status"] == "PASSED"
    assert obs_dom["output"]["evaluation_level"] == "DOM_PASS"

    # Scenario 2: Interactive behavior asserted -> BEHAVIOR_PASS
    scenario_behavior = Scenario(
        name="check_behavior",
        module="mod_html",
        interface="static_dom",
        behavior="client_interaction",
        inputs={
            "required_ids": ["app-root"],
            "behavior": True,
        },
    )
    obs_behavior = await replay_web_static(scenario_behavior, workspace_path=web_ws)
    assert obs_behavior["available"] is True
    assert obs_behavior["output"]["status"] == "PASSED"
    assert obs_behavior["output"]["evaluation_level"] == "BEHAVIOR_PASS"


# ---------------------------------------------------------------------------
# 7. Static Web: Broken DOM Element Assertion Fails Closed (DOM_FAILED)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_static_web_broken_assertion_fails_closed(tmp_path):
    """Element assertion failure fails closed with DOM_FAILED and exit_status=1."""
    web_ws = tmp_path / "static_site_fail"
    web_ws.mkdir()
    index_html = web_ws / "index.html"
    index_html.write_text(
        "<html><head><title>App</title></head><body><div id='header'></div></body></html>",
        encoding="utf-8",
    )

    scenario = Scenario(
        name="check_missing_button",
        module="mod_html",
        interface="static_dom",
        behavior="submit_order",
        inputs={
            "required_ids": ["checkout-submit-btn"],  # Absent from DOM
        },
    )
    obs = await replay_web_static(scenario, workspace_path=web_ws)
    assert obs["exit_status"] == 1
    assert obs["output"]["status"] == "FAILED"
    assert obs["output"]["evaluation_level"] == "DOM_FAILED"
    assert "Missing required element id: 'checkout-submit-btn'" in obs["output"]["reason"]


# ---------------------------------------------------------------------------
# 8. TEST-05: Real Environment Probes in FeasibilityAgent
# ---------------------------------------------------------------------------
def test_feasibility_agent_real_tool_probes():
    """TEST-05 Fix: FeasibilityAgent probe_tool executes real host subprocess probes.

    Installed tools return READY with probed version; missing tools return BLOCKED/MISSING.
    """
    # 1. Probe known installed host tool (git)
    installed_probe = FeasibilityAgent.probe_tool("git", ["git"])
    assert installed_probe.availability is True
    assert installed_probe.readiness == "READY"
    assert installed_probe.configuration_status == "CONFIGURED"
    assert installed_probe.version is not None
    assert "git version" in installed_probe.version.lower()

    # 2. Probe guaranteed non-existent imaginary binary
    missing_probe = FeasibilityAgent.probe_tool("definitely_nonexistent_cli_probe_xyz987", ["definitely_nonexistent_cli_probe_xyz987"])
    assert missing_probe.availability is False
    assert missing_probe.readiness == "BLOCKED"
    assert missing_probe.configuration_status == "MISSING"
    assert missing_probe.version is None
    assert any("not found on system PATH" in ev for ev in missing_probe.evidence)


# ---------------------------------------------------------------------------
# 9. Decoupled Characterizer and SchemaData AgentRuns
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_decoupled_characterizer_and_schema_data_agent_runs(tmp_path):
    """Characterizer and SchemaData create distinct AgentRun records in PostgreSQL."""
    ws = tmp_path / "ws_decouple"
    ws.mkdir()

    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)
        job = Job(
            job_id=uuid.uuid4(),
            name=f"test-w07-decouple-{uuid.uuid4().hex[:6]}",
            source_repository=str(ws),
            owner_user_id=admin.user_id,
            status=JobStatus.CHARACTERIZING.value,
            budget_used_usd=Decimal("0.00"),
        )
        g1 = WorkflowGate(
            gate_id=uuid.uuid4(),
            job_id=job.job_id,
            gate_type="G1",
            status="APPROVED",
        )
        db.add(job)
        db.add(g1)
        await db.commit()

        # Capture with empty scenarios
        req = CaptureRequest(
            idempotency_key=f"cap-{uuid.uuid4().hex[:8]}",
            scenarios=[],
            tables=[],
            target_tables=[],
        )
        report = await capture(db, job, req, actor_id=str(admin.user_id))
        await db.commit()

        # 1. Distinct AgentRun for Characterizer
        char_run = await db.scalar(
            select(AgentRun)
            .where(
                AgentRun.job_id == job.job_id,
                AgentRun.agent_name == "Characterizer",
            )
            .limit(1)
        )
        assert char_run is not None

        # 2. Distinct AgentRun for SchemaData
        schema_run = await db.scalar(
            select(AgentRun)
            .where(
                AgentRun.job_id == job.job_id,
                AgentRun.agent_name == "SchemaData",
            )
            .limit(1)
        )
        assert schema_run is not None

        # 3. Runs have distinct IDs and independent artifact references
        assert char_run.run_id != schema_run.run_id
        assert char_run.agent_name == "Characterizer"
        assert schema_run.agent_name == "SchemaData"
        assert len(char_run.output_artifact_refs) == 1
        assert len(schema_run.output_artifact_refs) == 1
        assert char_run.output_artifact_refs != schema_run.output_artifact_refs


# ---------------------------------------------------------------------------
# 10. Empty Scenario Set Blocks G2 Readiness
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_scenarios_blocks_g2_readiness(tmp_path):
    """Empty scenario set prevents G2 approval (ready_for_g2=False)."""
    ws = tmp_path / "ws_empty_scenarios"
    ws.mkdir()

    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)
        job = Job(
            job_id=uuid.uuid4(),
            name=f"test-w07-g2block-{uuid.uuid4().hex[:6]}",
            source_repository=str(ws),
            owner_user_id=admin.user_id,
            status=JobStatus.CHARACTERIZING.value,
        )
        g1 = WorkflowGate(
            gate_id=uuid.uuid4(),
            job_id=job.job_id,
            gate_type="G1",
            status="APPROVED",
        )
        db.add(job)
        db.add(g1)
        await db.commit()

        req = CaptureRequest(
            idempotency_key=f"cap-{uuid.uuid4().hex[:8]}",
            scenarios=[],
            tables=[],
            target_tables=[],
        )
        report = await capture(db, job, req, actor_id=str(admin.user_id))
        g2_readiness = report.get("g2_readiness", {})

        assert g2_readiness.get("ready_for_g2") is False
        assert len(g2_readiness.get("blocking_reasons", [])) > 0
        assert any("Zero" in reason for reason in g2_readiness["blocking_reasons"])
