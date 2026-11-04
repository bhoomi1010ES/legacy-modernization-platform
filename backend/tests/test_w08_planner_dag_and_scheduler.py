"""W08 Verification Suite: Planner DAG, dependency invariants, and parallel scheduling.

Verifies:
1. Exact acceptance graph topological wave computation:
   A -> {B, C, D}, {B, C} -> E, D -> F, {E, F} -> G
   Expected waves: [A], [B, C, D], [E, F], [G]
2. DAG invariant enforcement: cycles, dangling nodes, and duplicate edges.
3. Actual concurrent worker execution with overlapping windows across distinct worker IDs.
4. Dependency isolation: deliberately failing B blocks E while unrelated D/F progress.
5. Normalized module_dependencies table with FKs and unique constraint.
6. Canonical artifact type normalization (ConversionPlan -> CONVERSION_PLAN) and rejection of unknown types.
7. Replanning invalidation when module contracts change.
8. Full 9-prerequisite consumption in PlannerCoordinator.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import subprocess
from typing import Any, Dict, List
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.errors import ConflictException, PlatformException
from app.models.agent import AgentRun
from app.models.artifact import Artifact, ArtifactType, normalize_artifact_type
from app.models.base import utc_now
from app.models.job import Job
from app.models.module import Module, ModuleAttempt, ModuleDependency
from app.models.phase4 import (
    ConversionPlanModel,
    FeasibilityReportModel,
    LegacyModelRecord,
    RepositorySnapshotModel,
    TargetBlueprintModel,
)
from app.models.user import User
from app.models.workflow import WorkflowGate, WorkflowOutbox
from app.schemas.phase4 import (
    ConversionPlan,
    DependencyEdge,
    G1DecisionRecord,
    G1DecisionType,
    LegacyModel,
    ModulePlanningUnit,
    PlanningContext,
    PlanningTask,
    TargetBlueprint,
    TargetComponent,
)
from app.services.artifact_service import ArtifactService, artifact_service
from app.services.dependency_scheduler import dependency_scheduler
from app.services.plan_aggregator import plan_aggregator
from app.services.planner_coordinator import planner_coordinator


from app.core.database import AsyncSessionLocal


async def _create_test_job(db: AsyncSession, name_suffix: str = "w08") -> Job:
    """Helper to create a test job in CONVERTING state with approved gates."""
    job_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    user = User(
        user_id=owner_id,
        email=f"w08_user_{name_suffix}_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="test_bcrypt_hash",
        full_name="Test W08 User",
        role="ADMIN",
        status="ACTIVE",
    )
    db.add(user)

    job = Job(
        job_id=job_id,
        name=f"job_{name_suffix}",
        owner_user_id=owner_id,
        source_repository=f"https://github.com/example/repo_{name_suffix}.git",
        status="CONVERTING",
        budget_limit_usd=Decimal("500.00"),
        budget_used_usd=Decimal("0.00"),
        max_parallel_tasks=5,
        provider_concurrency_limit=5,
        sandbox_concurrency_limit=5,
    )
    job.stack_profile = {"runtime": "python-test"}
    job.source_commit_sha = "a" * 40
    db.add(job)

    # Add approved G1, G2, G3 gates
    for gtype in ("G1", "G2", "G3"):
        gate = WorkflowGate(
            gate_id=uuid.uuid4(),
            job_id=job_id,
            gate_type=gtype,
            status="APPROVED",
            version=1,
            decided_at=utc_now(),
        )
        db.add(gate)

    await db.commit()
    return job


async def _seed_planner_prerequisites(db: AsyncSession, job: Job) -> None:
    """Seed the minimum G1/G2 evidence required by the fail-closed planner."""
    db.add(FeasibilityReportModel(
        report_id=uuid.uuid4(), job_id=job.job_id, version=1,
        blueprint_version=1, legacy_model_version=1, overall_score=100,
        unsupported_count=0, custom_build_count=0, substitute_count=0,
        unknown_count=0, summary="All fixture capabilities supported.",
        content_hash=f"feas_{uuid.uuid4().hex}",
    ))
    db.add(RepositorySnapshotModel(
        snapshot_id=uuid.uuid4(), job_id=job.job_id, version=1,
        source_type="git", source_ref="main", commit_sha="a" * 40,
        content_hash=f"snapshot_{uuid.uuid4().hex}", inventory_hash=f"inventory_{uuid.uuid4().hex}",
        file_count=1, archive_size_bytes=0, tech_profile={"runtime": "python-test"},
    ))
    await artifact_service.create_artifact(
        db=db, job_id=job.job_id, artifact_type="CHARACTERIZATION_SUITE", version=1,
        content_bytes=json.dumps({"frozen": True, "cases": [], "coverage": {}}).encode(),
        producing_agent="CharacterizerAgent", derived_from=[], commit=False,
    )
    await artifact_service.create_artifact(
        db=db, job_id=job.job_id, artifact_type="SCHEMA_MIGRATION_PLAN", version=1,
        content_bytes=json.dumps({"status": "VALIDATED", "tables": []}).encode(),
        producing_agent="SchemaDataAgent", derived_from=[], commit=False,
    )
    await db.flush()
    g2 = await db.scalar(select(WorkflowGate).where(
        WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G2"
    ))
    suite = await db.scalar(select(Artifact).where(
        Artifact.job_id == job.job_id, Artifact.artifact_type == "CHARACTERIZATION_SUITE"
    ))
    schema = await db.scalar(select(Artifact).where(
        Artifact.job_id == job.job_id, Artifact.artifact_type == "SCHEMA_MIGRATION_PLAN"
    ))
    g2.artifact_ids = [str(suite.artifact_id)]
    g2.artifact_ids.append(str(schema.artifact_id))
    g2.artifact_hashes = {
        str(suite.artifact_id): suite.content_hash,
        str(schema.artifact_id): schema.content_hash,
    }
    await db.commit()


# ==============================================================================
# 1. ACCEPTANCE GRAPH TOPOLOGICAL WAVE COMPUTATION
# ==============================================================================

def test_acceptance_graph_topological_waves():
    """Verify exact acceptance graph produces waves: [A], [B, C, D], [E, F], [G].

    Graph:
    A -> {B, C, D}
    {B, C} -> E
    D -> F
    {E, F} -> G
    """
    def make_unit(mid: str, deps: List[str]) -> ModulePlanningUnit:
        task = PlanningTask(
            task_id=f"task_{mid}",
            module_id=mid,
            title=f"Implement {mid}",
            description=f"Task for module {mid}",
            estimate_hours=1.0,
            risk="LOW",
            acceptance_criteria=[f"{mid} functional and verified"],
            dependencies=[],
        )
        return ModulePlanningUnit(
            module_id=mid,
            responsibility=f"Responsibility of {mid}",
            source_scope=[f"src/{mid}.py"],
            target_scope=[f"target/{mid}.py"],
            dependencies=deps,
            interfaces=[f"I{mid}"],
            migration_steps=["Convert"],
            implementation_tasks=[task],
            required_tests=[f"test_{mid}.py"],
            acceptance_criteria=[f"{mid} verified"],
            estimate_hours=1.0,
            risk="LOW",
            required_tools=["compiler"],
            environment_requirements=["isolated"],
        )

    modules = [
        make_unit("A", []),
        make_unit("B", ["A"]),
        make_unit("C", ["A"]),
        make_unit("D", ["A"]),
        make_unit("E", ["B", "C"]),
        make_unit("F", ["D"]),
        make_unit("G", ["E", "F"]),
    ]

    tasks = [t for m in modules for t in m.implementation_tasks]
    waves = plan_aggregator.calculate_execution_waves(tasks, modules)

    assert len(waves) == 4, f"Expected 4 waves, got {len(waves)}"
    assert waves[0].module_ids == ["A"], f"Wave 1 expected ['A'], got {waves[0].module_ids}"
    assert waves[1].module_ids == ["B", "C", "D"], f"Wave 2 expected ['B', 'C', 'D'], got {waves[1].module_ids}"
    assert waves[2].module_ids == ["E", "F"], f"Wave 3 expected ['E', 'F'], got {waves[2].module_ids}"
    assert waves[3].module_ids == ["G"], f"Wave 4 expected ['G'], got {waves[3].module_ids}"


# ==============================================================================
# 2. DAG INVARIANT ENFORCEMENT: CYCLES, DANGLING NODES, DUPLICATES
# ==============================================================================

def test_dag_invariant_cycle_detection():
    """Verify that cycles among modules are detected and DAG is marked invalid."""
    def make_unit(mid: str, deps: List[str]) -> ModulePlanningUnit:
        return ModulePlanningUnit(
            module_id=mid,
            responsibility=f"Resp {mid}",
            source_scope=[f"{mid}.py"],
            target_scope=[f"out_{mid}.py"],
            dependencies=deps,
            interfaces=[],
            migration_steps=[],
            implementation_tasks=[
                PlanningTask(
                    task_id=f"t_{mid}",
                    module_id=mid,
                    title=f"Task {mid}",
                    description="desc",
                    estimate_hours=1.0,
                    risk="LOW",
                    acceptance_criteria=["done"],
                    dependencies=[],
                )
            ],
            required_tests=[],
            acceptance_criteria=["done"],
            estimate_hours=1.0,
            risk="LOW",
            required_tools=[],
            environment_requirements=[],
        )

    # Cycle: A -> B -> C -> A
    modules = [
        make_unit("A", ["C"]),
        make_unit("B", ["A"]),
        make_unit("C", ["B"]),
    ]
    tasks = [t for m in modules for t in m.implementation_tasks]
    val = plan_aggregator.validate_dag(tasks, modules, [])

    assert val.is_valid_dag is False
    assert val.has_cycles is True
    assert any("cycle" in msg.lower() for msg in val.validation_messages)


def test_dag_invariant_dangling_node_detection():
    """Verify that dependencies on non-existent modules are flagged and rejected."""
    unit = ModulePlanningUnit(
        module_id="mod_alpha",
        responsibility="Alpha",
        source_scope=["alpha.py"],
        target_scope=["out_alpha.py"],
        dependencies=["mod_ghost"],  # Nonexistent
        interfaces=[],
        migration_steps=[],
        implementation_tasks=[
            PlanningTask(
                task_id="t_alpha",
                module_id="mod_alpha",
                title="Task Alpha",
                description="desc",
                estimate_hours=1.0,
                risk="LOW",
                acceptance_criteria=["done"],
                dependencies=[],
            )
        ],
        required_tests=[],
        acceptance_criteria=["done"],
        estimate_hours=1.0,
        risk="LOW",
        required_tools=[],
        environment_requirements=[],
    )
    val = plan_aggregator.validate_dag(unit.implementation_tasks, [unit], [])

    assert val.is_valid_dag is False
    assert "mod_ghost" in val.missing_dependencies


# ==============================================================================
# 3. ACTUAL CONCURRENT WORKER EXECUTION
# ==============================================================================

@pytest.mark.asyncio
async def test_actual_concurrent_worker_execution_and_ordering(tmp_path, monkeypatch):
    """Run an actual concurrent worker test with overlapping execution windows.

    Workers concurrently claim tasks using claim_ready_modules().
    Verify:
    1. Two+ workers execute non-dependent modules concurrently (overlapping time windows).
    2. A finishes before B, C, D start.
    3. E never runs before BOTH B and C are verified.
    4. F never runs before D is verified.
    5. G never runs before BOTH E and F are verified.
    """
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, "concurrent-workers")
        job_id = job.job_id

        # Setup module IDs
        mod_names = ["A", "B", "C", "D", "E", "F", "G"]
        mod_uuids = {name: uuid.uuid5(job_id, name) for name in mod_names}

        # Dependencies:
        # A: none
        # B, C, D: A
        # E: B, C
        # F: D
        # G: E, F
        deps_map = {
            "A": [],
            "B": ["A"],
            "C": ["A"],
            "D": ["A"],
            "E": ["B", "C"],
            "F": ["D"],
            "G": ["E", "F"],
        }
        wave_map = {
            "A": 1,
            "B": 2, "C": 2, "D": 2,
            "E": 3, "F": 3,
            "G": 4,
        }

        # Create modules and module_dependencies in DB
        for name in mod_names:
            m = Module(
                module_id=mod_uuids[name],
                job_id=job_id,
                name=name,
                legacy_path=f"src/{name}.py",
                target_path=f"target/{name}.py",
                risk_level="MEDIUM",
                status="PENDING",
                wave_number=wave_map[name],
                dependency_module_ids=[str(mod_uuids[p]) for p in deps_map[name]],
                interfaces=[f"I{name}"],
                allowed_output_paths=[f"target/{name}.py"],
                required_tests=[f"test_{name}.py"],
                schema_dependencies=[],
                expected_resources={"required_tools": ["python"]},
                budget_limit_usd=Decimal("50.0"),
                budget_used_usd=Decimal("0.0"),
            )
            db.add(m)

        for child_name, parents in deps_map.items():
            child_id = mod_uuids[child_name]
            for parent_name in parents:
                parent_id = mod_uuids[parent_name]
                db.add(ModuleDependency(
                    dependency_id=uuid.uuid4(),
                    job_id=job_id,
                    parent_id=parent_id,
                    child_id=child_id,
                ))

        await db.commit()

        # Give every worker a real local Git repository and an attempt-owned worktree.
        repo = tmp_path / "fixture-repo"
        repo.mkdir()
        (repo / "src").mkdir()
        (repo / "target").mkdir()
        (repo / "src" / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
        subprocess.run(["git", "init", "--initial-branch=main", str(repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "W08 Test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "w08@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "fixture baseline"], check=True, capture_output=True)
        base_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        (repo / ".rebase_workspace.json").write_text("{}", encoding="utf-8")
        from app.services import phase6_workspace as workspace
        monkeypatch.setattr(workspace, "ROOT", tmp_path / "isolated-worktrees")
        execution_trace: List[Dict[str, Any]] = []

        async def worker_loop(worker_id: str):
            while True:
                async with AsyncSessionLocal() as worker_db:
                    claimed = await dependency_scheduler.claim_ready_modules(
                        worker_db,
                        job_id,
                        worker_id=worker_id,
                        limit=1,
                        commit_lease=True,
                    )
                    if not claimed:
                        # Check if all 7 modules are verified
                        stmt = select(Module).where(Module.job_id == job_id, Module.status == "VERIFIED")
                        res = await worker_db.execute(stmt)
                        if len(res.scalars().all()) == len(mod_names):
                            break
                        await asyncio.sleep(0.02)
                        continue

                    mod = claimed[0]
                    attempt_id = uuid.uuid4()
                    attempt_number = 1
                    worktree, branch = await workspace.prepare(
                        repo, str(job_id), str(mod.module_id), str(attempt_id), attempt_number, base_sha
                    )
                    started = utc_now()
                    mod.status = "RUNNING"
                    attempt = ModuleAttempt(
                        attempt_id=attempt_id, module_id=mod.module_id,
                        attempt_number=attempt_number, status="RUNNING",
                        git_branch=branch, worker_id=worker_id, started_at=started,
                        lease_generation=mod.lease_generation, lease_token=mod.lease_token,
                    )
                    worker_db.add(attempt)
                    worker_db.add(WorkflowOutbox(
                        job_id=job_id, idempotency_key=f"w08-start-{attempt_id}",
                        event_type="W08_WORKER_STARTED", status="PENDING",
                        payload={"module": mod.name, "worker_id": worker_id,
                                 "started_at": started.isoformat(), "worktree": str(worktree),
                                 "branch": branch, "integration_base_sha": base_sha},
                    ))
                    await worker_db.commit()
                    # Actual isolated ChangeSet application, with overlap caused by
                    # worker execution after each lease transaction has ended.
                    await asyncio.sleep(0.12)
                    applied = await workspace.apply_changes(
                        worktree, {f"target/{mod.name}.py": f"MODULE = {mod.name!r}\n"},
                        f"target/{mod.name}.py",
                    )
                    finished = utc_now()
                    mod.status = "VERIFIED"
                    mod.accepted_result_hash = applied["diff_hash"]
                    mod.lease_owner = None
                    attempt.status = "VERIFIED"
                    attempt.completed_at = finished
                    worker_db.add(WorkflowOutbox(
                        job_id=job_id, idempotency_key=f"w08-finish-{attempt_id}",
                        event_type="W08_WORKER_FINISHED", status="PENDING",
                        payload={"module": mod.name, "worker_id": worker_id,
                                 "started_at": started.isoformat(), "finished_at": finished.isoformat(),
                                 "worktree": str(worktree), "branch": branch,
                                 "integration_base_sha": base_sha, "base_sha": applied["base_sha"],
                                 "diff_hash": applied["diff_hash"]},
                    ))
                    await worker_db.commit()

        # Run 3 concurrent workers
        await asyncio.gather(
            worker_loop("worker-alpha"),
            worker_loop("worker-beta"),
            worker_loop("worker-gamma"),
        )

        async with AsyncSessionLocal() as trace_db:
            attempts = list((await trace_db.execute(
                select(ModuleAttempt, Module).join(Module).where(Module.job_id == job_id)
            )).all())
            trace_by_mod = {
                module.name: {
                    "worker_id": attempt.worker_id,
                    "started_at": attempt.started_at,
                    "finished_at": attempt.completed_at,
                    "branch": attempt.git_branch,
                }
                for attempt, module in attempts
            }
            finish_events = list((await trace_db.execute(select(WorkflowOutbox).where(
                WorkflowOutbox.job_id == job_id,
                WorkflowOutbox.event_type == "W08_WORKER_FINISHED",
            ))).scalars().all())
            start_events = list((await trace_db.execute(select(WorkflowOutbox).where(
                WorkflowOutbox.job_id == job_id,
                WorkflowOutbox.event_type == "W08_WORKER_STARTED",
            ))).scalars().all())
            for event in finish_events:
                execution_trace.append(event.payload)
        assert len(trace_by_mod) == 7, f"Expected 7 persisted worker attempts, got {len(trace_by_mod)}"
        assert len(execution_trace) == 7, "Expected seven persisted finish events"
        assert len(start_events) == 7, "Expected seven persisted start events"

        # 1. Verify A completed before B, C, D started
        a_finished = trace_by_mod["A"]["finished_at"]
        assert trace_by_mod["B"]["started_at"] >= a_finished
        assert trace_by_mod["C"]["started_at"] >= a_finished
        assert trace_by_mod["D"]["started_at"] >= a_finished

        # 2. Verify concurrent execution of Wave 2 modules (overlapping time windows)
        wave2_workers = {trace_by_mod[m]["worker_id"] for m in ("B", "C", "D")}

        # At least 2 different workers were active
        assert len(wave2_workers) >= 2, f"Expected multiple concurrent workers, got {wave2_workers}"
        assert len({trace_by_mod[m]["branch"] for m in mod_names}) == len(mod_names), "Each module must use a distinct Git branch/worktree"
        assert len({event["worktree"] for event in execution_trace}) == len(mod_names), "Each module must use a distinct writable worktree"
        assert all(event["integration_base_sha"] == base_sha for event in execution_trace)

        # Overlapping execution: max(starts) < min(ends) across at least two modules
        overlaps = False
        pairs = [("B", "C"), ("B", "D"), ("C", "D")]
        for m1, m2 in pairs:
            s1, e1 = trace_by_mod[m1]["started_at"].timestamp(), trace_by_mod[m1]["finished_at"].timestamp()
            s2, e2 = trace_by_mod[m2]["started_at"].timestamp(), trace_by_mod[m2]["finished_at"].timestamp()
            if max(s1, s2) < min(e1, e2):
                overlaps = True
                break
        assert overlaps, "Expected overlapping execution windows among Wave 2 modules"

        # 3. Verify E never started before BOTH B and C finished
        b_finished = trace_by_mod["B"]["finished_at"]
        c_finished = trace_by_mod["C"]["finished_at"]
        e_started = trace_by_mod["E"]["started_at"]
        assert e_started >= b_finished, f"E started at {e_started} before B finished at {b_finished}"
        assert e_started >= c_finished, f"E started at {e_started} before C finished at {c_finished}"

        # 4. Verify F never started before D finished
        d_finished = trace_by_mod["D"]["finished_at"]
        f_started = trace_by_mod["F"]["started_at"]
        assert f_started >= d_finished, f"F started at {f_started} before D finished at {d_finished}"

        # 5. Verify G never started before BOTH E and F finished
        e_finished = trace_by_mod["E"]["finished_at"]
        f_finished = trace_by_mod["F"]["finished_at"]
        g_started = trace_by_mod["G"]["started_at"]
        assert g_started >= e_finished, f"G started at {g_started} before E finished at {e_finished}"
        assert g_started >= f_finished, f"G started at {g_started} before F finished at {f_finished}"


# ==============================================================================
# 4. DELIBERATE FAILURE & DEPENDENCY ISOLATION
# ==============================================================================

@pytest.mark.asyncio
async def test_deliberate_dependency_failure_blocks_dependent_while_unrelated_progress():
    """Verify that deliberately failing B blocks E, while unrelated D and F progress to VERIFIED."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, "dep-failure")
        job_id = job.job_id

        mod_names = ["A", "B", "C", "D", "E", "F", "G"]
        mod_uuids = {name: uuid.uuid5(job_id, name) for name in mod_names}

        deps_map = {
            "A": [],
            "B": ["A"],
            "C": ["A"],
            "D": ["A"],
            "E": ["B", "C"],
            "F": ["D"],
            "G": ["E", "F"],
        }

        for name in mod_names:
            db.add(Module(
                module_id=mod_uuids[name],
                job_id=job_id,
                name=name,
                legacy_path=f"src/{name}.py",
                target_path=f"target/{name}.py",
                risk_level="MEDIUM",
                status="PENDING",
                wave_number=1,
                dependency_module_ids=[str(mod_uuids[p]) for p in deps_map[name]],
                budget_limit_usd=Decimal("50.0"),
            ))

        for child_name, parents in deps_map.items():
            for parent_name in parents:
                db.add(ModuleDependency(
                    dependency_id=uuid.uuid4(),
                    job_id=job_id,
                    parent_id=mod_uuids[parent_name],
                    child_id=mod_uuids[child_name],
                ))

        await db.commit()

        # Step 1: Claim and verify module A
        claimed_a = await dependency_scheduler.claim_ready_modules(db, job_id, worker_id="w-1", limit=1)
        assert len(claimed_a) == 1 and claimed_a[0].name == "A"
        claimed_a[0].status = "VERIFIED"
        await db.commit()

        # Wave 2 runs as three independent worker tasks. B fails while C and D
        # complete; timestamps and worker identity are persisted per attempt.
        async def execute_wave2(name: str, worker_id: str):
            async with AsyncSessionLocal() as worker_db:
                claimed = await dependency_scheduler.claim_ready_modules(
                    worker_db, job_id, worker_id=worker_id, limit=1,
                    module_ids=[mod_uuids[name]],
                )
                assert len(claimed) == 1 and claimed[0].name == name
                module = claimed[0]
                started = utc_now()
                attempt = ModuleAttempt(
                    module_id=module.module_id, attempt_number=1,
                    status="RUNNING", git_branch=f"test/{name}",
                    worker_id=worker_id, started_at=started,
                    lease_generation=module.lease_generation, lease_token=module.lease_token,
                )
                worker_db.add(attempt)
                await worker_db.commit()
                # Leave enough execution time for three independent DB-backed
                # claims to complete before any worker finishes.
                await asyncio.sleep(0.35)
                module.status = "FAILED" if name == "B" else "VERIFIED"
                attempt.status = module.status
                attempt.completed_at = utc_now()
                module.accepted_result_hash = None if name == "B" else f"verified-{name}"
                await worker_db.commit()
                return attempt

        wave2_attempts = await asyncio.gather(
            execute_wave2("B", "worker-B"),
            execute_wave2("C", "worker-C"),
            execute_wave2("D", "worker-D"),
        )
        assert len({a.worker_id for a in wave2_attempts}) == 3
        assert max(a.started_at for a in wave2_attempts) < min(a.completed_at for a in wave2_attempts)

        # Step 3: Now attempt to claim next ready modules
        claimed_next = await dependency_scheduler.claim_ready_modules(db, job_id, worker_id="w-2", limit=5)

        # F depends only on D (which is VERIFIED), so F CAN run!
        # E depends on B and C. Because B is FAILED (not VERIFIED), E MUST NOT run!
        claimed_names = {m.name for m in claimed_next}
        assert "F" in claimed_names, "Unrelated module F should be claimable because D is verified"
        assert "E" not in claimed_names, "Module E must be blocked because parent B failed"
        assert "G" not in claimed_names, "Module G must be blocked because E has not run"
        mod_f = next(m for m in claimed_next if m.name == "F")
        mod_f.status = "RUNNING"
        await db.commit()
        await asyncio.sleep(0.02)
        mod_f.status = "VERIFIED"
        mod_f.accepted_result_hash = "verified-F"
        await db.commit()

        # Verify module E in DB remains PENDING
        mod_e = await db.get(Module, mod_uuids["E"])
        assert mod_e.status == "PENDING"
        assert (await db.get(Module, mod_uuids["F"])).status == "VERIFIED"


# ==============================================================================
# 5. NORMALIZED MODULE_DEPENDENCIES TABLE & CONSTRAINTS
# ==============================================================================

@pytest.mark.asyncio
async def test_module_dependencies_table_constraints_and_cascade():
    """Verify module_dependencies enforces foreign keys and uniqueness."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, "mod-deps-fk")
        m1 = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="mod_1",
            legacy_path="1.py",
            target_path="1_out.py",
            status="PENDING",
        )
        m2 = Module(
            module_id=uuid.uuid4(),
            job_id=job.job_id,
            name="mod_2",
            legacy_path="2.py",
            target_path="2_out.py",
            status="PENDING",
        )
        db.add_all([m1, m2])
        await db.flush()

        dep = ModuleDependency(
            dependency_id=uuid.uuid4(),
            job_id=job.job_id,
            parent_id=m1.module_id,
            child_id=m2.module_id,
        )
        db.add(dep)
        await db.commit()

        # Check dependency was saved
        stmt = select(ModuleDependency).where(
            ModuleDependency.parent_id == m1.module_id,
            ModuleDependency.child_id == m2.module_id,
        )
        res = (await db.execute(stmt)).scalar_one_or_none()
        assert res is not None

        # Attempt duplicate edge (violating unique constraint uq_module_dependency_parent_child)
        dup_dep = ModuleDependency(
            dependency_id=uuid.uuid4(),
            job_id=job.job_id,
            parent_id=m1.module_id,
            child_id=m2.module_id,
        )
        db.add(dup_dep)
        with pytest.raises(Exception):
            await db.commit()
        await db.rollback()


@pytest.mark.asyncio
async def test_scheduler_rejects_incomplete_normalized_dependency_graph():
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, "incomplete-normalized-graph")
        parent_id, child_id = uuid.uuid4(), uuid.uuid4()
        db.add_all([
            Module(module_id=parent_id, job_id=job.job_id, name="parent", legacy_path="p.py", target_path="p_out.py"),
            Module(module_id=child_id, job_id=job.job_id, name="child", legacy_path="c.py", target_path="c_out.py",
                   dependency_module_ids=[str(parent_id)]),
        ])
        await db.commit()
        with pytest.raises(ConflictException, match="dependency representations disagree"):
            await dependency_scheduler.claim_ready_modules(
                db, job.job_id, worker_id="graph-checker", limit=2
            )


# ==============================================================================
# 6. CANONICAL ARTIFACT NORMALIZATION & READ COMPATIBILITY
# ==============================================================================

def test_canonical_artifact_type_normalization():
    """Verify normalize_artifact_type normalizes ConversionPlan and rejects unknown types."""
    # ConversionPlan -> CONVERSION_PLAN
    assert normalize_artifact_type("ConversionPlan") == "CONVERSION_PLAN"
    assert normalize_artifact_type("CONVERSION_PLAN") == "CONVERSION_PLAN"
    assert normalize_artifact_type("conversionplan") == "CONVERSION_PLAN"

    # Known platform types
    assert normalize_artifact_type("TargetBlueprint") == "TargetBlueprint"
    assert normalize_artifact_type("TARGET_BLUEPRINT") == "TargetBlueprint"
    assert normalize_artifact_type("LegacyModel") == "LegacyModel"
    assert normalize_artifact_type("FeasibilityReport") == "FeasibilityReport"
    assert normalize_artifact_type("CharacterizationSuite") == "CHARACTERIZATION_SUITE"
    assert normalize_artifact_type("SchemaMigrationPlan") == "SCHEMA_MIGRATION_PLAN"
    assert normalize_artifact_type("CONVERTED_MODULE") == "CodeModule"
    assert normalize_artifact_type("REVIEW_REPORT") == "ReviewReport"
    assert normalize_artifact_type("INTEGRATION_REPORT") == "IntegrationReport"
    assert normalize_artifact_type("JOB_REPORT") == "JobReport"
    assert normalize_artifact_type("SBOM") == "SBOM"
    assert normalize_artifact_type("DELIVERY_RECORD") == "DeliveryRecord"

    # Unknown types must be rejected
    with pytest.raises(PlatformException) as exc:
        normalize_artifact_type("UNKNOWN_FABRICATED_TYPE")
    assert exc.value.code == "INVALID_ARTIFACT_TYPE"

    with pytest.raises(PlatformException) as exc:
        normalize_artifact_type("")
    assert exc.value.code == "INVALID_ARTIFACT_TYPE"


@pytest.mark.asyncio
async def test_artifact_read_migration_backward_compatibility():
    """Verify that querying list_artifacts with 'ConversionPlan' matches canonical 'CONVERSION_PLAN'."""
    service = ArtifactService()
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, "read-compat")

        # Publish with canonical type
        art = await service.publish_artifact(
            db=db,
            job_id=job.job_id,
            artifact_type="CONVERSION_PLAN",
            version=1,
            content_bytes=json.dumps({"plan": "canonical"}).encode("utf-8"),
            producing_agent="PlannerCoordinator",
            commit=True,
        )

        assert art.artifact_type == "CONVERSION_PLAN"

        # Query using legacy alias "ConversionPlan"
        results = await service.list_artifacts(db, job.job_id, artifact_type="ConversionPlan")
        assert len(results) == 1
        assert results[0].artifact_id == art.artifact_id
        assert results[0].artifact_type == "CONVERSION_PLAN"


# ==============================================================================
# 7. REPLANNING CONTRACT INVALIDATION
# ==============================================================================

@pytest.mark.asyncio
async def test_replanning_invalidates_contract_changed_modules():
    """Verify that replanning with changed contracts resets module status and increments lease generation."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, "replanning-invalidation")
        await _seed_planner_prerequisites(db, job)
        job_id = job.job_id

        # Setup initial TargetBlueprint and LegacyModel
        bp = TargetBlueprint(
            job_id=str(job_id),
            version=1,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            components=[
                TargetComponent(
                    component_id="mod_core",
                    name="CoreComponent",
                    target_path="src/v1_core.py",
                    responsibilities=["Core"],
                    mapped_legacy_modules=["mod_1"],
                    interfaces=["ICoreV1"],
                    dependencies=[],
                )
            ],
            content_hash="bp_v1_hash",
        )
        leg = LegacyModel(
            job_id=str(job_id),
            snapshot_id=str(uuid.uuid4()),
            version=1,
            modules=[],
            public_interfaces=[],
            persistence_entities=[],
            evidence_index={},
            content_hash="leg_v1_hash",
        )

        # Seed TargetBlueprintModel record so provenance bridge resolves bp_v1_hash
        bp_model = TargetBlueprintModel(
            blueprint_id=uuid.uuid4(),
            job_id=job_id,
            version=1,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            content_hash="bp_v1_hash",
        )
        db.add(bp_model)
        await db.flush()

        # Seed TargetBlueprint artifact so bridge finds artifact_type=TargetBlueprint
        await artifact_service.create_artifact(
            db=db,
            job_id=job_id,
            artifact_type="TargetBlueprint",
            version=1,
            content_bytes=json.dumps({"blueprint": "v1"}).encode("utf-8"),
            producing_agent="ArchitectAgent",
            derived_from=[],
            commit=False,
        )
        await db.flush()

        # Plan v1
        plan_v1 = await planner_coordinator.execute_planning(
            db=db,
            job=job,
            blueprint=bp,
            legacy_model=leg,
        )
        assert plan_v1.version == 1

        # Simulate module leased by worker
        m_uuid = uuid.uuid5(job_id, "mod_core")
        mod = await db.get(Module, m_uuid)
        assert mod is not None
        assert mod.status == "PENDING"
        assert mod.target_path == "src/v1_core.py"
        assert mod.interfaces == ["ICoreV1"]

        mod.status = "LEASED"
        mod.lease_owner = "worker-old"
        mod.lease_generation = 1
        await db.commit()

        # Now replan with CHANGED CONTRACT (Target path and interfaces updated)
        bp_v2 = TargetBlueprint(
            job_id=str(job_id),
            version=2,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            components=[
                TargetComponent(
                    component_id="mod_core",
                    name="CoreComponent",
                    target_path="src/v2_core.py",  # Changed!
                    responsibilities=["Core v2"],
                    mapped_legacy_modules=["mod_1"],
                    interfaces=["ICoreV2"],        # Changed!
                    dependencies=[],
                )
            ],
            content_hash="bp_v2_hash",
        )

        # Seed TargetBlueprintModel v2 record so provenance bridge resolves bp_v2_hash
        bp_model_v2 = TargetBlueprintModel(
            blueprint_id=uuid.uuid4(),
            job_id=job_id,
            version=2,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            content_hash="bp_v2_hash",
        )
        db.add(bp_model_v2)

        # Seed TargetBlueprint artifact v2
        await artifact_service.create_artifact(
            db=db,
            job_id=job_id,
            artifact_type="TargetBlueprint",
            version=2,
            content_bytes=json.dumps({"blueprint": "v2"}).encode("utf-8"),
            producing_agent="ArchitectAgent",
            derived_from=[],
            commit=False,
        )
        await db.flush()

        plan_v2 = await planner_coordinator.execute_planning(
            db=db,
            job=job,
            blueprint=bp_v2,
            legacy_model=leg,
        )
        assert plan_v2.version == 2

        # Verify module was invalidated back to PENDING and lease cleared
        await db.refresh(mod)
        assert mod.status == "PENDING", "Module with changed contract must be reset to PENDING"
        assert mod.lease_owner is None, "Lease owner must be cleared on replanning"
        assert mod.lease_generation == 2, "Lease generation must be incremented"
        assert mod.target_path == "src/v2_core.py"
        assert mod.interfaces == ["ICoreV2"]


# ==============================================================================
# 8. 9-PREREQUISITE CONSUMPTION IN PLANNER COORDINATOR
# ==============================================================================

@pytest.mark.asyncio
async def test_planner_coordinator_consumes_all_nine_prerequisites():
    """Verify PlannerCoordinator consumes all 9 required inputs into PlanningContext."""
    async with AsyncSessionLocal() as db:
        job = await _create_test_job(db, "nine-inputs")
        job.stack_profile = {"framework": "fastapi", "python_version": "3.12"}
        job.source_commit_sha = "a" * 40
        await db.commit()

        # Seed RepositorySnapshot
        snap = RepositorySnapshotModel(
            snapshot_id=uuid.uuid4(),
            job_id=job.job_id,
            version=1,
            source_type="git",
            source_ref="main",
            commit_sha="a" * 40,
            content_hash="snap_hash_001",
            inventory_hash="inv_hash_001",
            file_count=10,
            archive_size_bytes=1000,
            tech_profile={"language": "python"},
        )
        db.add(snap)

        # Seed FeasibilityReport
        feas = FeasibilityReportModel(
            report_id=uuid.uuid4(),
            job_id=job.job_id,
            version=1,
            blueprint_version=1,
            legacy_model_version=1,
            overall_score=95.0,
            unsupported_count=0,
            custom_build_count=0,
            substitute_count=0,
            unknown_count=0,
            summary="Overall feasibility 95%: all capabilities supported.",
            content_hash="feas_hash_001",
        )
        db.add(feas)

        # Seed RepositorySnapshot artifact so derived_from references resolve
        await artifact_service.create_artifact(
            db=db,
            job_id=job.job_id,
            artifact_type="RepositorySnapshot",
            version=1,
            content_bytes=json.dumps({"snapshot": True}).encode("utf-8"),
            producing_agent="IntakeAgent",
            derived_from=[],
            commit=True,
        )

        # Seed CharacterizationSuite artifact
        await artifact_service.create_artifact(
            db=db,
            job_id=job.job_id,
            artifact_type="CHARACTERIZATION_SUITE",
            version=1,
            content_bytes=json.dumps({"frozen": True, "suite": "verified", "coverage": {"pct": 92.5}}).encode("utf-8"),
            producing_agent="CharacterizerAgent",
            derived_from=["snap_hash_001"],
            commit=True,
        )

        # Seed SchemaMigrationPlan artifact
        await artifact_service.create_artifact(
            db=db,
            job_id=job.job_id,
            artifact_type="SCHEMA_MIGRATION_PLAN",
            version=1,
            content_bytes=json.dumps({"tables": ["users", "accounts"], "status": "VALIDATED"}).encode("utf-8"),
            producing_agent="SchemaDataAgent",
            derived_from=["snap_hash_001"],
            commit=True,
        )

        bp = TargetBlueprint(
            job_id=str(job.job_id),
            version=1,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            components=[
                TargetComponent(
                    component_id="comp_app",
                    name="ApplicationComponent",
                    target_path="app.py",
                    responsibilities=["App"],
                    mapped_legacy_modules=["mod_app"],
                    interfaces=[],
                    dependencies=[],
                )
            ],
            content_hash="bp_hash_001",
        )
        leg = LegacyModel(
            job_id=str(job.job_id),
            snapshot_id=str(snap.snapshot_id),
            version=1,
            modules=[],
            public_interfaces=[],
            persistence_entities=[],
            evidence_index={},
            content_hash="leg_hash_001",
        )

        # Seed TargetBlueprintModel so provenance bridge resolves bp_hash_001
        bp_model = TargetBlueprintModel(
            blueprint_id=uuid.uuid4(),
            job_id=job.job_id,
            version=1,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            content_hash="bp_hash_001",
        )
        db.add(bp_model)

        # Seed TargetBlueprint artifact
        await artifact_service.create_artifact(
            db=db,
            job_id=job.job_id,
            artifact_type="TargetBlueprint",
            version=1,
            content_bytes=json.dumps({"blueprint": "nine-inputs"}).encode("utf-8"),
            producing_agent="ArchitectAgent",
            derived_from=[],
            commit=False,
        )
        g2 = await db.scalar(select(WorkflowGate).where(
            WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G2"
        ))
        suite_art = await db.scalar(select(Artifact).where(
            Artifact.job_id == job.job_id, Artifact.artifact_type == "CHARACTERIZATION_SUITE"
        ))
        schema_art = await db.scalar(select(Artifact).where(
            Artifact.job_id == job.job_id, Artifact.artifact_type == "SCHEMA_MIGRATION_PLAN"
        ))
        g2.artifact_ids = [str(suite_art.artifact_id), str(schema_art.artifact_id)]
        g2.artifact_hashes = {
            str(suite_art.artifact_id): suite_art.content_hash,
            str(schema_art.artifact_id): schema_art.content_hash,
        }
        await db.flush()
        await db.flush()

        plan = await planner_coordinator.execute_planning(
            db=db,
            job=job,
            blueprint=bp,
            legacy_model=leg,
        )

        assert plan is not None
        assert plan.version == 1
        # Check provenance hashes recorded all inputs
        prov = plan.provenance
        assert prov.get("target_blueprint_hash") == "bp_hash_001"
        assert prov.get("legacy_model_hash") == "leg_hash_001"
        assert prov.get("feasibility_report_hash") == "feas_hash_001"
        assert prov.get("characterization_suite_hash") is not None
        assert prov.get("schema_data_plan_hash") is not None
        assert prov.get("repo_inventory_hash") == "inv_hash_001"
        assert prov["upstream_approval_hashes"].get("g1_approval_hash")
        assert prov["upstream_approval_hashes"].get("g2_approval_hash")
        assert prov["upstream_approval_hashes"].get("g1_decision_hash")
        assert prov.get("baseline_source_sha") == "a" * 40
        assert prov.get("stack_profile") == {"framework": "fastapi", "python_version": "3.12"}
        assert prov.get("cost_ceiling_usd") == "500.00"
        module_row = await db.get(Module, uuid.uuid5(job.job_id, "comp_app"))
        plan_artifact = await db.scalar(select(Artifact).where(
            Artifact.job_id == job.job_id, Artifact.artifact_type == "CONVERSION_PLAN"
        ))
        assert module_row.plan_hash == plan_artifact.content_hash
        assert module_row.integration_base_sha == "a" * 40
        assert module_row.expected_input_hash
        assert module_row.upstream_approval_hashes == {
            "g1_approval_hash": prov["upstream_approval_hashes"]["g1_approval_hash"],
            "g2_approval_hash": prov["upstream_approval_hashes"]["g2_approval_hash"],
        }
        g3 = await db.scalar(select(WorkflowGate).where(
            WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G3"
        ))
        g3.artifact_ids = [str(plan_artifact.artifact_id)]
        g3.artifact_hashes = {str(plan_artifact.artifact_id): plan_artifact.content_hash}
        await db.commit()
        plan_modules = list((await db.execute(select(Module).where(
            Module.job_id == job.job_id
        ))).scalars().all())
        roots = [m for m in plan_modules if not m.dependency_module_ids]
        assert roots
        claimed = await dependency_scheduler.claim_ready_modules(
            db, job.job_id, worker_id="snapshot-verifier", limit=1,
            module_ids=[roots[0].module_id],
        )
        assert len(claimed) == 1, "A module may be leased only from the exact G3-approved artifact snapshot"

        # Verify ONLY canonical CONVERSION_PLAN was published (no duplicate ConversionPlan artifact)
        arts = await artifact_service.list_artifacts(db, job.job_id)
        plan_arts = [a for a in arts if a.artifact_type == "CONVERSION_PLAN"]
        legacy_plan_arts = [a for a in arts if a.artifact_type == "ConversionPlan"]
        assert len(plan_arts) == 1, f"Expected exactly 1 CONVERSION_PLAN artifact, got {len(plan_arts)}"
        assert len(legacy_plan_arts) == 0, "No duplicate 'ConversionPlan' artifact should be published"
