"""Worker registry domain persistence model."""

from datetime import datetime
from typing import Any, Dict
from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, utc_now


class WorkerRegistry(Base, TimestampMixin):
    __tablename__ = "worker_registry"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    worker_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    metadata_payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

