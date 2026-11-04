"""Async SQLAlchemy repository for characterization entities with in-memory fallback support."""

import uuid
from typing import Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.characterization.models import (
    CharacterizationEventModel,
    CharacterizationExecutionModel,
    CharacterizationScenarioModel,
    CharacterizationSuiteModel,
    GateG2ApprovalModel,
)
from app.models.base import utc_now


class CharacterizationRepository:
    """Encapsulates database operations for the Phase 5A Characterization engine."""

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self._executions: Dict[str, CharacterizationExecutionModel] = {}
        self._suites: List[CharacterizationSuiteModel] = []
        self._scenarios: List[CharacterizationScenarioModel] = []
        self._events: List[CharacterizationEventModel] = []
        self._approvals: List[GateG2ApprovalModel] = []

    async def create_execution(self, execution: CharacterizationExecutionModel) -> None:
        if self.db is not None:
            self.db.add(execution)
            await self.db.flush()
        else:
            self._executions[execution.execution_id] = execution

    async def update_execution_stage(
        self,
        execution_id: str,
        stage: str,
        progress_pct: int,
        summary: Optional[str] = None,
    ) -> None:
        if self.db is not None:
            values = {
                "stage": stage,
                "stage_progress_pct": progress_pct,
                "updated_at": utc_now(),
            }
            if summary is not None:
                values["summary"] = summary
            await self.db.execute(
                update(CharacterizationExecutionModel)
                .where(CharacterizationExecutionModel.execution_id == execution_id)
                .values(**values)
            )
            await self.db.flush()
        else:
            ex = self._executions.get(execution_id)
            if ex is not None:
                ex.stage = stage
                ex.stage_progress_pct = progress_pct
                if summary is not None:
                    ex.summary = summary
                ex.updated_at = utc_now()

    async def complete_execution(
        self,
        execution_id: str,
        status: str,
        total_scenarios: int = 0,
        total_workflows: int = 0,
        error_message: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> None:
        if self.db is not None:
            await self.db.execute(
                update(CharacterizationExecutionModel)
                .where(CharacterizationExecutionModel.execution_id == execution_id)
                .values(
                    status=status,
                    stage="COMPLETED" if status == "COMPLETED" else "FAILED",
                    stage_progress_pct=100 if status == "COMPLETED" else 0,
                    total_scenarios_executed=total_scenarios,
                    total_workflows_characterized=total_workflows,
                    error_message=error_message,
                    duration_ms=duration_ms,
                    completed_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
            await self.db.flush()
        else:
            ex = self._executions.get(execution_id)
            if ex is not None:
                ex.status = status
                ex.stage = "COMPLETED" if status == "COMPLETED" else "FAILED"
                ex.stage_progress_pct = 100 if status == "COMPLETED" else 0
                ex.total_scenarios_executed = total_scenarios
                ex.total_workflows_characterized = total_workflows
                ex.error_message = error_message
                ex.duration_ms = duration_ms
                ex.completed_at = utc_now()
                ex.updated_at = utc_now()

    async def get_execution(self, execution_id: str) -> Optional[CharacterizationExecutionModel]:
        if self.db is not None:
            return await self.db.scalar(
                select(CharacterizationExecutionModel)
                .where(CharacterizationExecutionModel.execution_id == execution_id)
            )
        return self._executions.get(execution_id)

    async def save_suite(self, suite: CharacterizationSuiteModel) -> None:
        if self.db is not None:
            self.db.add(suite)
            await self.db.flush()
        else:
            self._suites.append(suite)

    async def get_latest_suite(self, job_id: uuid.UUID) -> Optional[CharacterizationSuiteModel]:
        if self.db is not None:
            return await self.db.scalar(
                select(CharacterizationSuiteModel)
                .where(CharacterizationSuiteModel.job_id == job_id)
                .order_by(CharacterizationSuiteModel.version.desc())
                .limit(1)
            )
        matching = [s for s in self._suites if s.job_id == job_id]
        if not matching:
            return None
        return max(matching, key=lambda s: s.version)

    async def get_suite_by_version(
        self, job_id: uuid.UUID, version: int
    ) -> Optional[CharacterizationSuiteModel]:
        if self.db is not None:
            return await self.db.scalar(
                select(CharacterizationSuiteModel)
                .where(
                    CharacterizationSuiteModel.job_id == job_id,
                    CharacterizationSuiteModel.version == version,
                )
            )
        for s in self._suites:
            if s.job_id == job_id and s.version == version:
                return s
        return None

    async def freeze_suite(self, suite_id: str) -> None:
        if self.db is not None:
            await self.db.execute(
                update(CharacterizationSuiteModel)
                .where(CharacterizationSuiteModel.suite_id == suite_id)
                .values(is_frozen=True, frozen_at=utc_now())
            )
            await self.db.flush()
        else:
            for s in self._suites:
                if s.suite_id == suite_id:
                    s.is_frozen = True
                    s.frozen_at = utc_now()

    async def save_scenarios(self, scenarios: List[CharacterizationScenarioModel]) -> None:
        if self.db is not None:
            self.db.add_all(scenarios)
            await self.db.flush()
        else:
            self._scenarios.extend(scenarios)

    async def save_event(self, event: CharacterizationEventModel) -> None:
        if self.db is not None:
            self.db.add(event)
            await self.db.flush()
        else:
            self._events.append(event)

    async def save_g2_approval(self, approval: GateG2ApprovalModel) -> None:
        if self.db is not None:
            self.db.add(approval)
            await self.db.flush()
        else:
            self._approvals.append(approval)

    async def get_latest_g2_approval(self, job_id: uuid.UUID) -> Optional[GateG2ApprovalModel]:
        if self.db is not None:
            return await self.db.scalar(
                select(GateG2ApprovalModel)
                .where(GateG2ApprovalModel.job_id == job_id)
                .order_by(GateG2ApprovalModel.decided_at.desc())
                .limit(1)
            )
        matching = [a for a in self._approvals if a.job_id == job_id]
        if not matching:
            return None
        return sorted(matching, key=lambda a: a.decided_at or utc_now(), reverse=True)[0]

