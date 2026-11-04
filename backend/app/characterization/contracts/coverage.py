"""Contracts for 9-dimension empirical coverage evaluation."""

from typing import Dict, List
from pydantic import BaseModel, ConfigDict, Field
from app.characterization.contracts.enums import CoverageDimension


class CoverageMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: CoverageDimension
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    percentage: float = Field(ge=0.0, le=100.0)
    description: str


class CoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    aggregate_percentage: float = Field(ge=0.0, le=100.0)
    dimensions: Dict[str, CoverageMetric] = Field(default_factory=dict)
    coverage_gaps: List[str] = Field(default_factory=list)
    recommended_investigations: List[str] = Field(default_factory=list)
    meets_g2_threshold: bool = Field(default=False)

