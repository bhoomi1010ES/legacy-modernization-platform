"""Job and JobMembership domain persistence models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
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


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        GUID, default=uuid.uuid4, nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_repository: Mapped[str] = mapped_column(String(512), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(128), default="HEAD", nullable=False)
    source_stack: Mapped[str] = mapped_column(String(100), default="Java 8 / Spring Boot", nullable=False)
    target_stack: Mapped[str] = mapped_column(String(100), default="TypeScript / NestJS", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="CREATED", nullable=False, index=True)
    budget_limit_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("150.00"), nullable=False)
    budget_used_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    max_repair_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.user_id"), nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_repository: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    integration_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stack_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    workflow_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    workflow_phase: Mapped[str] = mapped_column(String(50), default="INTAKE", nullable=False, index=True)
    active_node: Mapped[str] = mapped_column(String(100), default="created", nullable=False)
    paused_from_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    blocking_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workflow_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_parallel_tasks: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    provider_concurrency_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    sandbox_concurrency_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_checkpoint_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_transition: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    terminal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    orchestration_owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    orchestration_lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    orchestration_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'INTAKE', 'ANALYZING', 'AWAITING_GATE_G1', 'CHARACTERIZING', "
            "'AWAITING_GATE_G2', 'PLANNING', 'AWAITING_GATE_G3', 'CONVERTING', 'VERIFYING', "
            "'INTEGRATING', 'AWAITING_GATE_G4', 'PAUSED', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="chk_job_status"
        ),
        Index("ix_jobs_owner_status", "owner_user_id", "status"),
        Index("ix_jobs_created_at_desc", "created_at"),
        CheckConstraint(
            "workflow_phase IN ('INTAKE', 'G1', 'CHARACTERIZATION', 'SCHEMA_DATA', 'G2', "
            "'PLANNING', 'G3', 'CONVERSION', 'VERIFICATION', 'INTEGRATION', 'G4', "
            "'COMPLETED', 'FAILED', 'CANCELLED')",
            name="chk_job_workflow_phase",
        ),
    )

    # Relationships
    owner = relationship("User", back_populates="owned_jobs")
    memberships = relationship("JobMembership", back_populates="job", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="job", cascade="all, delete-orphan")
    modules = relationship("Module", back_populates="job", cascade="all, delete-orphan")
    agent_runs = relationship("AgentRun", back_populates="job", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="job", cascade="all, delete-orphan")
    gate_decisions = relationship("GateDecision", back_populates="job", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="job", cascade="all, delete-orphan")
    budget_records = relationship("BudgetUsage", back_populates="job", cascade="all, delete-orphan")
    workflow_checkpoints = relationship("WorkflowCheckpoint", back_populates="job", cascade="all, delete-orphan")
    workflow_gates = relationship("WorkflowGate", back_populates="job", cascade="all, delete-orphan")
    workflow_outbox_events = relationship("WorkflowOutbox", back_populates="job", cascade="all, delete-orphan")

    @property
    def created_by_user_id(self) -> uuid.UUID:
        return self.owner_user_id



class JobMembership(Base):
    __tablename__ = "job_memberships"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("roles.role_id"), nullable=False, default="DEVELOPER"
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job_membership"),
        Index("ix_job_membership_user_role", "user_id", "role_id"),
    )

    job = relationship("Job", back_populates="memberships")
    user = relationship("User", back_populates="job_memberships")
    role = relationship("Role", back_populates="memberships")
