"""AgentRun domain persistence model."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, utc_now


class AgentRun(Base):
    __tablename__ = "agent_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_identifier: Mapped[str] = mapped_column(
        String(100), default="claude-3-5-sonnet-20241022", nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="COMPLETED", nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0.0000"), nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_agent_runs_job_agent", "job_id", "agent_name", "started_at"),
    )

    job = relationship("Job", back_populates="agent_runs")
    module_attempts = relationship("ModuleAttempt", back_populates="agent_run")
    budget_records = relationship("BudgetUsage", back_populates="agent_run")
