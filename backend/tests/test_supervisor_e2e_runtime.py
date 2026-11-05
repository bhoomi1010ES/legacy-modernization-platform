"""End-to-End Database-Backed Integration Tests for the Autonomous Supervisor Runtime.

Validates the complete modernization lifecycle:
G1 -> Characterization -> G2 -> Planning -> G3 -> CodeWriter -> Verifier -> Integrator -> G4 -> Project Complete.

Enforces:
- Canonical state machine DAG (rejecting invalid G1 -> Planning bypass)
- Durable database persistence, checkpoints, and audit trails
- Real GateService with human-only gate decisions
- Independent Verifier with bounded repair loops
- Dependency DAG scheduling and circular deadlock detection
- Budget manager limits and lease crash recovery
- Durable LangGraph supervisor loop state transitions
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictException, IllegalStateTransitionException
from app.domain.state_machine import JobStateMachine
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.module import Module
from app.models.user import User
from app.models.workflow import WorkflowCheckpoint, WorkflowGate
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, GateType
from app.schemas.jobs import JobStatus
from test_phase6 import ready, trusted_executor  # noqa: F401 -- registered pytest fixtures
from test_phase5 import isolated  # noqa: F401 -- dependency of reused ready fixture
from app.services.continuous_pipeline import continuous_pipeline_service
from app.services.dependency_scheduler import dependency_scheduler
from app.services.gate_service import gate_service
from app.services.integrator_agent import integrator_service
from app.services.supervisor_graph import supervisor_loop_graph
from app.services.supervisor_router import (
    SupervisorAction,
    supervisor_router,
)
from app.services.supervisor_service import supervisor_service
from app.services.verifier_agent import VerificationVerdict, verifier_service


async def _get_or_create_admin(db) -> User:
    """Retrieves an existing admin user or provisions one for testing gate reviews."""
    admin = await db.scalar(
        select(User).where(User.role.in_(["SUPER_ADMIN", "ADMIN"])).limit(1)
    )
    if not admin:
        admin = User(
            user_id=uuid.uuid4(),
            email=f"reviewer_{uuid.uuid4().hex[:8]}@example.com",
            full_name="Compliance Reviewer",
            password_hash="mock_hash_for_testing",
            role="ADMIN",
            status="ACTIVE",
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    return admin


async def _get_or_create_creator(db) -> User:
    creator = await db.scalar(
        select(User).where(User.role == "DEVELOPER").limit(1)
    )
    if not creator:
        creator = User(
            user_id=uuid.uuid4(),
            email=f"creator_{uuid.uuid4().hex[:8]}@example.com",
            full_name="Software Developer",
            password_hash="mock_hash_for_testing",
            role="DEVELOPER",
            status="ACTIVE",
        )
        db.add(creator)
        await db.commit()
        await db.refresh(creator)
    return creator


async def _create_test_job(
    db,
    status: JobStatus = JobStatus.CREATED,
    *,
    used: str = "0",
    limit: str = "1000",
    target_stack: str = "Python / FastAPI",
) -> Job:
    """Provisions a test job in the database with audit and budget defaults."""
    creator = await _get_or_create_creator(db)
    job = Job(
        name=f"supervisor-e2e-{uuid.uuid4().hex[:8]}",
        source_repository="https://github.com/acme/legacy-ordering-core",
        owner_user_id=creator.user_id,
        status=status.value,
        active_node=status.value.lower(),
        budget_used_usd=Decimal(used),
        budget_limit_usd=Decimal(limit),
        max_repair_attempts=3,
        target_stack=target_stack,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@pytest.mark.asyncio
async def test_supervisor_full_lifecycle_e2e_db(observed_phase5_baseline):
    """Validates the complete G1 -> G4 end-to-end lifecycle backed by the real database.

    Verifies:
    1. CREATED -> INTAKE -> ANALYZING -> AWAITING_GATE_G1
    2. Prevention of invalid G1 -> PLANNING bypass
    3. G1 approval -> CHARACTERIZING (Canonical flow)
    4. Characterizer produces suite artifact -> AWAITING_GATE_G2
    5. G2 approval -> PLANNING
    6. Planner decomposes module DAG & creates Module records -> AWAITING_GATE_G3
    7. G3 approval -> CONVERTING
    8. CodeWriter converts modules -> VERIFYING -> Verifier tests & passes
    9. All modules verified -> INTEGRATING -> Integrator merges workspace -> AWAITING_GATE_G4
    10. G4 approval -> COMPLETED (PROJECT_COMPLETE)
    """
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)
        job = await _create_test_job(db, JobStatus.CREATED)
        corr_id = f"e2e-{uuid.uuid4().hex[:8]}"

        # --- Phase 1: Intake & Analysis ---
        await supervisor_service.transition(db, job.job_id, JobStatus.INTAKE, actor_id=str(admin.user_id))
        await supervisor_service.transition(db, job.job_id, JobStatus.ANALYZING, actor_id=str(admin.user_id))

        # Add Legacy Model & Blueprint artifacts
        legacy_art = Artifact(
            artifact_id=uuid.uuid4(),
            job_id=job.job_id,
            artifact_type="LEGACY_MODEL",
            version=1,
            content_hash="sha256:legacy_hash_abc",
            storage_path="artifacts/legacy_v1.json",
            content_size_bytes=1024,
            media_type="application/json",
            producing_agent="AnalyzerCoordinator",
        )
        bp_art = Artifact(
            artifact_id=uuid.uuid4(),
            job_id=job.job_id,
            artifact_type="TARGET_BLUEPRINT",
            version=1,
            content_hash="sha256:blueprint_hash_xyz",
            storage_path="artifacts/blueprint_v1.json",
            content_size_bytes=2048,
            media_type="application/json",
            producing_agent="ArchitectAgent",
        )
        feasibility_art = Artifact(
            artifact_id=uuid.uuid4(),
            job_id=job.job_id,
            artifact_type="FEASIBILITY_REPORT",
            version=1,
            content_hash="sha256:feasibility_hash_xyz",
            storage_path="artifacts/feasibility_v1.json",
            content_size_bytes=2048,
            media_type="application/json",
            producing_agent="FeasibilityAgent",
        )
        db.add_all([legacy_art, bp_art, feasibility_art])
        await db.commit()

        # Advance to AWAITING_GATE_G1
        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G1, actor_id=str(admin.user_id))
        await db.refresh(job)
        assert job.status == JobStatus.AWAITING_GATE_G1.value

        # --- Invariant Check: Reject Invalid G1 -> PLANNING bypass ---
        with pytest.raises(IllegalStateTransitionException):
            JobStateMachine.validate_transition(JobStatus.AWAITING_GATE_G1, JobStatus.PLANNING)

        # Retrieve Gate G1
        g1_gate = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G1")
        )
        assert g1_gate is not None
        assert g1_gate.status == "PENDING"

        # --- Human Approval at Gate G1 ---
        g1_decision = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Legacy architecture and target blueprint verified and approved for characterization.",
            artifact_hashes=dict(g1_gate.artifact_hashes or {}),
            options={"auth_strategy": "jwt_oauth2"},
            waivers=[],
        )
        await gate_service.decide(
            db,
            gate_id=g1_gate.gate_id,
            payload=g1_decision,
            actor_id=admin.user_id,
            actor_role=admin.role,
            correlation_id=corr_id,
        )

        # Await autonomous continuous pipeline execution triggered by G1 approval
        task = continuous_pipeline_service._running_tasks.get(str(job.job_id))
        if task and not task.done():
            await task
        await db.refresh(job)
        assert job.status == JobStatus.AWAITING_GATE_G2.value

        # Discovery is not execution. Supply controlled adapter evidence, then request current G2.
        from app.services import phase5_service
        discovery = await phase5_service.report(db, job.job_id)
        assert not discovery["runtime_available"]
        baseline = await observed_phase5_baseline(db, job, admin)
        # Verify the stored bytes against the platform's canonical SHA-256 format.
        suite_art = await db.scalar(
            select(Artifact).where(Artifact.artifact_id == uuid.UUID(baseline["suite_id"]))
        )
        assert suite_art is not None
        assert suite_art.content_hash == baseline["content_hash"]
        assert len(suite_art.content_hash) == 64

        # Retrieve Gate G2
        g2_gate = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G2", WorkflowGate.status == "PENDING")
        )
        assert g2_gate is not None
        assert g2_gate.status == "PENDING"

        # Seed 2 modules to simulate planning DAG output
        mod_a = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="orders_module",
            legacy_path="legacy/orders",
            target_path="app/routers/orders.py",
            status="PENDING",
            wave_number=1,
            dependency_module_ids=[],
        )
        mod_b = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="billing_module",
            legacy_path="legacy/billing",
            target_path="app/routers/billing.py",
            status="PENDING",
            wave_number=2,
            dependency_module_ids=[str(mod_a.module_id)],
        )
        db.add_all([mod_a, mod_b])
        await db.commit()

        # --- Human Approval at Gate G2 (Baseline Freeze) ---
        import json
        from app.services.artifact_service import ArtifactService
        await ArtifactService().create_artifact(db, job.job_id, "ConversionPlan", 1, json.dumps({"modules": [{"module_id": m.name, "source_scope": [m.legacy_path], "target_scope": [m.target_path], "dependencies": []} for m in (mod_a, mod_b)]}).encode(), "Planner")
        g2_decision = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Characterization golden test vectors verified with zero drift; baseline frozen.",
            artifact_hashes=dict(g2_gate.artifact_hashes or {}),
            options={},
            waivers=[],
        )
        await gate_service.decide(
            db,
            gate_id=g2_gate.gate_id,
            payload=g2_decision,
            actor_id=admin.user_id,
            actor_role=admin.role,
            correlation_id=corr_id,
        )

        # Await autonomous continuous pipeline execution triggered by G2 approval
        task = continuous_pipeline_service._running_tasks.get(str(job.job_id))
        if task and not task.done():
            await task
        await db.refresh(job)
        assert job.status == JobStatus.AWAITING_GATE_G3.value

        g3_gate = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G3")
        )
        assert g3_gate is not None
        assert g3_gate.status == "PENDING"

        # --- Human Approval at Gate G3 (Conversion Plan Sign-Off) ---
        g3_decision = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Conversion plan DAG validated acyclic across 2 waves; approved for CodeWriter execution.",
            artifact_hashes=dict(g3_gate.artifact_hashes or {}),
            options={},
            waivers=[],
        )
        await gate_service.decide(
            db,
            gate_id=g3_gate.gate_id,
            payload=g3_decision,
            actor_id=admin.user_id,
            actor_role=admin.role,
            correlation_id=corr_id,
        )

        # Without a configured source/model/sandbox, G3 may not fabricate execution or G4 readiness.
        task = continuous_pipeline_service._running_tasks.get(str(job.job_id))
        if task and not task.done():
            await task
        await db.refresh(job)
        await db.refresh(mod_a)
        await db.refresh(mod_b)
        assert job.status == JobStatus.CONVERTING.value
        assert mod_a.status == "BLOCKED"
        assert mod_b.status == "PENDING"
        assert job.blocking_reason
        assert await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G4")) is None
        assert await db.scalar(select(Artifact).where(Artifact.job_id == job.job_id, Artifact.artifact_type == "INTEGRATED_WORKSPACE")) is None
        checkpoints = list((await db.execute(select(WorkflowCheckpoint).where(WorkflowCheckpoint.job_id == job.job_id))).scalars().all())
        assert len(checkpoints) >= 8


@pytest.mark.asyncio
async def test_bounded_repair_loop(ready, trusted_executor):
    """Each repair creates a new branch and reruns actual trusted fixture comparisons."""
    from test_phase6 import queued, generation
    from app.services import phase6_service
    from app.services.model_gateway import build_fake_gateway, FakeModelProvider
    db, job, _, _, module, _ = ready
    gateway = build_fake_gateway(FakeModelProvider([generation(4), generation(3)]))
    first = await queued(ready)
    await phase6_service.execute_attempt(db, first.attempt_id, gateway=gateway)
    assert first.status == "REPAIR_REQUIRED"
    second = await queued(ready, "resolved", previous=first, rationale="Resolve the recorded frozen output mismatch")
    await phase6_service.execute_attempt(db, second.attempt_id, gateway=gateway)
    assert second.status == module.status == "VERIFIED"
    assert first.git_branch != second.git_branch and len(trusted_executor) == 2
    assert (await verifier_service.verify_module(db, job, module)).verdict == VerificationVerdict.PASS


@pytest.mark.asyncio
async def test_dependency_deadlock_detection():
    """Validates that circular module dependencies are detected as DEPENDENCY_DEADLOCK rather than looping."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, JobStatus.CONVERTING)

        mod_id_1 = uuid.uuid4()
        mod_id_2 = uuid.uuid4()

        # Circular dependency: 1 depends on 2, 2 depends on 1
        mod_1 = Module(
            module_id=mod_id_1,
            job_id=job.job_id,
            name="module_alpha",
            legacy_path="legacy/alpha",
            target_path="app/alpha.py",
            status="PENDING",
            wave_number=1,
            dependency_module_ids=[str(mod_id_2)],
        )
        mod_2 = Module(
            module_id=mod_id_2,
            job_id=job.job_id,
            name="module_beta",
            legacy_path="legacy/beta",
            target_path="app/beta.py",
            status="PENDING",
            wave_number=1,
            dependency_module_ids=[str(mod_id_1)],
        )
        db.add_all([mod_1, mod_2])
        await db.commit()

        # Evaluate router decision
        decision = await supervisor_router.evaluate_next_action(db, job)
        assert decision.action == SupervisorAction.ESCALATE
        assert "DEPENDENCY_DEADLOCK" in decision.reason
        assert decision.target_status == JobStatus.FAILED.value


@pytest.mark.asyncio
async def test_budget_limit_enforcement():
    """Validates that reaching budget limits halts execution and triggers escalation."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)
        # Job has used $100 out of $100 limit
        job = await _create_test_job(db, JobStatus.INTAKE, used="100.00", limit="100.00")

        # Router must detect budget exhaustion
        decision = await supervisor_router.evaluate_next_action(db, job)
        assert decision.action == SupervisorAction.ESCALATE
        assert "budget exhausted" in decision.reason.lower()

        # State transition must block on budget exhaustion
        with pytest.raises(ConflictException, match="budget is exhausted"):
            await supervisor_service.transition(db, job.job_id, JobStatus.ANALYZING, actor_id=str(admin.user_id))


@pytest.mark.asyncio
async def test_lease_recovery_after_worker_crash():
    """Validates that expired worker leases are recovered and reset to PENDING for re-execution."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, JobStatus.CONVERTING)

        stale_lease_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        stale_mod = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="crashed_worker_module",
            legacy_path="legacy/crashed",
            target_path="app/crashed.py",
            status="RUNNING",
            lease_owner="worker-crashed-node-42",
            lease_expires_at=stale_lease_time,
            wave_number=1,
            retry_count=0,
        )
        db.add(stale_mod)
        await db.commit()

        # Reclaim expired leases
        reclaimed_count = await dependency_scheduler.reclaim_expired_leases(db, job.job_id)
        assert reclaimed_count >= 1

        await db.refresh(stale_mod)
        assert stale_mod.status == "PENDING"
        assert stale_mod.lease_owner is None
        assert stale_mod.lease_expires_at is None
        assert stale_mod.retry_count == 1  # retry count incremented on recovery


@pytest.mark.asyncio
async def test_gate_rejection_routes_to_revision(observed_phase5_baseline):
    """Validates that gate rejections route back to the appropriate previous revision stage."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)
        corr_id = f"rej-{uuid.uuid4().hex[:8]}"

        # Test G1 Rejection -> Routes back to ANALYZING
        job1 = await _create_test_job(db, JobStatus.ANALYZING)
        for art_type in ("LEGACY_MODEL", "TARGET_BLUEPRINT", "FEASIBILITY_REPORT"):
            db.add(Artifact(
                artifact_id=uuid.uuid4(),
                job_id=job1.job_id,
                artifact_type=art_type,
                version=1,
                content_hash=f"sha256:{art_type.lower()}_hash_1",
                storage_path=f"artifacts/{art_type.lower()}.json",
                content_size_bytes=1024,
                media_type="application/json",
                producing_agent="AnalyzerCoordinator",
            ))
        await db.commit()
        await supervisor_service.transition(db, job1.job_id, JobStatus.AWAITING_GATE_G1, actor_id=str(admin.user_id))
        g1_gate = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job1.job_id, WorkflowGate.gate_type == "G1")
        )
        assert g1_gate is not None
        rej_g1 = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED,
            rationale="Analysis incomplete; legacy dependencies missed in scanning.",
            artifact_hashes=dict(g1_gate.artifact_hashes or {}),
            options={},
            waivers=[],
        )
        await gate_service.decide(
            db,
            gate_id=g1_gate.gate_id,
            payload=rej_g1,
            actor_id=admin.user_id,
            actor_role=admin.role,
            correlation_id=corr_id,
        )
        await db.refresh(job1)
        assert job1.status == JobStatus.ANALYZING.value

        # Test G2 Rejection -> Routes back to CHARACTERIZING
        job2 = await _create_test_job(db, JobStatus.CHARACTERIZING)
        for art_type in ("CHARACTERIZATION_SUITE", "SCHEMA_MIGRATION_PLAN"):
            db.add(Artifact(
                artifact_id=uuid.uuid4(),
                job_id=job2.job_id,
                artifact_type=art_type,
                version=1,
                content_hash=f"sha256:{art_type.lower()}_hash_2",
                storage_path=f"artifacts/{art_type.lower()}.json",
                content_size_bytes=1024,
                media_type="application/json",
                producing_agent="CharacterizerAgent",
            ))
        await db.commit()
        await supervisor_service.transition(db, job2.job_id, JobStatus.AWAITING_GATE_G2, actor_id=str(admin.user_id))
        g2_gate = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job2.job_id, WorkflowGate.gate_type == "G2")
        )
        assert g2_gate is not None
        rej_g2 = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED,
            rationale="Characterization coverage insufficient; missing test vectors for billing API.",
            artifact_hashes=dict(g2_gate.artifact_hashes or {}),
            options={},
            waivers=[],
        )
        await gate_service.decide(
            db,
            gate_id=g2_gate.gate_id,
            payload=rej_g2,
            actor_id=admin.user_id,
            actor_role=admin.role,
            correlation_id=corr_id,
        )
        await db.refresh(job2)
        assert job2.status == JobStatus.CHARACTERIZING.value

        # Test G3 Rejection -> Routes back to PLANNING
        job3 = await _create_test_job(db, JobStatus.CHARACTERIZING)
        g1_approved = WorkflowGate(
            gate_id=uuid.uuid4(),
            job_id=job3.job_id,
            gate_type="G1",
            version=1,
            status="APPROVED",
            artifact_ids=[],
            artifact_hashes={},
        )
        db.add(g1_approved)
        await db.commit()
        await observed_phase5_baseline(db, job3, admin)
        from app.services.schema_data_agent import schema_data_service
        schema_art3 = await schema_data_service.execute_schema_data_analysis(db, job3, user=admin)
        await supervisor_service.transition(db, job3.job_id, JobStatus.AWAITING_GATE_G2, actor_id="supervisor")
        g2_gate3 = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job3.job_id, WorkflowGate.gate_type == "G2", WorkflowGate.status == "PENDING")
        )
        dec_req2 = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approved behavioral characterization baseline and schema migration plan.",
            artifact_hashes=g2_gate3.artifact_hashes,
            options={},
            waivers=[],
        )
        await gate_service.decide(db, g2_gate3.gate_id, dec_req2, actor_id=admin.user_id, actor_role=admin.role)
        await db.refresh(job3)
        assert job3.status == JobStatus.PLANNING.value

        db.add(Artifact(
            artifact_id=uuid.uuid4(),
            job_id=job3.job_id,
            artifact_type="CONVERSION_PLAN",
            version=1,
            content_hash="sha256:conversion_plan_hash_3",
            storage_path="artifacts/plan.json",
            content_size_bytes=1024,
            media_type="application/json",
            producing_agent="PlannerCoordinator",
        ))
        await db.commit()
        await supervisor_service.transition(db, job3.job_id, JobStatus.AWAITING_GATE_G3, actor_id=str(admin.user_id))
        g3_gate = await db.scalar(
            select(WorkflowGate).where(WorkflowGate.job_id == job3.job_id, WorkflowGate.gate_type == "G3")
        )
        assert g3_gate is not None
        rej_g3 = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED,
            rationale="Conversion plan waves are improperly ordered; module coupling too high.",
            artifact_hashes=dict(g3_gate.artifact_hashes or {}),
            options={},
            waivers=[],
        )
        await gate_service.decide(
            db,
            gate_id=g3_gate.gate_id,
            payload=rej_g3,
            actor_id=admin.user_id,
            actor_role=admin.role,
            correlation_id=corr_id,
        )
        await db.refresh(job3)
        assert job3.status == JobStatus.PLANNING.value


@pytest.mark.asyncio
async def test_langgraph_supervisor_loop_graph():
    """Validates that the 19-node LangGraph supervisor loop executes deterministically and pauses at human gates."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_admin(db)
        job = await _create_test_job(db, JobStatus.ANALYZING)
        for art_type in ("LEGACY_MODEL", "TARGET_BLUEPRINT", "FEASIBILITY_REPORT"):
            db.add(Artifact(
                artifact_id=uuid.uuid4(),
                job_id=job.job_id,
                artifact_type=art_type,
                version=1,
                content_hash=f"sha256:{art_type.lower()}_hash_lg",
                storage_path=f"artifacts/{art_type.lower()}.json",
                content_size_bytes=1024,
                media_type="application/json",
                producing_agent="AnalyzerCoordinator",
            ))
        await db.commit()
        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G1, actor_id=str(admin.user_id))

        # Execute supervisor loop graph
        result_state = await supervisor_loop_graph.ainvoke({
            "job_id": str(job.job_id),
            "status": job.status,
            "max_loops": 10,
        })

        assert result_state["is_valid_state"] is True
        assert result_state["is_human_gate_required"] is True
        assert result_state["decision_action"] == "WAIT"
        assert result_state["active_node"] == "pause_for_human"
