"""GateDecision domain persistence model."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, utc_now


class GateDecision(Base):
    __tablename__ = "gate_decisions"

    decision_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    gate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("workflow_gates.gate_id", ondelete="SET NULL"), nullable=True, index=True
    )
    gate_type: Mapped[str] = mapped_column(String(10), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    waivers: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    selected_options: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    artifact_hashes: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.user_id"), nullable=False, index=True
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("gate_type IN ('G1', 'G2', 'G3', 'G4')", name="chk_gate_type"),
        CheckConstraint("decision IN ('APPROVED', 'REJECTED', 'NEEDS_CHANGES')", name="chk_gate_decision"),
        Index("ix_gate_decisions_job_gate", "job_id", "gate_type"),
    )

    job = relationship("Job", back_populates="gate_decisions")
    workflow_gate = relationship("WorkflowGate", back_populates="decisions")
    reviewer = relationship("User", back_populates="gate_decisions")
