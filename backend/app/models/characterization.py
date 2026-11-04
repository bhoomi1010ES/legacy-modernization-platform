"""SQLAlchemy ORM models for Phase 5A Characterization and Gate G2."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, utc_now


class CharacterizationExecutionModel(Base):
    __tablename__ = "characterization_executions"
    __table_args__ = {"extend_existing": True}

    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    stage: Mapped[str] = mapped_column(String(64), default="INITIALIZING")
    stage_progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    total_scenarios_executed: Mapped[int] = mapped_column(Integer, default=0)
    total_workflows_characterized: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    scenarios = relationship("CharacterizationScenarioModel", back_populates="execution", cascade="all, delete-orphan")
    events = relationship("CharacterizationEventModel", back_populates="execution", cascade="all, delete-orphan")
    suites = relationship("CharacterizationSuiteModel", back_populates="execution", cascade="all, delete-orphan")


class CharacterizationSuiteModel(Base):
    __tablename__ = "characterization_suites"
    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_char_suite_job_version"),
        {"extend_existing": True},
    )

    suite_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("characterization_executions.execution_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    suite_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    is_partial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    frozen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    execution = relationship("CharacterizationExecutionModel", back_populates="suites")


class CharacterizationScenarioModel(Base):
    __tablename__ = "characterization_scenarios"
    __table_args__ = {"extend_existing": True}

    scenario_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    execution_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("characterization_executions.execution_id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    scenario_type: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PROPOSED", nullable=False)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    scenario_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    execution = relationship("CharacterizationExecutionModel", back_populates="scenarios")


class CharacterizationEventModel(Base):
    __tablename__ = "characterization_events"
    __table_args__ = (
        Index("ix_char_events_exec_seq", "execution_id", "sequence_number"),
        {"extend_existing": True},
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    execution_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("characterization_executions.execution_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    execution = relationship("CharacterizationExecutionModel", back_populates="events")


class GateG2ApprovalModel(Base):
    __tablename__ = "gate_g2_approvals"
    __table_args__ = {"extend_existing": True}

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("characterization_suites.suite_id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)
    suite_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(128), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    invalidation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

