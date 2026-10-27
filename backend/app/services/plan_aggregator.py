"""Plan Aggregator & DAG Validator: Merges planner outputs, validates DAG, and computes execution waves."""

from collections import defaultdict, deque
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from app.schemas.phase4 import (
    ConversionPlan,
    ConversionPlanValidation,
    ConversionPlanWave,
    DependencyEdge,
    ModulePlanningUnit,
    PlanningTask,
)

logger = logging.getLogger(__name__)


class PlanAggregator:
    """Aggregates module planner units, enforces DAG invariants, and calculates execution waves."""

    def __init__(self):
        pass

    def validate_dag(
        self,
        tasks: List[PlanningTask],
        modules: List[ModulePlanningUnit],
        dependencies: List[DependencyEdge],
    ) -> ConversionPlanValidation:
        """Enforces all DAG invariants: cycle detection, missing dependencies, duplicate IDs, acceptance criteria."""
        try:
            task_ids: Set[str] = set()
            duplicate_ids: List[str] = []
            missing_deps: List[str] = []
            missing_ac_tasks: List[str] = []
            messages: List[str] = []

            # 1. Check duplicate task IDs and acceptance criteria
            for t in tasks:
                if t.task_id in task_ids:
                    duplicate_ids.append(t.task_id)
                task_ids.add(t.task_id)

                if not t.acceptance_criteria:
                    missing_ac_tasks.append(t.task_id)

            # 2. Check missing task dependencies
            for t in tasks:
                for dep in t.dependencies:
                    if dep not in task_ids:
                        missing_deps.append(dep)
                        messages.append(f"Task {t.task_id} depends on nonexistent task {dep}")

            # 3. Cycle Detection using Kahn's algorithm / DFS
            adj: Dict[str, List[str]] = defaultdict(list)
            in_degree: Dict[str, int] = {t.task_id: 0 for t in tasks}

            for t in tasks:
                for dep in t.dependencies:
                    adj[dep].append(t.task_id)
                    in_degree[t.task_id] += 1

            queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
            visited_count = 0
            cycles: List[List[str]] = []

            while queue:
                curr = queue.popleft()
                visited_count += 1
                for nxt in adj[curr]:
                    in_degree[nxt] -= 1
                    if in_degree[nxt] == 0:
                        queue.append(nxt)

            has_cycles = visited_count < len(tasks)
            if has_cycles:
                cycle_nodes = [tid for tid, deg in in_degree.items() if deg > 0]
                cycles.append(cycle_nodes)
                messages.append(f"Dependency cycle detected among tasks: {cycle_nodes}")

            is_valid = (
                not has_cycles
                and not missing_deps
                and not duplicate_ids
                and not missing_ac_tasks
            )

            if duplicate_ids:
                messages.append(f"Duplicate task IDs found: {duplicate_ids}")
            if missing_deps:
                messages.extend(missing_deps)
            if missing_ac_tasks:
                messages.append(f"Tasks missing acceptance criteria: {missing_ac_tasks}")

            validation = ConversionPlanValidation(
                is_valid_dag=is_valid,
                has_cycles=has_cycles,
                cycle_nodes=cycles,
                missing_dependencies=missing_deps,
                duplicate_ids=duplicate_ids,
                invalid_references=[],
                interface_conflicts=[],
                scope_overlaps=[],
                missing_acceptance_criteria_tasks=missing_ac_tasks,
                validation_messages=messages,
            )
            return validation
        except Exception as exc:
            logger.exception("validate_dag failed | %s: %s", type(exc).__name__, exc)
            raise

    def calculate_execution_waves(
        self,
        tasks: List[PlanningTask],
        modules: List[ModulePlanningUnit],
    ) -> List[ConversionPlanWave]:
        """Calculates topological execution waves based on task dependency levels."""
        try:
            if not tasks:
                return []

            task_map = {t.task_id: t for t in tasks}
            in_degree = {t.task_id: len(t.dependencies) for t in tasks}
            adj = defaultdict(list)
            for t in tasks:
                for dep in t.dependencies:
                    if dep in task_map:
                        adj[dep].append(t.task_id)

            waves: List[ConversionPlanWave] = []
            remaining_tasks = set(task_map.keys())
            wave_num = 1

            while remaining_tasks:
                # Independent tasks in current tier
                current_wave_tasks = [
                    tid for tid in remaining_tasks
                    if in_degree[tid] == 0
                ]

                if not current_wave_tasks:
                    # Circular or broken dependency remaining: drain remaining
                    current_wave_tasks = list(remaining_tasks)

                current_wave_modules = sorted(list({task_map[tid].module_id for tid in current_wave_tasks}))

                wave_name = f"Wave {wave_num}"
                if wave_num == 1:
                    rationale = "Foundation: Shared domain contracts and independent base scaffolding."
                elif wave_num == 2:
                    rationale = "Core: Business logic services depending on Wave 1 contracts."
                elif wave_num == 3:
                    rationale = "Integration: Public controllers, API adapters, and downstream services."
                else:
                    rationale = f"Finalization and end-to-end integration wave {wave_num}."

                waves.append(ConversionPlanWave(
                    wave_number=wave_num,
                    name=wave_name,
                    module_ids=current_wave_modules,
                    task_ids=sorted(current_wave_tasks),
                    rationale=rationale,
                ))

                for tid in current_wave_tasks:
                    remaining_tasks.remove(tid)
                    for nxt in adj[tid]:
                        in_degree[nxt] = max(0, in_degree[nxt] - 1)

                wave_num += 1

            return waves
        except Exception as exc:
            logger.exception("calculate_execution_waves failed | %s: %s", type(exc).__name__, exc)
            raise

    def aggregate_plan(
        self,
        job_id: str,
        blueprint_version: Optional[int] = None,
        planning_units: Optional[List[ModulePlanningUnit]] = None,
        planner_units: Optional[List[ModulePlanningUnit]] = None,
        blueprint: Optional[Any] = None,
        version: int = 1,
        context: Optional[Any] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> ConversionPlan:
        """Aggregates module planning units into a validated canonical ConversionPlan."""
        try:
            units = [u for u in (planning_units or planner_units or []) if u is not None]
            bp_ver = blueprint_version
            if bp_ver is None and blueprint is not None:
                bp_ver = getattr(blueprint, "version", 1)
            if bp_ver is None:
                bp_ver = 1

            all_tasks: List[PlanningTask] = []
            all_dependencies: List[DependencyEdge] = []
            conflicts: List[str] = []

            seen_task_ids: Set[str] = set()

            for unit in units:
                for task in unit.implementation_tasks:
                    if task.task_id in seen_task_ids:
                        conflicts.append(f"Conflict: duplicate task ID '{task.task_id}' across planners.")
                    seen_task_ids.add(task.task_id)
                    all_tasks.append(task)

                for dep_id in unit.dependencies:
                    all_dependencies.append(DependencyEdge(
                        source=unit.module_id,
                        target=dep_id,
                        dependency_type="CODE_IMPORT",
                    ))

            # Validate DAG
            validation = self.validate_dag(all_tasks, units, all_dependencies)

            # Compute waves
            waves = self.calculate_execution_waves(all_tasks, units)

            total_hours = sum(t.estimate_hours for t in all_tasks)
            risk_counts: Dict[str, int] = defaultdict(int)
            for t in all_tasks:
                risk_counts[t.risk] += 1

            total_ac = sum(len(t.acceptance_criteria) for t in all_tasks)
            completeness = 100.0 if not validation.missing_acceptance_criteria_tasks else 85.0

            # Compute upstream provenance hashes
            prov = dict(context.provenance_hashes) if (context and getattr(context, "provenance_hashes", None)) else {}
            if provenance:
                prov.update(provenance)
            repo_inv_hash = prov.get("repo_inventory_hash") or (getattr(context, "repo_inventory_hash", None) if context else None)
            leg_hash = prov.get("legacy_model_hash") or (getattr(getattr(context, "legacy_model", None), "content_hash", None) if context else None)
            bp_hash = prov.get("target_blueprint_hash") or (getattr(getattr(context, "target_blueprint", None), "content_hash", None) if context else (getattr(blueprint, "content_hash", None) if blueprint else None))
            feas_hash = prov.get("feasibility_report_hash") or (getattr(getattr(context, "feasibility_report", None), "content_hash", None) if context else None)
            
            g1_dec_hash = prov.get("g1_decision_hash")
            if not g1_dec_hash and context and getattr(context, "g1_decisions", None):
                g1_raw = [d.model_dump(mode="json") if hasattr(d, "model_dump") else str(d) for d in context.g1_decisions]
                g1_dec_hash = hashlib.sha256(json.dumps(g1_raw, sort_keys=True).encode()).hexdigest()

            char_suite_hash = prov.get("characterization_suite_hash")
            if not char_suite_hash and context and getattr(context, "characterization_suite", None):
                cs = context.characterization_suite
                char_suite_hash = cs.get("content_hash") or cs.get("suite_hash") if isinstance(cs, dict) else getattr(cs, "content_hash", None)

            char_cov_hash = prov.get("characterization_coverage_hash")
            if not char_cov_hash and context and getattr(context, "characterization_coverage", None):
                cov = context.characterization_coverage
                char_cov_hash = cov.get("coverage_hash") or cov.get("content_hash") if isinstance(cov, dict) else getattr(cov, "content_hash", None)

            schema_hash = prov.get("schema_data_plan_hash")
            if not schema_hash and context and getattr(context, "schema_data_plan", None):
                sp = context.schema_data_plan
                schema_hash = sp.get("schema_hash") or sp.get("content_hash") or sp.get("source_schema_hash") if isinstance(sp, dict) else getattr(sp, "content_hash", None)

            # Content hash
            hasher = hashlib.sha256()
            hasher.update(json.dumps([m.model_dump() for m in units], sort_keys=True).encode("utf-8"))
            hasher.update(json.dumps([t.model_dump() for t in all_tasks], sort_keys=True).encode("utf-8"))
            hasher.update(json.dumps([w.model_dump() for w in waves], sort_keys=True).encode("utf-8"))
            if leg_hash:
                hasher.update(leg_hash.encode("utf-8"))
            if bp_hash:
                hasher.update(bp_hash.encode("utf-8"))
            content_hash = hasher.hexdigest()

            full_provenance = {
                "repo_inventory_hash": repo_inv_hash,
                "legacy_model_hash": leg_hash,
                "target_blueprint_hash": bp_hash,
                "feasibility_report_hash": feas_hash,
                "g1_decision_hash": g1_dec_hash,
                "characterization_suite_hash": char_suite_hash,
                "characterization_coverage_hash": char_cov_hash,
                "schema_data_plan_hash": schema_hash,
                "planner_version": "v4.5",
            }

            plan = ConversionPlan(
                plan_id=f"plan_{uuid.uuid4().hex[:12]}",
                job_id=job_id,
                version=version,
                blueprint_version=bp_ver,
                modules=units,
                tasks=all_tasks,
                dependencies=all_dependencies,
                waves=waves,
                interfaces=[],
                total_estimate_hours=round(total_hours, 1),
                risk_summary=dict(risk_counts),
                required_tests_count=sum(len(t.required_tests) for t in all_tasks),
                acceptance_criteria_completeness_pct=completeness,
                tool_requirements=["compiler", "type_checker", "test_runner", "sandbox"],
                environment_requirements=["Isolated Container Sandbox", "Target Runtime"],
                evidence_refs=[],
                conflicts=conflicts,
                validation=validation,
                validation_status=validation,
                content_hash=content_hash,
                provenance=full_provenance,
                repo_inventory_hash=repo_inv_hash,
                legacy_model_hash=leg_hash,
                target_blueprint_hash=bp_hash,
                feasibility_report_hash=feas_hash,
                g1_decision_hash=g1_dec_hash,
                characterization_suite_hash=char_suite_hash,
                characterization_coverage_hash=char_cov_hash,
                schema_data_plan_hash=schema_hash,
                planner_version="v4.5",
            )
            return plan
        except Exception as exc:
            logger.exception("aggregate_plan failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
            raise

    aggregate_plans = aggregate_plan


plan_aggregator = PlanAggregator()
