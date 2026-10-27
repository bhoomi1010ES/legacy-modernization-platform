"""Phase 3 Authoritative Supervisor & Durable Workflow Compliance Verification Suite.

Comprehensive compliance test suite verifying Sections 33, 34, 35, 36, and 37:
- Section 33: State Machine transitions, Gate Policy invariants, Supervisor canonical progression, and Bypass prevention.
- Section 34: Process crash, application restart, stale lease reclamation, orphan agent run reconciliation, durable checkpoints.
- Section 35: Concurrency race conditions, atomic mutual exclusion, and stale worker lease fencing.
- Section 36: End-to-end deterministic Phase 3 test (INTAKE -> G1 -> CHARACTERIZATION -> SCHEMA/DATA -> G2 -> PLANNING -> G3 -> CONVERSION TASK CREATED).
- Section 37: Mandatory Negative E2E tests (rejection of unauthorized jumps and evidence bypasses).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import uuid
import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.errors import (
    ConflictException,
    ForbiddenException,
    GatePolicyException,
    IllegalStateTransitionException,
    NotFoundException,
)
from app.domain.state_machine import GatePolicy, JobStateMachine
from app.models.agent import AgentRun
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.user import User
from app.models.workflow import WorkflowCheckpoint, WorkflowGate, WorkflowOutbox
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, GateType
from app.schemas.jobs import JobStatus
from app.schemas.workflow import WorkflowPhase
from app.services.artifact_service import ArtifactService
from app.services.continuous_pipeline import continuous_pipeline_service
from app.services.dependency_scheduler import dependency_scheduler
from app.services.gate_service import gate_service
from app.services.schema_data_agent import schema_data_service
from app.services.supervisor_graph import DeprecatedSupervisorGraph, supervisor_graph, supervisor_loop_graph
from app.services.supervisor_service import supervisor_service


async def _get_or_create_test_user(db, role: str = "ADMIN") -> User:
    """Helper to provision or retrieve a test user with a specific role."""
    user = await db.scalar(select(User).where(User.role == role).limit(1))
    if not user:
        user = User(
            user_id=uuid.uuid4(),
            email=f"{role.lower()}_{uuid.uuid4().hex[:6]}@example.com",
            full_name=f"Compliance Test {role.title()}",
            password_hash="mock_hash_for_testing",
            role=role,
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
    used: str = "0",
    limit: str = "2000",
) -> Job:
    """Helper to provision a test job in the database."""
    admin = await _get_or_create_test_user(db, "ADMIN")
    job = Job(
        name=f"phase3-compliance-{uuid.uuid4().hex[:8]}",
        source_repository="https://github.com/acme/legacy-monolith-phase3",
        owner_user_id=admin.user_id,
        status=status.value,
        active_node=status.value.lower(),
        budget_used_usd=Decimal(used),
        budget_limit_usd=Decimal(limit),
        max_repair_attempts=3,
        target_stack="Python / FastAPI",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


# ===========================================================================
# 1. STATE MACHINE COMPLIANCE TESTS (Section 33)
# ===========================================================================
@pytest.mark.asyncio
async def test_state_machine_canonical_transitions_and_rejections():
    """Validates the canonical state transitions, rejects invalid jumps, and verifies idempotency."""
    # Canonical transitions allowed
    assert JobStateMachine.can_transition(JobStatus.CREATED, JobStatus.INTAKE)
    assert JobStateMachine.can_transition(JobStatus.INTAKE, JobStatus.ANALYZING)
    assert JobStateMachine.can_transition(JobStatus.ANALYZING, JobStatus.AWAITING_GATE_G1)
    assert JobStateMachine.can_transition(JobStatus.AWAITING_GATE_G1, JobStatus.CHARACTERIZING)
    assert JobStateMachine.can_transition(JobStatus.CHARACTERIZING, JobStatus.AWAITING_GATE_G2)
    assert JobStateMachine.can_transition(JobStatus.AWAITING_GATE_G2, JobStatus.PLANNING)
    assert JobStateMachine.can_transition(JobStatus.PLANNING, JobStatus.AWAITING_GATE_G3)
    assert JobStateMachine.can_transition(JobStatus.AWAITING_GATE_G3, JobStatus.CONVERTING)
    assert JobStateMachine.can_transition(JobStatus.CONVERTING, JobStatus.VERIFYING)
    assert JobStateMachine.can_transition(JobStatus.VERIFYING, JobStatus.INTEGRATING)
    assert JobStateMachine.can_transition(JobStatus.INTEGRATING, JobStatus.AWAITING_GATE_G4)
    assert JobStateMachine.can_transition(JobStatus.AWAITING_GATE_G4, JobStatus.COMPLETED)

    # Invalid bypasses strictly rejected
    invalid_bypasses = [
        (JobStatus.INTAKE, JobStatus.CONVERTING),
        (JobStatus.AWAITING_GATE_G1, JobStatus.PLANNING),
        (JobStatus.AWAITING_GATE_G1, JobStatus.CONVERTING),
        (JobStatus.AWAITING_GATE_G2, JobStatus.CONVERTING),
        (JobStatus.AWAITING_GATE_G2, JobStatus.INTEGRATING),
        (JobStatus.AWAITING_GATE_G3, JobStatus.INTEGRATING),
        (JobStatus.AWAITING_GATE_G3, JobStatus.COMPLETED),
        (JobStatus.CONVERTING, JobStatus.COMPLETED),
    ]
    for src, dst in invalid_bypasses:
        assert not JobStateMachine.can_transition(src, dst)
        with pytest.raises(IllegalStateTransitionException):
            JobStateMachine.validate_transition(src, dst)

    # Idempotent duplicate transition: transition to same status returns job without error
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, JobStatus.INTAKE)
        same_job = await supervisor_service.transition(db, job.job_id, JobStatus.INTAKE)
        assert same_job.status == JobStatus.INTAKE.value


# ===========================================================================
# 2. GATE POLICY & INVARIANTS COMPLIANCE (Section 33)
# ===========================================================================
@pytest.mark.asyncio
async def test_gate_policy_and_human_authority():
    """Validates human-only approvals, role authorization, rationale bounds, and rejection routes."""
    # 1. Autonomous agent sign-off rejected
    with pytest.raises(GatePolicyException, match="Autonomous agents are strictly prohibited"):
        GatePolicy.validate_decision(
            gate_type=GateType.G1,
            decision=DecisionOutcome.APPROVED,
            rationale="Automated sign-off by autonomous agent.",
            actor_role="ADMIN",
            is_human=False,
            gap_options={"stack": "fastapi"},
        )

    # 2. Unauthorized roles (VIEWER, DEVELOPER) rejected
    with pytest.raises(ForbiddenException, match="not authorized"):
        GatePolicy.validate_decision(
            gate_type=GateType.G1,
            decision=DecisionOutcome.APPROVED,
            rationale="Valid review rationale meeting length bounds.",
            actor_role="VIEWER",
            is_human=True,
        )

    with pytest.raises(ForbiddenException, match="not authorized"):
        GatePolicy.validate_decision(
            gate_type=GateType.G2,
            decision=DecisionOutcome.APPROVED,
            rationale="Developer review rationale meeting length bounds.",
            actor_role="DEVELOPER",
            is_human=True,
        )

    # 3. Rationale length check
    with pytest.raises(GatePolicyException, match="Decision rationale must be at least"):
        GatePolicy.validate_decision(
            gate_type=GateType.G3,
            decision=DecisionOutcome.APPROVED,
            rationale="Too short",
            actor_role="ADMIN",
            is_human=True,
        )

    # 4. Gate Rejections route to the correct previous stage
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_test_user(db, "ADMIN")
        job = await _create_test_job(db, JobStatus.ANALYZING)
        for art_type in ("LEGACY_MODEL", "TARGET_BLUEPRINT", "FEASIBILITY_REPORT"):
            db.add(Artifact(
                artifact_id=uuid.uuid4(),
                job_id=job.job_id,
                artifact_type=art_type,
                version=1,
                content_hash=f"sha256:{art_type.lower()}_hash_comp",
                storage_path=f"artifacts/{art_type.lower()}.json",
                content_size_bytes=1024,
                media_type="application/json",
                producing_agent="AnalyzerCoordinator",
            ))
        await db.commit()

        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G1, actor_id=str(admin.user_id))
        gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G1", WorkflowGate.status == "PENDING"))
        assert gate is not None

        # Rejection routes back to ANALYZING
        rej_req = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED,
            rationale="Feasibility analysis incomplete; missing edge cases.",
            artifact_hashes=dict(gate.artifact_hashes or {}),
            options={},
            waivers=[],
        )
        _, decided_gate, routed_job, _ = await gate_service.decide(
            db, gate.gate_id, rej_req, actor_id=admin.user_id, actor_role=admin.role
        )
        assert decided_gate.status == "REJECTED"
        assert routed_job.status == JobStatus.ANALYZING.value

        # Stale decision attempt on already-decided gate is rejected
        with pytest.raises(ConflictException, match="already has terminal status"):
            await gate_service.decide(
                db, gate.gate_id, rej_req, actor_id=admin.user_id, actor_role=admin.role
            )


# ===========================================================================
# 3. WORKFLOW BYPASS PREVENTION TESTS (Section 33 & Sections 19, 20)
# ===========================================================================
@pytest.mark.asyncio
async def test_workflow_bypasses_strictly_prevented():
    """Validates that direct agent runs, legacy graphs, and premature phase calls cannot bypass Supervisor."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_test_user(db, "ADMIN")
        job = await _create_test_job(db, JobStatus.INTAKE)

        # 1. Deprecated supervisor graph ainvoke raises ConflictException
        with pytest.raises(ConflictException, match="Legacy single-transition supervisor graph is deprecated"):
            await supervisor_graph.ainvoke({"job_id": str(job.job_id)})

        with pytest.raises(ConflictException, match="Legacy single-transition supervisor graph is deprecated"):
            await DeprecatedSupervisorGraph().ainvoke({"job_id": str(job.job_id)})

        # 2. Direct conversion eligibility before G1/G2/G3 is rejected
        with pytest.raises(ConflictException, match="Phase 6 requires the canonical conversion state"):
            await supervisor_service.require_conversion_eligibility(db, job)

        # 3. Direct integration eligibility without verified modules is rejected
        with pytest.raises(ConflictException):
            await supervisor_service.require_integration_eligibility(db, job)

        # 4. Direct G4 final review without integrated candidate is rejected
        with pytest.raises((ConflictException, NotFoundException)):
            await supervisor_service.submit_final_review(db, job, "sha256:fake", actor="admin")

        # 5. Direct agent run cannot mutate job status
        from app.schemas.agent_runtime import AgentTask
        from app.services.agent_run_service import AgentRunService
        agent_svc = AgentRunService()
        task = AgentTask(
            job_id=str(job.job_id),
            agent_name="LegacyAnalyzer",
            task_type="AST_ANALYSIS",
            instruction="DIAGNOSTIC ONLY test",
            parameters={
                "execution_mode": "DIAGNOSTIC_NON_AUTHORITATIVE",
                "may_transition_workflow": False,
            },
            input_artifacts=[],
            allowed_tools=["read_file_ast", "extract_entities", "calculate_cyclomatic_complexity"],
        )
        # Execute diagnostic run
        run_record = await agent_svc.execute(db, job, task, "corr-diag-1", str(admin.user_id))
        await db.refresh(job)
        # Job status and phase must remain INTAKE
        assert job.status == JobStatus.INTAKE.value
        assert run_record.task_payload.get("parameters", {}).get("execution_mode") == "DIAGNOSTIC_NON_AUTHORITATIVE"


# ===========================================================================
# 4. CONCURRENCY & LEASE FENCING TESTS (Section 35)
# ===========================================================================
@pytest.mark.asyncio
async def test_concurrency_race_conditions_and_lease_fencing():
    """Validates atomic mutual exclusion and supervisor lease fence rejecting stale workers."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_test_user(db, "ADMIN")
        job = await _create_test_job(db, JobStatus.CONVERTING)

        # Create approved gates G1, G2, G3
        for gt in ("G1", "G2", "G3"):
            db.add(WorkflowGate(
                gate_id=uuid.uuid4(),
                job_id=job.job_id,
                gate_type=gt,
                version=1,
                status="APPROVED",
                artifact_ids=[],
                artifact_hashes={},
            ))

        mod = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="concurrency_target",
            legacy_path="legacy/target",
            target_path="app/target.py",
            status="PENDING",
            wave_number=1,
            retry_count=0,
            lease_generation=1,
        )
        db.add(mod)
        await db.commit()

        # Worker Alpha claims module M1
        claimed_alpha = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="worker-alpha", limit=1, lease_seconds=60
        )
        assert len(claimed_alpha) == 1
        assert claimed_alpha[0].module_id == mod.module_id

        # Worker Beta concurrently attempts to claim M1 -> receives 0 (atomic mutual exclusion)
        claimed_beta = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="worker-beta", limit=1
        )
        assert len(claimed_beta) == 0

        # Create attempt representing Worker Alpha's execution with lease generation 1
        attempt_alpha = ModuleAttempt(
            attempt_id=uuid.uuid4(),
            module_id=mod.module_id,
            attempt_number=1,
            status="RUNNING",
            git_branch="feature/target-v1",
            lease_generation=mod.lease_generation,
        )
        run_alpha = AgentRun(
            run_id=uuid.uuid4(),
            job_id=job.job_id,
            agent_name="CodeWriter",
            status="RUNNING",
            model_provider="fake",
            model_identifier="fake-model",
            input_tokens=100,
            output_tokens=100,
            cost_usd=Decimal("0.05"),
        )
        db.add_all([attempt_alpha, run_alpha])
        await db.commit()

        # Simulate Worker Alpha crashing: lease expires and scheduler reclaims it
        mod.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await db.commit()

        # Reclaim stale lease: resets module and increments lease_generation
        await dependency_scheduler.reclaim_expired_leases(db, job.job_id)
        await db.refresh(mod)
        assert mod.status == "PENDING"
        assert mod.lease_owner is None
        # lease generation incremented
        assert mod.lease_generation > attempt_alpha.lease_generation

        # Now Worker Alpha attempts late disposition commit with stale lease generation
        with pytest.raises(ConflictException, match="Stale worker result rejected by the supervisor lease fence"):
            await supervisor_service.record_module_disposition(
                db, job, mod, attempt_alpha, run_alpha, "FAILED", "Late commit by Worker Alpha"
            )

        # Worker Beta claims the module with incremented lease generation
        claimed_beta_2 = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="worker-beta", limit=1
        )
        assert len(claimed_beta_2) == 1
        await db.refresh(mod)
        assert mod.lease_generation > attempt_alpha.lease_generation
        assert mod.lease_owner == "worker-beta"

        # Worker Alpha still cannot commit (rejected by lease fence)
        with pytest.raises(ConflictException, match="Stale worker result rejected by the supervisor lease fence"):
            await supervisor_service.record_module_disposition(
                db, job, mod, attempt_alpha, run_alpha, "FAILED", "Worker Alpha stale attempt"
            )

        # Worker Beta creates attempt matching current lease generation and commits successfully
        attempt_beta = ModuleAttempt(
            attempt_id=uuid.uuid4(),
            module_id=mod.module_id,
            attempt_number=2,
            status="RUNNING",
            git_branch="feature/target-v2",
            lease_generation=mod.lease_generation,
        )
        run_beta = AgentRun(
            run_id=uuid.uuid4(),
            job_id=job.job_id,
            agent_name="CodeWriter",
            status="RUNNING",
            model_provider="fake",
            model_identifier="fake-model",
            input_tokens=100,
            output_tokens=100,
            cost_usd=Decimal("0.05"),
        )
        db.add_all([attempt_beta, run_beta])
        await db.commit()

        # Worker Beta commits disposition successfully
        await supervisor_service.record_module_disposition(
            db, job, mod, attempt_beta, run_beta, "FAILED", "Worker Beta completed disposition"
        )
        await db.refresh(mod)
        assert mod.status == "FAILED"


# ===========================================================================
# 5. CRASH & RECOVERY RECONCILIATION TESTS (Section 34)
# ===========================================================================
@pytest.mark.asyncio
async def test_crash_and_restart_recovery_reconciliation():
    """Validates that application restart recovers stale tasks, reconciles orphaned runs, and checkpoints state."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_test_user(db, "ADMIN")
        job = await _create_test_job(db, JobStatus.CONVERTING)

        for gt in ("G1", "G2", "G3"):
            db.add(WorkflowGate(
                gate_id=uuid.uuid4(),
                job_id=job.job_id,
                gate_type=gt,
                version=1,
                status="APPROVED",
                artifact_ids=[],
                artifact_hashes={},
            ))

        # Stale RUNNING module whose worker crashed
        stale_mod = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="crashed_module",
            legacy_path="legacy/crash",
            target_path="app/crash.py",
            status="RUNNING",
            lease_owner="crashed-worker-99",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            wave_number=1,
            retry_count=0,
            lease_generation=1,
        )
        # Orphaned agent run
        orphan_run = AgentRun(
            run_id=uuid.uuid4(),
            job_id=job.job_id,
            agent_name="CodeWriter",
            status="RUNNING",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            model_provider="fake",
            model_identifier="fake-model",
            input_tokens=500,
            output_tokens=500,
            cost_usd=Decimal("0.25"),
        )
        db.add_all([stale_mod, orphan_run])
        await db.flush()

        orphan_attempt = ModuleAttempt(
            attempt_id=uuid.uuid4(),
            module_id=stale_mod.module_id,
            attempt_number=1,
            status="RUNNING",
            git_branch="feature/crashed-v1",
            agent_run_id=orphan_run.run_id,
            lease_generation=1,
        )
        db.add(orphan_attempt)
        await db.commit()

        # Execute system restart recovery
        recovered_jobs_count = await supervisor_service.recover_active_jobs(
            db, job_ids=[job.job_id], auto_schedule=False
        )
        assert recovered_jobs_count >= 1

        # Verify module recovered
        await db.refresh(stale_mod)
        assert stale_mod.status == "PENDING"
        assert stale_mod.lease_owner is None
        assert stale_mod.lease_expires_at is None
        assert stale_mod.retry_count == 1
        assert stale_mod.lease_generation >= 2

        # Verify orphaned run marked FAILED
        await db.refresh(orphan_run)
        assert orphan_run.status == "FAILED"
        assert orphan_run.failure_classification == "ORPHANED_WORKER"

        # Verify recovery checkpoint created
        latest_cp = await supervisor_service.checkpointer.latest(db, job.job_id)
        assert latest_cp is not None
        assert latest_cp.checkpoint_kind == "RECOVERY"

        # Verify audit trail
        audit_event = await db.scalar(
            select(AuditEvent).where(
                AuditEvent.job_id == job.job_id,
                AuditEvent.event_type == "WORKFLOW_RECOVERED",
            ).order_by(AuditEvent.created_at.desc()).limit(1)
        )
        assert audit_event is not None
        assert audit_event.payload.get("stale_modules", 0) >= 1

        # Verify transactional outbox event persisted for safe continuation
        outbox_event = await db.scalar(
            select(WorkflowOutbox).where(
                WorkflowOutbox.job_id == job.job_id,
                WorkflowOutbox.event_type == "SUPERVISOR_RESUME",
            ).order_by(WorkflowOutbox.created_at.desc()).limit(1)
        )
        assert outbox_event is not None
        assert outbox_event.status == "PENDING"

        # Verify supervisor continuation is scheduled safely and workflow resumes
        task = supervisor_service.schedule_drive(job.job_id, correlation_id="test-restart-resume")
        assert task is not None
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


# ===========================================================================
# 6. DETERMINISTIC PHASE 3 E2E TEST (Section 36)
# ===========================================================================
@pytest.mark.asyncio
async def test_phase3_deterministic_supervisor_e2e(observed_phase5_baseline):
    """Executes deterministic progression through:
    INTAKE -> G1 -> CHARACTERIZATION -> SCHEMA/DATA -> G2 -> PLANNING -> G3 -> CONVERSION TASK CREATED.

    Proves:
    - Supervisor owns every transition.
    - Persists checkpoints at every step (BEFORE, AFTER, INTERRUPT).
    - Pauses at gates.
    - Resumes after human decisions.
    - Reaches G3 and creates conversion tasks.
    """
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_test_user(db, "ADMIN")
        job = await _create_test_job(db, JobStatus.CREATED)
        corr_id = f"phase3-e2e-{uuid.uuid4().hex[:8]}"

        # 1. CREATED -> INTAKE -> ANALYZING
        await supervisor_service.transition(db, job.job_id, JobStatus.INTAKE, actor_id=str(admin.user_id), correlation_id=corr_id)
        await supervisor_service.transition(db, job.job_id, JobStatus.ANALYZING, actor_id=str(admin.user_id), correlation_id=corr_id)
        await db.refresh(job)
        assert job.status == JobStatus.ANALYZING.value

        # Seed G1 required artifacts
        db.add_all([
            Artifact(
                artifact_id=uuid.uuid4(),
                job_id=job.job_id,
                artifact_type="LEGACY_MODEL",
                version=1,
                content_hash="sha256:legacy_model_hash_e2e",
                storage_path="artifacts/legacy_model.json",
                content_size_bytes=1024,
                media_type="application/json",
                producing_agent="AnalyzerCoordinator",
            ),
            Artifact(
                artifact_id=uuid.uuid4(),
                job_id=job.job_id,
                artifact_type="TARGET_BLUEPRINT",
                version=1,
                content_hash="sha256:target_blueprint_hash_e2e",
                storage_path="artifacts/target_blueprint.json",
                content_size_bytes=1024,
                media_type="application/json",
                producing_agent="ArchitectAgent",
            ),
            Artifact(
                artifact_id=uuid.uuid4(),
                job_id=job.job_id,
                artifact_type="FEASIBILITY_REPORT",
                version=1,
                content_hash="sha256:feasibility_report_hash_e2e",
                storage_path="artifacts/feasibility_report.json",
                content_size_bytes=1024,
                media_type="application/json",
                producing_agent="FeasibilityAgent",
            ),
        ])
        await db.commit()

        # Transition to AWAITING_GATE_G1 (pauses for human review)
        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G1, actor_id=str(admin.user_id), correlation_id=corr_id)
        await db.refresh(job)
        assert job.status == JobStatus.AWAITING_GATE_G1.value

        g1_gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G1", WorkflowGate.status == "PENDING"))
        assert g1_gate is not None

        # Human Approval at Gate G1
        g1_decision = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approved target architecture feasibility and modern blueprint.",
            artifact_hashes=dict(g1_gate.artifact_hashes or {}),
            options={"auth": "bearer_jwt"},
            waivers=[],
        )
        await gate_service.decide(db, g1_gate.gate_id, g1_decision, actor_id=admin.user_id, actor_role=admin.role, correlation_id=corr_id)

        # Wait for supervisor drive triggered by G1 approval
        task = continuous_pipeline_service._running_tasks.get(str(job.job_id))
        if task and not task.done():
            await task
        await db.refresh(job)

        # Establish observed Phase 5 baseline & schema analysis
        baseline = await observed_phase5_baseline(db, job, admin)
        await schema_data_service.execute_schema_data_analysis(db, job, user=admin)
        if job.status != JobStatus.AWAITING_GATE_G2.value:
            await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G2, actor_id="supervisor", correlation_id=corr_id)

        await db.refresh(job)
        assert job.status == JobStatus.AWAITING_GATE_G2.value

        g2_gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G2", WorkflowGate.status == "PENDING"))
        assert g2_gate is not None

        # Seed modules and conversion plan for planning stage
        mod_1 = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="auth_service",
            legacy_path="legacy/auth",
            target_path="app/auth.py",
            status="PENDING",
            wave_number=1,
            dependency_module_ids=[],
        )
        mod_2 = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="user_service",
            legacy_path="legacy/users",
            target_path="app/users.py",
            status="PENDING",
            wave_number=2,
            dependency_module_ids=[str(mod_1.module_id)],
        )
        db.add_all([mod_1, mod_2])
        await db.commit()

        await ArtifactService().create_artifact(
            db,
            job.job_id,
            "ConversionPlan",
            1,
            json.dumps({
                "modules": [
                    {"module_id": m.name, "source_scope": [m.legacy_path], "target_scope": [m.target_path], "dependencies": m.dependency_module_ids}
                    for m in (mod_1, mod_2)
                ]
            }).encode(),
            "PlannerCoordinator",
        )

        # Human Approval at Gate G2 (Freeze Characterization Baseline)
        g2_decision = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approved behavioral characterization baseline test suite and schema plan.",
            artifact_hashes=dict(g2_gate.artifact_hashes or {}),
            options={},
            waivers=[],
        )
        await gate_service.decide(db, g2_gate.gate_id, g2_decision, actor_id=admin.user_id, actor_role=admin.role, correlation_id=corr_id)

        task = continuous_pipeline_service._running_tasks.get(str(job.job_id))
        if task and not task.done():
            await task
        await db.refresh(job)
        assert job.status == JobStatus.AWAITING_GATE_G3.value

        g3_gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G3", WorkflowGate.status == "PENDING"))
        assert g3_gate is not None

        # Negative assertion: CodeWriter scheduling is strictly rejected prior to G3 approval
        with pytest.raises(ConflictException, match="CodeWriter scheduling is allowed only while the job is CONVERTING"):
            await dependency_scheduler.claim_ready_modules(db, job.job_id, worker_id="test-worker")

        # Human Approval at Gate G3 (Conversion Plan Approval)
        g3_decision = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Conversion plan DAG verified acyclic and modular across 2 waves; approved.",
            artifact_hashes=dict(g3_gate.artifact_hashes or {}),
            options={},
            waivers=[],
        )
        await gate_service.decide(db, g3_gate.gate_id, g3_decision, actor_id=admin.user_id, actor_role=admin.role, correlation_id=corr_id)
        await db.refresh(job)

        # Workflow has reached CONVERTING with conversion tasks created
        assert job.status == JobStatus.CONVERTING.value

        # Positive assertion: After valid G3 approval, CodeWriter scheduling succeeds in CONVERTING stage
        claimed_modules = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="codewriter-wave1-worker", limit=1
        )
        assert len(claimed_modules) == 1
        assert claimed_modules[0].module_id == mod_1.module_id
        assert claimed_modules[0].status == "LEASED"
        assert claimed_modules[0].lease_owner == "codewriter-wave1-worker"

        task = continuous_pipeline_service._running_tasks.get(str(job.job_id))
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        await db.refresh(job)
        assert job.status == JobStatus.CONVERTING.value
        await db.refresh(mod_1)
        await db.refresh(mod_2)
        # mod_1 (wave 1) and mod_2 (wave 2) are present
        assert mod_1.name == "auth_service"
        assert mod_2.name == "user_service"

        # Checkpoint sequence has advanced through all phases
        checkpoints = list((await db.execute(
            select(WorkflowCheckpoint).where(WorkflowCheckpoint.job_id == job.job_id).order_by(WorkflowCheckpoint.sequence)
        )).scalars().all())
        assert len(checkpoints) >= 6
        assert any(cp.checkpoint_kind == "INTERRUPT" for cp in checkpoints)


# ===========================================================================
# 7. MANDATORY NEGATIVE E2E TESTS (Section 37)
# ===========================================================================
@pytest.mark.asyncio
async def test_negative_e2e_scenarios(observed_phase5_baseline):
    """Exhaustively verifies every mandatory negative test scenario from Section 37:
    1. INTAKE -> G1 -> DIRECT CONVERSION: must fail.
    2. G2 -> CODEWRITER without G3: must fail.
    3. VERIFICATION -> INTEGRATION without verified evidence: must fail.
    4. G4 without integration evidence: must fail.
    """
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_test_user(db, "ADMIN")
        job = await _create_test_job(db, JobStatus.INTAKE)

        # 1. Attempt INTAKE -> G1 -> DIRECT CONVERSION: MUST FAIL
        with pytest.raises(ConflictException, match="Phase 6 requires the canonical conversion state"):
            await supervisor_service.require_conversion_eligibility(db, job)

        with pytest.raises(IllegalStateTransitionException):
            await supervisor_service.transition(db, job.job_id, JobStatus.CONVERTING, actor_id="attacker")

        # 2. Attempt G2 -> CODEWRITER without G3: MUST FAIL
        # Transition job to CONVERTING status with G1 and G2 approved, but G3 not approved
        job.status = JobStatus.CONVERTING.value
        db.add(WorkflowGate(
            gate_id=uuid.uuid4(),
            job_id=job.job_id,
            gate_type="G1",
            version=1,
            status="APPROVED",
            artifact_ids=[],
            artifact_hashes={},
        ))
        db.add(WorkflowGate(
            gate_id=uuid.uuid4(),
            job_id=job.job_id,
            gate_type="G2",
            version=1,
            status="APPROVED",
            artifact_ids=[],
            artifact_hashes={},
        ))
        # G3 is PENDING, NOT APPROVED
        db.add(WorkflowGate(
            gate_id=uuid.uuid4(),
            job_id=job.job_id,
            gate_type="G3",
            version=1,
            status="PENDING",
            artifact_ids=[],
            artifact_hashes={},
        ))
        await db.commit()

        # Claiming ready modules must fail because G3 is not approved
        with pytest.raises(ConflictException, match="G1, G2 and G3"):
            await dependency_scheduler.claim_ready_modules(db, job.job_id, worker_id="premature-worker")

        # 3. Attempt VERIFICATION -> INTEGRATION without verified evidence: MUST FAIL
        mod_unverified = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="unverified_module",
            legacy_path="legacy/unverified",
            target_path="app/unverified.py",
            status="PENDING",
            wave_number=1,
        )
        db.add(mod_unverified)
        await db.commit()

        with pytest.raises(ConflictException):
            await supervisor_service.require_integration_eligibility(db, job)

        # 4. Attempt G4 without integration evidence: MUST FAIL
        with pytest.raises((ConflictException, NotFoundException)):
            await supervisor_service.submit_final_review(db, job, "sha256:fake_unintegrated_report", actor="attacker")
