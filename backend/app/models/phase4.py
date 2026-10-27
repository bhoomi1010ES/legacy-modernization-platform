"""Phase 4 domain persistence models for intake, analysis, architect, feasibility, and planning."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class RepositorySnapshotModel(Base):
    __tablename__ = "repository_snapshots"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="git", nullable=False)
    source_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    commit_sha: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    inventory_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    archive_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tech_profile: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metadata_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_repo_snapshot_job_version"),
        Index("ix_repo_snapshots_job_created", "job_id", "created_at"),
    )
    job = relationship("Job", backref="repository_snapshots")


class RepositoryInventoryModel(Base):
    __tablename__ = "repository_inventories"

    inventory_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("repository_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    directories_payload: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    inventory_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    snapshot = relationship("RepositorySnapshotModel", backref="inventory_record")
    job = relationship("Job", backref="repository_inventories")


class AnalysisRunModel(Base):
    __tablename__ = "analysis_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("repository_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False)
    coordinator_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_analysis_run_job_version"),
    )
    job = relationship("Job", backref="analysis_runs")
    workers = relationship("AnalysisWorkerModel", back_populates="run", cascade="all, delete-orphan")


class AnalysisWorkerModel(Base):
    __tablename__ = "analysis_workers"

    worker_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    input_scope: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    findings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[str] = mapped_column(String(50), default="CONFIRMED", nullable=False)
    warnings: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    errors: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), default="deterministic-scanner", nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), default="v4.0", nullable=False)
    artifact_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    run = relationship("AnalysisRunModel", back_populates="workers")


class LegacyModelRecord(Base):
    __tablename__ = "legacy_models"

    model_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("repository_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False)
    modules_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    dependencies_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    interfaces_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    persistence_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    configurations_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    tests_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    risks_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    conflicts_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_legacy_model_job_version"),
    )
    job = relationship("Job", backref="legacy_models")


class AnalysisEvidenceRecord(Base):
    __tablename__ = "analysis_evidence"

    evidence_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    source_artifact: Mapped[str] = mapped_column(String(128), nullable=False)
    source_path: Mapped[str] = mapped_column(String(512), nullable=False)
    source_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    confidence: Mapped[str] = mapped_column(String(50), default="CONFIRMED", nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), default="analyzer", nullable=False)
    artifact_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("ix_analysis_evidence_job_path", "job_id", "source_path"),
    )
    job = relationship("Job", backref="analysis_evidence")


class AnalysisConflictRecord(Base):
    __tablename__ = "analysis_conflicts"

    conflict_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    claim_a: Mapped[str] = mapped_column(Text, nullable=False)
    claim_b: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_a: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence_b: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence_a: Mapped[str] = mapped_column(String(50), default="CONFIRMED", nullable=False)
    confidence_b: Mapped[str] = mapped_column(String(50), default="CONFIRMED", nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(50), default="UNRESOLVED", nullable=False)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    job = relationship("Job", backref="analysis_conflicts")


class TargetBlueprintModel(Base):
    __tablename__ = "target_blueprints"

    blueprint_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", nullable=False)
    target_stack: Mapped[str] = mapped_column(String(255), nullable=False)
    target_architecture: Mapped[str] = mapped_column(String(255), nullable=False)
    components_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    interfaces_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    data_model_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    integration_contracts_payload: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    constraints_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    accepted_decisions: Mapped[List[Any]] = mapped_column(JSON, default=list, nullable=False)
    evidence_refs: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), default="architect-agent", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_target_blueprint_job_version"),
    )
    job = relationship("Job", backref="target_blueprints")


class FeasibilityReportModel(Base):
    __tablename__ = "feasibility_reports"

    report_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    blueprint_version: Mapped[int] = mapped_column(Integer, nullable=False)
    legacy_model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    unsupported_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    custom_build_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    substitute_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unknown_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_feasibility_report_job_version"),
    )
    job = relationship("Job", backref="feasibility_reports")
    capabilities = relationship("FeasibilityCapabilityModel", back_populates="report", cascade="all, delete-orphan")


class FeasibilityCapabilityModel(Base):
    __tablename__ = "feasibility_capabilities"

    capability_record_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("feasibility_reports.report_id", ondelete="CASCADE"), nullable=False, index=True)
    capability_id: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    legacy_requirement: Mapped[str] = mapped_column(Text, nullable=False)
    target_requirement: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    tool_dependency: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    effort: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    risk: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    verification_impact: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    report = relationship("FeasibilityReportModel", back_populates="capabilities")


class FeasibilityDecisionModel(Base):
    __tablename__ = "feasibility_decisions"

    decision_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    capability_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_feasibility_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_blueprint_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    job = relationship("Job", backref="feasibility_decisions")


class PlannerRunModel(Base):
    __tablename__ = "planner_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_version: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_planner_run_job_version"),
    )
    job = relationship("Job", backref="planner_runs")
    outputs = relationship("PlannerOutputModel", back_populates="run", cascade="all, delete-orphan")


class PlannerOutputModel(Base):
    __tablename__ = "planner_outputs"

    output_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("planner_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    module_id: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    run = relationship("PlannerRunModel", back_populates="outputs")


class ConversionPlanModel(Base):
    __tablename__ = "conversion_plans"

    plan_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    blueprint_version: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(50), default="VALID", nullable=False)
    is_valid_dag: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    total_estimate_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_summary_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_conversion_plan_job_version"),
    )
    job = relationship("Job", backref="conversion_plans")
    modules = relationship("ConversionPlanModuleModel", back_populates="plan", cascade="all, delete-orphan")
    tasks = relationship("ConversionPlanTaskModel", back_populates="plan", cascade="all, delete-orphan")
    dependencies = relationship("ConversionPlanDependencyModel", back_populates="plan", cascade="all, delete-orphan")


class ConversionPlanModuleModel(Base):
    __tablename__ = "conversion_plan_modules"

    module_record_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("conversion_plans.plan_id", ondelete="CASCADE"), nullable=False, index=True)
    module_id: Mapped[str] = mapped_column(String(100), nullable=False)
    responsibility: Mapped[str] = mapped_column(Text, nullable=False)
    wave_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    estimate_hours: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    risk: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    acceptance_criteria: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    plan = relationship("ConversionPlanModel", back_populates="modules")


class ConversionPlanTaskModel(Base):
    __tablename__ = "conversion_plan_tasks"

    task_record_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("conversion_plans.plan_id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(100), nullable=False)
    module_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    estimate_hours: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    risk: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    acceptance_criteria: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    dependencies: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    plan = relationship("ConversionPlanModel", back_populates="tasks")


class ConversionPlanDependencyModel(Base):
    __tablename__ = "conversion_plan_dependencies"

    dependency_id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("conversion_plans.plan_id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(String(100), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(50), default="CODE_IMPORT", nullable=False)
    confidence: Mapped[str] = mapped_column(String(50), default="CONFIRMED", nullable=False)

    plan = relationship("ConversionPlanModel", back_populates="dependencies")
