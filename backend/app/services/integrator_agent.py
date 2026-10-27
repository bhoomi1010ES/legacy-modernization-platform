"""Compatibility specialist entrypoint; Supervisor owns Phase 7 scheduling and G4."""

from __future__ import annotations

import logging
from typing import Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException
from app.models.job import Job
from app.models.user import User

logger = logging.getLogger(__name__)


class IntegrationResult:
    """Compatibility result contract for a future evidence-backed Integrator."""

    def __init__(
        self,
        job_id: uuid.UUID,
        success: bool,
        integrated_modules_count: int,
        system_tests_passed: bool,
        workspace_artifact_id: uuid.UUID | None,
        workspace_hash: str | None,
        gate_g4_id: Optional[uuid.UUID] = None,
    ):
        try:
            self.job_id = job_id
            self.success = success
            self.integrated_modules_count = integrated_modules_count
            self.system_tests_passed = system_tests_passed
            self.workspace_artifact_id = workspace_artifact_id
            self.workspace_hash = workspace_hash
            self.gate_g4_id = gate_g4_id
        except Exception:
            logger.exception("IntegrationResult initialization failed")
            raise


class IntegratorService:
    """Delegate to real Phase 7 integration without generating code or approving gates."""

    async def execute_integration(
        self,
        db: AsyncSession,
        job: Job,
        *,
        user: Optional[User] = None,
        correlation_id: Optional[str] = None,
    ) -> IntegrationResult:
        try:
            if job.status != "INTEGRATING":
                raise ConflictException("G4 is blocked until the canonical integration state and verified evidence are available")
            from sqlalchemy import select
            from app.models.agent import AgentRun
            from app.services.supervisor_service import supervisor_service
            from app.services import phase7_service as service
            actor = str(user.user_id) if user else "Supervisor"
            current, bindings = await service.bindings_for(db, job)
            key = "continuous-" + service.identity(current, bindings)
            active = await db.scalar(select(AgentRun).where(AgentRun.job_id == job.job_id, AgentRun.agent_name == "Integrator", AgentRun.status.in_(("QUEUED", "RUNNING"))).order_by(AgentRun.started_at.desc()).limit(1))
            run = active or await supervisor_service.queue_integration(db, job, key, actor)
            output = await service.execute_integration(db, run.run_id)
            gate = None
            if output.get("status") == "READY_FOR_REVIEW":
                gate = await supervisor_service.submit_final_review(db, job, output["report_hash"], actor)
            return IntegrationResult(job.job_id, output.get("status") == "READY_FOR_REVIEW", len(bindings), output.get("status") == "READY_FOR_REVIEW", uuid.UUID(output["report_artifact_id"]) if output.get("report_artifact_id") else None, output.get("report_hash"), gate.gate_id if gate else None)
        except Exception:
            logger.exception(
                "Integrator.execute_integration blocked | job_id=%s", job.job_id
            )
            raise


integrator_service = IntegratorService()
