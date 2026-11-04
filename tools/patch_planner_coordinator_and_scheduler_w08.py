"""Update PlannerCoordinator and DependencyScheduler for W08."""

from pathlib import Path

PC_PATH = Path("backend/app/services/planner_coordinator.py")
DS_PATH = Path("backend/app/services/dependency_scheduler.py")

# ==============================================================================
# 1. Update PlannerCoordinator
# ==============================================================================
pc_content = PC_PATH.read_text(encoding="utf-8")

# In PlanningContext creation (lines 348-358)
old_pc_ctx = """                context = PlanningContext(
                    job_id=job_id_str,
                    legacy_model=legacy_model,
                    target_blueprint=blueprint,
                    feasibility_report=feas_report_obj,
                    g1_decisions=g1_decisions,
                    characterization_suite=char_suite,
                    characterization_coverage=char_coverage,
                    schema_data_plan=schema_plan,
                    provenance_hashes=prov_hashes,
                )"""

new_pc_ctx = """                context = PlanningContext(
                    job_id=job_id_str,
                    legacy_model=legacy_model,
                    target_blueprint=blueprint,
                    feasibility_report=feas_report_obj,
                    g1_decisions=g1_decisions,
                    characterization_suite=char_suite,
                    characterization_coverage=char_coverage,
                    schema_data_plan=schema_plan,
                    provenance_hashes=prov_hashes,
                    stack_profile=getattr(job, "stack_profile", None) or (snap_record.tech_profile if snap_record else None),
                    cost_ceiling_usd=getattr(job, "budget_limit_usd", None),
                    baseline_source_sha=snap_record.commit_sha if snap_record else getattr(job, "source_commit_sha", None),
                )"""

assert old_pc_ctx in pc_content, "old_pc_ctx not found in planner_coordinator.py"
pc_content = pc_content.replace(old_pc_ctx, new_pc_ctx, 1)

# In Module persistence and ModuleDependency persistence (lines 496-519)
old_pc_mod = """            from app.models.module import Module
            wave_by_module = {}
            for wave in conversion_plan.waves:
                for mid in wave.module_ids:
                    if mid not in wave_by_module:
                        wave_by_module[mid] = wave.wave_number
            for unit in conversion_plan.modules:
                m_uuid = uuid.uuid5(job.job_id, unit.module_id)
                existing_m = await db.get(Module, m_uuid)
                if not existing_m:
                    db.add(Module(
                        module_id=m_uuid,
                        job_id=job.job_id,
                        name=unit.module_id,
                        legacy_path=unit.source_scope[0] if unit.source_scope else "",
                        target_path=unit.target_scope[0] if unit.target_scope else "",
                        risk_level=unit.risk if unit.risk in ("LOW", "MEDIUM", "HIGH") else "MEDIUM",
                        status="PENDING",
                        wave_number=wave_by_module.get(unit.module_id, 1),
                        dependency_module_ids=[str(uuid.uuid5(job.job_id, d)) for d in unit.dependencies],
                        budget_limit_usd=Decimal("50.0"),
                        budget_used_usd=Decimal("0.0"),
                    ))"""

new_pc_mod = """            from app.models.module import Module, ModuleDependency
            from sqlalchemy import delete
            wave_by_module = {}
            for wave in conversion_plan.waves:
                for mid in wave.module_ids:
                    if mid not in wave_by_module:
                        wave_by_module[mid] = wave.wave_number

            # Clean up existing module dependencies for this job before re-inserting
            await db.execute(delete(ModuleDependency).where(ModuleDependency.job_id == job.job_id))

            for unit in conversion_plan.modules:
                m_uuid = uuid.uuid5(job.job_id, unit.module_id)
                dep_uuids = [str(uuid.uuid5(job.job_id, d)) for d in dict.fromkeys(unit.dependencies)]
                existing_m = await db.get(Module, m_uuid)
                if not existing_m:
                    db.add(Module(
                        module_id=m_uuid,
                        job_id=job.job_id,
                        name=unit.module_id,
                        legacy_path=unit.source_scope[0] if unit.source_scope else "",
                        target_path=unit.target_scope[0] if unit.target_scope else "",
                        risk_level=unit.risk if unit.risk in ("LOW", "MEDIUM", "HIGH") else "MEDIUM",
                        status="PENDING",
                        wave_number=wave_by_module.get(unit.module_id, 1),
                        dependency_module_ids=dep_uuids,
                        interfaces=unit.interfaces or [],
                        allowed_output_paths=unit.target_scope or [],
                        required_tests=unit.required_tests or [],
                        schema_dependencies=[unit.data_considerations] if unit.data_considerations else [],
                        expected_resources={"required_tools": unit.required_tools, "environment_requirements": unit.environment_requirements},
                        budget_limit_usd=Decimal("50.0"),
                        budget_used_usd=Decimal("0.0"),
                    ))
                else:
                    # Replanning contract change detection
                    contract_changed = (
                        existing_m.target_path != (unit.target_scope[0] if unit.target_scope else "")
                        or existing_m.interfaces != (unit.interfaces or [])
                        or existing_m.dependency_module_ids != dep_uuids
                    )
                    if contract_changed:
                        existing_m.target_path = unit.target_scope[0] if unit.target_scope else ""
                        existing_m.interfaces = unit.interfaces or []
                        existing_m.dependency_module_ids = dep_uuids
                        existing_m.allowed_output_paths = unit.target_scope or []
                        existing_m.required_tests = unit.required_tests or []
                        existing_m.schema_dependencies = [unit.data_considerations] if unit.data_considerations else []
                        existing_m.expected_resources = {"required_tools": unit.required_tools, "environment_requirements": unit.environment_requirements}
                        existing_m.wave_number = wave_by_module.get(unit.module_id, 1)
                        if existing_m.status in ("LEASED", "RUNNING", "COMPLETED"):
                            existing_m.status = "PENDING"
                            existing_m.lease_owner = None
                            existing_m.lease_expires_at = None
                            existing_m.lease_generation += 1

            await db.flush()

            # Insert normalized module_dependencies
            for unit in conversion_plan.modules:
                child_uuid = uuid.uuid5(job.job_id, unit.module_id)
                for dep_name in dict.fromkeys(unit.dependencies):
                    parent_uuid = uuid.uuid5(job.job_id, dep_name)
                    parent_mod = await db.get(Module, parent_uuid)
                    if parent_mod:
                        db.add(ModuleDependency(
                            dependency_id=uuid.uuid4(),
                            job_id=job.job_id,
                            parent_id=parent_uuid,
                            child_id=child_uuid,
                        ))"""

assert old_pc_mod in pc_content, "old_pc_mod not found in planner_coordinator.py"
pc_content = pc_content.replace(old_pc_mod, new_pc_mod, 1)

# Remove duplicate ConversionPlan artifact publishing (lines 560-571)
old_dup_art = """            # Maintain backward compatibility for legacy queries expecting "ConversionPlan"
            await self.artifact_service.create_artifact(
                db=db,
                job_id=job.job_id,
                artifact_type="ConversionPlan",
                version=next_version,
                content_bytes=plan_bytes,
                producing_agent="PlannerCoordinator",
                derived_from=[blueprint.content_hash],
                user=user,
                correlation_id=correlation_id,
            )"""

assert old_dup_art in pc_content, "old_dup_art not found in planner_coordinator.py"
pc_content = pc_content.replace(old_dup_art, "", 1)

PC_PATH.write_text(pc_content, encoding="utf-8")
print("Successfully patched planner_coordinator.py")

# ==============================================================================
# 2. Update DependencyScheduler
# ==============================================================================
ds_content = DS_PATH.read_text(encoding="utf-8")

# Replace job lock with standard select to avoid job-global conversion mutex
old_ds_job = "job = await db.scalar(select(Job).where(Job.job_id == job_id).with_for_update())"
new_ds_job = "job = await db.scalar(select(Job).where(Job.job_id == job_id))"
assert old_ds_job in ds_content, "old_ds_job not found in dependency_scheduler.py"
ds_content = ds_content.replace(old_ds_job, new_ds_job, 1)

# Replace completed_ids and dependency check to require VERIFIED and consult module_dependencies
old_ds_deps = """        completed_ids = set((await db.execute(
            select(Module.module_id).where(Module.job_id == job_id, Module.status.in_(("VERIFIED", "COMPLETED")))
        )).scalars().all())
        claimed: list[Module] = []
        for module in candidates:
            dependencies = {UUID(value) for value in (module.dependency_module_ids or [])}
            if not dependencies.issubset(completed_ids):
                continue"""

new_ds_deps = """        completed_ids = set((await db.execute(
            select(Module.module_id).where(Module.job_id == job_id, Module.status == "VERIFIED")
        )).scalars().all())
        claimed: list[Module] = []
        from app.models.module import ModuleDependency
        for module in candidates:
            # Check normalized module_dependencies junction table first
            parent_ids = set((await db.execute(
                select(ModuleDependency.parent_id).where(ModuleDependency.child_id == module.module_id)
            )).scalars().all())
            if not parent_ids:
                # Fallback to materialized JSON array if module_dependencies empty
                parent_ids = {UUID(value) for value in (module.dependency_module_ids or [])}
            if not parent_ids.issubset(completed_ids):
                continue"""

assert old_ds_deps in ds_content, "old_ds_deps not found in dependency_scheduler.py"
ds_content = ds_content.replace(old_ds_deps, new_ds_deps, 1)

DS_PATH.write_text(ds_content, encoding="utf-8")
print("Successfully patched dependency_scheduler.py")

