"""AuditEvent domain persistence model for immutable, append-only audit logging."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, utc_now


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(50), default="USER", nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    target_resource: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM', 'AGENT')", name="chk_audit_actor_type"
        ),
        Index("ix_audit_events_job_created", "job_id", "created_at"),
        Index("ix_audit_events_type_created", "event_type", "created_at"),
    )

    job = relationship("Job", back_populates="audit_events")
