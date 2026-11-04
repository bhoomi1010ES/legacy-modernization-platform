"""Artifact and ArtifactDependency domain persistence models with versioning, cryptographic hashing, and lineage."""

from enum import Enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, utc_now
from app.core.errors import PlatformException


class ArtifactType(str, Enum):
    CONVERSION_PLAN = "CONVERSION_PLAN"
    TARGET_BLUEPRINT = "TargetBlueprint"
    LEGACY_MODEL = "LegacyModel"
    FEASIBILITY_REPORT = "FeasibilityReport"
    CHARACTERIZATION_SUITE = "CHARACTERIZATION_SUITE"
    SCHEMA_MIGRATION_PLAN = "SCHEMA_MIGRATION_PLAN"
    REPOSITORY_SNAPSHOT = "RepositorySnapshot"
    REPOSITORY_INVENTORY = "RepositoryInventory"
    ANALYSIS_REPORT = "AnalysisReport"
    CODE_MODULE = "CodeModule"
    TEST_RESULT = "TestResult"
    VERIFICATION_REPORT = "VerificationReport"
    REVIEW_REPORT = "ReviewReport"
    EQUIVALENCE_REPORT = "EquivalenceReport"
    SYSTEM_VERIFICATION = "SystemVerification"
    SBOM = "SBOM"
    INTEGRATION_REPORT = "IntegrationReport"
    JOB_REPORT = "JobReport"
    DELIVERY_RECORD = "DeliveryRecord"
    DELIVERY_PACKAGE = "DeliveryPackage"
    MODERNIZATION_MANIFEST = "ModernizationManifest"
    MODULE_SPECIFICATION = "ModuleSpecification"
    SHARED_BLUEPRINT = "SharedBlueprint"


CANONICAL_TYPE_MAP = {
    # ConversionPlan variants ALWAYS normalize to canonical CONVERSION_PLAN
    "CONVERSIONPLAN": ArtifactType.CONVERSION_PLAN.value,
    "CONVERSION_PLAN": ArtifactType.CONVERSION_PLAN.value,
    "CONVERSION_PLAN_MODEL": ArtifactType.CONVERSION_PLAN.value,

    # TargetBlueprint variants
    "TARGETBLUEPRINT": ArtifactType.TARGET_BLUEPRINT.value,
    "TARGET_BLUEPRINT": ArtifactType.TARGET_BLUEPRINT.value,
    "BLUEPRINT": ArtifactType.TARGET_BLUEPRINT.value,
    "SHAREDBLUEPRINT": ArtifactType.SHARED_BLUEPRINT.value,
    "SHARED_BLUEPRINT": ArtifactType.SHARED_BLUEPRINT.value,

    # LegacyModel variants
    "LEGACYMODEL": ArtifactType.LEGACY_MODEL.value,
    "LEGACY_MODEL": ArtifactType.LEGACY_MODEL.value,

    # FeasibilityReport variants
    "FEASIBILITYREPORT": ArtifactType.FEASIBILITY_REPORT.value,
    "FEASIBILITY_REPORT": ArtifactType.FEASIBILITY_REPORT.value,

    # CharacterizationSuite variants
    "CHARACTERIZATIONSUITE": ArtifactType.CHARACTERIZATION_SUITE.value,
    "CHARACTERIZATION_SUITE": ArtifactType.CHARACTERIZATION_SUITE.value,
    "BEHAVIORALBASELINE": ArtifactType.CHARACTERIZATION_SUITE.value,
    "BEHAVIORAL_BASELINE": ArtifactType.CHARACTERIZATION_SUITE.value,

    # SchemaMigrationPlan variants
    "SCHEMAMIGRATIONPLAN": ArtifactType.SCHEMA_MIGRATION_PLAN.value,
    "SCHEMA_MIGRATION_PLAN": ArtifactType.SCHEMA_MIGRATION_PLAN.value,
    "SCHEMAPLAN": ArtifactType.SCHEMA_MIGRATION_PLAN.value,
    "SCHEMA_PLAN": ArtifactType.SCHEMA_MIGRATION_PLAN.value,

    # RepositorySnapshot variants
    "REPOSITORYSNAPSHOT": ArtifactType.REPOSITORY_SNAPSHOT.value,
    "REPOSITORY_SNAPSHOT": ArtifactType.REPOSITORY_SNAPSHOT.value,

    # RepositoryInventory variants
    "REPOSITORYINVENTORY": ArtifactType.REPOSITORY_INVENTORY.value,
    "REPOSITORY_INVENTORY": ArtifactType.REPOSITORY_INVENTORY.value,

    # AnalysisReport variants
    "ANALYSISREPORT": ArtifactType.ANALYSIS_REPORT.value,
    "ANALYSIS_REPORT": ArtifactType.ANALYSIS_REPORT.value,

    # CodeModule / ModuleSpecification variants
    "CONVERTEDMODULE": ArtifactType.CODE_MODULE.value,
    "CONVERTED_MODULE": ArtifactType.CODE_MODULE.value,
    "CODEMODULE": ArtifactType.CODE_MODULE.value,
    "CODE_MODULE": ArtifactType.CODE_MODULE.value,
    "MODULESPECIFICATION": ArtifactType.MODULE_SPECIFICATION.value,
    "MODULE_SPECIFICATION": ArtifactType.MODULE_SPECIFICATION.value,

    # Verification evidence
    "TESTRESULT": ArtifactType.TEST_RESULT.value,
    "TEST_RESULT": ArtifactType.TEST_RESULT.value,
    "VERIFICATIONREPORT": ArtifactType.VERIFICATION_REPORT.value,
    "VERIFICATION_REPORT": ArtifactType.VERIFICATION_REPORT.value,
    "REVIEWREPORT": ArtifactType.REVIEW_REPORT.value,
    "REVIEW_REPORT": ArtifactType.REVIEW_REPORT.value,
    "EQUIVALENCEREPORT": ArtifactType.EQUIVALENCE_REPORT.value,
    "EQUIVALENCE_REPORT": ArtifactType.EQUIVALENCE_REPORT.value,
    "SYSTEMVERIFICATION": ArtifactType.SYSTEM_VERIFICATION.value,
    "SYSTEM_VERIFICATION": ArtifactType.SYSTEM_VERIFICATION.value,
    "SYSTEMVERIFICATIONREPORT": ArtifactType.SYSTEM_VERIFICATION.value,
    "SYSTEM_VERIFICATION_REPORT": ArtifactType.SYSTEM_VERIFICATION.value,
    "SBOM": ArtifactType.SBOM.value,
    "INTEGRATIONREPORT": ArtifactType.INTEGRATION_REPORT.value,
    "INTEGRATION_REPORT": ArtifactType.INTEGRATION_REPORT.value,
    "JOBREPORT": ArtifactType.JOB_REPORT.value,
    "JOB_REPORT": ArtifactType.JOB_REPORT.value,
    "DELIVERYRECORD": ArtifactType.DELIVERY_RECORD.value,
    "DELIVERY_RECORD": ArtifactType.DELIVERY_RECORD.value,
    "DELIVERYPACKAGE": ArtifactType.DELIVERY_PACKAGE.value,
    "DELIVERY_PACKAGE": ArtifactType.DELIVERY_PACKAGE.value,
    "MODERNIZATIONMANIFEST": ArtifactType.MODERNIZATION_MANIFEST.value,
    "MODERNIZATION_MANIFEST": ArtifactType.MODERNIZATION_MANIFEST.value,
}


def normalize_artifact_type(raw_type: str) -> str:
    """Normalize artifact type to canonical enum representation, rejecting unknown types."""
    if not raw_type or not isinstance(raw_type, str):
        raise PlatformException(
            code="INVALID_ARTIFACT_TYPE",
            message=f"Artifact type must be a non-empty string, got {raw_type!r}",
        )
    clean = raw_type.strip()
    upper = clean.upper()

    # Exact match on enum values
    for member in ArtifactType:
        if clean == member.value:
            return member.value

    # Look up alphanumeric normalized key in canonical map
    alpha = "".join(ch for ch in upper if ch.isalnum())
    if alpha in CANONICAL_TYPE_MAP:
        return CANONICAL_TYPE_MAP[alpha]

    if upper in CANONICAL_TYPE_MAP:
        return CANONICAL_TYPE_MAP[upper]

    valid = [t.value for t in ArtifactType]
    raise PlatformException(
        code="INVALID_ARTIFACT_TYPE",
        message=f"Unknown artifact type '{raw_type}'. Allowed canonical types: {valid}",
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("modules.module_id", ondelete="SET NULL"), nullable=True, index=True
    )
    producer_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("agent_runs.run_id", ondelete="SET NULL"), nullable=True, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0.0", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), default="application/json", nullable=False)
    producing_agent: Mapped[str] = mapped_column(String(100), nullable=False)
    derived_from: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    is_invalidated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invalidated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidation_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    extra_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("job_id", "artifact_type", "version", name="uq_artifact_version"),
        Index("ix_artifacts_job_type", "job_id", "artifact_type"),
        Index("ix_artifacts_lineage", "job_id", "created_at"),
    )

    job = relationship("Job", back_populates="artifacts")
    module = relationship("Module", back_populates="artifacts")
    producer_run = relationship("AgentRun", foreign_keys=[producer_run_id])
    downstream_dependencies = relationship(
        "ArtifactDependency",
        foreign_keys="ArtifactDependency.ancestor_artifact_id",
        back_populates="ancestor_artifact",
        cascade="all, delete-orphan",
    )
    upstream_dependencies = relationship(
        "ArtifactDependency",
        foreign_keys="ArtifactDependency.artifact_id",
        back_populates="artifact",
        cascade="all, delete-orphan",
    )


class ArtifactDependency(Base):
    __tablename__ = "artifact_dependencies"

    dependency_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("artifacts.artifact_id", ondelete="CASCADE"), nullable=False, index=True
    )
    ancestor_artifact_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("artifacts.artifact_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("artifact_id", "ancestor_artifact_id", name="uq_artifact_dependency"),
    )

    artifact = relationship("Artifact", foreign_keys=[artifact_id], back_populates="upstream_dependencies")
    ancestor_artifact = relationship("Artifact", foreign_keys=[ancestor_artifact_id], back_populates="downstream_dependencies")
