"""Update PlanAggregator in backend/app/services/plan_aggregator.py for W08."""

from pathlib import Path

FILE_PATH = Path("backend/app/services/plan_aggregator.py")
content = FILE_PATH.read_text(encoding="utf-8")

new_validate_dag = """    def validate_dag(
        self,
        tasks: List[PlanningTask],
        modules: List[ModulePlanningUnit],
        dependencies: List[DependencyEdge],
    ) -> ConversionPlanValidation:
        \"\"\"Enforces all DAG invariants: cycle detection, missing dependencies, duplicate IDs, acceptance criteria.\"\"\"
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

            # 3. Task cycle detection using Kahn's algorithm
            task_adj: Dict[str, List[str]] = defaultdict(list)
            task_in_degree: Dict[str, int] = {t.task_id: 0 for t in tasks}

            for t in tasks:
                for dep in t.dependencies:
                    task_adj[dep].append(t.task_id)
                    task_in_degree[t.task_id] += 1

            queue = deque([tid for tid, deg in task_in_degree.items() if deg == 0])
            task_visited_count = 0
            cycles: List[List[str]] = []

            while queue:
                curr = queue.popleft()
                task_visited_count += 1
                for nxt in task_adj[curr]:
                    task_in_degree[nxt] -= 1
                    if task_in_degree[nxt] == 0:
                        queue.append(nxt)

            has_task_cycles = task_visited_count < len(tasks) if tasks else False
            if has_task_cycles:
                cycle_nodes = [tid for tid, deg in task_in_degree.items() if deg > 0]
                cycles.append(cycle_nodes)
                messages.append(f"Dependency cycle detected among tasks: {cycle_nodes}")

            # 4. Module-level validation: missing dependencies, duplicate module IDs, and cycles
            module_ids: Set[str] = set()
            dup_modules: List[str] = []
            for m in modules:
                if m.module_id in module_ids:
                    dup_modules.append(m.module_id)
                module_ids.add(m.module_id)

            if dup_modules:
                duplicate_ids.extend(dup_modules)
                messages.append(f"Duplicate module IDs found: {dup_modules}")

            for m in modules:
                for dep in m.dependencies:
                    if dep not in module_ids:
                        missing_deps.append(dep)
                        messages.append(f"Module {m.module_id} depends on nonexistent module {dep}")

            # Module cycle detection
            mod_adj: Dict[str, List[str]] = defaultdict(list)
            mod_in_degree: Dict[str, int] = {m.module_id: 0 for m in modules}
            for m in modules:
                # Deduplicate dependencies
                deps = list(dict.fromkeys(m.dependencies))
                for dep in deps:
                    if dep in module_ids:
                        mod_adj[dep].append(m.module_id)
                        mod_in_degree[m.module_id] += 1

            mod_queue = deque([mid for mid, deg in mod_in_degree.items() if deg == 0])
            mod_visited = 0
            while mod_queue:
                curr_m = mod_queue.popleft()
                mod_visited += 1
                for nxt_m in mod_adj[curr_m]:
                    mod_in_degree[nxt_m] -= 1
                    if mod_in_degree[nxt_m] == 0:
                        mod_queue.append(nxt_m)

            has_module_cycles = mod_visited < len(modules) if modules else False
            if has_module_cycles:
                mod_cycle_nodes = [mid for mid, deg in mod_in_degree.items() if deg > 0]
                cycles.append(mod_cycle_nodes)
                messages.append(f"Dependency cycle detected among modules: {mod_cycle_nodes}")

            has_cycles = has_task_cycles or has_module_cycles
            is_valid = (
                not has_cycles
                and not missing_deps
                and not duplicate_ids
                and not missing_ac_tasks
            )

            if duplicate_ids and not dup_modules:
                messages.append(f"Duplicate task IDs found: {duplicate_ids}")
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
            raise"""

new_calculate_waves = """    def calculate_execution_waves(
        self,
        tasks: List[PlanningTask],
        modules: List[ModulePlanningUnit],
    ) -> List[ConversionPlanWave]:
        \"\"\"Calculates topological execution waves based on module dependency levels (and task levels).\"\"\"
        try:
            if not modules and not tasks:
                return []

            # If modules are provided, compute waves directly on the module DAG
            if modules:
                module_map = {m.module_id: m for m in modules}
                task_by_module: Dict[str, List[str]] = defaultdict(list)
                for t in tasks:
                    task_by_module[t.module_id].append(t.task_id)

                waves: List[ConversionPlanWave] = []
                completed_modules: Set[str] = set()
                remaining_modules: Dict[str, ModulePlanningUnit] = dict(module_map)
                wave_num = 1

                while remaining_modules:
                    # Find all modules whose dependencies are satisfied
                    current_wave_modules = [
                        mid
                        for mid, m in remaining_modules.items()
                        if all(dep in completed_modules for dep in dict.fromkeys(m.dependencies))
                    ]

                    if not current_wave_modules:
                        # Cycle or unresolvable dependency: drain remaining
                        current_wave_modules = sorted(list(remaining_modules.keys()))

                    current_wave_modules.sort()
                    current_wave_tasks: List[str] = []
                    for mid in current_wave_modules:
                        current_wave_tasks.extend(task_by_module.get(mid, []))
                    current_wave_tasks.sort()

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
                        task_ids=current_wave_tasks,
                        rationale=rationale,
                    ))

                    completed_modules.update(current_wave_modules)
                    for mid in current_wave_modules:
                        if mid in remaining_modules:
                            del remaining_modules[mid]

                    wave_num += 1

                return waves

            # Fallback for task-only planning
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
                current_wave_tasks = [
                    tid for tid in remaining_tasks
                    if in_degree[tid] == 0
                ]
                if not current_wave_tasks:
                    current_wave_tasks = list(remaining_tasks)

                current_wave_modules = sorted(list({task_map[tid].module_id for tid in current_wave_tasks}))
                waves.append(ConversionPlanWave(
                    wave_number=wave_num,
                    name=f"Wave {wave_num}",
                    module_ids=current_wave_modules,
                    task_ids=sorted(current_wave_tasks),
                    rationale=f"Execution wave {wave_num}.",
                ))

                for tid in current_wave_tasks:
                    remaining_tasks.remove(tid)
                    for nxt in adj[tid]:
                        in_degree[nxt] = max(0, in_degree[nxt] - 1)

                wave_num += 1

            return waves
        except Exception as exc:
            logger.exception("calculate_execution_waves failed | %s: %s", type(exc).__name__, exc)
            raise"""

# Replace in content
start_v = content.find("    def validate_dag(")
end_v = content.find("    def calculate_execution_waves(")
assert start_v != -1 and end_v != -1, "validate_dag region not found"

start_w = end_v
end_w = content.find("    def aggregate_plan(")
assert end_w != -1, "calculate_execution_waves region not found"

content = content[:start_v] + new_validate_dag + "\n\n" + new_calculate_waves + "\n\n" + content[end_w:]

FILE_PATH.write_text(content, encoding="utf-8")
print("Successfully patched plan_aggregator.py")

