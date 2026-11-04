"""AgentRun domain persistence model."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    JSON,
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
    task_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    model_provider: Mapped[str] = mapped_column(String(50), default="fake", nullable=False)
    model_identifier: Mapped[str] = mapped_column(
        String(100), default="fake-model-v1", nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0.0000"), nullable=False
    )
    
    # Provider usage recording (W06 requirement 5: separate nullable fields, unknown is null not 0)
    reported_input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reported_output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pricing_table_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    estimated_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    billed_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_classification: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    task_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    trace_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    input_artifact_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    output_artifact_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
