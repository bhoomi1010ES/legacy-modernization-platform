"""G1 Human Gap Decision Service: Enforces audit trail, deterministic routing, and versioning."""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, ForbiddenException, NotFoundException, ValidationException
from app.domain.state_machine import GatePolicy, JobStateMachine, RBACPolicy
from app.models.audit import AuditEvent
from app.models.gate import GateDecision
from app.models.job import Job
from app.models.phase4 import FeasibilityDecisionModel, FeasibilityReportModel, TargetBlueprintModel
from app.models.user import User
from app.models.workflow import WorkflowGate
from app.schemas.gates import DecisionOutcome, GateType
from app.schemas.jobs import JobStatus
from app.schemas.phase4 import (
    BlueprintStatus,
    G1DecisionRecord,
    G1DecisionType,
    TargetBlueprint,
)
from app.services.architect_agent import architect_agent
from app.services.artifact_service import ArtifactService
from app.services.supervisor_service import supervisor_service

logger = logging.getLogger(__name__)


class G1DecisionService:
    """Manages human review decisions on feasibility gaps at Gate G1."""

    def __init__(self, artifact_service: Optional[ArtifactService] = None):
        try:
            self.artifact_service = artifact_service or ArtifactService()
        except Exception as exc:
            logger.exception("G1DecisionService init failed | %s: %s", type(exc).__name__, exc)
            raise

    def apply_decision(
        self,
        blueprint: TargetBlueprint,
        feasibility_report: Any,
        decision_record: G1DecisionRecord,
    ) -> Dict[str, Any]:
        """Calculates deterministic outcome for a G1 decision record and updates versions."""
        try:
            dec = decision_record.decision
            res_bp_ver = blueprint.version
            rerun = False
            status = "APPLIED"

            if dec == G1DecisionType.ACCEPT_SUBSTITUTE:
                status = "APPLIED"
                rerun = False
            elif dec == G1DecisionType.ADD_TOOL:
                status = "TOOL_ADDED"
                rerun = True
            elif dec == G1DecisionType.CUSTOM_BUILD:
                status = "APPLIED"
                rerun = False
            elif dec == G1DecisionType.DESCOPE:
                status = "DESCOPED"
                rerun = True
            elif dec == G1DecisionType.REVISE_BLUEPRINT:
                status = "REVISION_REQUIRED"
                res_bp_ver = blueprint.version + 1
                rerun = True
            elif dec == G1DecisionType.REQUEST_MORE_ANALYSIS:
                status = "ANALYSIS_REQUESTED"
                rerun = True
            elif dec == G1DecisionType.CANCEL:
                status = "CANCELLED"
                rerun = False
            elif dec == G1DecisionType.REJECT:
                status = "REJECTED"
                rerun = False

            decision_record.resulting_blueprint_version = res_bp_ver

            return {
                "status": status,
                "resulting_blueprint_version": res_bp_ver,
                "rerun_triggered": rerun,
                "decision": dec.value if hasattr(dec, "value") else str(dec),
            }
        except Exception as exc:
            logger.exception("apply_decision failed | %s: %s", type(exc).__name__, exc)
            raise

    async def submit_decisions(
        self,
        db: AsyncSession,
        job: Job,
        user: User,
        decisions: List[G1DecisionRecord],
        global_decision: Optional[G1DecisionType] = None,
        global_rationale: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> List[G1DecisionRecord]:
        """Applies G1 human gap decisions, updates blueprint constraints, and determines workflow routing."""
        try:
            job_id = job.job_id
            if job.status not in (JobStatus.AWAITING_GATE_G1.value, JobStatus.ANALYZING.value):
                raise ConflictException(f"G1 decisions can only be submitted while job is awaiting G1. Current: {job.status}")

            # Separation of duties: creator cannot approve own gate
            creator_id = getattr(job, "created_by_user_id", None) or getattr(job, "owner_user_id", None)
            if creator_id and str(creator_id) == str(user.user_id):
                raise ForbiddenException(
                    "Separation of duties violation: Job creator cannot approve or reject gates for their own job."
                )

            # Verify user permissions
            effective_role = getattr(user, "_effective_job_role", user.role)
            if not RBACPolicy.has_permission(effective_role, "gate:approve_g1") and effective_role not in ("ADMIN", "SUPER_ADMIN", "REVIEWER"):
                raise ForbiddenException(f"Role '{effective_role}' lacks required permission 'gate:approve_g1' to decide gate G1.")

            # Get latest feasibility report
            report = (
                await db.execute(
                    select(FeasibilityReportModel)
                    .where(FeasibilityReportModel.job_id == job_id)
                    .order_by(FeasibilityReportModel.version.desc())
                )
            ).scalars().first()
            if not report:
                raise NotFoundException("FeasibilityReport", str(job_id))

            # Get latest blueprint
            blueprint_model = (
                await db.execute(
                    select(TargetBlueprintModel)
                    .where(TargetBlueprintModel.job_id == job_id)
                    .order_by(TargetBlueprintModel.version.desc())
                )
            ).scalars().first()
            if not blueprint_model:
                raise NotFoundException("TargetBlueprint", str(job_id))

            recorded_decisions: List[G1DecisionRecord] = []
            has_revise_blueprint = False
            has_request_analysis = False
            has_cancel = False
            has_reject = False

            # Process individual decisions
            for d in decisions:
                if len(d.reason.strip()) < 10:
                    raise ValidationException("Decision rationale must be at least 10 characters.")

                db_decision = FeasibilityDecisionModel(
                    decision_id=uuid.uuid4(),
                    job_id=job_id,
                    capability_id=d.capability_id,
                    decision=d.decision.value,
                    reason=d.reason,
                    actor=str(user.user_id),
                    previous_feasibility_version=report.version,
                    resulting_blueprint_version=blueprint_model.version,
                )
                db.add(db_decision)
                recorded_decisions.append(d)

                if d.decision == G1DecisionType.REVISE_BLUEPRINT:
                    has_revise_blueprint = True
                elif d.decision == G1DecisionType.REQUEST_MORE_ANALYSIS:
                    has_request_analysis = True
                elif d.decision == G1DecisionType.CANCEL:
                    has_cancel = True
                elif d.decision == G1DecisionType.REJECT:
                    has_reject = True

            if global_decision:
                if global_decision == G1DecisionType.CANCEL:
                    has_cancel = True
                elif global_decision == G1DecisionType.REJECT:
                    has_reject = True
                elif global_decision == G1DecisionType.REVISE_BLUEPRINT:
                    has_revise_blueprint = True
                elif global_decision == G1DecisionType.REQUEST_MORE_ANALYSIS:
                    has_request_analysis = True

            # Determine routing effect
            if has_cancel:
                await supervisor_service.cancel(db, job_id, actor_id=str(user.user_id), correlation_id=correlation_id)
            elif has_reject:
                # Reject G1 gate
                gate = await db.scalar(select(WorkflowGate).where(
                    WorkflowGate.job_id == job_id, WorkflowGate.gate_type == "G1", WorkflowGate.status == "PENDING"
                ))
                if gate:
                    gate.status = "REJECTED"
                    gate.decided_at = datetime.now(timezone.utc)
                job.blocking_reason = "Gate G1 rejected by human reviewer."
            elif has_request_analysis:
                # Route back to ANALYZING
                await supervisor_service.transition(
                    db, job_id, JobStatus.ANALYZING, actor_id=str(user.user_id), correlation_id=correlation_id,
                    reason="G1 requested more legacy analysis.",
                )
            elif has_revise_blueprint:
                # Revise blueprint and remain in AWAITING_GATE_G1 or transition
                blueprint_model.status = BlueprintStatus.REVISED.value
                job.blocking_reason = "Blueprint revision requested at G1."
            else:
                # All gaps approved / accepted / descoped / custom-built -> Approve G1!
                gate = await db.scalar(select(WorkflowGate).where(
                    WorkflowGate.job_id == job_id, WorkflowGate.gate_type == "G1", WorkflowGate.status == "PENDING"
                ))
                if gate:
                    gate.status = "APPROVED"
                    gate.decided_at = datetime.now(timezone.utc)

                blueprint_model.status = BlueprintStatus.APPROVED.value

                # Record GateDecision
                db.add(GateDecision(
                    decision_id=uuid.uuid4(),
                    job_id=job_id,
                    gate_id=gate.gate_id if gate else None,
                    gate_type="G1",
                    decision="APPROVED",
                    rationale=global_rationale or "All feasibility capabilities approved / resolved at G1.",
                    reviewer_user_id=user.user_id,
                    selected_options={d.capability_id: d.decision.value for d in decisions if d.capability_id},
                    artifact_hashes=gate.artifact_hashes if gate else {},
                ))

                # Transition to CHARACTERIZING in the canonical state machine DAG (G1 -> Characterization -> G2 -> Planning)
                await supervisor_service.transition(
                    db, job_id, JobStatus.CHARACTERIZING, actor_id=str(user.user_id), correlation_id=correlation_id,
                    reason="G1 approved by reviewer; proceeding to behavioral characterization suite.",
                )

            # Record audit event
            db.add(AuditEvent(
                job_id=job_id,
                event_type="G1_GAP_DECISIONS_SUBMITTED",
                actor_type="USER",
                actor_id=str(user.user_id),
                correlation_id=correlation_id,
                payload={
                    "decisions_count": len(recorded_decisions),
                    "global_decision": global_decision.value if global_decision else None,
                    "target_status": job.status,
                },
            ))

            await db.commit()
            return recorded_decisions
        except Exception as exc:
            logger.exception("submit_decisions failed | job_id=%s | %s: %s", getattr(job, "job_id", "unknown"), type(exc).__name__, exc)
            raise


g1_decision_service = G1DecisionService()
