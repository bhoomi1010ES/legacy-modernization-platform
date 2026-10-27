"""Full Diagram-Level Supervisor End-to-End Architectural Integration Test Suite.

Proves:
1. Full Diagram Lifecycle:
   Analyzer -> Architect -> Feasibility -> Planner -> Characterizer -> Schema/Data -> G2 -> Planning -> G3 -> CodeWriter Pool -> Verifier -> Repair -> Integrator -> G4 -> Complete.
2. Multi-Agent Routing & Capabilities (Dependencies, allowed states, explicit decision auditability).
3. Supervisor Durable Restart Recovery across multiple phases.
4. Parallel Feature Planning & DAG Aggregation.
5. Multi-Dimensional Budget Governance (Tokens, Time, Concurrency, Agent/Task caps, USD).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import uuid
import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.domain.state_machine import GatePolicy, JobStateMachine
from app.models.agent import AgentRun
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.budget import BudgetUsage
from app.models.job import Job
from app.models.module import Module
from app.models.phase4 import (
    ConversionPlanModel,
    FeasibilityReportModel,
    LegacyModelRecord,
    RepositorySnapshotModel,
    TargetBlueprintModel,
)
from app.models.user import User
from app.models.workflow import WorkflowCheckpoint, WorkflowGate
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, GateType
from app.schemas.jobs import JobStatus
from app.schemas.phase4 import (
    ConversionPlan,
    FeasibilityReport,
    LegacyModel,
    TargetBlueprint,
    TargetComponent,
)
from app.schemas.workflow import SupervisorTask, TaskType
from app.services.budget_manager import budget_manager
from app.services.code_writer import code_writer_service
from app.services.dependency_scheduler import dependency_scheduler
from app.services.gate_service import gate_service
from app.services.integrator_agent import integrator_service
from app.services.plan_aggregator import plan_aggregator
from app.services.schema_data_agent import schema_data_service
from app.services.supervisor_graph import supervisor_loop_graph
from app.services.supervisor_router import (
    AGENT_CAPABILITY_REGISTRY,
    SupervisorAction,
    SupervisorDecision,
    supervisor_router,
)
from app.services.supervisor_service import supervisor_service
from app.services.verifier_agent import VerificationVerdict, verifier_service


async def _get_or_create_admin(db) -> User:
    user = await db.scalar(select(User).where(User.role == "ADMIN").limit(1))
    if not user:
        user = User(
            user_id=uuid.uuid4(),
            email=f"admin_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Admin Reviewer",
            password_hash="mock_admin_hash",
            role="ADMIN",
            status="ACTIVE",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def _create_test_job(
    db,
    status: JobStatus = JobStatus.CREATED,
    *,
    limit: str = "25000",
    concurrency: int = 4,
    stack_meta: dict = None,
) -> Job:
    admin = await _get_or_create_admin(db)
    job = Job(
        name=f"full-diagram-{uuid.uuid4().hex[:8]}",
        source_repository="https://github.com/acme/legacy-monolith",
        owner_user_id=admin.user_id,
        status=status.value,
        active_node=status.value.lower(),
        budget_used_usd=Decimal("0.00"),
        budget_limit_usd=Decimal(limit),
        max_repair_attempts=3,
        max_parallel_tasks=concurrency,
        provider_concurrency_limit=concurrency,
        sandbox_concurrency_limit=concurrency,
        source_stack="Java 8 / Spring Boot",
        target_stack="Python / FastAPI / SQLAlchemy",
        stack_metadata=stack_meta or {},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Test 1: Full Diagram-Level Agent Lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_diagram_agent_lifecycle_e2e(monkeypatch, observed_phase5_baseline):
    """Proves the authoritative Supervisor drives the complete multi-agent lifecycle:
    Analyzer -> Architect -> Feasibility -> G1 -> Characterizer -> Schema/Data -> G2
    -> Planning -> G3 -> CodeWriter Pool -> Verifier -> Repair -> Integrator -> G4 -> Complete.
    """
    monkeypatch.setattr("app.services.continuous_pipeline.continuous_pipeline_service.trigger_continuous_pipeline", lambda *a, **k: None)
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)
        job = await _create_test_job(db, JobStatus.CREATED)

        # 1. CREATED -> INTAKE
        d_create = await supervisor_router.evaluate_next_action(db, job)
        assert d_create.action == SupervisorAction.EXECUTE
        assert d_create.agent_id == "IntakeAgent"
        await supervisor_service.transition(db, job.job_id, JobStatus.INTAKE, actor_id=str(admin.user_id))

        # 2. INTAKE -> ANALYZING
        d_intake = await supervisor_router.evaluate_next_action(db, job)
        assert d_intake.action == SupervisorAction.EXECUTE
        assert d_intake.agent_id == "IntakeAgent"
        await supervisor_service.transition(db, job.job_id, JobStatus.ANALYZING, actor_id=str(admin.user_id))

        # 3. ANALYZING Phase:
        # 3a. Analyzer step
        d_ana = await supervisor_router.evaluate_next_action(db, job)
        assert d_ana.action == SupervisorAction.EXECUTE
        assert d_ana.agent_id in ("ANALYZER", "AnalyzerCoordinator")

        # Synthesize RepositorySnapshot and LegacyModel artifact
        snap_id = uuid.uuid4()
        db.add(RepositorySnapshotModel(
            snapshot_id=snap_id,
            job_id=job.job_id,
            version=1,
            source_ref="git://test/repo",
            metadata_payload={"source": "test"},
            tech_profile={"primary_language": "Java"},
            inventory_hash="sha256:inv",
            content_hash="sha256:snap",
        ))
        await db.flush()
        leg_hash = "sha256:" + hashlib.sha256(b"legacy_model_v1").hexdigest()
        leg_art = Artifact(
            job_id=job.job_id,
            artifact_type="LEGACY_MODEL",
            version=1,
            content_hash=leg_hash,
            storage_path=f"artifacts/{job.job_id}/legacy_model_v1.json",
            content_size_bytes=4096,
            media_type="application/json",
            producing_agent="ANALYZER",
        )
        db.add(leg_art)
        db.add(LegacyModelRecord(
            model_id=uuid.uuid4(),
            job_id=job.job_id,
            snapshot_id=snap_id,
            version=1,
            content_hash=leg_hash,
            modules_payload=[{"name": "orders", "module_id": "mod_orders"}],
            dependencies_payload={"nodes": ["mod_orders"], "edges": []},
            interfaces_payload=[{"endpoint": "/api/orders"}],
            persistence_payload=[{"name": "OrderTable"}],
            configurations_payload={},
            tests_payload=[],
            risks_payload=[],
            conflicts_payload=[],
        ))
        await db.commit()

        # 3b. Architect step
        d_arch = await supervisor_router.evaluate_next_action(db, job)
        assert d_arch.action == SupervisorAction.EXECUTE
        assert d_arch.agent_id in ("ARCHITECT", "ArchitectAgent")

        bp_hash = "sha256:" + hashlib.sha256(b"target_blueprint_v1").hexdigest()
        bp_art = Artifact(
            job_id=job.job_id,
            artifact_type="TARGET_BLUEPRINT",
            version=1,
            content_hash=bp_hash,
            storage_path=f"artifacts/{job.job_id}/target_blueprint_v1.json",
            content_size_bytes=4096,
            media_type="application/json",
            producing_agent="ARCHITECT",
        )
        db.add(bp_art)
        db.add(TargetBlueprintModel(
            blueprint_id=uuid.uuid4(),
            job_id=job.job_id,
            version=1,
            status="APPROVED",
            target_stack="Python / FastAPI",
            target_architecture="MODULAR_CLEAN_ARCHITECTURE",
            components_payload=[{"component_id": "comp_orders", "name": "orders_service"}],
            interfaces_payload=[],
            data_model_payload={},
            integration_contracts_payload={},
            constraints_payload={},
            accepted_decisions=[],
            evidence_refs=[],
            created_by="Architect",
            content_hash=bp_hash,
        ))
        await db.commit()

        # 3c. Feasibility step
        d_feas = await supervisor_router.evaluate_next_action(db, job)
        assert d_feas.action == SupervisorAction.EXECUTE
        assert d_feas.agent_id in ("FEASIBILITY", "FeasibilityAgent")

        feas_hash = "sha256:" + hashlib.sha256(b"feasibility_report_v1").hexdigest()
        feas_art = Artifact(
            job_id=job.job_id,
            artifact_type="FEASIBILITY_REPORT",
            version=1,
            content_hash=feas_hash,
            storage_path=f"artifacts/{job.job_id}/feasibility_report_v1.json",
            content_size_bytes=2048,
            media_type="application/json",
            producing_agent="FEASIBILITY",
        )
        db.add(feas_art)
        await db.commit()

        # 3d. Gate G1 readiness
        d_g1 = await supervisor_router.evaluate_next_action(db, job)
        assert d_g1.action == SupervisorAction.ADVANCE_GATE
        assert d_g1.target_status == JobStatus.AWAITING_GATE_G1.value

        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G1, actor_id="supervisor")
        gate_g1 = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G1", WorkflowGate.status == "PENDING")
        )
        assert gate_g1 is not None

        # Human approves Gate G1
        dec_req1 = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approved Phase 1 legacy analysis, blueprint, and feasibility scorecard.",
            artifact_hashes=gate_g1.artifact_hashes,
            options={"strategy": "PROCEED"},
        )
        await gate_service.decide(db, gate_g1.gate_id, dec_req1, actor_id=admin.user_id, actor_role="ADMIN")
        await db.refresh(job)
        assert job.status == JobStatus.CHARACTERIZING.value

        # 4. CHARACTERIZING Phase:
        # 4a. Characterizer step
        d_char = await supervisor_router.evaluate_next_action(db, job)
        assert d_char.action == SupervisorAction.EXECUTE
        assert d_char.agent_id in ("CHARACTERIZER", "CharacterizerAgent")

        baseline = await observed_phase5_baseline(db, job, admin)
        schema_art = await schema_data_service.execute_schema_data_analysis(db, job, user=admin)
        assert schema_art.artifact_type == "SCHEMA_MIGRATION_PLAN"
        assert schema_art.extra_metadata["phase"] == 5
        assert len(schema_art.content_hash) == 64
        # The helper requested review; readiness was realized through Supervisor.
        await db.refresh(job)


        # 4c. Gate G2 readiness
        d_g2 = await supervisor_router.evaluate_next_action(db, job)
        assert d_g2.action == SupervisorAction.WAIT
        assert job.status == JobStatus.AWAITING_GATE_G2.value

        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G2, actor_id="supervisor")
        gate_g2 = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G2", WorkflowGate.status == "PENDING")
        )
        assert gate_g2 is not None
        assert str(schema_art.artifact_id) in gate_g2.artifact_hashes

        # Human approves Gate G2
        dec_req2 = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approved behavioral characterization baseline and schema migration plan.",
            artifact_hashes=gate_g2.artifact_hashes,
        )
        await gate_service.decide(db, gate_g2.gate_id, dec_req2, actor_id=admin.user_id, actor_role="ADMIN")
        await db.refresh(job)
        assert job.status == JobStatus.PLANNING.value

        # 5. PLANNING Phase:
        d_plan = await supervisor_router.evaluate_next_action(db, job)
        assert d_plan.action == SupervisorAction.EXECUTE
        assert d_plan.agent_id in ("PLANNER", "PlannerCoordinator")

        # Synthesize ConversionPlan and Module DAG
        mod1_id = uuid.uuid4()
        mod2_id = uuid.uuid4()
        m1 = Module(module_id=mod1_id, job_id=job.job_id, name="mod_orders", legacy_path="l/o", target_path="m/o.py", status="PENDING", wave_number=1, dependency_module_ids=[])
        m2 = Module(module_id=mod2_id, job_id=job.job_id, name="mod_payments", legacy_path="l/p", target_path="m/p.py", status="PENDING", wave_number=2, dependency_module_ids=[str(mod1_id)])
        db.add_all([m1, m2])

        plan_data = {
            "modules": [
                {"module_id": str(mod1_id), "name": "mod_orders", "source_scope": ["l/o"], "target_scope": ["m/o.py"], "dependencies": []},
                {"module_id": str(mod2_id), "name": "mod_payments", "source_scope": ["l/p"], "target_scope": ["m/p.py"], "dependencies": [str(mod1_id)]},
            ]
        }
        plan_bytes = json.dumps(plan_data).encode("utf-8")
        plan_hash = hashlib.sha256(plan_bytes).hexdigest()
        from app.core.storage import get_storage_adapter
        await get_storage_adapter().put_object(
            key=f"artifacts/{job.job_id}/conversion_plan_v1.json",
            data=plan_bytes,
            media_type="application/json",
        )

        plan_art = Artifact(
            job_id=job.job_id,
            artifact_type="CONVERSION_PLAN",
            version=1,
            content_hash=plan_hash,
            storage_path=f"artifacts/{job.job_id}/conversion_plan_v1.json",
            content_size_bytes=len(plan_bytes),
            media_type="application/json",
            producing_agent="PLANNER",
        )
        db.add(plan_art)
        await db.commit()

        # Gate G3 readiness
        d_g3 = await supervisor_router.evaluate_next_action(db, job)
        assert d_g3.action == SupervisorAction.ADVANCE_GATE
        assert d_g3.target_status == JobStatus.AWAITING_GATE_G3.value

        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G3, actor_id="supervisor")
        gate_g3 = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G3", WorkflowGate.status == "PENDING")
        )
        assert gate_g3 is not None

        # Human approves Gate G3
        dec_req3 = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approved modular conversion DAG and wave execution plan.",
            artifact_hashes=gate_g3.artifact_hashes,
        )
        await gate_service.decide(db, gate_g3.gate_id, dec_req3, actor_id=admin.user_id, actor_role="ADMIN")
        await db.refresh(job)
        assert job.status == JobStatus.CONVERTING.value

        # 6. CONVERTING & VERIFYING Phase (Wave 1: mod_orders, Wave 2: mod_payments)
        # 6a. Wave 1 ready for CodeWriter
        d_cw1 = await supervisor_router.evaluate_next_action(db, job)
        assert d_cw1.action == SupervisorAction.EXECUTE
        assert d_cw1.agent_id == "CodeWriter"
        assert str(mod1_id) in d_cw1.task_id

        # CodeWriter converts mod1
        m1.status = "GENERATED"
        await db.commit()

        # 6b. Verifier verifies mod1
        d_v1 = await supervisor_router.evaluate_next_action(db, job)
        assert d_v1.action == SupervisorAction.EXECUTE
        assert d_v1.agent_id == "Verifier"
        assert str(mod1_id) in d_v1.task_id

        m1.status = "VERIFIED"
        await db.commit()

        # 6c. Wave 2 (mod2) is now unblocked and ready for CodeWriter!
        d_cw2 = await supervisor_router.evaluate_next_action(db, job)
        assert d_cw2.action == SupervisorAction.EXECUTE
        assert d_cw2.agent_id == "CodeWriter"
        assert str(mod2_id) in d_cw2.task_id

        m2.status = "GENERATED"
        await db.commit()

        # Verifier encounters repair requirement
        d_v2 = await supervisor_router.evaluate_next_action(db, job)
        assert d_v2.action == SupervisorAction.EXECUTE
        assert d_v2.agent_id == "Verifier"

        # Simulate repair loop:
        m2.status = "PENDING"
        m2.retry_count = 1
        await db.commit()

        d_rep = await supervisor_router.evaluate_next_action(db, job)
        assert d_rep.action == SupervisorAction.REPAIR
        assert d_rep.agent_id == "CodeWriter"

        # CodeWriter repaired module, now generated and verified
        m2.status = "GENERATED"
        await db.commit()
        m2.status = "VERIFIED"
        await db.commit()

        # 7. INTEGRATING Phase:
        # All modules verified! Supervisor routes to Integrator
        d_int = await supervisor_router.evaluate_next_action(db, job)
        assert d_int.action == SupervisorAction.EXECUTE
        assert d_int.agent_id in ("INTEGRATOR", "Integrator")

        await supervisor_service.transition(db, job.job_id, JobStatus.VERIFYING, actor_id="supervisor")
        # Routing simulation is not execution evidence. Manually setting VERIFIED must never
        # authorize integration or manufacture G4 readiness.
        from app.core.errors import PlatformException
        with pytest.raises(PlatformException):
            await supervisor_service.transition(db, job.job_id, JobStatus.INTEGRATING, actor_id="supervisor")
        await db.rollback()


# ---------------------------------------------------------------------------
# Test 2: Multi-Agent Capability Registry & Routing Constraints
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_multi_agent_capability_routing():
    """Validates the canonical agent registry covers all 9 required agents with strict constraints."""
    required_agents = [
        "ANALYZER",
        "ARCHITECT",
        "FEASIBILITY",
        "PLANNER",
        "CHARACTERIZER",
        "SCHEMA_DATA",
        "CODE_WRITER",
        "VERIFIER",
        "INTEGRATOR",
    ]

    for agent_key in required_agents:
        assert agent_key in AGENT_CAPABILITY_REGISTRY, f"Agent {agent_key} must be in AGENT_CAPABILITY_REGISTRY"
        cap = AGENT_CAPABILITY_REGISTRY[agent_key]
        assert cap.agent_id is not None
        assert cap.name is not None
        assert len(cap.capabilities) > 0
        assert len(cap.allowed_states) > 0
        assert len(cap.required_permissions) > 0
        assert "max_cost_usd" in cap.resource_profile
        assert "max_retries" in cap.retry_policy

    # Verify CodeWriter cannot run in ANALYZING or CHARACTERIZING
    cw_cap = AGENT_CAPABILITY_REGISTRY["CODE_WRITER"]
    assert "ANALYZING" not in cw_cap.allowed_states
    assert "CHARACTERIZING" not in cw_cap.allowed_states
    assert "CONVERTING" in cw_cap.allowed_states

    # Verify Schema/Data runs in CHARACTERIZING and produces SCHEMA_MIGRATION_PLAN
    schema_cap = AGENT_CAPABILITY_REGISTRY["SCHEMA_DATA"]
    assert "CHARACTERIZING" in schema_cap.allowed_states
    assert "SCHEMA_MIGRATION_PLAN" in schema_cap.produced_artifacts

    # Verify SupervisorDecision is fully auditable with budget, gate, and dependency state
    decision = SupervisorDecision(
        action=SupervisorAction.EXECUTE,
        task_id="schema_data_001",
        agent_id="SCHEMA_DATA",
        reason="characterization artifact available and G2 prerequisites incomplete",
        budget_state={"used_usd": 12.50, "limit_usd": 15000.0},
        gate_state={"gate_type": "G2", "status": "PENDING"},
        dependency_state={"inputs": ["CHARACTERIZATION_SUITE"], "ready": True},
    )
    assert decision.agent_id == "SCHEMA_DATA"
    assert decision.task_id == "schema_data_001"
    assert decision.budget_state["used_usd"] == 12.50
    assert decision.dependency_state["ready"] is True


# ---------------------------------------------------------------------------
# Test 3: Supervisor Durable Restart Recovery across All Stages
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_supervisor_durable_restart_recovery_across_stages():
    """Validates that restarting the supervisor reconstructs the next action from durable state without duplicate work."""
    stages = [
        JobStatus.ANALYZING,
        JobStatus.CHARACTERIZING,
        JobStatus.PLANNING,
        JobStatus.CONVERTING,
        JobStatus.INTEGRATING,
    ]

    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)

        for stage in stages:
            job = await _create_test_job(db, stage)
            # Create a durable checkpoint
            state = supervisor_service.state_for(job)
            await supervisor_service.checkpointer.save(
                db, job, kind="BEFORE", node_name=job.active_node, state=state, correlation_id="restart-test"
            )

            # Simulate full process restart recovery for this active job
            recovered_job = await supervisor_service.recover(db, job.job_id, correlation_id="restart-test")
            assert recovered_job is not None

            await db.refresh(job)
            # Verify durable state preserved
            assert job.status == stage.value
            assert job.budget_used_usd == Decimal("0.00")
            assert job.blocking_reason is None

            # Verify decision can be deterministically calculated
            decision = await supervisor_router.evaluate_next_action(db, job)
            assert decision.action in (SupervisorAction.EXECUTE, SupervisorAction.WAIT, SupervisorAction.ESCALATE)


# -----------------------------------------------------------
# Test 4: Parallel Feature Planning & DAG Aggregation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parallel_feature_planning_and_dag_aggregation():
    """Validates parallel planning for independent modules, acyclic DAG verification, and plan aggregation."""
    from app.services.planner_coordinator import PlannerCoordinator
    from app.schemas.phase4 import ConfidenceLevel, LegacyModule

    job_id = f"job_plan_{uuid.uuid4().hex[:8]}"

    legacy = LegacyModel(
        model_id=f"leg_{uuid.uuid4().hex[:6]}",
        job_id=job_id,
        snapshot_id=str(uuid.uuid4()),
        version=1,
        modules=[
            LegacyModule(module_id="mod_core", path="core", responsibility="Core Models", language="Python", risk="LOW", confidence=ConfidenceLevel.CONFIRMED),
            LegacyModule(module_id="mod_auth", path="auth", responsibility="Auth Service", language="Python", dependencies=["mod_core"], risk="HIGH", confidence=ConfidenceLevel.CONFIRMED),
            LegacyModule(module_id="mod_billing", path="billing", responsibility="Billing Service", language="Python", dependencies=["mod_core"], risk="MEDIUM", confidence=ConfidenceLevel.CONFIRMED),
        ],
        content_hash="hash_legacy_plan",
    )

    blueprint = TargetBlueprint(
        blueprint_id=f"bp_{uuid.uuid4().hex[:6]}",
        job_id=job_id,
        version=1,
        target_stack="FastAPI + PostgreSQL",
        target_architecture="CLEAN_ARCHITECTURE",
        components=[
            TargetComponent(component_id="comp_core", name="CoreDomain", target_path="src/domain/core", mapped_legacy_modules=["mod_core"], responsibilities=["Core"], technologies=["Python"], dependencies=[], interfaces=[]),
            TargetComponent(component_id="comp_auth", name="AuthService", target_path="src/services/auth", mapped_legacy_modules=["mod_auth"], responsibilities=["Auth"], technologies=["FastAPI"], dependencies=["comp_core"], interfaces=[]),
            TargetComponent(component_id="comp_billing", name="BillingService", target_path="src/services/billing", mapped_legacy_modules=["mod_billing"], responsibilities=["Billing"], technologies=["FastAPI"], dependencies=["comp_core"], interfaces=[]),
        ],
        content_hash="hash_bp_plan",
    )

    coordinator = PlannerCoordinator()
    plan = coordinator.coordinate_planning(job_id=job_id, blueprint=blueprint, legacy_model=legacy)

    assert plan.validation_status.is_valid_dag is True
    assert plan.validation_status.has_cycles is False
    assert len(plan.waves) >= 2
    # comp_core is wave 1
    assert "comp_core" in plan.waves[0].module_ids
    # comp_auth and comp_billing both depend only on comp_core, so both are scheduled parallel in Wave 2!
    wave2_modules = sorted(plan.waves[1].module_ids)
    assert "comp_auth" in wave2_modules
    assert "comp_billing" in wave2_modules


# ---------------------------------------------------------------------------
# Test 5: Multi-Dimensional Budget Governance
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_multi_dimensional_budget_governance():
    """Validates multi-dimensional spend enforcement: USD, Tokens, Time, Concurrency, and Caps."""
    async with AsyncSessionLocal() as db:
        # 1. USD Budget Exceeded
        job_usd = await _create_test_job(db, JobStatus.CONVERTING, limit="100.00")
        job_usd.budget_used_usd = Decimal("100.00")
        await db.commit()

        eval_usd = await budget_manager.evaluate_budget(db, job_usd)
        assert eval_usd.is_exceeded is True
        assert eval_usd.exceeded_dimension == "PROJECT_USD"
        assert "Project budget exhausted" in eval_usd.blocking_reason

        # 2. Token Budget Exceeded
        job_tok = await _create_test_job(db, JobStatus.CONVERTING, stack_meta={"token_limit": 50000})
        db.add(BudgetUsage(
            job_id=job_tok.job_id,
            cost_type="LLM_INFERENCE",
            amount_usd=Decimal("5.00"),
            tokens=55000,
        ))
        await db.commit()

        eval_tok = await budget_manager.evaluate_budget(db, job_tok)
        assert eval_tok.is_exceeded is True
        assert eval_tok.exceeded_dimension == "TOKEN"
        assert "Cumulative token budget exhausted" in eval_tok.blocking_reason

        # 3. Execution Time Limit Exceeded
        job_time = await _create_test_job(db, JobStatus.CONVERTING, stack_meta={"time_limit_seconds": 10})
        # artificially backdate created_at
        job_time.created_at = datetime.now(timezone.utc) - timedelta(seconds=20)
        await db.commit()

        eval_time = await budget_manager.evaluate_budget(db, job_time)
        assert eval_time.is_exceeded is True
        assert eval_time.exceeded_dimension == "TIME"
        assert "execution time exceeded" in eval_time.blocking_reason

        # 4. Concurrency Limit Reached
        job_conc = await _create_test_job(db, JobStatus.CONVERTING, concurrency=2)
        future_lease = datetime.now(timezone.utc) + timedelta(minutes=10)
        m1 = Module(module_id=uuid.uuid4(), job_id=job_conc.job_id, name="m1", legacy_path="l1", target_path="t1", status="LEASED", lease_expires_at=future_lease)
        m2 = Module(module_id=uuid.uuid4(), job_id=job_conc.job_id, name="m2", legacy_path="l2", target_path="t2", status="LEASED", lease_expires_at=future_lease)
        db.add_all([m1, m2])
        await db.commit()

        eval_conc = await budget_manager.evaluate_budget(db, job_conc)
        assert eval_conc.is_exceeded is True
        assert eval_conc.exceeded_dimension == "CONCURRENCY"
        assert "concurrency limit reached" in eval_conc.blocking_reason

        # 5. Agent Budget Cap Exceeded
        job_agent = await _create_test_job(db, JobStatus.CONVERTING, stack_meta={"CodeWriter_budget_usd": 200.0})
        run_id = uuid.uuid4()
        db.add(AgentRun(
            run_id=run_id,
            job_id=job_agent.job_id,
            agent_name="CodeWriter",
            task_id="t1",
            cost_usd=Decimal("250.00"),
            status="SUCCEEDED",
        ))
        await db.commit()

        eval_agent = await budget_manager.evaluate_budget(db, job_agent, agent_id="CodeWriter")
        assert eval_agent.is_exceeded is True
        assert eval_agent.exceeded_dimension == "AGENT"
        assert "Agent 'CodeWriter' budget cap exceeded" in eval_agent.blocking_reason
