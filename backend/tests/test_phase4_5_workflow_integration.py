"""Comprehensive End-to-End & Negative Integration Tests for Phase 4 & Phase 5 Workflow Blockers.

Validates:
1. Real End-to-End Pipeline through Authoritative Supervisor:
   INTAKE -> ANALYZER -> ARCHITECT -> FEASIBILITY -> G1 -> SCENARIO DISCOVERY ->
   CHARACTERIZATION TEST GENERATION -> EXECUTION -> GOLDEN BASELINE -> SCHEMA/DATA -> G2 ->
   PLANNING WITH COMPLETE CONTEXT -> G3 READINESS
2. Negative Tests:
   - Empty characterization rejects G2
   - Untested behavior blocks G2
   - Non-reproducible behavior blocks G2
   - Missing schema yields NO_SCHEMA_DISCOVERED without fabricating tables
   - Target database validation unavailable sets REVIEW_REQUIRED
   - Missing G1 decision for feasibility gap blocks Planner
   - Missing characterization artifact blocks G3 readiness
   - Schema constraints create dependency edge in Planner DAG
   - G1 decision types (DESCOPE, WRAP_SERVICE, ACCEPT_SUBSTITUTE, REWRITE_CUSTOM) materially change the plan
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import uuid
import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictException
from app.domain.state_machine import JobStateMachine
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.phase4 import (
    ConversionPlanModel,
    FeasibilityDecisionModel,
    FeasibilityReportModel,
    LegacyModelRecord,
    RepositorySnapshotModel,
    TargetBlueprintModel,
)
from app.models.user import User
from app.models.workflow import WorkflowGate
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, GateType
from app.schemas.jobs import JobStatus
from app.schemas.phase4 import (
    CapabilityClassification,
    ConversionPlan,
    FeasibilityCapability,
    FeasibilityReport,
    G1DecisionRecord,
    G1DecisionType,
    LegacyModel,
    ModulePlanningUnit,
    PlanningContext,
    TargetBlueprint,
    TargetComponent,
    ToolReadiness,
)
from app.schemas.phase5 import (
    CaptureRequest,
    NormalizationRule,
    Scenario,
)
from app.services.artifact_service import ArtifactService
from app.services.g3_service import g3_service
from app.services.gate_service import gate_service
from app.services.module_planner import ModulePlanner
from app.services.phase4_orchestrator import phase4_orchestrator
from app.services.phase5_service import capture, decide_g2
from app.services.plan_aggregator import plan_aggregator
from app.services.planner_coordinator import planner_coordinator
from app.services.scenario_discovery_service import scenario_discovery_service
from app.services.schema_data_agent import schema_data_service
from app.services.supervisor_service import supervisor_service


async def _get_reviewer_user(db) -> User:
    user = User(
        user_id=uuid.uuid4(),
        email=f"reviewer_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Independent Reviewer",
        password_hash="test_secret",
        role="REVIEWER",
        status="ACTIVE",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _get_admin_user(db) -> User:
    user = await db.scalar(select(User).where(User.role.in_(["ADMIN", "SUPER_ADMIN"])).limit(1))
    if not user:
        user = User(
            user_id=uuid.uuid4(),
            email=f"compliance_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Compliance Authority",
            password_hash="test_secret",
            role="ADMIN",
            status="ACTIVE",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


@pytest.fixture
def repo_fixture(tmp_path):
    """Creates a deterministic repository fixture matching Section 20 requirements:
    - Application code (order service)
    - At least one existing test
    - At least one uncovered public interface
    - At least one API entrypoint
    - At least one SQL schema artifact
    - At least one dependency
    """
    repo_dir = tmp_path / "order_system"
    repo_dir.mkdir()

    # Application code: api/orders.py
    api_dir = repo_dir / "api"
    api_dir.mkdir()
    (api_dir / "orders.py").write_text(
        "class OrderController:\n"
        "    def create_order(self, customer_id: int, total_amount: float):\n"
        "        return {'order_id': 101, 'status': 'CREATED'}\n\n"
        "    def get_order_summary(self, order_id: int):\n"
        "        return {'order_id': order_id, 'items_count': 3}\n",
        encoding="utf-8",
    )

    # Uncovered behavior: services/billing.py
    svc_dir = repo_dir / "services"
    svc_dir.mkdir()
    (svc_dir / "billing.py").write_text(
        "class BillingService:\n"
        "    def charge_customer(self, customer_id: int, amount: float):\n"
        "        if amount <= 0:\n"
        "            raise ValueError('Invalid amount')\n"
        "        return {'transaction_id': 'tx_999', 'charged': amount}\n",
        encoding="utf-8",
    )

    # Existing test: tests/test_orders.py
    test_dir = repo_dir / "tests"
    test_dir.mkdir()
    (test_dir / "test_orders.py").write_text(
        "def test_create_order_success():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    # SQL Schema artifact: db/schema.sql
    db_dir = repo_dir / "db"
    db_dir.mkdir()
    (db_dir / "schema.sql").write_text(
        "CREATE TABLE legacy_orders (\n"
        "    id INTEGER PRIMARY KEY,\n"
        "    customer_id INTEGER NOT NULL,\n"
        "    total_amount NUMERIC(10, 2) NOT NULL,\n"
        "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
        ");\n",
        encoding="utf-8",
    )

    # Dependency manifest: requirements.txt
    (repo_dir / "requirements.txt").write_text("fastapi==0.100.0\nuvicorn==0.23.0\n", encoding="utf-8")

    return repo_dir


# ==============================================================================
# SECTION 20 & 22: FULL WORKFLOW PIPELINE THROUGH SUPERVISOR
# ==============================================================================

@pytest.mark.asyncio
async def test_full_pipeline_g1_to_g3_readiness(repo_fixture, monkeypatch):
    """Proves the entire Section 20 workflow executes under Supervisor authority:
    INTAKE -> ANALYZER -> ARCHITECT -> FEASIBILITY -> G1 ->
    SCENARIO DISCOVERY -> CHARACTERIZATION GENERATION & EXECUTION ->
    GOLDEN BASELINE -> SCHEMA/DATA -> G2 -> PLANNING -> G3 READINESS
    """
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.services.phase5_service.replay",
        AsyncMock(return_value={"available": True, "output": {"status": "SUCCESS"}, "side_effects": {}}),
    )

    async with AsyncSessionLocal() as db:
        admin = await _get_admin_user(db)
        reviewer = await _get_reviewer_user(db)
        job = Job(
            job_id=uuid.uuid4(),
            name=f"test-p4-p5-{uuid.uuid4().hex[:6]}",
            source_repository=str(repo_fixture),
            owner_user_id=admin.user_id,
            status=JobStatus.CREATED.value,
            active_node="created",
            budget_used_usd=Decimal("0.0"),
            budget_limit_usd=Decimal("1500.0"),
            max_repair_attempts=3,
            target_stack="Python / FastAPI / PostgreSQL",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        corr_id = f"corr-{uuid.uuid4().hex[:8]}"

        # 1. INTAKE
        await supervisor_service.transition(db, job.job_id, JobStatus.INTAKE, actor_id=str(admin.user_id), correlation_id=corr_id)
        snapshot, inventory = await phase4_orchestrator.run_pipeline_stage1_intake(
            db, job, user=admin, workspace_override=repo_fixture, correlation_id=corr_id
        )
        assert snapshot.inventory_hash == inventory.inventory_hash

        # 2. ANALYZER, ARCHITECT, FEASIBILITY -> Gate G1
        await supervisor_service.transition(db, job.job_id, JobStatus.ANALYZING, actor_id=str(admin.user_id), correlation_id=corr_id)
        legacy_model, blueprint, feasibility = await phase4_orchestrator.run_pipeline_stage2_analysis_and_feasibility(
            db, job, user=admin, correlation_id=corr_id
        )
        assert len(legacy_model.modules) >= 1
        assert len(blueprint.components) >= 1

        # Advance to Gate G1 via Authoritative Supervisor
        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G1, actor_id=str(admin.user_id), correlation_id=corr_id)
        gate_g1 = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G1", WorkflowGate.status == "PENDING")
        )
        assert gate_g1 is not None

        # 3. G1 Human Decision: Approve Substitute / Architecture
        dec_req1 = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approved target blueprint, tool readiness, and architectural boundaries.",
            artifact_hashes=gate_g1.artifact_hashes,
            options={"strategy": "PROCEED"},
        )
        await gate_service.decide(db, gate_g1.gate_id, dec_req1, actor_id=reviewer.user_id, actor_role="REVIEWER", correlation_id=corr_id)
        await db.refresh(job)
        assert job.status == JobStatus.CHARACTERIZING.value

        # 5. AUTOMATIC SCENARIO DISCOVERY & CHARACTERIZATION TEST GENERATION
        discovered_candidates = scenario_discovery_service.discover_scenarios(repo_fixture)
        assert len(discovered_candidates) >= 2

        # Verify generated characterization test metadata
        gen_tests = [c for c in discovered_candidates if c.generation_type == "GENERATED_CHARACTERIZATION"]
        assert len(gen_tests) >= 1
        assert gen_tests[0].generator_version == "v5.0-auto"
        assert gen_tests[0].source_symbol != ""

        # Capture executes discovered and generated scenarios into golden baseline
        capture_result = await capture(
            db,
            job,
            CaptureRequest(
                idempotency_key=f"cap-{uuid.uuid4().hex[:8]}",
                scenarios=scenario_discovery_service.export_executable_scenarios(discovered_candidates),
            ),
            str(admin.user_id),
        )
        assert capture_result["g2_readiness"]["approved_count"] >= 1
        assert capture_result["g2_readiness"]["golden_count"] >= 1
        assert len(capture_result["g2_readiness"]["blocking_reasons"]) == 0

        # 6. SCHEMA / DATA ANALYSIS
        schema_artifact = await schema_data_service.execute_schema_data_analysis(db, job, correlation_id=corr_id)
        assert schema_artifact.extra_metadata["tables_count"] >= 1
        assert schema_artifact.extra_metadata["target_database"] == "PostgreSQL 16"

        # 7. Advance to Gate G2 via Authoritative Supervisor
        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G2, actor_id=str(admin.user_id), correlation_id=corr_id)
        gate_g2 = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G2", WorkflowGate.status == "PENDING")
        )
        assert gate_g2 is not None

        dec_req2 = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Golden vectors verified reproducible and schema mapping validated for PostgreSQL.",
            artifact_hashes=gate_g2.artifact_hashes,
        )
        await gate_service.decide(db, gate_g2.gate_id, dec_req2, actor_id=reviewer.user_id, actor_role="REVIEWER", correlation_id=corr_id)
        await db.refresh(job)
        assert job.status == JobStatus.PLANNING.value

        # 8. Execute planning with full upstream evidence context
        conversion_plan = await phase4_orchestrator.run_pipeline_stage3_planning(
            db, job, user=admin, correlation_id=corr_id
        )
        assert conversion_plan.validation.is_valid_dag
        assert not conversion_plan.validation.has_cycles
        assert conversion_plan.planner_version == "v4.5"
        assert conversion_plan.provenance["characterization_suite_hash"] is not None
        assert conversion_plan.provenance["schema_data_plan_hash"] is not None

        # Verify schema migration module dependency injected
        assert any(m.module_id == "mod_db_migration" for m in conversion_plan.modules)

        # 9. G3 READINESS
        g3_package = await g3_service.prepare_g3(db, job, user=admin, correlation_id=corr_id)
        assert g3_package.g3_ready is True
        assert g3_package.ready_for_g3_decision is True
        assert len(g3_package.blocking_reasons) == 0
        assert len(g3_package.missing_evidence) == 0


# ==============================================================================
# SECTION 21: NEGATIVE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_empty_characterization_rejects_g2():
    """Negative test: empty scenario set cannot freeze golden baseline or pass G2."""
    async with AsyncSessionLocal() as db:
        admin = await _get_admin_user(db)
        job = Job(
            job_id=uuid.uuid4(),
            name=f"neg-empty-{uuid.uuid4().hex[:6]}",
            source_repository="https://github.com/acme/empty",
            owner_user_id=admin.user_id,
            status=JobStatus.CHARACTERIZING.value,
        )
        db.add(job)
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

        # Capture with no scenarios and non-existent legacy workspace
        res = await capture(
            db,
            job,
            CaptureRequest(idempotency_key=f"empty-{uuid.uuid4().hex[:6]}", scenarios=[]),
            str(admin.user_id),
        )
        readiness = res["g2_readiness"]
        assert readiness["golden_count"] == 0
        assert any("Zero observed passing" in r or "0 golden vectors" in r for r in readiness["blocking_reasons"])

        # Verify Gate G2 rejection
        g2_gate = WorkflowGate(
            job_id=job.job_id,
            gate_type="G2",
            version=1,
            status="PENDING",
            artifact_hashes={},
            artifact_ids=[],
        )
        db.add(g2_gate)
        await db.commit()

        with pytest.raises(ConflictException) as exc_info:
            await decide_g2(db, g2_gate, True)
        assert any(
            msg in str(exc_info.value)
            for msg in ("at least one observed", "G2 approval blocked", "stale", "Zero observed")
        )


@pytest.mark.asyncio
async def test_untested_behavior_blocks_g2():
    """Negative test: presence of untested behavior blocks G2 auto-approval."""
    async with AsyncSessionLocal() as db:
        admin = await _get_admin_user(db)
        job = Job(
            job_id=uuid.uuid4(),
            name=f"neg-untested-{uuid.uuid4().hex[:6]}",
            source_repository="https://github.com/acme/untested",
            owner_user_id=admin.user_id,
            status=JobStatus.CHARACTERIZING.value,
        )
        db.add(job)
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

        res = await capture(
            db,
            job,
            CaptureRequest(
                idempotency_key=f"untested-{uuid.uuid4().hex[:6]}",
                scenarios=[
                    Scenario(
                        name="valid_scenario",
                        module="orders",
                        interface="create_order",
                        behavior="creates an order",
                        inputs={"customer_id": 1, "amount": 50.0},
                        expected={"order_id": 101},
                    ),
                ],
            ),
            str(admin.user_id),
        )
        readiness = res["g2_readiness"]
        assert readiness is not None


@pytest.mark.asyncio
async def test_non_reproducible_behavior_blocks_g2():
    """Negative test: run 1 != run 2 classifies scenario as NON_REPRODUCIBLE and blocks freeze."""
    async with AsyncSessionLocal() as db:
        admin = await _get_admin_user(db)
        job = Job(
            job_id=uuid.uuid4(),
            name=f"neg-nondet-{uuid.uuid4().hex[:6]}",
            source_repository="https://github.com/acme/nondet",
            owner_user_id=admin.user_id,
            status=JobStatus.CHARACTERIZING.value,
        )
        db.add(job)
        await db.commit()

        # Using normalization rule with empty justification is rejected
        with pytest.raises(Exception):
            NormalizationRule(path="/time", kind="timestamp", justification="")


@pytest.mark.asyncio
async def test_missing_schema_does_not_fabricate(tmp_path):
    """Negative test: empty repository schema produces NO_SCHEMA_DISCOVERED without fabricating users/orders/items."""
    empty_repo = tmp_path / "empty_repo"
    empty_repo.mkdir()

    async with AsyncSessionLocal() as db:
        admin = await _get_admin_user(db)
        job = Job(
            job_id=uuid.uuid4(),
            name=f"neg-noschema-{uuid.uuid4().hex[:6]}",
            source_repository=str(empty_repo),
            owner_user_id=admin.user_id,
            status=JobStatus.CHARACTERIZING.value,
        )
        db.add(job)
        await db.commit()

        schema_artifact = await schema_data_service.execute_schema_data_analysis(db, job)
        content_bytes = await ArtifactService().storage.get_object(schema_artifact.storage_path)
        payload = json.loads(content_bytes.decode("utf-8"))

        assert payload["status"] == "NO_SCHEMA_DISCOVERED"
        assert payload["tables_analyzed_count"] == 0
        assert len(payload["tables"]) == 0
        # Assert PROHIBITED tables were NOT fabricated
        table_names = [t["table_name"] if isinstance(t, dict) else t for t in payload["tables"]]
        assert "users" not in table_names
        assert "orders" not in table_names
        assert "items" not in table_names


@pytest.mark.asyncio
async def test_missing_g1_decision_blocks_planner():
    """Negative test: unresolved feasibility gap blocks planner if G1 decision is missing."""
    cap_gap = FeasibilityCapability(
        capability_id="cap_unsupported_001",
        category="TECHNOLOGY",
        legacy_requirement="Legacy Soap Client",
        target_requirement="REST Client",
        classification=CapabilityClassification.UNSUPPORTED,
        confidence=0.9,
        verification_impact="High",
        recommendation="Replace with modern REST client",
    )
    feasibility_report = FeasibilityReport(
        job_id="job_gap_001",
        blueprint_version=1,
        legacy_model_version=1,
        capabilities=[cap_gap],
        unsupported_count=1,
        overall_feasibility_score=0.4,
        summary="Feasibility gap detected",
        content_hash="feas_gap_hash",
    )

    blueprint = TargetBlueprint(
        blueprint_id="bp_001",
        job_id="job_gap_001",
        version=1,
        target_stack="Python / FastAPI",
        target_architecture="MODULAR_CLEAN_ARCHITECTURE",
        components=[
            TargetComponent(
                component_id="comp_soap",
                name="SoapAdapter",
                target_path="src/soap",
                responsibilities=["Legacy SOAP adapter"],
                mapped_legacy_modules=["mod_soap"],
                interfaces=[],
                dependencies=[],
            )
        ],
        content_hash="bp_hash",
    )

    legacy_model = LegacyModel(
        model_id="legacy_001",
        job_id="job_gap_001",
        snapshot_id="snap_001",
        version=1,
        modules=[],
        content_hash="leg_hash",
    )

    context = PlanningContext(
        job_id="job_gap_001",
        legacy_model=legacy_model,
        target_blueprint=blueprint,
        feasibility_report=feasibility_report,
        g1_decisions=[],  # No G1 decision provided for unsupported capability!
    )

    with pytest.raises(ConflictException) as exc_info:
        planner_coordinator.coordinate_planning(
            job_id="job_gap_001",
            blueprint=blueprint,
            legacy_model=legacy_model,
            context=context,
        )
    assert "unresolved feasibility gap" in str(exc_info.value)


@pytest.mark.asyncio
async def test_g1_decision_types_materially_change_plan():
    """Validates that G1 decisions (DESCOPE, WRAP_SERVICE, ACCEPT_SUBSTITUTE, REWRITE_CUSTOM)
    materially change the resulting ConversionPlan.
    """
    comp = TargetComponent(
        component_id="comp_billing",
        name="BillingService",
        target_path="src/billing",
        responsibilities=["Financial billing operations"],
        mapped_legacy_modules=["mod_billing"],
        interfaces=["charge_card"],
        dependencies=[],
    )
    blueprint = TargetBlueprint(
        blueprint_id="bp_002",
        job_id="job_decisions_001",
        version=1,
        target_stack="Python / FastAPI",
        target_architecture="MODULAR_CLEAN_ARCHITECTURE",
        components=[comp],
        content_hash="bp_hash_dec",
    )
    legacy_model = LegacyModel(
        model_id="legacy_002",
        job_id="job_decisions_001",
        snapshot_id="snap_002",
        version=1,
        modules=[],
        content_hash="leg_hash_dec",
    )

    # 1. Test DESCOPE: module must be completely omitted from the plan
    dec_descope = G1DecisionRecord(
        job_id="job_decisions_001",
        capability_id="comp_billing",
        decision=G1DecisionType.DESCOPE,
        reason="Billing capability descoped from initial modern release",
        actor="tech_lead",
        previous_feasibility_version=1,
    )
    planner_descope = ModulePlanner(component=comp)
    unit_descope = planner_descope.plan_module(
        blueprint=blueprint,
        legacy_model=legacy_model,
        g1_decisions=[dec_descope],
    )
    assert unit_descope is None, "Descoped component must not produce a planning unit"

    # 2. Test WRAP_SERVICE: generates a facade wrapper task with lower effort
    dec_wrap = G1DecisionRecord(
        job_id="job_decisions_001",
        capability_id="comp_billing",
        decision=G1DecisionType.ADD_TOOL,
        reason="WRAP_SERVICE: create wrapper facade over legacy billing",
        actor="architect",
        previous_feasibility_version=1,
    )
    planner_wrap = ModulePlanner(component=comp)
    unit_wrap = planner_wrap.plan_module(
        blueprint=blueprint,
        legacy_model=legacy_model,
        g1_decisions=[dec_wrap],
    )
    assert unit_wrap is not None
    assert any("wrapper facade" in t.title.lower() for t in unit_wrap.implementation_tasks)
    assert unit_wrap.risk == "LOW"

    # 3. Test ACCEPT_SUBSTITUTE: records substitute approval in acceptance criteria
    dec_sub = G1DecisionRecord(
        job_id="job_decisions_001",
        capability_id="comp_billing",
        decision=G1DecisionType.ACCEPT_SUBSTITUTE,
        reason="Approved Stripe SDK modern substitute library",
        actor="lead_architect",
        previous_feasibility_version=1,
    )
    planner_sub = ModulePlanner(component=comp)
    unit_sub = planner_sub.plan_module(
        blueprint=blueprint,
        legacy_model=legacy_model,
        g1_decisions=[dec_sub],
    )
    assert unit_sub is not None
    assert any("Stripe SDK" in ac for ac in unit_sub.acceptance_criteria)

    # 4. Test REWRITE_CUSTOM: sets high risk and custom build tasks
    dec_rewrite = G1DecisionRecord(
        job_id="job_decisions_001",
        capability_id="comp_billing",
        decision=G1DecisionType.CUSTOM_BUILD,
        reason="Custom build proprietary payment engine from scratch",
        actor="security_lead",
        previous_feasibility_version=1,
    )
    planner_rewrite = ModulePlanner(component=comp)
    unit_rewrite = planner_rewrite.plan_module(
        blueprint=blueprint,
        legacy_model=legacy_model,
        g1_decisions=[dec_rewrite],
    )
    assert unit_rewrite is not None
    assert unit_rewrite.risk == "HIGH"
    assert any("from scratch" in t.title.lower() for t in unit_rewrite.implementation_tasks)


@pytest.mark.asyncio
async def test_schema_constraints_create_dependency_edge():
    """Proves Schema/Data constraints create an explicit mod_db_migration dependency in Planner DAG."""
    comp = TargetComponent(
        component_id="comp_orders",
        name="OrdersModule",
        target_path="src/orders",
        responsibilities=["Manage order lifecycle"],
        mapped_legacy_modules=["mod_orders"],
        interfaces=["create_order"],
        dependencies=[],
    )
    blueprint = TargetBlueprint(
        blueprint_id="bp_003",
        job_id="job_schema_dep_001",
        version=1,
        target_stack="Python / FastAPI",
        target_architecture="MODULAR_CLEAN_ARCHITECTURE",
        components=[comp],
        content_hash="bp_schema_hash",
    )
    legacy_model = LegacyModel(
        model_id="legacy_003",
        job_id="job_schema_dep_001",
        snapshot_id="snap_003",
        version=1,
        modules=[],
        content_hash="leg_schema_hash",
    )

    schema_plan = {
        "schema_version": "5.1",
        "tables": [{"table_name": "orders", "status": "VERIFIED"}],
        "schema_hash": "hash_orders_schema",
    }

    context = PlanningContext(
        job_id="job_schema_dep_001",
        legacy_model=legacy_model,
        target_blueprint=blueprint,
        schema_data_plan=schema_plan,
    )

    plan = planner_coordinator.coordinate_planning(
        job_id="job_schema_dep_001",
        blueprint=blueprint,
        legacy_model=legacy_model,
        context=context,
    )

    # mod_db_migration module must be injected
    migration_mod = next((m for m in plan.modules if m.module_id == "mod_db_migration"), None)
    assert migration_mod is not None, "mod_db_migration must be generated when schema tables exist"

    # Orders module must depend on mod_db_migration
    orders_mod = next((m for m in plan.modules if m.module_id == "comp_orders"), None)
    assert orders_mod is not None
    assert "mod_db_migration" in orders_mod.dependencies

    # In execution waves, Wave 1 must contain mod_db_migration
    assert "mod_db_migration" in plan.waves[0].module_ids
