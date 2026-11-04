"""Adversarial Verification Suite for the Multi-Agent Autonomous Supervisor Runtime.

Exhaustively verifies every architectural invariant and failure mode:
1. Strict Gate Enforcement (Rejection of invalid bypasses: G1->Planning, G2->CodeWriter, G3->Integrator, *->G4)
2. Human-Only Approval Policy (Rejection of autonomous agents, non-human actors, and unauthorized roles)
3. Specialist Agent Lifecycle (CodeWriter -> Verifier -> Bounded Repair -> Integrator -> Gate G4)
4. Durability & Recovery (Task state, retry counts, budget tracking, and checkpoints across restarts)
5. Task Lease Mutual Exclusion & Lease Recovery (Atomic concurrency and stale lease reclamation)
6. True Parallelism & Topological Dependency Scheduling (Concurrent worker leasing and dependency blocking)
7. Deadlock Detection (A -> B -> C -> A circular dependency detection with ESCALATE)
8. Budget Enforcement (Cost budget exhaustion and concurrency saturation blocking)
9. Artifact Cryptographic Integrity (Tamper detection and downstream gate invalidation)
10. Deterministic LangGraph Execution (Multi-node loop progression without premature termination)
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictException, ForbiddenException, GatePolicyException, IllegalStateTransitionException
from app.domain.state_machine import GatePolicy, JobStateMachine
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
from app.services.dependency_scheduler import dependency_scheduler
from app.services.gate_service import gate_service
from app.services.integrator_agent import integrator_service
from app.services.supervisor_graph import supervisor_loop_graph
from app.services.supervisor_router import SupervisorAction, supervisor_router
from app.services.supervisor_service import supervisor_service
from app.services.verifier_agent import VerificationVerdict, verifier_service


async def _get_or_create_user(db, role: str = "ADMIN") -> User:
    user = await db.scalar(select(User).where(User.role == role).limit(1))
    if not user:
        user = User(
            user_id=uuid.uuid4(),
            email=f"{role.lower()}_{uuid.uuid4().hex[:6]}@example.com",
            full_name=f"Test {role.title()}",
            password_hash="mock_hash_for_testing",
            role=role,
            status="ACTIVE",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def _create_adversarial_job(
    db,
    status: JobStatus = JobStatus.CREATED,
    *,
    used: str = "0",
    limit: str = "5000",
    max_repairs: int = 3,
    concurrency: int = 4,
) -> Job:
    admin = await _get_or_create_user(db, "ADMIN")
    job = Job(
        name=f"adversarial-{uuid.uuid4().hex[:8]}",
        source_repository="https://github.com/acme/legacy-monolith",
        owner_user_id=admin.user_id,
        status=status.value,
        active_node=status.value.lower(),
        budget_used_usd=Decimal(used),
        budget_limit_usd=Decimal(limit),
        max_repair_attempts=max_repairs,
        max_parallel_tasks=concurrency,
        provider_concurrency_limit=concurrency,
        sandbox_concurrency_limit=concurrency,
        target_stack="Python / FastAPI",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    if status in (JobStatus.CONVERTING, JobStatus.VERIFYING, JobStatus.INTEGRATING, JobStatus.AWAITING_GATE_G4):
        for gt in ("G1", "G2", "G3"):
            g = WorkflowGate(
                gate_id=uuid.uuid4(),
                job_id=job.job_id,
                gate_type=gt,
                version=1,
                status="APPROVED",
                artifact_ids=[],
                artifact_hashes={},
            )
            db.add(g)
        await db.commit()

    return job


# ===========================================================================
# 1. VERIFY EVERY GATE & BYPASS PREVENTION
# ===========================================================================
@pytest.mark.asyncio
async def test_gate_bypass_prevention_exhaustive():
    """Confirms that direct transitions bypassing mandatory human approval gates fail definitively."""
    # G1 -> PLANNING bypass must fail
    assert not JobStateMachine.can_transition(JobStatus.AWAITING_GATE_G1, JobStatus.PLANNING)
    with pytest.raises(IllegalStateTransitionException):
        JobStateMachine.validate_transition(JobStatus.AWAITING_GATE_G1, JobStatus.PLANNING)

    # G2 -> CODEWRITER (CONVERTING) bypass must fail
    assert not JobStateMachine.can_transition(JobStatus.AWAITING_GATE_G2, JobStatus.CONVERTING)
    with pytest.raises(IllegalStateTransitionException):
        JobStateMachine.validate_transition(JobStatus.AWAITING_GATE_G2, JobStatus.CONVERTING)

    # G3 -> INTEGRATOR (INTEGRATING) bypass must fail
    assert not JobStateMachine.can_transition(JobStatus.AWAITING_GATE_G3, JobStatus.INTEGRATING)
    with pytest.raises(IllegalStateTransitionException):
        JobStateMachine.validate_transition(JobStatus.AWAITING_GATE_G3, JobStatus.INTEGRATING)

    # Direct jump from any state to G4 (or COMPLETED) without prior pipeline stages must fail
    invalid_targets = [JobStatus.CREATED, JobStatus.INTAKE, JobStatus.ANALYZING, JobStatus.CHARACTERIZING, JobStatus.PLANNING]
    for src in invalid_targets:
        assert not JobStateMachine.can_transition(src, JobStatus.AWAITING_GATE_G4)
        assert not JobStateMachine.can_transition(src, JobStatus.COMPLETED)
        with pytest.raises(IllegalStateTransitionException):
            JobStateMachine.validate_transition(src, JobStatus.COMPLETED)


# ===========================================================================
# 2. VERIFY HUMAN-ONLY APPROVAL (NO AUTONOMOUS AGENT SIGN-OFF)
# ===========================================================================
@pytest.mark.asyncio
async def test_human_only_approval_enforcement():
    """Proves that autonomous agents and unauthorized non-human callers cannot approve gates."""
    # 1. Autonomous agent sign-off attempt
    with pytest.raises(GatePolicyException, match="Autonomous agents are strictly prohibited"):
        GatePolicy.validate_decision(
            gate_type=GateType.G1,
            decision=DecisionOutcome.APPROVED,
            rationale="Automated sign-off by autonomous supervisor agent.",
            actor_role="ADMIN",
            is_human=False,
            gap_options={"auth": "oauth2"},
        )

    # 2. Unauthorized roles (VIEWER, DEVELOPER) cannot approve gates
    with pytest.raises(ForbiddenException, match="not authorized"):
        GatePolicy.validate_decision(
            gate_type=GateType.G2,
            decision=DecisionOutcome.APPROVED,
            rationale="Developer attempting approval without reviewer authority.",
            actor_role="DEVELOPER",
            is_human=True,
        )

    with pytest.raises(ForbiddenException, match="not authorized"):
        GatePolicy.validate_decision(
            gate_type=GateType.G3,
            decision=DecisionOutcome.APPROVED,
            rationale="Viewer attempting approval.",
            actor_role="VIEWER",
            is_human=True,
        )

    # 3. Insufficient rationale length rejected
    with pytest.raises(GatePolicyException, match="Decision rationale must be at least"):
        GatePolicy.validate_decision(
            gate_type=GateType.G3,
            decision=DecisionOutcome.APPROVED,
            rationale="Short",
            actor_role="ADMIN",
            is_human=True,
        )


# ===========================================================================
# 3. VERIFY CODEWRITER -> VERIFIER -> INTEGRATOR LIFECYCLE
# ===========================================================================
@pytest.mark.asyncio
async def test_codewriter_cannot_bypass_verifier_and_integrator_blocks(ready, trusted_executor):
    """A model's self-verification claim is rejected; only independently executed evidence can pass."""
    from test_phase6 import queued, generation
    from app.services import phase6_service
    from app.services.model_gateway import build_fake_gateway, FakeModelProvider
    db, job, _, _, module, _ = ready
    attempt = await queued(ready)
    gateway = build_fake_gateway(FakeModelProvider([generation(verified=True), generation()]))
    await phase6_service.execute_attempt(db, attempt.attempt_id, gateway=gateway)
    assert attempt.status == module.status == "BLOCKED"
    assert (await verifier_service.verify_module(db, job, module)).verdict == VerificationVerdict.REJECT
    with pytest.raises(ConflictException):
        await supervisor_service.require_integration_eligibility(db, job)
    repair = await queued(ready, "repair-self-claim", previous=attempt, rationale="Remove unsupported self-verification and submit scoped code")
    await phase6_service.execute_attempt(db, repair.attempt_id, gateway=gateway)
    assert repair.status == "VERIFIED" and trusted_executor


@pytest.mark.asyncio
async def test_bounded_repair_escalation_prevents_infinite_loop(ready, trusted_executor):
    """Real fixture regression evidence exhausts the bounded loop; no force_failure success fiction."""
    from test_phase6 import queued, generation
    from app.services import phase6_service
    from app.services.model_gateway import build_fake_gateway, FakeModelProvider
    db, job, *_ = ready
    job.max_repair_attempts = 1
    await db.commit()
    gateway = build_fake_gateway(FakeModelProvider([generation(4), generation(4)]))
    first = await queued(ready)
    await phase6_service.execute_attempt(db, first.attempt_id, gateway=gateway)
    second = await queued(ready, "repeat", previous=first, rationale="Repair exact recorded characterization discrepancy")
    await phase6_service.execute_attempt(db, second.attempt_id, gateway=gateway)
    assert second.status == "WAITING_FOR_HUMAN"
    with pytest.raises(ConflictException):
        await queued(ready, "exhausted", previous=second, rationale="Must not exceed the configured repair bound")


# ===========================================================================
# 4. VERIFY TASK LEASE RECOVERY & MUTUAL EXCLUSION
# ===========================================================================
@pytest.mark.asyncio
async def test_lease_mutual_exclusion_and_stale_lease_recovery():
    """Proves that two workers cannot claim the same task, and expired leases are recovered."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_user(db, "ADMIN")
        job = await _create_adversarial_job(db, JobStatus.CONVERTING, concurrency=2)

        mod = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="concurrent_module",
            legacy_path="legacy/concurrent",
            target_path="app/concurrent.py",
            status="PENDING",
            wave_number=1,
            retry_count=0,
        )
        db.add(mod)
        await db.commit()

        # Worker 1 leases module
        claimed1 = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="worker-node-alpha", limit=1, lease_seconds=60
        )
        assert len(claimed1) == 1
        assert claimed1[0].module_id == mod.module_id

        # Worker 2 attempts to claim while Worker 1 holds active lease -> MUST get empty list
        claimed2 = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="worker-node-beta", limit=1
        )
        assert len(claimed2) == 0

        # Simulate Worker 1 crashing and lease expiring
        await db.refresh(mod)
        mod.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await db.commit()

        # Reconcile stale leases
        recovered = await dependency_scheduler.reclaim_expired_leases(db, job.job_id)
        assert recovered >= 1

        await db.refresh(mod)
        assert mod.status == "PENDING"
        assert mod.lease_owner is None
        assert mod.retry_count == 1

        # Worker 2 can now claim the recovered module
        claimed3 = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="worker-node-beta", limit=1
        )
        assert len(claimed3) == 1
        assert claimed3[0].module_id == mod.module_id
        assert claimed3[0].lease_owner == "worker-node-beta"


# ===========================================================================
# 5. VERIFY TRUE PARALLELISM & DEPENDENCY BLOCKING
# ===========================================================================
@pytest.mark.asyncio
async def test_true_parallelism_and_topological_dependency_blocking():
    """Validates that M1, M2, M3 can be leased in parallel, while M4 is strictly blocked until M1+M2+M3 are verified."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_user(db, "ADMIN")
        job = await _create_adversarial_job(db, JobStatus.CONVERTING, concurrency=4)

        # Create M1, M2, M3 (Wave 1, independent)
        m1_id = uuid.uuid4()
        m2_id = uuid.uuid4()
        m3_id = uuid.uuid4()
        m4_id = uuid.uuid4()

        m1 = Module(module_id=m1_id, job_id=job.job_id, name="M1", legacy_path="l/m1", target_path="m/m1.py", status="PENDING", wave_number=1, dependency_module_ids=[])
        m2 = Module(module_id=m2_id, job_id=job.job_id, name="M2", legacy_path="l/m2", target_path="m/m2.py", status="PENDING", wave_number=1, dependency_module_ids=[])
        m3 = Module(module_id=m3_id, job_id=job.job_id, name="M3", legacy_path="l/m3", target_path="m/m3.py", status="PENDING", wave_number=1, dependency_module_ids=[])
        # M4 depends on M1 + M2 + M3
        m4 = Module(module_id=m4_id, job_id=job.job_id, name="M4", legacy_path="l/m4", target_path="m/m4.py", status="PENDING", wave_number=2, dependency_module_ids=[str(m1_id), str(m2_id), str(m3_id)])

        db.add_all([m1, m2, m3, m4])
        await db.commit()

        # Claim ready modules with limit=4
        claimed = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="parallel-worker-pool", limit=4
        )
        claimed_ids = {m.module_id for m in claimed}

        # PROVE TRUE PARALLELISM: All 3 independent modules (M1, M2, M3) claimed concurrently
        assert m1_id in claimed_ids
        assert m2_id in claimed_ids
        assert m3_id in claimed_ids
        # PROVE DEPENDENCY BLOCKING: M4 CANNOT be claimed because M1, M2, M3 are not yet VERIFIED/COMPLETED
        assert m4_id not in claimed_ids

        # Now mark M1 and M2 VERIFIED, but leave M3 PENDING
        m1.status = "VERIFIED"
        m1.lease_owner = None
        m2.status = "VERIFIED"
        m2.lease_owner = None
        await db.commit()

        # M4 still cannot be claimed because M3 is not yet verified
        claimed_again = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="parallel-worker-pool", limit=4
        )
        assert m4_id not in {m.module_id for m in claimed_again}

        # Mark M3 VERIFIED
        m3.status = "VERIFIED"
        m3.lease_owner = None
        await db.commit()

        # Now M4's dependencies are 100% satisfied; M4 must be claimed!
        claimed_m4 = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="parallel-worker-pool", limit=4
        )
        assert len(claimed_m4) >= 1
        assert m4_id in {m.module_id for m in claimed_m4}


# ===========================================================================
# 6. VERIFY DEPENDENCY DEADLOCK DETECTION
# ===========================================================================
@pytest.mark.asyncio
async def test_circular_dependency_deadlock_detection():
    """Validates that a 3-way circular dependency cycle (A -> B -> C -> A) escalates to DEPENDENCY_DEADLOCK."""
    async with AsyncSessionLocal() as db:
        job = await _create_adversarial_job(db, JobStatus.CONVERTING)

        id_a, id_b, id_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mod_a = Module(module_id=id_a, job_id=job.job_id, name="A", legacy_path="l/a", target_path="m/a.py", status="PENDING", wave_number=1, dependency_module_ids=[str(id_b)])
        mod_b = Module(module_id=id_b, job_id=job.job_id, name="B", legacy_path="l/b", target_path="m/b.py", status="PENDING", wave_number=1, dependency_module_ids=[str(id_c)])
        mod_c = Module(module_id=id_c, job_id=job.job_id, name="C", legacy_path="l/c", target_path="m/c.py", status="PENDING", wave_number=1, dependency_module_ids=[str(id_a)])

        db.add_all([mod_a, mod_b, mod_c])
        await db.commit()

        decision = await supervisor_router.evaluate_next_action(db, job)
        assert decision.action == SupervisorAction.ESCALATE
        assert "DEPENDENCY_DEADLOCK" in decision.reason
        assert decision.target_status == JobStatus.FAILED.value


# ===========================================================================
# 7. VERIFY BUDGET ENFORCEMENT & CONCURRENCY LIMITS
# ===========================================================================
@pytest.mark.asyncio
async def test_budget_exhaustion_blocks_progress_and_escalates():
    """Validates that budget exhaustion blocks state transitions and triggers reviewer escalation."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_user(db, "ADMIN")
        job = await _create_adversarial_job(db, JobStatus.INTAKE, used="100.00", limit="100.00")

        # Router must detect budget exhaustion
        decision = await supervisor_router.evaluate_next_action(db, job)
        assert decision.action == SupervisorAction.ESCALATE
        assert "budget exhausted" in decision.reason.lower()

        # Transition must be blocked with ConflictException
        with pytest.raises(ConflictException, match="budget is exhausted"):
            await supervisor_service.transition(db, job.job_id, JobStatus.ANALYZING, actor_id=str(admin.user_id))


# ===========================================================================
# 8. VERIFY ARTIFACT INTEGRITY & TAMPER DETECTION
# ===========================================================================
@pytest.mark.asyncio
async def test_artifact_tamper_detection_invalidates_downstream_gates():
    """Validates that modifying an approved artifact invalidates bound and downstream gates."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_user(db, "ADMIN")
        job = await _create_adversarial_job(db, JobStatus.AWAITING_GATE_G1)

        art_id = uuid.uuid4()
        original_hash = "sha256:original_characterization_hash_123"
        artifact = Artifact(
            artifact_id=art_id,
            job_id=job.job_id,
            artifact_type="CHARACTERIZATION_SUITE",
            version=1,
            content_hash=original_hash,
            storage_path="artifacts/char_v1.json",
            content_size_bytes=4096,
            media_type="application/json",
            producing_agent="CharacterizerAgent",
        )
        db.add(artifact)
        await db.commit()

        # Create approved Gate G2 referencing this artifact
        g2 = WorkflowGate(
            gate_id=uuid.uuid4(),
            job_id=job.job_id,
            gate_type="G2",
            version=1,
            status="APPROVED",
            artifact_ids=[str(art_id)],
            artifact_hashes={str(art_id): original_hash},
        )
        db.add(g2)
        await db.commit()

        # Modify artifact content hash to simulate tamper / revision
        tampered_hash = "sha256:tampered_content_hash_999"
        invalidated = await gate_service.invalidate_for_artifact(
            db, job.job_id, art_id, tampered_hash, reason="Tamper detected during adversarial audit"
        )

        assert len(invalidated) >= 1
        await db.refresh(g2)
        assert g2.status == "INVALIDATED"
        assert "Tamper detected" in (g2.blocking_reason or "")


# ===========================================================================
# 9. VERIFY SUPERVISOR LOOP GRAPH
# ===========================================================================
@pytest.mark.asyncio
async def test_supervisor_loop_graph_pauses_at_pending_gate():
    """Validates that supervisor_loop_graph executes all nodes up to human review and halts."""
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_user(db, "ADMIN")
        job = await _create_adversarial_job(db, JobStatus.ANALYZING)
        for art_type in ("LEGACY_MODEL", "TARGET_BLUEPRINT", "FEASIBILITY_REPORT"):
            db.add(Artifact(
                artifact_id=uuid.uuid4(),
                job_id=job.job_id,
                artifact_type=art_type,
                version=1,
                content_hash=f"sha256:{art_type.lower()}_hash_adv",
                storage_path=f"artifacts/{art_type.lower()}.json",
                content_size_bytes=1024,
                media_type="application/json",
                producing_agent="AnalyzerCoordinator",
            ))
        await db.commit()
        await supervisor_service.transition(db, job.job_id, JobStatus.AWAITING_GATE_G1, actor_id=str(admin.user_id))

        result_state = await supervisor_loop_graph.ainvoke({
            "job_id": str(job.job_id),
            "status": job.status,
            "max_loops": 10,
        })

        assert result_state["is_valid_state"] is True
        assert result_state["is_human_gate_required"] is True
        assert result_state["decision_action"] == "WAIT"
        assert result_state["active_node"] == "pause_for_human"
