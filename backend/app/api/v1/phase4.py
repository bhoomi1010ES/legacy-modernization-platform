"""Phase 4 API router: Intake, Repository, Modules, Analysis, Feasibility, Blueprint, and Conversion Plan."""

import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_job_access
from app.core.errors import ConflictException, ForbiddenException, NotFoundException, ValidationException
from app.domain.state_machine import RBACPolicy
from app.models.job import Job
from app.models.phase4 import (
    AnalysisConflictRecord,
    ConversionPlanModel,
    FeasibilityDecisionModel,
    FeasibilityReportModel,
    LegacyModelRecord,
    RepositoryInventoryModel,
    RepositorySnapshotModel,
    TargetBlueprintModel,
)
from app.models.user import User
from app.schemas.jobs import JobDetailResponse, JobIntakeRequest, JobStatus
from app.schemas.phase4 import (
    AnalysisConflict,
    AnalysisDetailResponse,
    AnalysisRetryRequest,
    BlueprintDetailResponse,
    BlueprintStatus,
    ConversionPlan,
    ConversionPlanDetailResponse,
    ConversionPlanValidation,
    ConversionPlanWave,
    DetectedTechnologyProfile,
    FeasibilityCapability,
    FeasibilityDetailResponse,
    FeasibilityReport,
    G1DecisionBatchRequest,
    G1DecisionRecord,
    LegacyModel,
    PlanRevisionRequest,
    RepositoryInventory,
    RepositorySnapshot,
    SourceMetadata,
    TargetBlueprint,
    ToolReadiness,
)
from app.services.g1_decision_service import g1_decision_service
from app.services.phase4_orchestrator import phase4_orchestrator
from app.services.plan_aggregator import plan_aggregator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Phase 4 Pipeline"])


# ==============================================================================
# 1. REPOSITORY REVIEWS & INVENTORY
# ==============================================================================


@router.get(
    "/{job_id}/repository",
    status_code=status.HTTP_200_OK,
    summary="Retrieve repository snapshot, deterministic inventory, and source metadata",
    operation_id="phase4_get_repository",
)
async def get_repository_details(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        job, _ = access
        snap = (
            await db.execute(
                select(RepositorySnapshotModel)
                .where(RepositorySnapshotModel.job_id == job.job_id)
                .order_by(RepositorySnapshotModel.version.desc())
            )
        ).scalars().first()

        if not snap:
            raise NotFoundException("RepositorySnapshot", job_id)

        inv = (
            await db.execute(
                select(RepositoryInventoryModel)
                .where(RepositoryInventoryModel.snapshot_id == snap.snapshot_id)
            )
        ).scalars().first()

        return {
            "job_id": str(job.job_id),
            "version": snap.version,
            "source_type": snap.source_type,
            "source_ref": snap.source_ref,
            "commit_sha": snap.commit_sha,
            "content_hash": snap.content_hash,
            "inventory_hash": snap.inventory_hash,
            "file_count": snap.file_count,
            "archive_size_bytes": snap.archive_size_bytes,
            "tech_profile": snap.tech_profile,
            "metadata": snap.metadata_payload,
            "files": inv.files_payload if inv else [],
            "directories": inv.directories_payload if inv else [],
            "created_at": snap.created_at.isoformat(),
        }
    except NotFoundException:
        raise
    except Exception as exc:
        logger.exception("get_repository_details API failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
        raise


# ==============================================================================
# 3. MODULES ENDPOINT
# ==============================================================================

@router.get(
    "/{job_id}/modules",
    status_code=status.HTTP_200_OK,
    summary="List discovered legacy modules and domain packages",
    operation_id="phase4_get_modules",
)
async def get_modules(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        job, _ = access
        legacy = (
            await db.execute(
                select(LegacyModelRecord)
                .where(LegacyModelRecord.job_id == job.job_id)
                .order_by(LegacyModelRecord.version.desc())
            )
        ).scalars().first()

        modules = legacy.modules_payload if legacy else []
        return {
            "job_id": str(job.job_id),
            "total": len(modules),
            "modules": modules,
        }
    except Exception as exc:
        logger.exception("get_modules API failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
        raise


# ==============================================================================
# 4. ANALYSIS & RETRY ENDPOINTS
# ==============================================================================

@router.get(
    "/{job_id}/analysis",
    response_model=AnalysisDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve canonical LegacyModel, evidence links, and conflicts",
    operation_id="phase4_get_analysis",
)
async def get_analysis(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> AnalysisDetailResponse:
    try:
        job, _ = access
        legacy = (
            await db.execute(
                select(LegacyModelRecord)
                .where(LegacyModelRecord.job_id == job.job_id)
                .order_by(LegacyModelRecord.version.desc())
            )
        ).scalars().first()

        if not legacy:
            raise NotFoundException("LegacyModel", job_id)

        legacy_model = LegacyModel(
            model_id=str(legacy.model_id),
            job_id=str(job.job_id),
            snapshot_id=str(legacy.snapshot_id),
            version=legacy.version,
            modules=legacy.modules_payload,
            dependency_graph=legacy.dependencies_payload,
            public_interfaces=legacy.interfaces_payload,
            persistence_entities=legacy.persistence_payload,
            configurations=legacy.configurations_payload,
            test_suites=legacy.tests_payload,
            risks=legacy.risks_payload,
            conflicts=legacy.conflicts_payload,
            evidence_index={},
            content_hash=legacy.content_hash,
        )

        conflicts = [AnalysisConflict(**c) for c in legacy.conflicts_payload]

        return AnalysisDetailResponse(
            legacy_model=legacy_model,
            evidence_index={},
            conflicts=conflicts,
            analysis_version=legacy.version,
            content_hash=legacy.content_hash,
        )
    except NotFoundException:
        raise
    except Exception as exc:
        logger.exception("get_analysis API failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
        raise


@router.post(
    "/{job_id}/analysis/retry",
    response_model=AnalysisDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry legacy analysis with optional constraints, preserving history",
    operation_id="phase4_retry_analysis",
)
async def retry_analysis(
    job_id: str,
    payload: AnalysisRetryRequest,
    request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:intake")),
    db: AsyncSession = Depends(get_db),
) -> AnalysisDetailResponse:
    try:
        job, user = access
        correlation_id = getattr(request.state, "correlation_id", None)

        legacy_model, _, _ = await phase4_orchestrator.run_pipeline_stage2_analysis_and_feasibility(
            db=db,
            job=job,
            user=user,
            correlation_id=correlation_id,
            slices_to_run=payload.slices_to_retry,
        )

        return AnalysisDetailResponse(
            legacy_model=legacy_model,
            evidence_index=legacy_model.evidence_index,
            conflicts=legacy_model.conflicts,
            analysis_version=legacy_model.version,
            content_hash=legacy_model.content_hash,
        )
    except Exception as exc:
        logger.exception("retry_analysis API failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
        raise


# ==============================================================================
# 5. FEASIBILITY & G1 GAP DECISIONS
# ==============================================================================

@router.get(
    "/{job_id}/feasibility",
    response_model=FeasibilityDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve feasibility assessment, capability classifications, and decision history",
    operation_id="phase4_get_feasibility",
)
async def get_feasibility(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> FeasibilityDetailResponse:
    try:
        job, _ = access
        report_record = (
            await db.execute(
                select(FeasibilityReportModel)
                .options(selectinload(FeasibilityReportModel.capabilities))
                .where(FeasibilityReportModel.job_id == job.job_id)
                .order_by(FeasibilityReportModel.version.desc())
            )
        ).scalars().first()

        if not report_record:
            raise NotFoundException("FeasibilityReport", job_id)

        caps = [
            FeasibilityCapability(
                capability_id=c.capability_id,
                category=c.category,
                legacy_requirement=c.legacy_requirement,
                target_requirement=c.target_requirement,
                classification=c.classification,
                confidence=c.confidence,
                evidence=c.evidence,
                tool_dependency=c.tool_dependency,
                effort=c.effort,
                risk=c.risk,
                verification_impact=c.verification_impact,
                recommendation=c.recommendation,
            ) for c in report_record.capabilities
        ]

        decisions_db = (
            await db.execute(
                select(FeasibilityDecisionModel)
                .where(FeasibilityDecisionModel.job_id == job.job_id)
                .order_by(FeasibilityDecisionModel.created_at.asc())
            )
        ).scalars().all()

        decisions_history = [
            G1DecisionRecord(
                decision_id=str(d.decision_id),
                job_id=str(job.job_id),
                capability_id=d.capability_id,
                decision=d.decision,
                reason=d.reason,
                actor=d.actor,
                previous_feasibility_version=d.previous_feasibility_version,
                resulting_blueprint_version=d.resulting_blueprint_version,
            ) for d in decisions_db
        ]

        report_obj = FeasibilityReport(
            report_id=str(report_record.report_id),
            job_id=str(job.job_id),
            version=report_record.version,
            blueprint_version=report_record.blueprint_version,
            legacy_model_version=report_record.legacy_model_version,
            capabilities=caps,
            tool_readiness=[],
            overall_feasibility_score=report_record.overall_score,
            unsupported_count=report_record.unsupported_count,
            custom_build_count=report_record.custom_build_count,
            substitute_count=report_record.substitute_count,
            unknown_count=report_record.unknown_count,
            summary=report_record.summary,
            content_hash=report_record.content_hash,
        )

        return FeasibilityDetailResponse(
            feasibility_report=report_obj,
            capabilities=caps,
            tool_readiness=[],
            decisions_history=decisions_history,
        )
    except NotFoundException:
        raise
    except Exception as exc:
        logger.exception("get_feasibility API failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
        raise


@router.post(
    "/{job_id}/feasibility/decisions",
    response_model=List[G1DecisionRecord],
    status_code=status.HTTP_200_OK,
    summary="Submit human gap decisions for Gate G1 review",
    operation_id="phase4_submit_feasibility_decisions",
)
async def submit_feasibility_decisions(
    job_id: str,
    payload: G1DecisionBatchRequest,
    request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="gate:approve_g1")),
    db: AsyncSession = Depends(get_db),
) -> List[G1DecisionRecord]:
    try:
        job, user = access
        creator_id = getattr(job, "created_by_user_id", None) or getattr(job, "owner_user_id", None)
        if creator_id and str(creator_id) == str(user.user_id):
            raise ForbiddenException(
                "Separation of duties violation: Job creator cannot approve or reject gates for their own job."
            )
        correlation_id = getattr(request.state, "correlation_id", None)

        recorded = await g1_decision_service.submit_decisions(
            db=db,
            job=job,
            user=user,
            decisions=payload.decisions,
            global_decision=payload.global_decision,
            global_rationale=payload.global_rationale,
            correlation_id=correlation_id,
        )

        return recorded
    except Exception as exc:
        logger.exception("submit_feasibility_decisions API failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
        raise


# ==============================================================================
# 6. BLUEPRINT ENDPOINT
# ==============================================================================

@router.get(
    "/{job_id}/blueprint",
    response_model=BlueprintDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve target modular blueprint and interface contracts",
    operation_id="phase4_get_blueprint",
)
async def get_blueprint(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> BlueprintDetailResponse:
    try:
        job, _ = access
        bp_record = (
            await db.execute(
                select(TargetBlueprintModel)
                .where(TargetBlueprintModel.job_id == job.job_id)
                .order_by(TargetBlueprintModel.version.desc())
            )
        ).scalars().first()

        if not bp_record:
            raise NotFoundException("TargetBlueprint", job_id)

        blueprint = TargetBlueprint(
            blueprint_id=str(bp_record.blueprint_id),
            job_id=str(job.job_id),
            version=bp_record.version,
            status=BlueprintStatus(bp_record.status),
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

        return BlueprintDetailResponse(
            blueprint=blueprint,
            version=bp_record.version,
            status=BlueprintStatus(bp_record.status),
            content_hash=bp_record.content_hash,
        )
    except NotFoundException:
        raise
    except Exception as exc:
        logger.exception("get_blueprint API failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
        raise


# ==============================================================================
# 7. CONVERSION PLAN & REVISIONS
# ==============================================================================

@router.get(
    "/{job_id}/conversion-plan",
    response_model=ConversionPlanDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve canonical conversion plan, DAG validation, and wave schedule",
    operation_id="phase4_get_conversion_plan",
)
async def get_conversion_plan(
    job_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> ConversionPlanDetailResponse:
    try:
        job, _ = access
        plan_record = (
            await db.execute(
                select(ConversionPlanModel)
                .options(
                    selectinload(ConversionPlanModel.modules),
                    selectinload(ConversionPlanModel.tasks),
                    selectinload(ConversionPlanModel.dependencies),
                )
                .where(ConversionPlanModel.job_id == job.job_id)
                .order_by(ConversionPlanModel.version.desc())
            )
        ).scalars().first()

        if not plan_record:
            raise NotFoundException("ConversionPlan", job_id)

        modules = [m.payload for m in plan_record.modules]
        tasks = [t.payload for t in plan_record.tasks]
        val_dict = plan_record.validation_payload or {}
        validation = ConversionPlanValidation(**val_dict)

        plan = ConversionPlan(
            plan_id=str(plan_record.plan_id),
            job_id=str(job.job_id),
            version=plan_record.version,
            blueprint_version=plan_record.blueprint_version,
            modules=modules,
            tasks=tasks,
            dependencies=[],
            waves=[],
            interfaces=[],
            total_estimate_hours=plan_record.total_estimate_hours,
            risk_summary=plan_record.risk_summary_payload,
            required_tests_count=sum(len(t.get("required_tests", [])) for t in tasks),
            acceptance_criteria_completeness_pct=100.0,
            tool_requirements=["compiler", "test_runner"],
            environment_requirements=["Isolated Container Sandbox"],
            evidence_refs=[],
            conflicts=[],
            validation=validation,
            content_hash=plan_record.content_hash,
        )

        waves = plan_aggregator.calculate_execution_waves(plan.tasks, plan.modules)

        return ConversionPlanDetailResponse(
            conversion_plan=plan,
            version=plan_record.version,
            validation=validation,
            waves=waves,
            content_hash=plan_record.content_hash,
        )
    except NotFoundException:
        raise
    except Exception as exc:
        logger.exception("get_conversion_plan API failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
        raise


@router.post(
    "/{job_id}/conversion-plan/revisions",
    response_model=ConversionPlanDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Create a new conversion plan revision, preserving history",
    operation_id="phase4_revise_conversion_plan",
)
async def revise_conversion_plan(
    job_id: str,
    payload: PlanRevisionRequest,
    request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="gate:approve_g3")),
    db: AsyncSession = Depends(get_db),
) -> ConversionPlanDetailResponse:
    try:
        job, user = access
        correlation_id = getattr(request.state, "correlation_id", None)

        plan = await phase4_orchestrator.run_pipeline_stage3_planning(
            db=db,
            job=job,
            user=user,
            correlation_id=correlation_id,
        )

        waves = plan_aggregator.calculate_execution_waves(plan.tasks, plan.modules)

        return ConversionPlanDetailResponse(
            conversion_plan=plan,
            version=plan.version,
            validation=plan.validation,
            waves=waves,
            content_hash=plan.content_hash,
        )
    except Exception as exc:
        logger.exception("revise_conversion_plan API failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
        raise
