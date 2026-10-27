"""Verification and final delivery report schemas."""

from typing import Any
from pydantic import BaseModel, Field


class TestDifferenceClassification(BaseModel):
    test_name: str
    module: str
    classification: str  # REGRESSION, INTENDED_DIFFERENCE, NONDETERMINISTIC, TEST_DEFECT
    legacy_behavior: str
    converted_behavior: str
    resolution: str


class VerificationReportResponse(BaseModel):
    job_id: str
    total_tests: int
    passing_tests: int
    behavioral_equivalence_pct: float
    regressions_count: int
    intended_differences_count: int
    uncovered_code_pct: float | None
    differences: list[TestDifferenceClassification]
    limitations: list[str] = Field(default_factory=list)


class DeliveryReportResponse(BaseModel):
    job_id: str
    project_name: str
    integration_branch: str
    pull_request_url: str | None = None
    equivalence_pct: float
    signed_waivers_count: int
    production_cutover_included: bool = Field(False, description="Explicit disclaimer: cutover migrations are not automated.")
    included_artifacts: list[str]
    delivered_at: str | None
