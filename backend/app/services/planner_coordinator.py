"""Planner Coordinator: Orchestrates parallel module planners, aggregates plans, and persists ConversionPlan."""

import asyncio
from decimal import Decimal
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.job import Job
from app.core.errors import ConflictException, NotFoundException
from app.models.artifact import Artifact, normalize_artifact_type
from app.models.job import Job
from app.models.phase4 import (
    ConversionPlanDependencyModel,
    ConversionPlanModel,
    ConversionPlanModuleModel,
    ConversionPlanTaskModel,
    FeasibilityDecisionModel,
    FeasibilityReportModel,
    PlannerOutputModel,
    PlannerRunModel,
    RepositorySnapshotModel,
    TargetBlueprintModel,
)
from app.models.user import User
from app.models.workflow import WorkflowGate
from app.schemas.phase4 import (
    ConversionPlan,
    G1DecisionRecord,
    G1DecisionType,
    LegacyModel,
    ModulePlanningUnit,
    PlanningContext,
    PlanningTask,
    TargetBlueprint,
)
from app.services.artifact_service import ArtifactService
from app.services.module_planner import ModulePlanner
from app.services.plan_aggregator import plan_aggregator

logger = logging.getLogger(__name__)


class PlannerCoordinator:
    """Coordinates parallel module-level planners, detects scope gaps, and coordinates aggregation."""

    def __init__(self, artifact_service: Optional[ArtifactService] = None):
        try:
            self.artifact_service = artifact_service or ArtifactService()
        except Exception as exc:
            logger.exception("PlannerCoordinator init failed | %s: %s", type(exc).__name__, exc)
            raise

    def coordinate_planning(
        self,
        job_id: str,
        blueprint: TargetBlueprint,
        legacy_model: LegacyModel,
        version: int = 1,
        context: Optional[PlanningContext] = None,
    ) -> ConversionPlan:
        """Synchronously coordinates planning for all components in blueprint and legacy model incorporating full context."""
        try:
            # Section 21: Check for unresolved feasibility gaps without G1 decisions
            if context and context.feasibility_report:
                report = context.feasibility_report
                gap_capabilities = [
                    c for c in report.capabilities
                    if str(getattr(c, "classification", "")).upper() in ("UNSUPPORTED", "SUBSTITUTE", "CUSTOM_BUILD", "UNKNOWN")
                    or (hasattr(getattr(c, "classification", None), "value") and c.classification.value in ("UNSUPPORTED", "SUBSTITUTE", "CUSTOM_BUILD", "UNKNOWN"))
                ]
                if gap_capabilities:
                    decided_caps = {d.capability_id for d in context.g1_decisions if d.capability_id}
                    has_general_decision = any(not d.capability_id for d in context.g1_decisions)
                    for cap in gap_capabilities:
                        if not has_general_decision and cap.capability_id not in decided_caps:
                            cap_id = getattr(cap, "capability_id", "unknown")
                            raise ConflictException(f"Planner blocked: unresolved feasibility gap for capability '{cap_id}' without G1 decision.")

            components = blueprint.components or []
            planning_units: List[ModulePlanningUnit] = []
            for comp in components:
                planner = ModulePlanner(module_id=comp.component_id, component=comp, context=context)
                unit = planner.plan_module(blueprint=blueprint, legacy_model=legacy_model)
                if unit is not None:
                    planning_units.append(unit)

            if not planning_units and legacy_model.modules:
                for mod in legacy_model.modules:
                    planner = ModulePlanner(module_id=mod.module_id, context=context)
                    unit = planner.plan_module(blueprint=blueprint, legacy_model=legacy_model, legacy_module=mod)
                    if unit is not None:
                        planning_units.append(unit)

            # Section 17: Schema / Data constraint module injection
            if context and context.schema_data_plan:
                schema_plan = context.schema_data_plan
                tables = schema_plan.get("tables", []) or schema_plan.get("table_mappings", [])
                if tables and not any(u.module_id == "mod_db_migration" for u in planning_units):
                    db_task = PlanningTask(
                        task_id="task_db_migration_001",
                        module_id="mod_db_migration",
                        title="Execute Schema & Data Migrations",
                        description=f"Apply DDL transformations, schema constraints, and verification queries for {len(tables)} tables.",
                        estimate_hours=3.0,
                        risk="MEDIUM",
                        acceptance_criteria=[
                            "Target database schema applied cleanly with all constraints and indices",
                            "Rollback script tested and verified in disposable target environment",
                            "Data migration validation queries return 100% parity",
                        ],
                        dependencies=[],
                    )
                    for u in planning_units:
                        if "mod_db_migration" not in u.dependencies:
                            u.dependencies.append("mod_db_migration")

                    db_unit = ModulePlanningUnit(
                        module_id="mod_db_migration",
                        responsibility="Database schema migration, constraint application, and data verification",
                        source_scope=["db/schema.sql"],
                        target_scope=["migrations/001_initial.sql"],
                        dependencies=[],
                        interfaces=["migration_runner"],
                        migration_steps=["Run DDL migration", "Validate constraints", "Run rollback test"],
                        implementation_tasks=[db_task],
                        required_tests=["test_schema_migration_ddl", "test_schema_migration_rollback"],
                        acceptance_criteria=["Target database schema applied cleanly with all constraints and indices"],
                        estimate_hours=3.0,
                        risk="MEDIUM",
                        required_tools=["schema_migrator", "postgres_validator"],
                        environment_requirements=["Isolated Container Sandbox", "Target Runtime"],
                        data_considerations="Core database migration on which all application modules depend.",
                    )
                    planning_units.insert(0, db_unit)

            return plan_aggregator.aggregate_plan(
                job_id=job_id,
                blueprint_version=blueprint.version,
                planning_units=planning_units,
                version=version,
                context=context,
            )
        except Exception as exc:
            logger.exception("coordinate_planning failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
            raise

    async def run_single_module_planner(
        self,
        module_id: str,
        blueprint: TargetBlueprint,
        legacy_model: LegacyModel,
        context: Optional[PlanningContext] = None,
    ) -> Optional[ModulePlanningUnit]:
        """Run a single module planner in thread pool for parallel execution."""
        try:
            comp = next(
                (c for c in blueprint.components if c.component_id == f"comp_{module_id.replace('mod_', '')}"),
                blueprint.components[0] if blueprint.components else None,
            )
            planner = ModulePlanner(module_id=module_id, component=comp, context=context)
            loop = asyncio.get_running_loop()
            unit = await loop.run_in_executor(None, planner.plan_module, blueprint, legacy_model)
            return unit
        except Exception as exc:
            logger.exception("run_single_module_planner failed | module=%s | %s: %s", module_id, type(exc).__name__, exc)
            raise

    async def execute_planning(
        self,
        db: AsyncSession,
        job: Job,
        blueprint: TargetBlueprint,
        legacy_model: LegacyModel,
        user: Optional[User] = None,
        correlation_id: Optional[str] = None,
        context: Optional[PlanningContext] = None,
    ) -> ConversionPlan:
        """Runs parallel feature planners, aggregates plan, persists database records, and publishes artifact."""
        try:
            job_id_str = str(job.job_id)

            # Build PlanningContext if not explicitly provided
            if context is None:
                # Planning is a post-G2 operation. Require the human-approved
                # inputs and never manufacture hash-only stand-ins on read errors.
                for gate_type in ("G1", "G2"):
                    approved = await db.scalar(
                        select(WorkflowGate).where(
                            WorkflowGate.job_id == job.job_id,
                            WorkflowGate.gate_type == gate_type,
                            WorkflowGate.status == "APPROVED",
                        ).order_by(WorkflowGate.version.desc()).limit(1)
                    )
                    if approved is None:
                        raise ConflictException(f"Planner requires an approved {gate_type} snapshot")
                feas_model = (
                    await db.execute(
                        select(FeasibilityReportModel)
                        .options(selectinload(FeasibilityReportModel.capabilities))
                        .where(FeasibilityReportModel.job_id == job.job_id)
                        .order_by(FeasibilityReportModel.version.desc())
                    )
                ).scalars().first()
                if feas_model is None:
                    raise ConflictException("Planner requires a persisted FeasibilityReport")
                feas_report_obj = None
                if feas_model:
                    try:
                        from app.schemas.phase4 import FeasibilityCapability, FeasibilityReport, ToolReadiness
                        caps = []
                        for c in (feas_model.capabilities or []):
                            caps.append(
                                FeasibilityCapability(
                                    capability_id=c.capability_id,
                                    category=c.category,
                                    legacy_requirement=c.legacy_requirement,
                                    target_requirement=c.target_requirement,
                                    classification=c.classification,
                                    confidence=c.confidence,
                                    evidence=c.evidence or [],
                                    tool_dependency=c.tool_dependency,
                                    effort=c.effort or "MEDIUM",
                                    risk=c.risk or "MEDIUM",
                                    verification_impact=c.verification_impact,
                                    recommendation=c.recommendation,
                                )
                            )
                        feas_report_obj = FeasibilityReport(
                            report_id=str(feas_model.report_id),
                            job_id=job_id_str,
                            version=feas_model.version,
                            blueprint_version=feas_model.blueprint_version,
                            legacy_model_version=feas_model.legacy_model_version,
                            capabilities=caps,
                            tool_readiness=[],
                            overall_feasibility_score=(
                                float(feas_model.overall_score) / 100.0
                                if float(feas_model.overall_score) > 1.0
                                else float(feas_model.overall_score)
                            ),
                            unsupported_count=feas_model.unsupported_count,
                            custom_build_count=feas_model.custom_build_count,
                            substitute_count=feas_model.substitute_count,
                            unknown_count=feas_model.unknown_count,
                            summary=feas_model.summary or "",
                            content_hash=feas_model.content_hash,
                        )
                    except Exception as e:
                        logger.warning("Could not reconstruct FeasibilityReport from model: %s", e)

                decisions_db = (
                    await db.execute(
                        select(FeasibilityDecisionModel)
                        .where(FeasibilityDecisionModel.job_id == job.job_id)
                        .order_by(FeasibilityDecisionModel.created_at.asc())
                    )
                ).scalars().all()
                g1_decisions = [
                    G1DecisionRecord(
                        decision_id=str(d.decision_id),
                        job_id=job_id_str,
                        capability_id=d.capability_id,
                        decision=d.decision,
                        reason=d.reason,
                        actor=d.actor,
                        previous_feasibility_version=d.previous_feasibility_version,
                        resulting_blueprint_version=d.resulting_blueprint_version,
                    ) for d in decisions_db
                ]
                g1_gate = (
                    await db.execute(
                        select(WorkflowGate).where(
                            WorkflowGate.job_id == job.job_id,
                            WorkflowGate.gate_type == "G1",
                            WorkflowGate.status == "APPROVED",
                        )
                    )
                ).scalars().first()
                if g1_gate and not any(not d.capability_id for d in g1_decisions):
                    g1_decisions.append(
                        G1DecisionRecord(
                            decision_id=str(g1_gate.gate_id),
                            job_id=job_id_str,
                            capability_id=None,
                            decision=G1DecisionType.ACCEPT_SUBSTITUTE,
                            reason="Gate G1 approved: blueprint and feasibility accepted",
                            actor="REVIEWER",
                            previous_feasibility_version=feas_model.version if feas_model else 1,
                            resulting_blueprint_version=blueprint.version,
                        )
                    )

                artifacts = list((await db.execute(
                    select(Artifact).where(Artifact.job_id == job.job_id)
                    .order_by(Artifact.version.desc())
                )).scalars().all())
                normalized_artifacts = []
                for artifact in artifacts:
                    try:
                        normalized_artifacts.append((normalize_artifact_type(artifact.artifact_type), artifact))
                    except Exception as exc:
                        raise ConflictException(f"Planner encountered unknown artifact type {artifact.artifact_type!r}") from exc
                char_art = next((a for kind, a in normalized_artifacts if kind == "CHARACTERIZATION_SUITE"), None)
                char_suite = None
                char_coverage = None
                if char_art is None:
                    raise ConflictException("Planner requires the G2-frozen CharacterizationSuite artifact")
                content_bytes = await self.artifact_service.storage.get_object(char_art.storage_path)
                char_suite = json.loads(content_bytes.decode("utf-8"))
                if not isinstance(char_suite, dict):
                    raise ConflictException("Frozen CharacterizationSuite payload must be an object")
                char_suite["content_hash"] = char_art.content_hash
                char_coverage = char_suite.get("coverage") or char_suite.get("coverage_report")

                schema_art = next((a for kind, a in normalized_artifacts if kind == "SCHEMA_MIGRATION_PLAN"), None)
                if schema_art is None:
                    raise ConflictException("Planner requires a validated SchemaPlan artifact")
                content_bytes = await self.artifact_service.storage.get_object(schema_art.storage_path)
                schema_plan = json.loads(content_bytes.decode("utf-8"))
                if not isinstance(schema_plan, dict):
                    raise ConflictException("SchemaPlan payload must be an object")
                schema_state = str(schema_plan.get("status") or schema_plan.get("validation_status") or "").upper()
                if schema_state not in {"VALIDATED", "APPROVED", "COMPLETE", "VALID"}:
                    raise ConflictException("Planner requires a validated SchemaPlan")
                schema_plan["schema_hash"] = schema_art.content_hash
                schema_plan["content_hash"] = schema_art.content_hash
                g2_snapshot = await db.scalar(
                    select(WorkflowGate).where(
                        WorkflowGate.job_id == job.job_id,
                        WorkflowGate.gate_type == "G2",
                        WorkflowGate.status == "APPROVED",
                    ).order_by(WorkflowGate.version.desc()).limit(1)
                )
                approved_g2_hashes = set((g2_snapshot.artifact_hashes or {}).values()) if g2_snapshot else set()
                if char_art.content_hash not in approved_g2_hashes or schema_art.content_hash not in approved_g2_hashes:
                    raise ConflictException("G2 approval does not bind the exact frozen suite and validated schema hashes")

                snap_record = (
                    await db.execute(
                        select(RepositorySnapshotModel)
                        .where(RepositorySnapshotModel.job_id == job.job_id)
                        .order_by(RepositorySnapshotModel.version.desc())
                    )
                ).scalars().first()
                repo_inv_hash = snap_record.inventory_hash if snap_record else None
                stack_profile = getattr(job, "stack_profile", None) or (snap_record.tech_profile if snap_record else None)
                baseline_source_sha = snap_record.commit_sha if snap_record else getattr(job, "source_commit_sha", None)
                if not stack_profile or not baseline_source_sha:
                    raise ConflictException("Planner requires a stack profile and pinned baseline source SHA")

                prov_hashes = {}
                if repo_inv_hash:
                    prov_hashes["repo_inventory_hash"] = repo_inv_hash
                if char_art:
                    prov_hashes["characterization_suite_hash"] = char_art.content_hash
                if schema_art:
                    prov_hashes["schema_data_plan_hash"] = schema_art.content_hash
                if feas_model:
                    prov_hashes["feasibility_report_hash"] = feas_model.content_hash
                for gate_type in ("G1", "G2"):
                    gate = await db.scalar(
                        select(WorkflowGate).where(
                            WorkflowGate.job_id == job.job_id,
                            WorkflowGate.gate_type == gate_type,
                            WorkflowGate.status == "APPROVED",
                        ).order_by(WorkflowGate.version.desc()).limit(1)
                    )
                    if gate:
                        encoded = json.dumps({"gate_id": str(gate.gate_id), "version": gate.version, "artifact_hashes": gate.artifact_hashes or {}}, sort_keys=True, separators=(",", ":"))
                        prov_hashes[f"{gate_type.lower()}_approval_hash"] = hashlib.sha256(encoded.encode()).hexdigest()
                decisions_encoded = json.dumps(
                    [d.model_dump(mode="json") for d in g1_decisions],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                prov_hashes["g1_decision_hash"] = hashlib.sha256(decisions_encoded.encode()).hexdigest()

                context = PlanningContext(
                    job_id=job_id_str,
                    legacy_model=legacy_model,
                    target_blueprint=blueprint,
                    feasibility_report=feas_report_obj,
                    g1_decisions=g1_decisions,
                    characterization_suite=char_suite,
                    characterization_coverage=char_coverage,
                    schema_data_plan=schema_plan,
                    provenance_hashes=prov_hashes,
                    stack_profile=stack_profile,
                    cost_ceiling_usd=getattr(job, "budget_limit_usd", None),
                    baseline_source_sha=baseline_source_sha,
                )

            # Validate every input contract even when callers provide a context
            # directly; no test, API, or alternate planner path can skip gates.
            if context is None:
                raise ConflictException("Planner input context could not be constructed")
            required_context_hashes = (
                "feasibility_report_hash",
                "characterization_suite_hash", "schema_data_plan_hash",
                "g1_approval_hash", "g2_approval_hash", "g1_decision_hash",
            )
            missing_hashes = [key for key in required_context_hashes if not context.provenance_hashes.get(key)]
            if missing_hashes:
                raise ConflictException(f"Planner input snapshot is missing hashes: {', '.join(missing_hashes)}")
            if not context.feasibility_report or not context.characterization_suite or not context.schema_data_plan:
                raise ConflictException("Planner requires feasibility, frozen characterization, and schema planning inputs")
            if not context.characterization_suite.get("content_hash"):
                raise ConflictException("Frozen CharacterizationSuite is missing its approved content hash")
            schema_state = str(context.schema_data_plan.get("status") or context.schema_data_plan.get("validation_status") or "").upper()
            if schema_state not in {"VALIDATED", "APPROVED", "COMPLETE", "VALID"} or not context.schema_data_plan.get("content_hash"):
                raise ConflictException("Planner requires a validated, hash-bound SchemaPlan")
            if not context.stack_profile or not context.baseline_source_sha or context.cost_ceiling_usd is None:
                raise ConflictException("Planner requires stack profile, cost ceiling, and pinned source SHA")

            # Check feasibility gaps: blocked if unresolved gaps without G1 decision
            if context.feasibility_report:
                report = context.feasibility_report
                gap_capabilities = [
                    c for c in report.capabilities
                    if str(getattr(c, "classification", "")).upper() in ("UNSUPPORTED", "SUBSTITUTE", "CUSTOM_BUILD", "UNKNOWN")
                    or (hasattr(getattr(c, "classification", None), "value") and c.classification.value in ("UNSUPPORTED", "SUBSTITUTE", "CUSTOM_BUILD", "UNKNOWN"))
                ]
                if gap_capabilities:
                    decided_caps = {d.capability_id for d in context.g1_decisions if d.capability_id}
                    has_general_decision = any(not d.capability_id for d in context.g1_decisions)
                    for cap in gap_capabilities:
                        if not has_general_decision and cap.capability_id not in decided_caps:
                            cap_id = getattr(cap, "capability_id", "unknown")
                            raise ConflictException(f"Planner blocked: unresolved feasibility gap for capability '{cap_id}' without G1 decision.")

            existing_plan = (
                await db.execute(
                    select(ConversionPlanModel)
                    .where(ConversionPlanModel.job_id == job.job_id)
                    .order_by(ConversionPlanModel.version.desc())
                )
            ).scalars().first()
            next_version = 1 if not existing_plan else existing_plan.version + 1

            # 1. Start Planner Run
            run_id = uuid.uuid4()
            db_run = PlannerRunModel(
                run_id=run_id,
                job_id=job.job_id,
                blueprint_version=blueprint.version,
                version=next_version,
                status="RUNNING",
            )
            db.add(db_run)
            await db.flush()

            # 2. Identify independently plannable modules
            module_ids = [m.module_id for m in legacy_model.modules]
            if not module_ids:
                module_ids = ["mod_root"]

            # 3. Parallel planning tasks with context
            tasks = [self.run_single_module_planner(mid, blueprint, legacy_model, context=context) for mid in module_ids]
            raw_units: List[Optional[ModulePlanningUnit]] = await asyncio.gather(*tasks)
            planning_units: List[ModulePlanningUnit] = [u for u in raw_units if u is not None]

            # Section 17: Schema / Data constraint module injection
            if context and context.schema_data_plan:
                schema_plan = context.schema_data_plan
                tables = schema_plan.get("tables", []) or schema_plan.get("table_mappings", [])
                if tables and not any(u.module_id == "mod_db_migration" for u in planning_units):
                    db_task = PlanningTask(
                        task_id="task_db_migration_001",
                        module_id="mod_db_migration",
                        title="Execute Schema & Data Migrations",
                        description=f"Apply DDL transformations, schema constraints, and verification queries for {len(tables)} tables.",
                        estimate_hours=3.0,
                        risk="MEDIUM",
                        acceptance_criteria=[
                            "Target database schema applied cleanly with all constraints and indices",
                            "Rollback script tested and verified in disposable target environment",
                            "Data migration validation queries return 100% parity",
                        ],
                        dependencies=[],
                    )
                    for u in planning_units:
                        if "mod_db_migration" not in u.dependencies:
                            u.dependencies.append("mod_db_migration")

                    db_unit = ModulePlanningUnit(
                        module_id="mod_db_migration",
                        responsibility="Database schema migration, constraint application, and data verification",
                        source_scope=["db/schema.sql"],
                        target_scope=["migrations/001_initial.sql"],
                        dependencies=[],
                        interfaces=["migration_runner"],
                        migration_steps=["Run DDL migration", "Validate constraints", "Run rollback test"],
                        implementation_tasks=[db_task],
                        required_tests=["test_schema_migration_ddl", "test_schema_migration_rollback"],
                        acceptance_criteria=["Target database schema applied cleanly with all constraints and indices"],
                        estimate_hours=3.0,
                        risk="MEDIUM",
                        required_tools=["schema_migrator", "postgres_validator"],
                        environment_requirements=["Isolated Container Sandbox", "Target Runtime"],
                        data_considerations="Core database migration on which all application modules depend.",
                    )
                    planning_units.insert(0, db_unit)

            # 4. Record individual planner outputs
            for unit in planning_units:
                db.add(PlannerOutputModel(
                    output_id=uuid.uuid4(),
                    run_id=run_id,
                    module_id=unit.module_id,
                    unit_payload=unit.model_dump(),
                ))

            # 5. Aggregate into canonical ConversionPlan with context
            conversion_plan = plan_aggregator.aggregate_plan(
                job_id=job_id_str,
                blueprint_version=blueprint.version,
                planning_units=planning_units,
                version=next_version,
                context=context,
            )
            if not conversion_plan.validation.is_valid_dag:
                raise ConflictException(
                    "Planner rejected an invalid DAG: "
                    + "; ".join(conversion_plan.validation.validation_messages)
                )

            # 6. Persist ConversionPlan in DB
            db_plan = ConversionPlanModel(
                plan_id=uuid.UUID(conversion_plan.plan_id.replace("plan_", "").ljust(32, "0")[:32]) if len(conversion_plan.plan_id) == 37 else uuid.uuid4(),
                job_id=job.job_id,
                version=next_version,
                blueprint_version=blueprint.version,
                validation_status="VALID" if conversion_plan.validation.is_valid_dag else "INVALID",
                is_valid_dag=conversion_plan.validation.is_valid_dag,
                total_estimate_hours=conversion_plan.total_estimate_hours,
                risk_summary_payload=conversion_plan.risk_summary,
                validation_payload=conversion_plan.validation.model_dump(),
                content_hash=conversion_plan.content_hash,
            )
            db.add(db_plan)
            await db.flush()

            # Persist the exact immutable artifact before assigning module
            # contracts so task plan_hash is the hash G3 will approve.
            plan_bytes = json.dumps(conversion_plan.model_dump(mode="json"), indent=2).encode("utf-8")
            plan_artifact = await self.artifact_service.create_artifact(
                db=db,
                job_id=job.job_id,
                artifact_type="CONVERSION_PLAN",
                version=next_version,
                content_bytes=plan_bytes,
                producing_agent="PlannerCoordinator",
                derived_from=[blueprint.content_hash],
                user=user,
                correlation_id=correlation_id,
                commit=False,
            )

            wave_by_module = {}
            for wave in conversion_plan.waves:
                for mid in wave.module_ids:
                    wave_by_module[mid] = wave.wave_number

            for unit in conversion_plan.modules:
                db.add(ConversionPlanModuleModel(
                    module_record_id=uuid.uuid4(),
                    plan_id=db_plan.plan_id,
                    module_id=unit.module_id,
                    responsibility=unit.responsibility,
                    wave_number=wave_by_module.get(unit.module_id, 1),
                    estimate_hours=unit.estimate_hours,
                    risk=unit.risk,
                    acceptance_criteria=unit.acceptance_criteria,
                    payload=unit.model_dump(),
                ))

            from app.models.module import Module, ModuleDependency
            from sqlalchemy import delete
            # Clean up existing module dependencies for this job before re-inserting
            await db.execute(delete(ModuleDependency).where(ModuleDependency.job_id == job.job_id))

            for unit in conversion_plan.modules:
                m_uuid = uuid.uuid5(job.job_id, unit.module_id)
                dep_uuids = [str(uuid.uuid5(job.job_id, d)) for d in dict.fromkeys(unit.dependencies)]
                existing_m = await db.get(Module, m_uuid)
                approval_hashes = {
                    key: value
                    for key, value in (context.provenance_hashes if context else {}).items()
                    if key in ("g1_approval_hash", "g2_approval_hash")
                }
                contract_payload = {
                    "module_id": unit.module_id,
                    "plan_hash": plan_artifact.content_hash,
                    "dependencies": dep_uuids,
                    "interfaces": unit.interfaces or [],
                    "allowed_output_paths": unit.target_scope or [],
                    "required_tests": unit.required_tests or [],
                    "schema_dependencies": [unit.data_considerations] if unit.data_considerations else [],
                    "upstream_approval_hashes": approval_hashes,
                    "integration_base_sha": context.baseline_source_sha if context else None,
                }
                contract_hash = hashlib.sha256(json.dumps(contract_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
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
                        expected_input_hash=contract_hash,
                        plan_hash=plan_artifact.content_hash,
                        upstream_approval_hashes=approval_hashes,
                        integration_base_sha=context.baseline_source_sha if context else None,
                        budget_limit_usd=Decimal("50.0"),
                        budget_used_usd=Decimal("0.0"),
                    ))
                else:
                    # Replanning contract change detection
                    contract_changed = (
                        existing_m.target_path != (unit.target_scope[0] if unit.target_scope else "")
                        or existing_m.interfaces != (unit.interfaces or [])
                        or existing_m.dependency_module_ids != dep_uuids
                        or existing_m.plan_hash != plan_artifact.content_hash
                        or existing_m.upstream_approval_hashes != approval_hashes
                        or existing_m.integration_base_sha != (context.baseline_source_sha if context else None)
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
                        existing_m.plan_hash = plan_artifact.content_hash
                        existing_m.upstream_approval_hashes = approval_hashes
                        existing_m.integration_base_sha = context.baseline_source_sha if context else None
                        existing_m.expected_input_hash = contract_hash
                        existing_m.status = "PENDING"
                        existing_m.accepted_result_hash = None
                        existing_m.lease_owner = None
                        existing_m.lease_token = None
                        existing_m.lease_expires_at = None
                        existing_m.lease_heartbeat_at = None
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
                        ))

            for task in conversion_plan.tasks:
                db.add(ConversionPlanTaskModel(
                    task_record_id=uuid.uuid4(),
                    plan_id=db_plan.plan_id,
                    task_id=task.task_id,
                    module_id=task.module_id,
                    title=task.title,
                    estimate_hours=task.estimate_hours,
                    risk=task.risk,
                    acceptance_criteria=task.acceptance_criteria,
                    dependencies=task.dependencies,
                    payload=task.model_dump(),
                ))

            for dep in conversion_plan.dependencies:
                db.add(ConversionPlanDependencyModel(
                    dependency_id=uuid.uuid4(),
                    plan_id=db_plan.plan_id,
                    source=dep.source,
                    target=dep.target,
                    dependency_type=dep.dependency_type,
                    confidence=dep.confidence.value,
                ))

            db_run.status = "COMPLETED"
            db_run.completed_at = conversion_plan.created_at

            await db.commit()
            return conversion_plan
        except Exception as exc:
            logger.exception("execute_planning failed | job_id=%s | %s: %s", getattr(job, "job_id", "unknown"), type(exc).__name__, exc)
            raise


planner_coordinator = PlannerCoordinator()
