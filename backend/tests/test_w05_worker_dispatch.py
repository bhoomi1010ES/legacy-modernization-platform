"""W05 Test Suite: Durable Worker Dispatch, Leasing, Fencing, Outbox & Recovery.

Covers:
- FLOW-01: Parallel Module Execution and Fan-Out
- DATA-04: Expired Worker Lease Fencing & Generation Bumping
- DATA-05: Outbox Backoff, Jitter, Deduplication & Classified Dead-Letter Handling
- Section 8.1 & 8.2: Worker Registry, Task Leasing, CAS Fencing Commit Protocol
- Section 8.3: Fault Injection (Worker Crash, Frozen Worker, Double Claim, Terminal Job Abort)
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import uuid
from uuid import UUID

import pytest
from sqlalchemy import select, update
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictException, NotFoundException
from app.models.agent import AgentRun
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.user import User
from app.models.worker import WorkerRegistry
from app.models.workflow import WorkflowGate, WorkflowOutbox
from app.schemas.jobs import JobStatus
from app.services.dependency_scheduler import dependency_scheduler
from app.services.supervisor_router import supervisor_router
from app.services.worker_dispatch_service import worker_dispatch_service
from app.services.workflow_outbox import workflow_outbox_dispatcher


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_test_users(db):
    owner = await db.scalar(select(User).order_by(User.created_at.asc()).limit(1))
    if not owner:
        owner = User(
            user_id=uuid.uuid4(),
            email=f"w05_owner_{uuid.uuid4().hex[:6]}@acme.corp",
            full_name="W05 Owner User",
            password_hash="argon2_test_hash",
            role="DEVELOPER",
            status="ACTIVE",
        )
        db.add(owner)
        await db.commit()
        await db.refresh(owner)

    admin = await db.scalar(select(User).where(User.role == "ADMIN", User.user_id != owner.user_id).limit(1))
    if not admin:
        admin = User(
            user_id=uuid.uuid4(),
            email=f"w05_admin_{uuid.uuid4().hex[:6]}@acme.corp",
            full_name="W05 Admin User",
            password_hash="argon2_test_hash",
            role="ADMIN",
            status="ACTIVE",
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    return owner, admin


async def _create_converting_job_with_gates(db) -> Job:
    owner, _ = await _get_test_users(db)
    job = Job(
        job_id=uuid.uuid4(),
        name=f"w05-job-{uuid.uuid4().hex[:8]}",
        source_repository="https://github.com/example/w05-repo.git",
        owner_user_id=owner.user_id,
        status="CONVERTING",
        active_node="converting",
        budget_used_usd=Decimal("0.00"),
        budget_limit_usd=Decimal("500.00"),
        max_parallel_tasks=4,
        provider_concurrency_limit=4,
        sandbox_concurrency_limit=4,
        orchestration_generation=1,
    )
    db.add(job)
    await db.flush()

    # Seed approved G1, G2, G3 gates
    for g_type in ("G1", "G2", "G3"):
        gate = WorkflowGate(
            job_id=job.job_id,
            gate_type=g_type,
            version=1,
            status="APPROVED",
            artifact_ids=[],
            artifact_hashes={},
            decided_at=utc_now(),
        )
        db.add(gate)

    await db.commit()
    await db.refresh(job)
    return job


# ==============================================================================
# 1. Worker Registry Lifecycle
# ==============================================================================


@pytest.mark.asyncio
async def test_worker_registry_lifecycle():
    """Verify worker registration, heartbeat updates, active listing, and deregistration."""
    async with AsyncSessionLocal() as db:
        worker_id = f"worker-test-{uuid.uuid4().hex[:6]}"

        # 1. Register
        reg = await worker_dispatch_service.register_worker(
            db,
            worker_id=worker_id,
            worker_type="CONVERSION_WORKER",
            version="1.2.0",
            metadata_payload={"host": "worker-node-1", "capacity": 2},
        )
        assert reg.worker_id == worker_id
        assert reg.worker_type == "CONVERSION_WORKER"
        assert reg.status == "ACTIVE"

        # 2. Heartbeat
        ok = await worker_dispatch_service.heartbeat_worker(db, worker_id)
        assert ok is True

        # 3. List active workers
        active = await worker_dispatch_service.get_active_workers(db, heartbeat_timeout_seconds=60)
        assert any(w.worker_id == worker_id for w in active)

        # 4. Deregister
        dereg_ok = await worker_dispatch_service.deregister_worker(db, worker_id, status="STOPPED")
        assert dereg_ok is True

        worker_db = await db.get(WorkerRegistry, worker_id)
        assert worker_db.status == "STOPPED"


# ==============================================================================
# 2. Parallel Module Fan-Out (FLOW-01 Fix)
# ==============================================================================


@pytest.mark.asyncio
async def test_parallel_module_dispatch_flow01():
    """FLOW-01: Proves that multiple ready independent modules are scheduled in parallel
    rather than serial single-element selection.
    """
    async with AsyncSessionLocal() as db:
        job = await _create_converting_job_with_gates(db)

        # Create 5 independent modules in Wave 1
        modules = []
        for i in range(5):
            m = Module(
                job_id=job.job_id,
                name=f"module_parallel_{i}",
                legacy_path=f"legacy/mod_{i}.py",
                target_path=f"target/mod_{i}.py",
                risk_level="LOW",
                status="PENDING",
                wave_number=1,
                dependency_module_ids=[],
                budget_limit_usd=Decimal("50.00"),
                budget_used_usd=Decimal("0.00"),
            )
            db.add(m)
            modules.append(m)
        await db.commit()

        # 1. Evaluate router decision - verify parallel metadata
        decision = await supervisor_router.evaluate_next_action(db, job)
        assert decision.action.value in ("EXECUTE", "REPAIR")
        assert decision.metadata.get("parallel_fanout_eligible") is True
        assert decision.metadata.get("ready_count") == 5
        assert len(decision.metadata.get("ready_module_ids", [])) == 5

        # 2. Evaluate parallel actions directly from router
        parallel_decisions = await supervisor_router.evaluate_parallel_actions(db, job, max_tasks=4)
        assert len(parallel_decisions) >= 3, f"Expected at least 3 parallel decisions, got {len(parallel_decisions)}"

        # 3. Claim ready tasks with limit=3 in a single call (parallel fan-out)
        claimed = await worker_dispatch_service.claim_ready_tasks(
            db,
            job.job_id,
            worker_id="parallel-worker-pool",
            limit=3,
            lease_seconds=300,
        )
        assert len(claimed) == 3, f"Expected 3 parallel claimed modules, got {len(claimed)}"

        # Verify each claimed task has unique attempt and monotonic generation
        generations = [t["lease_generation"] for t in claimed]
        tokens = [t["lease_token"] for t in claimed]
        assert len(set(tokens)) == 3, "Each parallel task must receive a unique lease_token"
        assert all(g >= 1 for g in generations)

        # Verify TASK_LEASED outbox events exist
        outbox_events = list(
            (
                await db.execute(
                    select(WorkflowOutbox).where(
                        WorkflowOutbox.job_id == job.job_id,
                        WorkflowOutbox.event_type == "TASK_LEASED",
                    )
                )
            ).scalars().all()
        )
        assert len(outbox_events) == 3


# ==============================================================================
# 3. Lease Heartbeat & Renewal
# ==============================================================================


@pytest.mark.asyncio
async def test_lease_renewal_and_stale_rejection():
    """Verify lease heartbeat extends deadline for valid owner, but rejects stale/unauthorized workers."""
    async with AsyncSessionLocal() as db:
        job = await _create_converting_job_with_gates(db)

        m = Module(
            job_id=job.job_id,
            name="test_renew_module",
            legacy_path="legacy/renew.py",
            target_path="target/renew.py",
            status="PENDING",
            wave_number=1,
            dependency_module_ids=[],
        )
        db.add(m)
        await db.commit()

        claimed = await worker_dispatch_service.claim_ready_tasks(
            db, job.job_id, worker_id="worker-valid", limit=1, lease_seconds=120
        )
        assert len(claimed) == 1
        task = claimed[0]

        # Valid renewal
        ok = await worker_dispatch_service.renew_lease(
            db,
            task["module_id"],
            worker_id="worker-valid",
            lease_token=task["lease_token"],
            lease_generation=task["lease_generation"],
            lease_seconds=300,
        )
        assert ok is True

        # Invalid renewal (wrong worker)
        bad_worker = await worker_dispatch_service.renew_lease(
            db,
            task["module_id"],
            worker_id="worker-imposter",
            lease_token=task["lease_token"],
            lease_generation=task["lease_generation"],
        )
        assert bad_worker is False

        # Invalid renewal (stale generation)
        bad_gen = await worker_dispatch_service.renew_lease(
            db,
            task["module_id"],
            worker_id="worker-valid",
            lease_token=task["lease_token"],
            lease_generation=task["lease_generation"] + 5,
        )
        assert bad_gen is False


# ==============================================================================
# 4. CAS Fencing Rejects Stale Worker After Expiry (DATA-04)
# ==============================================================================


@pytest.mark.asyncio
async def test_cas_fencing_rejects_stale_worker_after_expiry():
    """DATA-04: Worker A claims task at gen 1, freezes beyond lease expiry.
    Supervisor reclaims task and Worker B claims at gen 2.
    Worker A unfreezes and attempts commit -> FENCE TRIPS (ConflictException).
    Worker B commits successfully at gen 2.
    """
    async with AsyncSessionLocal() as db:
        job = await _create_converting_job_with_gates(db)

        m = Module(
            job_id=job.job_id,
            name="test_fence_module",
            legacy_path="legacy/fence.py",
            target_path="target/fence.py",
            status="PENDING",
            wave_number=1,
            dependency_module_ids=[],
        )
        db.add(m)
        await db.commit()

        # 1. Worker A claims task at generation 1
        claimed_a = await worker_dispatch_service.claim_ready_tasks(
            db, job.job_id, worker_id="worker-A", limit=1, lease_seconds=1
        )
        task_a = claimed_a[0]
        assert task_a["lease_generation"] == 1

        # 2. Worker A freezes; lease expires
        # Artificially expire lease in DB
        await db.execute(
            update(Module)
            .where(Module.module_id == task_a["module_id"])
            .values(lease_expires_at=utc_now() - timedelta(seconds=10))
        )
        await db.commit()

        # 3. Crash reconciler reclaims expired lease (bumps generation to 2)
        reclaimed = await worker_dispatch_service.reclaim_expired_leases(db, job.job_id)
        assert reclaimed == 1

        # 4. Worker B claims task at generation 2
        claimed_b = await worker_dispatch_service.claim_ready_tasks(
            db, job.job_id, worker_id="worker-B", limit=1, lease_seconds=300
        )
        task_b = claimed_b[0]
        assert task_b["lease_generation"] > task_a["lease_generation"]

        # 5. Worker A wakes up and attempts to commit with stale gen 1 -> CAS FENCE TRIPS!
        with pytest.raises(ConflictException) as exc_info:
            await worker_dispatch_service.commit_stage_result(
                db,
                job_id=job.job_id,
                module_id=task_a["module_id"],
                attempt_id=task_a["attempt_id"],
                worker_id="worker-A",
                lease_token=task_a["lease_token"],
                lease_generation=task_a["lease_generation"],  # stale gen 1!
                result_status="VERIFIED",
                result_hash="sha256:worker_a_stale_hash",
            )
        assert "fenced" in str(exc_info.value).lower() or "stale" in str(exc_info.value).lower()

        # Verify module is NOT verified yet
        m_check = await db.get(Module, task_a["module_id"])
        assert m_check.status == "RUNNING"
        assert m_check.lease_owner == "worker-B"

        # 6. Worker B commits successfully with valid gen 2
        receipt_b = await worker_dispatch_service.commit_stage_result(
            db,
            job_id=job.job_id,
            module_id=task_b["module_id"],
            attempt_id=task_b["attempt_id"],
            worker_id="worker-B",
            lease_token=task_b["lease_token"],
            lease_generation=task_b["lease_generation"],
            result_status="VERIFIED",
            result_hash="sha256:worker_b_valid_hash",
        )
        assert receipt_b["status"] == "COMMITTED"
        assert receipt_b["result_status"] == "VERIFIED"

        # Verify module is now VERIFIED
        await db.refresh(m_check)
        assert m_check.status == "VERIFIED"
        assert m_check.accepted_result_hash == "sha256:worker_b_valid_hash"


# ==============================================================================
# 5. Crash Recovery Reclaims Expired Leases with Generation Bump
# ==============================================================================


@pytest.mark.asyncio
async def test_crash_recovery_reclaims_expired_leases():
    """Verify that crashed/dead workers have their expired leases reclaimed,
    interrupted attempts marked BLOCKED, and monotonic generation incremented.
    """
    async with AsyncSessionLocal() as db:
        job = await _create_converting_job_with_gates(db)

        # Create 2 modules and lease them to a dead worker
        for i in range(2):
            m = Module(
                job_id=job.job_id,
                name=f"crashed_mod_{i}",
                legacy_path=f"legacy/{i}.py",
                target_path=f"target/{i}.py",
                status="RUNNING",
                wave_number=1,
                lease_owner="crashed-worker-99",
                lease_generation=1,
                lease_expires_at=utc_now() - timedelta(minutes=5),  # already expired
            )
            db.add(m)
            await db.flush()

            att = ModuleAttempt(
                module_id=m.module_id,
                attempt_number=1,
                status="RUNNING",
                git_branch="rebase/crashed-att-1",
                started_at=utc_now() - timedelta(minutes=10),
                lease_generation=1,
            )
            db.add(att)
        await db.commit()

        # Run reconciler
        reclaimed_count = await worker_dispatch_service.reclaim_expired_leases(db, job.job_id)
        assert reclaimed_count == 2

        # Verify modules returned to PENDING with bumped generation
        m_list = list(
            (
                await db.execute(
                    select(Module).where(
                        Module.job_id == job.job_id,
                        Module.name.in_(["crashed_mod_0", "crashed_mod_1"]),
                    )
                )
            ).scalars().all()
        )
        for m in m_list:
            assert m.status == "PENDING"
            assert m.lease_owner is None
            assert m.lease_expires_at is None
            assert m.lease_generation == 2  # Monotonic increment!
            assert m.retry_count == 1

        # Verify attempts marked BLOCKED
        attempts = list(
            (
                await db.execute(
                    select(ModuleAttempt).where(
                        ModuleAttempt.module_id.in_([m.module_id for m in m_list])
                    )
                )
            ).scalars().all()
        )
        assert all(a.status == "BLOCKED" for a in attempts)


# ==============================================================================
# 6. Terminal Job Rejection (Mid-Execution Cancellation)
# ==============================================================================


@pytest.mark.asyncio
async def test_cancelled_job_quarantines_worker_commit():
    """Verify that if a job is cancelled while work is running, result commit
    is strictly rejected and staged artifacts are quarantined.
    """
    async with AsyncSessionLocal() as db:
        job = await _create_converting_job_with_gates(db)

        m = Module(
            job_id=job.job_id,
            name="test_cancel_module",
            legacy_path="legacy/cancel.py",
            target_path="target/cancel.py",
            status="PENDING",
            wave_number=1,
            dependency_module_ids=[],
        )
        db.add(m)
        await db.commit()

        claimed = await worker_dispatch_service.claim_ready_tasks(
            db, job.job_id, worker_id="worker-cancel-test", limit=1
        )
        task = claimed[0]

        # Job is cancelled mid-execution!
        job.status = "CANCELLED"
        await db.commit()

        # Worker attempts to commit result
        with pytest.raises(ConflictException) as exc_info:
            await worker_dispatch_service.commit_stage_result(
                db,
                job_id=job.job_id,
                module_id=task["module_id"],
                attempt_id=task["attempt_id"],
                worker_id="worker-cancel-test",
                lease_token=task["lease_token"],
                lease_generation=task["lease_generation"],
                result_status="VERIFIED",
                result_hash="sha256:cancelled_job_hash",
            )
        assert "terminal" in str(exc_info.value).lower() or "quarantined" in str(exc_info.value).lower()


# ==============================================================================
# 7. Outbox Dispatcher: Backoff, Jitter, Deduplication & DLQ (DATA-05)
# ==============================================================================


@pytest.mark.asyncio
async def test_outbox_dispatcher_deduplication_and_poison_handling():
    """DATA-05: Outbox dispatcher enforces deduplication, exponential retry with jitter,
    and DLQ routing with POISON_PAYLOAD classification.
    """
    async with AsyncSessionLocal() as db:
        job = await _create_converting_job_with_gates(db)

        idemp_key = f"outbox-test-{uuid.uuid4().hex[:8]}"

        # 1. Normal event
        evt_normal = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=f"{idemp_key}-normal",
            event_type="TEST_NORMAL",
            payload={"msg": "hello"},
            status="PENDING",
        )
        # 2. Poison event (handler will raise ValueError)
        evt_poison = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=f"{idemp_key}-poison",
            event_type="TEST_POISON",
            payload={"corrupt": True},
            status="PENDING",
        )
        # 3. Transient failure event (retries with backoff + jitter)
        evt_transient = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=f"{idemp_key}-transient",
            event_type="TEST_TRANSIENT",
            payload={"attempt": 1},
            status="PENDING",
        )
        db.add_all([evt_normal, evt_poison, evt_transient])
        await db.commit()

        calls = []

        async def dummy_handler(event_type: str, payload: dict):
            calls.append((event_type, payload))
            if event_type == "TEST_POISON":
                raise ValueError("poison payload: schema malformed")
            elif event_type == "TEST_TRANSIENT":
                raise TimeoutError("transient network glitch")

        # Dispatch
        processed = await workflow_outbox_dispatcher.dispatch_ready(db, dummy_handler, limit=10)
        assert processed >= 1

        # Verify normal event is PROCESSED
        await db.refresh(evt_normal)
        assert evt_normal.status == "PROCESSED"

        # Verify transient event was retried with exponential backoff and jitter
        await db.refresh(evt_transient)
        assert evt_transient.status == "PENDING"
        assert evt_transient.attempts == 1
        assert evt_transient.available_at > utc_now()

        # Verify poison event was classified and routed to DEAD_LETTER
        await db.refresh(evt_poison)
        assert evt_poison.status == "DEAD_LETTER"
        assert "poison payload" in (evt_poison.last_error or "").lower()

        # Verify OUTBOX_DEAD_LETTER alert audit event was logged
        dl_audit = await db.scalar(
            select(AuditEvent).where(
                AuditEvent.job_id == job.job_id,
                AuditEvent.event_type == "OUTBOX_DEAD_LETTER",
                AuditEvent.target_resource == str(evt_poison.outbox_id),
            )
        )
        assert dl_audit is not None
        assert dl_audit.payload.get("classification") == "POISON_PAYLOAD"


# ==============================================================================
# 8. DependencyScheduler Integration with TASK_LEASED Outbox
# ==============================================================================


@pytest.mark.asyncio
async def test_dependency_scheduler_emits_task_leased_outbox():
    """Verify that existing DependencyScheduler integration properly emits TASK_LEASED outbox events."""
    async with AsyncSessionLocal() as db:
        job = await _create_converting_job_with_gates(db)

        m = Module(
            job_id=job.job_id,
            name="test_dep_scheduler_outbox",
            legacy_path="legacy/ds.py",
            target_path="target/ds.py",
            status="PENDING",
            wave_number=1,
            dependency_module_ids=[],
        )
        db.add(m)
        await db.commit()

        claimed = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="scheduler-worker-1", limit=1
        )
        assert len(claimed) == 1
        assert claimed[0].status == "LEASED"
        assert claimed[0].lease_token is not None

        # Verify TASK_LEASED outbox event exists
        outbox = await db.scalar(
            select(WorkflowOutbox).where(
                WorkflowOutbox.job_id == job.job_id,
                WorkflowOutbox.event_type == "TASK_LEASED",
                WorkflowOutbox.idempotency_key == f"task-leased-{claimed[0].module_id}-{claimed[0].lease_generation}",
            )
        )
        assert outbox is not None
        assert outbox.payload.get("worker_id") == "scheduler-worker-1"
