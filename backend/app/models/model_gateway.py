"""Durable request and budget records for chargeable model gateway calls."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, utc_now


class ModelGatewayBudget(Base):
    __tablename__ = "model_gateway_budgets"
    __table_args__ = (
        CheckConstraint("budget_id = 1", name="ck_model_gateway_single_budget"),
        CheckConstraint("reserved_usd >= 0 AND spent_usd >= 0", name="ck_model_gateway_nonnegative_budget"),
    )

    budget_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    ceiling_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    reserved_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    spent_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ModelGatewayRequest(Base):
    __tablename__ = "model_gateway_requests"

    request_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    job_id: Mapped[Optional[UUID]] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="SET NULL"), nullable=True, index=True
    )
    run_id: Mapped[Optional[UUID]] = mapped_column(
        GUID, ForeignKey("agent_runs.run_id", ondelete="SET NULL"), nullable=True, index=True
    )
    attempt_id: Mapped[Optional[UUID]] = mapped_column(GUID, ForeignKey('module_attempts.attempt_id',ondelete='SET NULL'),nullable=True,index=True)
    selection_hash: Mapped[Optional[str]] = mapped_column(String(64),nullable=True)
    reconciliation_status: Mapped[Optional[str]] = mapped_column(String(40),nullable=True)
    charged_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12,6),nullable=True)
    released_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12,6),nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    requested_model: Mapped[str] = mapped_column(String(100), nullable=False)
    actual_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    prompt_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    estimated_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6), nullable=True)
    billed_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_limit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_model_gateway_requests_status_created", "status", "created_at"),
    )
