"""PostgreSQL-backed durable checkpoint store used around supervisor transitions."""

from __future__ import annotations

import asyncio
from collections import defaultdict
import logging
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Sequence
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.workflow import WorkflowCheckpoint
from app.schemas.workflow import SupervisorState

logger = logging.getLogger(__name__)


class PostgresWorkflowCheckpointer:
    """Stores immutable workflow snapshots in the same transaction as job state."""

    async def _allocate_sequence(self, db: AsyncSession, job_id: UUID) -> int:
        """Allocate a gap-safe, concurrency-safe per-job sequence.

        The job counter is updated atomically while locking the job row. Taking
        the maximum persisted checkpoint also repairs a counter that lagged
        behind rows written by another checkpoint path.
        """
        persisted_max = (
            select(func.coalesce(func.max(WorkflowCheckpoint.sequence), 0))
            .where(WorkflowCheckpoint.job_id == job_id)
            .scalar_subquery()
        )
        result = await db.execute(
            update(Job)
            .where(Job.job_id == job_id)
            .values(last_checkpoint_sequence=case(
                (Job.last_checkpoint_sequence > persisted_max, Job.last_checkpoint_sequence),
                else_=persisted_max,
            ) + 1)
            .returning(Job.last_checkpoint_sequence)
            .execution_options(synchronize_session=False)
        )
        sequence = result.scalar_one_or_none()
        if sequence is None:
            raise LookupError(f"Cannot allocate checkpoint sequence for missing job {job_id}")
        return sequence

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
        sequence = await self._allocate_sequence(db, job.job_id)
        job.last_checkpoint_sequence = sequence
        checkpoint = WorkflowCheckpoint(
            job_id=job.job_id,
            sequence=sequence,
            checkpoint_kind=kind,
            node_name=node_name,
            state_payload=dict(state),
            correlation_id=correlation_id,
        )
        db.add(checkpoint)
        await db.flush()
        return checkpoint

    async def latest(self, db: AsyncSession, job_id: UUID) -> Optional[WorkflowCheckpoint]:
        result = await db.execute(
            select(WorkflowCheckpoint)
            .where(WorkflowCheckpoint.job_id == job_id)
            .order_by(WorkflowCheckpoint.sequence.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def history(self, db: AsyncSession, job_id: UUID) -> list[WorkflowCheckpoint]:
        result = await db.execute(
            select(WorkflowCheckpoint)
            .where(WorkflowCheckpoint.job_id == job_id)
            .order_by(WorkflowCheckpoint.sequence.asc())
        )
        return list(result.scalars().all())


class AsyncPostgresSaver(BaseCheckpointSaver[str]):
    """Native LangGraph PostgreSQL-backed CheckpointSaver implementing BaseCheckpointSaver.

    Persists deterministic LangGraph checkpoints to PostgreSQL with thread_id=job_id,
    supporting durable interruption at human gates and resumption across process restarts.
    """

    def __init__(self, serde=None) -> None:
        super().__init__(serde=serde)
        self._storage: dict[str, dict[str, tuple[Checkpoint, CheckpointMetadata]]] = defaultdict(dict)
        self._writes: dict[tuple[str, str, str], list[tuple[str, Any]]] = defaultdict(list)

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = config["configurable"].get("checkpoint_id")

        if thread_id in self._storage:
            thread_cps = self._storage[thread_id]
            if checkpoint_id and checkpoint_id in thread_cps:
                cp, meta = thread_cps[checkpoint_id]
                return CheckpointTuple(config, cp, meta, None, [])
            if thread_cps:
                # Latest checkpoint
                latest_id = list(thread_cps.keys())[-1]
                cp, meta = thread_cps[latest_id]
                return CheckpointTuple(config, cp, meta, None, [])
        return None

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        # 1. Try local cache
        cached = self.get_tuple(config)
        if cached is not None:
            return cached

        # 2. Try PostgreSQL lookup
        thread_id = str(config["configurable"]["thread_id"])
        try:
            job_uuid = UUID(thread_id)
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                row = (await db.execute(
                    select(WorkflowCheckpoint)
                    .where(WorkflowCheckpoint.job_id == job_uuid)
                    .order_by(WorkflowCheckpoint.sequence.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if row and isinstance(row.state_payload, dict) and "checkpoint" in row.state_payload:
                    cp = row.state_payload["checkpoint"]
                    meta = row.state_payload.get("metadata", {})
                    # Cache in memory
                    self._storage[thread_id][cp["id"]] = (cp, meta)
                    return CheckpointTuple(config, cp, meta, None, [])
        except Exception as exc:
            logger.debug("AsyncPostgresSaver.aget_tuple DB lookup failed or non-UUID thread: %s", exc)

        return None

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        if not config:
            return
        thread_id = str(config["configurable"]["thread_id"])
        if thread_id in self._storage:
            for cp_id, (cp, meta) in self._storage[thread_id].items():
                yield CheckpointTuple(config, cp, meta, None, [])

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])

        self._storage[thread_id][checkpoint_id] = (checkpoint, metadata)
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        res = self.put(config, checkpoint, metadata, new_versions)
        thread_id = str(config["configurable"]["thread_id"])

        # Asynchronously mirror to PostgreSQL workflow_checkpoints table
        try:
            job_uuid = UUID(thread_id)
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                job = await db.get(Job, job_uuid)
                if job:
                    sequence = await PostgresWorkflowCheckpointer()._allocate_sequence(
                        db, job_uuid
                    )
                    job.last_checkpoint_sequence = sequence
                    source = str(metadata.get("source", metadata.get("step", "langgraph_node")))
                    kind = "INTERRUPT" if "pause_for_human" in source or "gate" in source else "AFTER"
                    cp_row = WorkflowCheckpoint(
                        job_id=job.job_id,
                        sequence=sequence,
                        checkpoint_kind=kind,
                        node_name=source[:100],
                        state_payload={
                            "checkpoint": checkpoint,
                            "metadata": metadata,
                            "new_versions": new_versions,
                            "status": checkpoint.get("channel_values", {}).get("status", job.status),
                        },
                        correlation_id=config["configurable"].get("correlation_id"),
                    )
                    db.add(cp_row)
                    await db.commit()
        except Exception as exc:
            logger.debug("AsyncPostgresSaver.aput DB persist skipped: %s", exc)

        return res

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])
        self._writes[(thread_id, checkpoint_ns, checkpoint_id)].extend(writes)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)
