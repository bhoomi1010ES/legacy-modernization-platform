"""Phase 3 durable workflow, gate, scheduling, recovery and quota tests."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictException, ForbiddenException
from app.domain.state_machine import GatePolicy, JobStateMachine
from app.models.job import Job
from app.models.artifact import Artifact
from app.models.module import Module
from app.models.user import User
from app.models.workflow import WorkflowCheckpoint, WorkflowGate, WorkflowOutbox
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, GateType
from app.schemas.jobs import JobStatus
from app.services.dependency_scheduler import DependencyScheduler
from app.services.gate_service import GateService
from app.services.supervisor_graph import WORKFLOW_NODES, supervisor_graph
from app.services.supervisor_service import SupervisorService
from app.services.workflow_outbox import WorkflowOutboxDispatcher


async def _owner(db):
    owner = await db.scalar(select(User).order_by(User.created_at.asc()).limit(1))
    assert owner is not None, "seeded test user is required"
    return owner


async def _job(db, status: JobStatus = JobStatus.CREATED, *, used="0", limit="100") -> Job:
    owner = await _owner(db)
    job = Job(
        name=f"phase3-{uuid.uuid4()}", source_repository="https://github.com/acme/phase3",
        owner_user_id=owner.user_id, status=status.value,
        active_node=status.value.lower(), budget_used_usd=Decimal(used), budget_limit_usd=Decimal(limit),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@pytest.mark.asyncio
async def test_langgraph_transition_checkpoints_before_and_after():
    assert {"analysis", "gate_g1", "conversion", "gate_g4", "complete"}.issubset(set(WORKFLOW_NODES))
    async with AsyncSessionLocal() as db:
        job = await _job(db)
        transitioned = await SupervisorService().transition(db, job.job_id, JobStatus.INTAKE)
        checkpoints = list((await db.execute(
            select(WorkflowCheckpoint).where(WorkflowCheckpoint.job_id == job.job_id).order_by(WorkflowCheckpoint.sequence)
        )).scalars().all())
        assert transitioned.status == "INTAKE"
        assert [item.checkpoint_kind for item in checkpoints] == ["BEFORE", "AFTER"]
        assert checkpoints[-1].state_payload["active_node"] == "intake"


@pytest.mark.asyncio
async def test_gate_transition_materializes_durable_interrupt():
    async with AsyncSessionLocal() as db:
        job = await _job(db, JobStatus.ANALYZING)
        for art_type in ("LEGACY_MODEL", "TARGET_BLUEPRINT", "FEASIBILITY_REPORT"):
            db.add(Artifact(
                artifact_id=uuid.uuid4(),
                job_id=job.job_id,
                artifact_type=art_type,
                version=1,
                content_hash=f"sha256:{art_type.lower()}_hash_123",
                storage_path=f"artifacts/{art_type.lower()}.json",
                content_size_bytes=1024,
                media_type="application/json",
                producing_agent="AnalyzerCoordinator",
            ))
        await db.commit()
        transitioned = await SupervisorService().transition(db, job.job_id, JobStatus.AWAITING_GATE_G1)
        gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G1"))
        latest = await db.scalar(select(WorkflowCheckpoint).where(
            WorkflowCheckpoint.job_id == job.job_id
        ).order_by(WorkflowCheckpoint.sequence.desc()).limit(1))
        assert transitioned.blocking_reason == "Human decision required for G1."
        assert gate is not None and gate.status == "PENDING"
        assert latest.checkpoint_kind == "INTERRUPT"


@pytest.mark.asyncio
async def test_pause_resume_and_restart_recovery_are_durable():
    async with AsyncSessionLocal() as db:
        job = await _job(db, JobStatus.ANALYZING)
        service = SupervisorService()
        paused = await service.pause(db, job.job_id, actor_id="reviewer", reason="maintenance window")
        assert paused.status == "PAUSED" and paused.paused_from_status == "ANALYZING"
        resumed = await service.resume(db, job.job_id, actor_id="reviewer")
        assert resumed.status == "ANALYZING" and resumed.paused_from_status is None
        before = resumed.last_checkpoint_sequence
        recovered = await service.recover(db, job.job_id)
        assert recovered.last_checkpoint_sequence == before + 1
        latest = await service.checkpointer.latest(db, job.job_id)
        assert latest.checkpoint_kind == "RECOVERY"


@pytest.mark.asyncio
async def test_budget_exhaustion_blocks_progress():
    async with AsyncSessionLocal() as db:
        job = await _job(db, JobStatus.INTAKE, used="100", limit="100")
        with pytest.raises(ConflictException, match="budget is exhausted"):
            await SupervisorService().transition(db, job.job_id, JobStatus.ANALYZING)


def test_gate_policy_denies_unauthorized_and_agents():
    with pytest.raises(ForbiddenException):
        GatePolicy.validate_decision(GateType.G2, DecisionOutcome.APPROVED, "valid review rationale", "DEVELOPER")
    with pytest.raises(Exception, match="agents"):
        GatePolicy.validate_decision(GateType.G2, DecisionOutcome.APPROVED, "valid review rationale", "ADMIN", is_human=False)


@pytest.mark.asyncio
async def test_rejection_stores_rationale_and_routes_to_revision():
    async with AsyncSessionLocal() as db:
        job = await _job(db, JobStatus.AWAITING_GATE_G2)
        owner = await _owner(db)
        gate = WorkflowGate(job_id=job.job_id, gate_type="G2", version=1, artifact_hashes={})
        db.add(gate)
        await db.commit()
        result, decided_gate, routed_job, replay = await GateService().decide(
            db, gate.gate_id,
            GateDecisionRequest(decision=DecisionOutcome.REJECTED, rationale="Coverage is missing the retry edge case.", artifact_hashes={}),
            actor_id=owner.user_id, actor_role="ADMIN",
        )
        assert result.rationale.startswith("Coverage is missing")
        assert decided_gate.status == "REJECTED"
        assert routed_job.status == "CHARACTERIZING"
        assert replay is False


@pytest.mark.asyncio
async def test_duplicate_gate_decision_is_rejected_but_idempotency_replays():
    async with AsyncSessionLocal() as db:
        job = await _job(db, JobStatus.AWAITING_GATE_G1)
        owner = await _owner(db)
        gate = WorkflowGate(job_id=job.job_id, gate_type="G1", version=1, artifact_hashes={})
        db.add(gate)
        await db.commit()
        payload = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED, rationale="Feasibility gaps require another analysis pass.",
            artifact_hashes={}, idempotency_key=f"gate-{uuid.uuid4()}",
        )
        first = await GateService().decide(db, gate.gate_id, payload, actor_id=owner.user_id, actor_role="ADMIN")
        second = await GateService().decide(db, gate.gate_id, payload, actor_id=owner.user_id, actor_role="ADMIN")
        assert first[0].decision_id == second[0].decision_id and second[3] is True
        conflicting = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED, rationale="A second reviewer attempted a stale decision.", artifact_hashes={}
        )
        with pytest.raises(ConflictException, match="already has terminal status"):
            await GateService().decide(db, gate.gate_id, conflicting, actor_id=owner.user_id, actor_role="ADMIN")


@pytest.mark.asyncio
async def test_revised_artifact_invalidates_bound_and_downstream_approvals():
    async with AsyncSessionLocal() as db:
        job = await _job(db, JobStatus.CONVERTING)
        artifact = Artifact(
            job_id=job.job_id, artifact_type="CHARACTERIZATION_SUITE", version=1,
            content_hash="sha256:old", storage_path=f"phase3/{uuid.uuid4()}.json", producing_agent="TestDesigner",
        )
        db.add(artifact)
        await db.flush()
        g2 = WorkflowGate(
            job_id=job.job_id, gate_type="G2", version=1, status="APPROVED",
            artifact_ids=[str(artifact.artifact_id)], artifact_hashes={str(artifact.artifact_id): "sha256:old"},
        )
        g3 = WorkflowGate(job_id=job.job_id, gate_type="G3", version=1, status="APPROVED", artifact_hashes={})
        db.add_all([g2, g3])
        await db.commit()
        invalidated = await GateService().invalidate_for_artifact(
            db, job.job_id, artifact.artifact_id, "sha256:new", reason="Characterization suite version changed."
        )
        assert {gate.gate_type for gate in invalidated} == {"G2", "G3"}
        await db.refresh(job)
        assert job.status == "CHARACTERIZING"
        assert job.last_checkpoint_sequence == 2


@pytest.mark.asyncio
async def test_codewriter_requires_all_gates_and_schedules_dependencies_leaf_first():
    async with AsyncSessionLocal() as db:
        job = await _job(db, JobStatus.CONVERTING)
        scheduler = DependencyScheduler()
        with pytest.raises(ConflictException, match="G1, G2 and G3"):
            await scheduler.claim_ready_modules(db, job.job_id, worker_id="worker-a")
        for gate_type in ("G1", "G2", "G3"):
            db.add(WorkflowGate(job_id=job.job_id, gate_type=gate_type, version=1, status="APPROVED", artifact_hashes={}))
        leaf = Module(job_id=job.job_id, name="leaf", legacy_path="leaf", target_path="leaf", wave_number=1)
        db.add(leaf)
        await db.flush()
        parent = Module(
            job_id=job.job_id, name="parent", legacy_path="parent", target_path="parent", wave_number=2,
            dependency_module_ids=[str(leaf.module_id)],
        )
        db.add(parent)
        await db.commit()
        claimed = await scheduler.claim_ready_modules(db, job.job_id, worker_id="worker-a", limit=3)
        assert [module.name for module in claimed] == ["leaf"]


@pytest.mark.asyncio
async def test_outbox_retry_exhaustion_moves_to_dead_letter():
    async with AsyncSessionLocal() as db:
        job = await _job(db)
        event = WorkflowOutbox(job_id=job.job_id, idempotency_key=f"outbox-{uuid.uuid4()}", event_type="GIT_COMMIT")
        db.add(event)
        await db.commit()

        async def failing_handler(_event_type, _payload):
            raise RuntimeError("sandbox unavailable")

        assert await WorkflowOutboxDispatcher(max_attempts=1).dispatch_ready(db, failing_handler) == 0
        await db.refresh(event)
        assert event.status == "DEAD_LETTER" and event.attempts == 1


def test_state_machine_prevents_gate_bypass():
    assert not JobStateMachine.can_transition(JobStatus.ANALYZING, JobStatus.CONVERTING)
    assert not JobStateMachine.can_transition(JobStatus.AWAITING_GATE_G2, JobStatus.CONVERTING)
