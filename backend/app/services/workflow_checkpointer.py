"""PostgreSQL-backed durable checkpoint store used around supervisor transitions."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.workflow import WorkflowCheckpoint
from app.schemas.workflow import SupervisorState


class PostgresWorkflowCheckpointer:
    """Stores immutable workflow snapshots in the same transaction as job state."""

    async def save(
        self,
        db: AsyncSession,
        job: Job,
        *,
        kind: str,
        node_name: str,
        state: SupervisorState,
        correlation_id: Optional[str] = None,
    ) -> WorkflowCheckpoint:
        # The owning job is locked by the supervisor; its counter makes sequence
        # allocation deterministic even when several workers attempt progress.
        job.last_checkpoint_sequence += 1
        checkpoint = WorkflowCheckpoint(
            job_id=job.job_id,
            sequence=job.last_checkpoint_sequence,
            checkpoint_kind=kind,
            node_name=node_name,
            state_payload=dict(state),
            correlation_id=correlation_id,
        )
        db.add(checkpoint)
        await db.flush()
        return checkpoint

    async def latest(self, db: AsyncSession, job_id) -> Optional[WorkflowCheckpoint]:
        result = await db.execute(
            select(WorkflowCheckpoint)
            .where(WorkflowCheckpoint.job_id == job_id)
            .order_by(WorkflowCheckpoint.sequence.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def history(self, db: AsyncSession, job_id) -> list[WorkflowCheckpoint]:
        result = await db.execute(
            select(WorkflowCheckpoint)
            .where(WorkflowCheckpoint.job_id == job_id)
            .order_by(WorkflowCheckpoint.sequence.asc())
        )
        return list(result.scalars().all())
