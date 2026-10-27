"""At-least-once outbox dispatcher with bounded retry and dead-letter handling."""

from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utc_now
from app.models.workflow import WorkflowOutbox

OutboxHandler = Callable[[str, dict], Awaitable[None]]


class WorkflowOutboxDispatcher:
    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts

    async def dispatch_ready(self, db: AsyncSession, handler: OutboxHandler, limit: int = 100) -> int:
        now = utc_now()
        processed = 0
        while True:
            stmt = (
                select(WorkflowOutbox)
                .where(
                    WorkflowOutbox.status == "PENDING",
                    or_(
                        WorkflowOutbox.available_at.is_(None),
                        WorkflowOutbox.available_at <= func.now(),
                        WorkflowOutbox.available_at <= now,
                    ),
                )
                .order_by(WorkflowOutbox.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = list((await db.execute(stmt)).scalars().all())
            if not rows:
                break
            for event in rows:
                event.status = "PROCESSING"
                event.attempts += 1
                try:
                    await handler(event.event_type, event.payload)
                except Exception as exc:
                    event.last_error = str(exc)[:2000]
                    if event.attempts >= self.max_attempts:
                        event.status = "DEAD_LETTER"
                    else:
                        event.status = "PENDING"
                        event.available_at = utc_now() + timedelta(seconds=min(300, 2 ** event.attempts))
                else:
                    event.status = "PROCESSED"
                    event.processed_at = utc_now()
                    processed += 1
            await db.commit()
        return processed


workflow_outbox_dispatcher = WorkflowOutboxDispatcher()
