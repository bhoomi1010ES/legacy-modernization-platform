"""BudgetUsage domain persistence model for tracking token spend and financial caps."""

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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, utc_now


class BudgetUsage(Base):
    __tablename__ = "budget_usage"

    usage_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("agent_runs.run_id", ondelete="SET NULL"), nullable=True, index=True
    )
    cost_type: Mapped[str] = mapped_column(String(50), default="LLM_INFERENCE", nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0.0000"), nullable=False
    )
    tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_budget_usage_job_recorded", "job_id", "recorded_at"),
    )

    job = relationship("Job", back_populates="budget_records")
    agent_run = relationship("AgentRun", back_populates="budget_records")
