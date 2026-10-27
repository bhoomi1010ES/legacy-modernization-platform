"""Module and ModuleAttempt domain persistence models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, TimestampMixin, utc_now


class Module(Base, TimestampMixin):
    __tablename__ = "modules"

    module_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legacy_path: Mapped[str] = mapped_column(String(512), nullable=False)
    target_path: Mapped[str] = mapped_column(String(512), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    wave_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    dependency_module_ids: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    budget_limit_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)
    budget_used_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint("risk_level IN ('LOW', 'MEDIUM', 'HIGH')", name="chk_module_risk_level"),
        Index("ix_modules_job_status", "job_id", "status"),
        Index("ix_modules_job_wave", "job_id", "wave_number"),
    )

    job = relationship("Job", back_populates="modules")
    attempts = relationship("ModuleAttempt", back_populates="module", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="module")
    artifacts = relationship("Artifact", back_populates="module")


class ModuleAttempt(Base):
    __tablename__ = "module_attempts"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("modules.module_id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("agent_runs.run_id"), nullable=True, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False)
    git_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("module_id", "attempt_number", name="uq_module_attempt_number"),
        CheckConstraint("attempt_number <= 5", name="chk_attempt_number_limit"),
    )

    module = relationship("Module", back_populates="attempts")
    agent_run = relationship("AgentRun", back_populates="module_attempts")
    test_results = relationship("TestResult", back_populates="attempt")
