"""Durable supervisor checkpoints, approval gates and transactional outbox."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, utc_now


class WorkflowCheckpoint(Base):
    __tablename__ = "workflow_checkpoints"

    checkpoint_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    checkpoint_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    state_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="uq_workflow_checkpoint_job_sequence"),
        CheckConstraint("checkpoint_kind IN ('BEFORE', 'AFTER', 'INTERRUPT', 'RECOVERY')", name="chk_workflow_checkpoint_kind"),
        Index("ix_workflow_checkpoint_job_created", "job_id", "created_at"),
    )
    job = relationship("Job", back_populates="workflow_checkpoints")


class WorkflowGate(Base):
    __tablename__ = "workflow_gates"

    gate_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    gate_type: Mapped[str] = mapped_column(String(10), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    artifact_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    artifact_hashes: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    blocking_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supersedes_gate_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID, ForeignKey("workflow_gates.gate_id", ondelete="SET NULL"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("job_id", "gate_type", "version", name="uq_workflow_gate_job_type_version"),
        CheckConstraint("gate_type IN ('G1', 'G2', 'G3', 'G4')", name="chk_workflow_gate_type"),
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'NEEDS_CHANGES', 'INVALIDATED', 'TIMED_OUT')", name="chk_workflow_gate_status"),
        Index("ix_workflow_gate_job_status", "job_id", "status"),
    )
    job = relationship("Job", back_populates="workflow_gates")
    decisions = relationship("GateDecision", back_populates="workflow_gate")


class WorkflowOutbox(Base):
    __tablename__ = "workflow_outbox"

    outbox_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'DEAD_LETTER')", name="chk_workflow_outbox_status"),
        Index("ix_workflow_outbox_ready", "status", "available_at"),
    )
    job = relationship("Job", back_populates="workflow_outbox_events")
