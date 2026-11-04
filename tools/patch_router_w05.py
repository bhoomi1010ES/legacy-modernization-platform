
with open("backend/app/services/supervisor_router.py", "r", encoding="utf-8") as f:
    c = f.read()

old_block = """            if ready_modules:
                target_mod = ready_modules[0]
                action = SupervisorAction.REPAIR if target_mod.retry_count > 0 else SupervisorAction.EXECUTE
                return SupervisorDecision(
                    action=action,
                    task_id=f"convert-{target_mod.module_id}",
                    agent_id="CodeWriter",
                    target_status=JobStatus.CONVERTING.value,
                    reason=f"Module {target_mod.name} is ready for conversion (Wave {target_mod.wave_number}).",
                    budget_state=b_res.state,
                    dependency_state={"module_id": str(target_mod.module_id), "wave": target_mod.wave_number, "dependencies_satisfied": True},
                    metadata={"module_id": str(target_mod.module_id), "module_name": target_mod.name},
                )"""

new_block = """            if ready_modules:
                target_mod = ready_modules[0]
                action = SupervisorAction.REPAIR if target_mod.retry_count > 0 else SupervisorAction.EXECUTE
                ready_module_ids = [str(m.module_id) for m in ready_modules]
                parallel_cap = min(
                    len(ready_modules),
                    getattr(job, "max_parallel_tasks", 4) or 4,
                    getattr(job, "provider_concurrency_limit", 4) or 4,
                )
                return SupervisorDecision(
                    action=action,
                    task_id=f"convert-{target_mod.module_id}",
                    agent_id="CodeWriter",
                    target_status=JobStatus.CONVERTING.value,
                    reason=f"Module {target_mod.name} is ready for conversion (Wave {target_mod.wave_number}); {len(ready_modules)} total ready modules discovered for parallel dispatch.",
                    budget_state=b_res.state,
                    dependency_state={
                        "module_id": str(target_mod.module_id),
                        "wave": target_mod.wave_number,
                        "dependencies_satisfied": True,
                        "ready_count": len(ready_modules),
                    },
                    metadata={
                        "module_id": str(target_mod.module_id),
                        "module_name": target_mod.name,
                        "ready_modules": [
                            {"module_id": str(m.module_id), "name": m.name, "wave": m.wave_number}
                            for m in ready_modules
                        ],
                        "ready_module_ids": ready_module_ids,
                        "ready_count": len(ready_modules),
                        "parallel_capacity": parallel_cap,
                        "parallel_fanout_eligible": len(ready_modules) > 1,
                    },
                )"""

c_norm = c.replace("\r\n", "\n")
old_norm = old_block.replace("\r\n", "\n")
new_norm = new_block.replace("\r\n", "\n")

assert old_norm in c_norm, "old_block not found in supervisor_router.py"
c_norm = c_norm.replace(old_norm, new_norm, 1)

parallel_method = """
    async def evaluate_parallel_actions(
        self, db: AsyncSession, job: Job, max_tasks: Optional[int] = None
    ) -> List[SupervisorDecision]:
        \"\"\"Discovers and returns parallel task decisions for all ready modules within concurrency capacity.\"\"\"
        now = utc_now()
        modules_res = await db.execute(
            select(Module)
            .where(Module.job_id == job.job_id)
            .order_by(Module.wave_number.asc(), Module.created_at.asc())
        )
        modules = list(modules_res.scalars().all())
        verified_ids = {m.module_id for m in modules if m.status == "VERIFIED"}
        completed_ids = {m.module_id for m in modules if m.status == "COMPLETED"}
        active_modules = [
            m for m in modules
            if m.status in ("LEASED", "RUNNING")
            and (m.lease_expires_at is None or m.lease_expires_at > now)
        ]

        max_allowed = min(
            getattr(job, "max_parallel_tasks", 4) or 4,
            getattr(job, "provider_concurrency_limit", 4) or 4,
            getattr(job, "sandbox_concurrency_limit", 4) or 4,
        )
        if max_tasks is not None:
            max_allowed = min(max_allowed, max_tasks)
        capacity = max(0, max_allowed - len(active_modules))
        if capacity <= 0:
            return []

        ready_modules: List[Module] = []
        for m in modules:
            if m.status == "PENDING":
                deps = set(m.dependency_module_ids or [])
                if deps.issubset(verified_ids | completed_ids):
                    ready_modules.append(m)

        decisions: List[SupervisorDecision] = []
        for m in ready_modules[:capacity]:
            action = SupervisorAction.REPAIR if m.retry_count > 0 else SupervisorAction.EXECUTE
            decisions.append(
                SupervisorDecision(
                    action=action,
                    task_id=f"convert-{m.module_id}",
                    agent_id="CodeWriter",
                    target_status=JobStatus.CONVERTING.value,
                    reason=f"Module {m.name} ready for parallel conversion (Wave {m.wave_number}).",
                    metadata={
                        "module_id": str(m.module_id),
                        "module_name": m.name,
                        "wave_number": m.wave_number,
                    },
                )
            )
        return decisions
"""

assert "supervisor_router = SupervisorRouter()" in c_norm, "supervisor_router instantiation not found"
c_norm = c_norm.replace("supervisor_router = SupervisorRouter()", parallel_method + "\nsupervisor_router = SupervisorRouter()", 1)

with open("backend/app/services/supervisor_router.py", "w", encoding="utf-8") as f:
    f.write(c_norm)

print("Updated supervisor_router.py successfully")
