"""Tests for Phase 4 Planner Coordinator, Module Planners, Plan Aggregator, and DAG Cycle Detection."""

import pytest
from app.services.module_planner import ModulePlanner
from app.services.plan_aggregator import PlanAggregator
from app.services.planner_coordinator import PlannerCoordinator
from app.schemas.phase4 import (
    TargetBlueprint,
    TargetComponent,
    TargetInterfaceContract,
    LegacyModel,
    LegacyModule,
    PlanningTask,
    ModulePlanningUnit,
    DependencyEdge,
    ConversionPlanValidation,
    ConfidenceLevel,
)


@pytest.fixture
def sample_blueprint_and_legacy():
    """Provides a synthetic blueprint and legacy model pair."""
    legacy = LegacyModel(
        model_id="legacy_p_01",
        job_id="job_plan_01",
        snapshot_id="snap_p_01",
        version=1,
        modules=[
            LegacyModule(
                module_id="mod_core",
                path="core",
                responsibility="Core Models and Utils",
                language="Python",
                risk="LOW",
                confidence=ConfidenceLevel.CONFIRMED,
            ),
            LegacyModule(
                module_id="mod_auth",
                path="auth",
                responsibility="User Authentication",
                language="Python",
                dependencies=["mod_core"],
                risk="HIGH",
                confidence=ConfidenceLevel.CONFIRMED,
            ),
            LegacyModule(
                module_id="mod_api",
                path="api",
                responsibility="Public API Endpoints",
                language="Python",
                dependencies=["mod_auth"],
                risk="MEDIUM",
                confidence=ConfidenceLevel.CONFIRMED,
            ),
        ],
        content_hash="hash_legacy_01",
    )

    blueprint = TargetBlueprint(
        blueprint_id="bp_plan_01",
        job_id="job_plan_01",
        version=1,
        target_stack="FastAPI + PostgreSQL",
        target_architecture="CLEAN_ARCHITECTURE",
        components=[
            TargetComponent(
                component_id="comp_core",
                name="CoreDomain",
                target_path="src/domain/core",
                mapped_legacy_modules=["mod_core"],
                responsibilities=["Core domain logic"],
                technologies=["Python 3.12"],
                dependencies=[],
                interfaces=[],
            ),
            TargetComponent(
                component_id="comp_auth",
                name="AuthService",
                target_path="src/services/auth",
                mapped_legacy_modules=["mod_auth"],
                responsibilities=["JWT Token Validation"],
                technologies=["FastAPI", "Passlib"],
                dependencies=["comp_core"],
                interfaces=[],
            ),
            TargetComponent(
                component_id="comp_api",
                name="RestApi",
                target_path="src/api/v1",
                mapped_legacy_modules=["mod_api"],
                responsibilities=["Route Handlers"],
                technologies=["FastAPI Router"],
                dependencies=["comp_auth"],
                interfaces=[],
            ),
        ],
        content_hash="hash_bp_01",
    )
    return blueprint, legacy


class TestPlannerAndDAGValidation:
    """Planner coordinator, module planner, aggregator, and DAG invariant verification."""

    def test_single_module_planner_output(self, sample_blueprint_and_legacy):
        """ModulePlanner produces complete planning unit with tasks and acceptance criteria."""
        blueprint, legacy = sample_blueprint_and_legacy
        comp = blueprint.components[0]

        planner = ModulePlanner()
        plan_unit = planner.plan_module(
            component=comp,
            legacy_module=legacy.modules[0],
            blueprint=blueprint,
        )

        assert plan_unit.module_id == comp.component_id
        assert len(plan_unit.implementation_tasks) >= 2

        # Invariant 8: Every module has acceptance criteria
        assert len(plan_unit.acceptance_criteria) >= 2
        for crit in plan_unit.acceptance_criteria:
            assert len(crit) > 5

        # Invariant 5: Every task has an owner/module ID
        for task in plan_unit.implementation_tasks:
            assert task.module_id == comp.component_id
            assert task.estimate_hours > 0.0
            assert len(task.acceptance_criteria) > 0

    def test_plan_aggregator_topological_waves(self, sample_blueprint_and_legacy):
        """PlanAggregator merges planning units, validates DAG, and builds execution waves."""
        blueprint, legacy = sample_blueprint_and_legacy

        coordinator = PlannerCoordinator()
        conversion_plan = coordinator.coordinate_planning(
            job_id="job_plan_01",
            blueprint=blueprint,
            legacy_model=legacy,
        )

        assert conversion_plan.plan_id.startswith("plan_")
        assert conversion_plan.validation_status.is_valid_dag is True
        assert conversion_plan.validation_status.has_cycles is False

        # Invariant 7: ConversionPlan contains no cycle
        assert len(conversion_plan.validation_status.cycle_nodes) == 0

        # Waves must be topologically sorted
        assert len(conversion_plan.waves) >= 2
        wave_1 = conversion_plan.waves[0]
        # comp_core has no dependencies so must be in Wave 1
        assert "comp_core" in wave_1.module_ids

        # Total estimate hours must match sum of tasks
        expected_hours = sum(t.estimate_hours for t in conversion_plan.tasks)
        assert abs(conversion_plan.estimates.total_hours - expected_hours) < 0.01

    def test_dag_cycle_detection_and_rejection(self):
        """Cycle A -> B -> C -> A must be identified and rejected."""
        aggregator = PlanAggregator()

        tasks = [
            PlanningTask(
                task_id="task_A",
                module_id="mod_1",
                title="Task A",
                description="Desc A",
                dependencies=["task_C"],  # Cycle: A depends on C
                acceptance_criteria=["Done A"],
            ),
            PlanningTask(
                task_id="task_B",
                module_id="mod_1",
                title="Task B",
                description="Desc B",
                dependencies=["task_A"],  # B depends on A
                acceptance_criteria=["Done B"],
            ),
            PlanningTask(
                task_id="task_C",
                module_id="mod_1",
                title="Task C",
                description="Desc C",
                dependencies=["task_B"],  # C depends on B
                acceptance_criteria=["Done C"],
            ),
        ]

        unit = ModulePlanningUnit(
            module_id="mod_1",
            responsibility="Cyclic Unit",
            implementation_tasks=tasks,
            acceptance_criteria=["Pass all"],
        )

        plan = aggregator.aggregate_plans(
            job_id="job_cycle_test",
            blueprint_version=1,
            planner_units=[unit],
        )

        assert plan.validation_status.is_valid_dag is False
        assert plan.validation_status.has_cycles is True
        assert len(plan.validation_status.cycle_nodes) > 0

    def test_dag_missing_dependency_detection(self):
        """Task depending on a non-existent task ID must be detected and rejected."""
        aggregator = PlanAggregator()

        tasks = [
            PlanningTask(
                task_id="task_valid",
                module_id="mod_1",
                title="Task Valid",
                description="Desc",
                dependencies=["task_ghost_missing_404"],
                acceptance_criteria=["Completed"],
            )
        ]

        unit = ModulePlanningUnit(
            module_id="mod_1",
            responsibility="Unit with broken reference",
            implementation_tasks=tasks,
            acceptance_criteria=["Pass all"],
        )

        plan = aggregator.aggregate_plans(
            job_id="job_dep_test",
            blueprint_version=1,
            planner_units=[unit],
        )

        assert plan.validation_status.is_valid_dag is False
        assert "task_ghost_missing_404" in plan.validation_status.missing_dependencies

    def test_dag_duplicate_id_rejection(self):
        """Duplicate task IDs must be detected and rejected."""
        aggregator = PlanAggregator()

        tasks = [
            PlanningTask(
                task_id="task_duplicate_id",
                module_id="mod_1",
                title="First Task",
                description="Desc 1",
                acceptance_criteria=["Criteria 1"],
            ),
            PlanningTask(
                task_id="task_duplicate_id",
                module_id="mod_1",
                title="Second Task Duplicate",
                description="Desc 2",
                acceptance_criteria=["Criteria 2"],
            ),
        ]

        unit = ModulePlanningUnit(
            module_id="mod_1",
            responsibility="Duplicate tasks unit",
            implementation_tasks=tasks,
            acceptance_criteria=["Pass all"],
        )

        plan = aggregator.aggregate_plans(
            job_id="job_dup_test",
            blueprint_version=1,
            planner_units=[unit],
        )

        assert plan.validation_status.is_valid_dag is False
        assert "task_duplicate_id" in plan.validation_status.duplicate_ids
