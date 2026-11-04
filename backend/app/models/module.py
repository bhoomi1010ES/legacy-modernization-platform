"""Module and ModuleAttempt domain persistence models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
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
    event,
    inspect,
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
    lease_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expected_input_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    plan_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    upstream_approval_hashes: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    integration_base_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    accepted_result_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    interfaces: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_output_paths: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    required_tests: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    schema_dependencies: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_resources: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("risk_level IN ('LOW', 'MEDIUM', 'HIGH')", name="chk_module_risk_level"),
        Index("ix_modules_job_status", "job_id", "status"),
        Index("ix_modules_job_wave", "job_id", "wave_number"),
    )

    job = relationship("Job", back_populates="modules")
    attempts = relationship("ModuleAttempt", back_populates="module", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="module")
    artifacts = relationship("Artifact", back_populates="module")
    parent_dependencies = relationship(
        "ModuleDependency",
        foreign_keys="ModuleDependency.child_id",
        back_populates="child",
        cascade="all, delete-orphan",
    )
    child_dependencies = relationship(
        "ModuleDependency",
        foreign_keys="ModuleDependency.parent_id",
        back_populates="parent",
        cascade="all, delete-orphan",
    )


class ModuleDependency(Base):
    __tablename__ = "module_dependencies"

    dependency_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("modules.module_id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("modules.module_id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("parent_id", "child_id", name="uq_module_dependency_parent_child"),
    )

    job = relationship("Job")
    parent = relationship("Module", foreign_keys=[parent_id], back_populates="child_dependencies")
    child = relationship("Module", foreign_keys=[child_id], back_populates="parent_dependencies")


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
    worker_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("module_id", "attempt_number", name="uq_module_attempt_number"),
        CheckConstraint("attempt_number <= 50", name="chk_attempt_number_limit"),
    )

    module = relationship("Module", back_populates="attempts")
    agent_run = relationship("AgentRun", back_populates="module_attempts")
    test_results = relationship("TestResult", back_populates="attempt")
    verification_runs = relationship("VerificationRun", back_populates="attempt")


class VerificationRun(Base):
    """Append-only verifier work item pinned to one candidate and frozen suite."""

    __tablename__ = "verification_runs"

    verification_run_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID, ForeignKey("module_attempts.attempt_id", ondelete="CASCADE"), nullable=True, index=True)
    integration_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID, ForeignKey("agent_runs.run_id", ondelete="CASCADE"), nullable=True, index=True)
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID, ForeignKey("agent_runs.run_id", ondelete="SET NULL"), nullable=True, index=True)
    candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    suite_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    lease_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="QUEUED")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('QUEUED', 'RUNNING', 'PASS', 'FAIL', 'BLOCKED')", name="chk_verification_run_status"),
    )

    attempt = relationship("ModuleAttempt", back_populates="verification_runs")


@event.listens_for(VerificationRun, "before_update")
def _reject_verification_run_rewrite(mapper, connection, target):
    """A terminal run is append-only evidence; retries allocate a new run row."""
    state = inspect(target)
    previous = state.attrs.status.history.deleted
    old_status = previous[0] if previous else target.status
    if old_status in {"PASS", "FAIL", "BLOCKED"}:
        raise ValueError("Terminal VerificationRun evidence is immutable")
