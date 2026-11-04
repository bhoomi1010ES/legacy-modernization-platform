"""Domain Application Service and Real-Time Event Bus for Characterization."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.characterization.contracts.approval import G2ApprovalDecisionRecord, GateG2Request
from app.characterization.contracts.enums import ExecutionStatus
from app.characterization.contracts.suite import CharacterizationRequest, CharacterizationSuite
from app.characterization.coordinator import CharacterizationCoordinator
from app.characterization.gate_g2 import GateG2Manager
from app.characterization.models import (
    CharacterizationExecutionModel,
    GateG2ApprovalModel,
)
from app.characterization.persistence.repository import CharacterizationRepository
from app.core.database import AsyncSessionLocal
from app.models.base import utc_now
from app.services.repository_workspace_service import repository_workspace_service

logger = logging.getLogger(__name__)


class CharacterizationService:
    """Coordinates asynchronous characterization execution, real-time events, and Gate G2 freezes."""

    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self.g2_manager = GateG2Manager()

    def _get_or_create_subscribers(self, execution_id: str) -> List[asyncio.Queue]:
        if execution_id not in self._subscribers:
            self._subscribers[execution_id] = []
        return self._subscribers[execution_id]

    async def broadcast_event(self, execution_id: str, event_data: Dict[str, Any]) -> None:
        queues = self._subscribers.get(execution_id, [])
        for q in list(queues):
            try:
                await q.put(event_data)
            except Exception:
                pass

    async def subscribe_events(
        self, execution_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to real-time event updates for a running execution."""
        q: asyncio.Queue = asyncio.Queue()
        subscribers = self._get_or_create_subscribers(execution_id)
        subscribers.append(q)
        try:
            while True:
                item = await q.get()
                yield item
                if item.get("event_type") in ("GATE_G2_READINESS_EVALUATED", "EXECUTION_FAILED"):
                    break
        finally:
            if q in subscribers:
                subscribers.remove(q)
            if not subscribers and execution_id in self._subscribers:
                del self._subscribers[execution_id]

    async def start_characterization(
        self,
        db: AsyncSession,
        job_id: str,
        request: CharacterizationRequest,
    ) -> str:
        """Initialize and launch asynchronous characterization run."""
        job_uuid = uuid.UUID(job_id)
        execution_id = f"char_exec_{job_id[:8]}_{uuid.uuid4().hex[:8]}"

        execution = CharacterizationExecutionModel(
            execution_id=execution_id,
            job_id=job_uuid,
            status=ExecutionStatus.PENDING.value,
            stage="INITIALIZING",
            stage_progress_pct=0,
            summary=f"Initiated 9-stage characterization for job {job_id}.",
            started_at=utc_now(),
        )
        repo = CharacterizationRepository(db)
        await repo.create_execution(execution)
        await db.commit()

        # Workspace resolution
        workspace_path = repository_workspace_service.get_workspace_path(job_uuid)

        # Launch background task
        asyncio.create_task(
            self._run_background_pipeline(execution_id, job_id, workspace_path, request)
        )

        return execution_id

    async def _run_background_pipeline(
        self,
        execution_id: str,
        job_id: str,
        workspace_path: Path,
        request: CharacterizationRequest,
    ) -> None:
        """Background runner with isolated session."""
        async with AsyncSessionLocal() as db:
            async def event_callback(event_data: Dict[str, Any]):
                await self.broadcast_event(execution_id, event_data)

            coordinator = CharacterizationCoordinator(db, event_callback=event_callback)
            try:
                await coordinator.run(
                    execution_id=execution_id,
                    job_id_str=job_id,
                    workspace_path=workspace_path,
                    request=request,
                )
            except Exception as exc:
                logger.exception("Background characterization failed for %s", execution_id)
                await self.broadcast_event(
                    execution_id,
                    {
                        "stage": "FAILED",
                        "event_type": "EXECUTION_FAILED",
                        "message": str(exc),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )

    async def get_execution(
        self, db: AsyncSession, execution_id: str
    ) -> Optional[CharacterizationExecutionModel]:
        repo = CharacterizationRepository(db)
        return await repo.get_execution(execution_id)

    async def get_latest_suite(
        self, db: AsyncSession, job_id: str
    ) -> Optional[CharacterizationSuite]:
        repo = CharacterizationRepository(db)
        model = await repo.get_latest_suite(uuid.UUID(job_id))
        if not model:
            return None
        return CharacterizationSuite.model_validate(model.suite_data)

    async def get_suite_by_version(
        self, db: AsyncSession, job_id: str, version: int
    ) -> Optional[CharacterizationSuite]:
        repo = CharacterizationRepository(db)
        model = await repo.get_suite_by_version(uuid.UUID(job_id), version)
        if not model:
            return None
        return CharacterizationSuite.model_validate(model.suite_data)

    async def submit_gate_g2_decision(
        self,
        db: AsyncSession,
        job_id: str,
        request: GateG2Request,
        decided_by: str,
    ) -> Tuple[G2ApprovalDecisionRecord, CharacterizationSuite]:
        """Process Gate G2 human decision, freeze baseline, and update approval ledger."""
        job_uuid = uuid.UUID(job_id)
        repo = CharacterizationRepository(db)
        suite_model = await repo.get_latest_suite(job_uuid)
        if not suite_model:
            raise ValueError(f"No characterization suite found for job {job_id}")

        suite = CharacterizationSuite.model_validate(suite_model.suite_data)
        decision_record, updated_suite = self.g2_manager.process_g2_decision(
            suite=suite, request=request, decided_by=decided_by
        )

        approval_model = GateG2ApprovalModel(
            approval_id=decision_record.approval_id,
            job_id=job_uuid,
            suite_id=suite.suite_id,
            suite_version=suite.version,
            suite_content_hash=suite.content_hash,
            decision=request.decision.value,
            decided_by=decided_by,
            rationale=request.rationale,
            conditions=request.conditions,
            is_valid=True,
            decided_at=utc_now(),
        )
        await repo.save_g2_approval(approval_model)

        if updated_suite.is_frozen:
            await repo.freeze_suite(suite.suite_id)
            # Also sync with REBASE WorkflowGate so downstream workflow unlocks cleanly
            from app.models.workflow import WorkflowGate
            from sqlalchemy import select, update
            gate = await db.scalar(
                select(WorkflowGate).where(
                    WorkflowGate.job_id == job_uuid,
                    WorkflowGate.gate_type == "G2",
                ).limit(1)
            )
            if gate:
                await db.execute(
                    update(WorkflowGate)
                    .where(WorkflowGate.gate_id == gate.gate_id)
                    .values(status="APPROVED", decided_at=utc_now())
                )

        await db.commit()
        return decision_record, updated_suite


characterization_service = CharacterizationService()
