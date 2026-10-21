"""Artifact domain persistence model with versioning, cryptographic hashing, and lineage."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    BigInteger,
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
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), default="application/json", nullable=False)
    producing_agent: Mapped[str] = mapped_column(String(100), nullable=False)
    derived_from: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
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
