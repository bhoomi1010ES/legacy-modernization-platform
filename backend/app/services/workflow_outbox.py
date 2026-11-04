"""At-least-once outbox dispatcher with bounded exponential retry, jitter, deduplication, and classified dead-letter handling (W05)."""

import logging
import random
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.base import utc_now
from app.models.workflow import WorkflowOutbox

logger = logging.getLogger(__name__)

OutboxHandler = Callable[[str, dict], Awaitable[None]]


class WorkflowOutboxDispatcher:
    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts

    async def dispatch_ready(
        self,
        db: AsyncSession,
        handler: OutboxHandler,
        limit: int = 100,
    ) -> int:
        now = utc_now()
        processed = 0
        seen_keys: set[str] = set()

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
                # Deduplication check: if idempotency key was already processed in this batch
                if event.idempotency_key in seen_keys:
                    event.status = "PROCESSED"
                    event.processed_at = utc_now()
                    continue

                # Check if another event with the same idempotency key is already PROCESSED
                existing_processed = await db.scalar(
                    select(WorkflowOutbox.outbox_id).where(
                        WorkflowOutbox.idempotency_key == event.idempotency_key,
                        WorkflowOutbox.status == "PROCESSED",
                        WorkflowOutbox.outbox_id != event.outbox_id,
                    ).limit(1)
                )
                if existing_processed:
                    event.status = "PROCESSED"
                    event.processed_at = utc_now()
                    seen_keys.add(event.idempotency_key)
                    continue

                event.status = "PROCESSING"
                event.attempts += 1
                try:
                    await handler(event.event_type, event.payload)
                except Exception as exc:
                    err_str = str(exc)[:2000]
                    event.last_error = err_str

                    # Failure classification
                    is_poison = (
                        isinstance(exc, (ValueError, KeyError, TypeError))
                        or "poison" in err_str.lower()
                        or "malformed" in err_str.lower()
                    )

                    if is_poison:
                        event.status = "DEAD_LETTER"
                        classification = "POISON_PAYLOAD"
                    elif event.attempts >= self.max_attempts:
                        event.status = "DEAD_LETTER"
                        classification = "MAX_ATTEMPTS_EXCEEDED"
                    else:
                        event.status = "PENDING"
                        classification = "TRANSIENT_ERROR"
                        # Bounded exponential backoff + jitter
                        base_backoff = min(300, 2 ** event.attempts)
                        jitter = random.uniform(0.75, 1.25)
                        backoff_seconds = base_backoff * jitter
                        event.available_at = utc_now() + timedelta(seconds=backoff_seconds)

                    if event.status == "DEAD_LETTER":
                        logger.error(
                            "Outbox event %s routed to DEAD_LETTER | classification=%s | error=%s",
                            event.outbox_id,
                            classification,
                            err_str,
                        )
                        # Structured audit event for DLQ alert
                        db.add(
                            AuditEvent(
                                job_id=event.job_id,
                                event_type="OUTBOX_DEAD_LETTER",
                                actor_type="SYSTEM",
                                actor_id="WorkflowOutboxDispatcher",
                                target_resource=str(event.outbox_id),
                                payload={
                                    "event_type": event.event_type,
                                    "idempotency_key": event.idempotency_key,
                                    "attempts": event.attempts,
                                    "classification": classification,
                                    "last_error": err_str,
                                },
                            )
                        )
                else:
                    event.status = "PROCESSED"
                    event.processed_at = utc_now()
                    seen_keys.add(event.idempotency_key)
                    processed += 1

            await db.commit()
        return processed


workflow_outbox_dispatcher = WorkflowOutboxDispatcher()
