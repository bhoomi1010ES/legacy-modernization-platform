"""Contracts for empirical uncertainty reporting."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class UncertaintyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uncertainty_id: str
    target_workflow: str
    nature: str
    impact: str
    recommended_mitigation: str
    observed_in_scenarios: List[str] = Field(default_factory=list)


class UncertaintyReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_uncertainties: int = Field(default=0, ge=0)
    records: List[UncertaintyRecord] = Field(default_factory=list)
    risk_level: str = "LOW"

