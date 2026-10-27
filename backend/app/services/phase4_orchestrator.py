"""Phase 4 execution helpers. Workflow authority belongs to SupervisorService."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, NotFoundException
from app.models.job import Job
from app.models.phase4 import (
    ConversionPlanModel,
    FeasibilityReportModel,
    LegacyModelRecord,
    RepositorySnapshotModel,
    TargetBlueprintModel,
)
from app.models.user import User
from app.schemas.jobs import JobStatus
from app.schemas.phase4 import (
    AnalysisType,
    ConversionPlan,
    DetectedTechnologyProfile,
    FeasibilityReport,
    LegacyModel,
    RepositoryInventory,
    RepositorySnapshot,
    SourceMetadata,
    TargetBlueprint,
)
from app.services.analyzer_coordinator import analyzer_coordinator
from app.services.architect_agent import architect_agent
from app.services.feasibility_agent import feasibility_agent
from app.services.g3_service import g3_service
from app.services.intake_agent import intake_agent
from app.services.planner_coordinator import planner_coordinator
from app.services.supervisor_service import supervisor_service

logger = logging.getLogger(__name__)


class Phase4PipelineOrchestrator:
    """Executes phase work and returns results; never advances workflow state."""

    def __init__(self):
        pass

    async def run_pipeline_stage1_intake(
        self,
        db: AsyncSession,
        job: Job,
        user: Optional[User] = None,
        *,
        git_token: Optional[str] = None,
        preview_snapshot_id: Optional[str] = None,
        snapshot_fingerprint: Optional[str] = None,
        workspace_override: Optional[Path] = None,
        correlation_id: Optional[str] = None,
    ) -> Tuple[RepositorySnapshot, RepositoryInventory]:
        """Execute safe intake and inventory for a supervisor-owned INTAKE task."""
        try:
            if job.status != JobStatus.INTAKE.value:
                raise ConflictException("Intake helper requires a supervisor-owned INTAKE task")

            snapshot, inventory, _ = await intake_agent.execute_intake(
                db=db,
                job=job,
                user=user,
                git_token=git_token,
                preview_snapshot_id=preview_snapshot_id,
                snapshot_fingerprint=snapshot_fingerprint,
                workspace_override=workspace_override,
                correlation_id=correlation_id,
            )

            return snapshot, inventory
        except Exception as exc:
            logger.exception("run_pipeline_stage1_intake failed | job_id=%s | %s: %s", getattr(job, "job_id", "unknown"), type(exc).__name__, exc)
            raise

    async def run_pipeline_stage2_analysis_and_feasibility(
        self,
        db: AsyncSession,
        job: Job,
        user: Optional[User] = None,
        *,
        correlation_id: Optional[str] = None,
        slices_to_run: Optional[List[AnalysisType]] = None,
    ) -> Tuple[LegacyModel, TargetBlueprint, FeasibilityReport]:
        """Executes Legacy Analyzer -> Target Blueprint -> Feasibility -> Opens Gate G1."""
        try:
            job_id_str = str(job.job_id)
            if job.status != JobStatus.ANALYZING.value:
                raise ConflictException("Analysis helper requires a supervisor-owned ANALYZING task")

            # 1. Fetch latest snapshot
            snap_record = (
                await db.execute(
                    select(RepositorySnapshotModel)
                    .where(RepositorySnapshotModel.job_id == job.job_id)
                    .order_by(RepositorySnapshotModel.version.desc())
                )
            ).scalars().first()
            if not snap_record:
                raise NotFoundException("RepositorySnapshot", job_id_str)

            snapshot_obj = RepositorySnapshot(
                snapshot_id=str(snap_record.snapshot_id),
                job_id=job_id_str,
                version=snap_record.version,
                metadata=snap_record.metadata_payload,
                tech_profile=snap_record.tech_profile,
                inventory_hash=snap_record.inventory_hash,
                content_hash=snap_record.content_hash,
            )

            # Reconstruct workspace path
            backend_dir = Path(__file__).resolve().parent.parent.parent
            workspace_path = backend_dir / "repo_workspaces" / f"job_{job_id_str}"
            if not workspace_path.exists():
                workspace_path = backend_dir / "repo_workspaces" / f"job_{job_id_str}_git"
            if not workspace_path.exists() and job.source_repository and Path(job.source_repository).exists():
                workspace_path = Path(job.source_repository)

            # Build inventory
            inventory, _, _ = intake_agent.build_deterministic_inventory(workspace_path, job_id_str)

            # 2. Parallel Analyzer Workers -> Reconciled LegacyModel
            legacy_model = await analyzer_coordinator.execute_analysis(
                db=db,
                job=job,
                snapshot=snapshot_obj,
                inventory=inventory,
                workspace_path=workspace_path,
                user=user,
                correlation_id=correlation_id,
                slices_to_run=slices_to_run,
            )

            # 3. Architect Agent -> TargetBlueprint
            blueprint = await architect_agent.execute_architect(
                db=db,
                job=job,
                legacy_model=legacy_model,
                user=user,
                correlation_id=correlation_id,
            )

            # 4. Feasibility Agent -> FeasibilityReport
            report = await feasibility_agent.execute_feasibility(
                db=db,
                job=job,
                legacy_model=legacy_model,
                blueprint=blueprint,
                user=user,
                correlation_id=correlation_id,
            )

            return legacy_model, blueprint, report
        except Exception as exc:
            logger.exception("run_pipeline_stage2_analysis_and_feasibility failed | job_id=%s | %s: %s", getattr(job, "job_id", "unknown"), type(exc).__name__, exc)
            raise

    async def run_pipeline_stage3_planning(
        self,
        db: AsyncSession,
        job: Job,
        user: Optional[User] = None,
        *,
        correlation_id: Optional[str] = None,
    ) -> ConversionPlan:
        """Executes parallel module planning -> Plan Aggregator -> DAG Validation -> G3 Preparation."""
        try:
            await supervisor_service.require_planning_eligibility(db, job)
            job_id_str = str(job.job_id)
            actor = str(user.user_id) if user else "supervisor"

            # 1. Fetch latest blueprint
            bp_record = (
                await db.execute(
                    select(TargetBlueprintModel)
                    .where(TargetBlueprintModel.job_id == job.job_id)
                    .order_by(TargetBlueprintModel.version.desc())
                )
            ).scalars().first()
            if not bp_record:
                raise NotFoundException("TargetBlueprint", job_id_str)

            blueprint = TargetBlueprint(
                blueprint_id=str(bp_record.blueprint_id),
                job_id=job_id_str,
                version=bp_record.version,
                status=bp_record.status,
                target_stack=bp_record.target_stack,
                target_architecture=bp_record.target_architecture,
                components=bp_record.components_payload,
                interfaces=bp_record.interfaces_payload,
                data_model=bp_record.data_model_payload,
                integration_contracts=bp_record.integration_contracts_payload,
                deployment_constraints=bp_record.constraints_payload.get("deployment", []),
                security_constraints=bp_record.constraints_payload.get("security", []),
                compatibility_constraints=bp_record.constraints_payload.get("compatibility", []),
                migration_constraints=bp_record.constraints_payload.get("migration", []),
                accepted_decisions=bp_record.accepted_decisions,
                open_constraints=bp_record.constraints_payload.get("open", []),
                evidence_refs=bp_record.evidence_refs,
                created_by=bp_record.created_by,
                content_hash=bp_record.content_hash,
            )

            # 2. Fetch latest legacy model
            leg_record = (
                await db.execute(
                    select(LegacyModelRecord)
                    .where(LegacyModelRecord.job_id == job.job_id)
                    .order_by(LegacyModelRecord.version.desc())
                )
            ).scalars().first()
            if not leg_record:
                raise NotFoundException("LegacyModel", job_id_str)

            legacy_model = LegacyModel(
                model_id=str(leg_record.model_id),
                job_id=job_id_str,
                snapshot_id=str(leg_record.snapshot_id),
                version=leg_record.version,
                modules=leg_record.modules_payload,
                dependency_graph=leg_record.dependencies_payload,
                public_interfaces=leg_record.interfaces_payload,
                persistence_entities=leg_record.persistence_payload,
                configurations=leg_record.configurations_payload,
                test_suites=leg_record.tests_payload,
                risks=leg_record.risks_payload,
                conflicts=leg_record.conflicts_payload,
                evidence_index={},
                content_hash=leg_record.content_hash,
            )

            # 3. Parallel planning & aggregation
            conversion_plan = await planner_coordinator.execute_planning(
                db=db,
                job=job,
                blueprint=blueprint,
                legacy_model=legacy_model,
                user=user,
                correlation_id=correlation_id,
            )

            # 4. Prepare Gate G3
            await g3_service.prepare_g3(
                db=db,
                job=job,
                user=user,
                correlation_id=correlation_id,
            )

            return conversion_plan
        except Exception as exc:
            logger.exception("run_pipeline_stage3_planning failed | job_id=%s | %s: %s", getattr(job, "job_id", "unknown"), type(exc).__name__, exc)
            raise

    def execute_intake_to_feasibility(
        self,
        job_id: str,
        workspace_path: Any,
        source_ref: str,
        target_stack: str,
        target_architecture: str = "MODULAR_CLEAN_ARCHITECTURE",
        project_constraints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """In-memory end-to-end execution of Stage 1 & 2 without database dependencies."""
        try:
            ws_path = Path(workspace_path)
            file_items, dirs, inv_hash = intake_agent.build_inventory(ws_path, job_id)

            metadata = SourceMetadata(
                repository_id=job_id,
                source_type="git" if str(source_ref).startswith("git") else "local",
                source_ref=source_ref,
                commit_sha=None,
                content_hash=inv_hash,
                file_count=len(file_items),
                archive_size_bytes=sum(f.size_bytes for f in file_items),
            )

            tech_profile = DetectedTechnologyProfile(
                primary_language="Python",
                languages={"Python": 100.0},
                frameworks=["FastAPI"],
                build_systems=["pip"],
                package_managers=["pip"],
                manifest_files=[f.path for f in file_items if f.is_manifest],
                config_files=[f.path for f in file_items if f.is_config],
                test_frameworks=["pytest"],
                database_dialects=[],
                confidence=0.95,
            )

            snapshot = RepositorySnapshot(
                snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
                job_id=job_id,
                version=1,
                metadata=metadata,
                tech_profile=tech_profile,
                inventory_hash=inv_hash,
                content_hash=inv_hash,
            )

            inventory = RepositoryInventory(
                inventory_id=f"inv_{uuid.uuid4().hex[:12]}",
                snapshot_id=snapshot.snapshot_id,
                job_id=job_id,
                total_files=len(file_items),
                total_bytes=sum(f.size_bytes for f in file_items),
                files=file_items,
                directories=dirs,
                inventory_hash=inv_hash,
            )

            legacy_model = analyzer_coordinator.analyze_repository(
                job_id=job_id,
                snapshot_id=snapshot.snapshot_id,
                workspace_path=ws_path,
                file_items=file_items,
            )

            blueprint = architect_agent.create_blueprint(
                legacy_model=legacy_model,
                target_stack=target_stack,
                target_architecture=target_architecture,
                project_constraints=project_constraints or [],
            )

            feasibility_report = feasibility_agent.evaluate_feasibility(
                legacy_model=legacy_model,
                target_blueprint=blueprint,
            )

            return {
                "status": "G1_PENDING",
                "snapshot": snapshot,
                "inventory": inventory,
                "legacy_model": legacy_model,
                "blueprint": blueprint,
                "feasibility_report": feasibility_report,
            }
        except Exception as exc:
            logger.exception("execute_intake_to_feasibility failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
            raise

    def execute_planning_to_g3(
        self,
        job_id: str,
        blueprint: TargetBlueprint,
        legacy_model: LegacyModel,
        feasibility_report: FeasibilityReport,
        g1_decisions: Optional[List[Any]] = None,
        characterization_suite: Optional[Dict[str, Any]] = None,
        schema_data_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """In-memory end-to-end execution of Stage 3 (Parallel Planners, Aggregation, G3 package)."""
        try:
            from app.schemas.phase4 import PlanningContext
            context = PlanningContext(
                job_id=job_id,
                legacy_model=legacy_model,
                target_blueprint=blueprint,
                feasibility_report=feasibility_report,
                g1_decisions=g1_decisions or [],
                characterization_suite=characterization_suite,
                schema_data_plan=schema_data_plan,
            )

            conversion_plan = planner_coordinator.coordinate_planning(
                job_id=job_id,
                blueprint=blueprint,
                legacy_model=legacy_model,
                context=context,
            )

            g3_package = g3_service.generate_g3_package(
                job_id=job_id,
                blueprint=blueprint,
                conversion_plan=conversion_plan,
                feasibility_report=feasibility_report,
                g1_decisions=g1_decisions or [],
                characterization_suite=characterization_suite,
                schema_data_plan=schema_data_plan,
            )

            return {
                "status": "G3_READY" if g3_package.g3_ready else "G3_BLOCKED",
                "conversion_plan": conversion_plan,
                "g3_package": g3_package,
            }
        except Exception as exc:
            logger.exception("execute_planning_to_g3 failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
            raise


Phase4Orchestrator = Phase4PipelineOrchestrator
phase4_orchestrator = Phase4PipelineOrchestrator()
