"""TestCase and TestResult domain persistence models."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import (
    Boolean,
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


class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = {"extend_existing": True}

    test_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("modules.module_id", ondelete="SET NULL"), nullable=True, index=True
    )
    test_layer: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fixture_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "test_layer IN ('UNIT', 'API_CONTRACT', 'DATA_EFFECT', 'BATCH', 'UI_FLOW')",
            name="chk_test_layer"
        ),
        Index("ix_test_cases_job_layer", "job_id", "test_layer"),
    )

    job = relationship("Job", back_populates="test_cases")
    module = relationship("Module", back_populates="test_cases")
    results = relationship("TestResult", back_populates="test_case", cascade="all, delete-orphan")


class TestResult(Base):
    __tablename__ = "test_results"

    result_id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("test_cases.test_case_id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("module_attempts.attempt_id", ondelete="SET NULL"), nullable=True, index=True
    )
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    difference_classification: Mapped[str] = mapped_column(
        String(50), default="NONE", nullable=False
    )
    legacy_output: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    converted_output: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    invalidated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invalidation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("outcome IN ('PASSED', 'FAILED')", name="chk_test_outcome"),
        CheckConstraint(
            "difference_classification IN ('NONE', 'REGRESSION', 'INTENDED_DIFFERENCE', 'NONDETERMINISTIC', 'TEST_DEFECT')",
            name="chk_difference_classification"
        ),
    )

    test_case = relationship("TestCase", back_populates="results")
    attempt = relationship("ModuleAttempt", back_populates="test_results")
