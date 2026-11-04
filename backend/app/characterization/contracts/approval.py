"""Contracts for Gate G2 human approval and freeze decisions."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.characterization.contracts.enums import G2Decision


class GateG2Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: G2Decision
    rationale: str = Field(..., min_length=10)
    conditions: List[str] = Field(default_factory=list)


class G2ApprovalDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str
    job_id: str
    suite_id: str
    suite_version: int
    suite_content_hash: str
    decision: G2Decision
    decided_by: str
    rationale: str
    conditions: List[str] = Field(default_factory=list)
    is_valid: bool = True
    invalidation_reason: Optional[str] = None
    decided_at: str


class GateG2CompletionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    suite_id: str
    suite_version: int
    content_hash: str
    decision: G2Decision
    frozen_at: str
    aggregate_coverage: float
    total_scenarios_frozen: int

