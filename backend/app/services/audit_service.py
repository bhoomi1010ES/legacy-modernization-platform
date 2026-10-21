"""Immutable, append-only audit event service."""

from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenException
from app.models.audit import AuditEvent


class AuditService:
    """Provides append-only audit logging and authorized historical inspection."""

    @staticmethod
    async def record_event(
        db: AsyncSession,
        event_type: str,
        actor_id: str,
        actor_type: str = "USER",
        job_id: Optional[uuid.UUID] = None,
        correlation_id: Optional[str] = None,
        target_resource: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        event = AuditEvent(
            job_id=job_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=correlation_id,
            target_resource=target_resource,
            payload=payload or {},
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event

    @staticmethod
    async def list_job_events(
        db: AsyncSession,
        job_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[AuditEvent], int]:
        count_query = select(func.count(AuditEvent.event_id)).where(AuditEvent.job_id == job_id)
        total_res = await db.execute(count_query)
        total = total_res.scalar() or 0

        query = (
            select(AuditEvent)
            .where(AuditEvent.job_id == job_id)
            .order_by(AuditEvent.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        res = await db.execute(query)
        events = list(res.scalars().all())
        return events, total

    @staticmethod
    async def list_all_events(
        db: AsyncSession,
        limit: int = 50,
        offset: int = 0,
        actor_type: Optional[str] = None,
    ) -> Tuple[List[AuditEvent], int]:
        count_query = select(func.count(AuditEvent.event_id))
        if actor_type:
            count_query = count_query.where(AuditEvent.actor_type == actor_type.upper())
        total_res = await db.execute(count_query)
        total = total_res.scalar() or 0

        query = select(AuditEvent)
        if actor_type:
            query = query.where(AuditEvent.actor_type == actor_type.upper())
        query = query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit)
        res = await db.execute(query)
        events = list(res.scalars().all())
        return events, total

    @staticmethod
    async def update_event(*args, **kwargs) -> None:
        """Enforces application-level append-only invariant."""
        raise ForbiddenException("Audit trail records are immutable and append-only. Modification is strictly forbidden.")

    @staticmethod
    async def delete_event(*args, **kwargs) -> None:
        """Enforces application-level append-only invariant."""
        raise ForbiddenException("Audit trail records are immutable and append-only. Deletion is strictly forbidden.")
