"""Continuous Agent Pipeline Runner: Executes agent stages autonomously with real-time activity events and strict error handling."""

import asyncio
import logging
import traceback
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.user import User
from app.models.workflow import WorkflowGate
from app.schemas.jobs import JobStatus
from app.services.phase4_orchestrator import phase4_orchestrator
from app.services.supervisor_service import supervisor_service

logger = logging.getLogger(__name__)


class ContinuousPipelineService:
    """Deprecated execution-helper facade; SupervisorService owns all workflow decisions."""

    @property
    def _running_tasks(self) -> Dict[str, asyncio.Task]:
        return supervisor_service._running_tasks

    @_running_tasks.setter
    def _running_tasks(self, val: Any) -> None:
        pass

    def trigger_continuous_pipeline(
        self,
        job_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> asyncio.Task:
        """Kicks off continuous execution in background without blocking the caller."""
        return supervisor_service.schedule_drive(
            job_id, correlation_id=correlation_id or f"drive-{uuid.uuid4().hex[:12]}"
        )

    async def _emit_event(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        event_type: str,
        payload: Dict[str, Any],
        actor_id: Optional[str] = "SYSTEM",
        correlation_id: Optional[str] = None,
    ) -> None:
        """Records an event to AuditEvent table for live polling in Code Workspace."""
        evt = AuditEvent(
            job_id=job_id,
            event_type=event_type,
            actor_type="AGENT",
            actor_id=actor_id or "SYSTEM",
            correlation_id=correlation_id,
            payload=payload,
        )
        db.add(evt)
        await db.commit()

    async def _execute_pipeline_loop(
        self,
        job_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Compatibility entrypoint that delegates to the authoritative graph."""
        try:
            await supervisor_service.drive_job(
                job_id, correlation_id=correlation_id or f"drive-{uuid.uuid4().hex[:12]}"
            )
        finally:
            self._running_tasks.pop(str(job_id), None)

    async def _run_conversion_and_verification_stage(
        self, session: AsyncSession, job: Job, user: Optional[User],
        actor_str: str, corr_id: str,
    ) -> None:
        """Supervisor-controlled workers; no synthetic output or unobserved verification."""
        try:
            await supervisor_service.run_phase6_pool(session, job, actor_id=actor_str, correlation_id=corr_id)
        except Exception:
            logger.exception("Continuous Phase 6 stage failed | job_id=%s", job.job_id)
            raise


    async def _run_integration_stage(
        self,
        session: AsyncSession,
        job: Job,
        user: Optional[User],
        actor_str: str,
        corr_id: str,
    ) -> None:
        """Executes IntegratorAgent step, merges modules, verifies system, and transitions to G4."""
        from app.services.integrator_agent import integrator_service

        logger.info("Executing Integrator stage | job_id=%s", job.job_id)

        await self._emit_event(
            session,
            job.job_id,
            "agent.started",
            {
                "agent_name": "Integrator",
                "role": "System Integration Specialist",
                "summary": "Merging verified modules into consolidated workspace and running system test vectors",
            },
            actor_id="Integrator",
            correlation_id=corr_id,
        )

        result = await integrator_service.execute_integration(
            session, job, user=user, correlation_id=corr_id
        )

        if not result.success:
            await self._emit_event(session, job.job_id, "integration.blocked", {"summary": "Integration is blocked; review real conflicts/checks/SBOM status", "status": "blocked"}, actor_id="Supervisor", correlation_id=corr_id)
            return

        await self._emit_event(
            session,
            job.job_id,
            "gate.pending",
            {
                "gate": "G4",
                "title": "System Delivery & Acceptance Approval",
                "summary": "All modules merged and system verified against golden vectors · Gate G4 open for human delivery approval",
                "status": "pending",
            },
            actor_id="System",
            correlation_id=corr_id,
        )

        logger.info("Integration completed successfully; Gate G4 ready | job_id=%s", job.job_id)

    async def _run_characterization_stage(
        self, session: AsyncSession, job: Job, user: Optional[User],
        actor_str: str, corr_id: str, *, transition_to_gate: bool = True,
    ) -> None:
        """Publish discovered evidence with honest runtime and coverage gaps."""
        try:
            from app.schemas.phase5 import CaptureRequest
            from app.services.phase5_service import capture
            await capture(session, job, CaptureRequest(idempotency_key=f"discovery-{corr_id}"), actor_str)
        except Exception:
            logger.exception("continuous characterization failed | job_id=%s", job.job_id)
            raise

    async def _run_schema_data_stage(
        self, session: AsyncSession, job: Job, user: Optional[User],
        actor_str: str, corr_id: str,
    ) -> None:
        """Schema evidence is published atomically with characterization."""
        try:
            from app.services.phase5_service import latest
            await latest(session, job.job_id, "SCHEMA_MIGRATION_PLAN")
        except Exception:
            logger.exception("continuous schema discovery failed | job_id=%s", job.job_id)
            raise



    async def _run_planning_stage(
        self, session: AsyncSession, job: Job, user: Optional[User],
        actor_str: str, corr_id: str,
    ) -> None:
        """Reuse authoritative Phase 4 plans, never fabricate plan artifacts or billing."""
        try:
            from app.services.phase5_service import read_payload
            await supervisor_service.require_planning_eligibility(session, job)
            plan = await session.scalar(select(Artifact).where(
                Artifact.job_id == job.job_id,
                Artifact.artifact_type.in_(("CONVERSION_PLAN", "ConversionPlan")),
            ).order_by(Artifact.created_at.desc(), Artifact.version.desc()).limit(1))
            if plan:
                payload = await read_payload(plan)
                if not payload.get("modules"):
                    raise ValueError("Conversion plan has no approved module scope")
                return
            await phase4_orchestrator.run_pipeline_stage3_planning(session, job=job, user=user, correlation_id=corr_id)
        except Exception:
            logger.exception("Continuous planning handoff failed | job_id=%s", job.job_id)
            raise

    async def _record_failure(
        self,
        job_id: uuid.UUID,
        error_msg: str,
        trace_str: str,
        corr_id: str,
    ) -> None:
        """Marks the job as FAILED and records a visible error event for the UI and live log."""
        try:
            async with AsyncSessionLocal() as error_session:
                await supervisor_service.fail(
                    error_session,
                    job_id,
                    reason=f"Agent failed: {error_msg}",
                    correlation_id=corr_id,
                )
        except Exception as inner_exc:
            logger.exception("Failed to write failure audit record | job_id=%s | %s", job_id, inner_exc)


continuous_pipeline_service = ContinuousPipelineService()
