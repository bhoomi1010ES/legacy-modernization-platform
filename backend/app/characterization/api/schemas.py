"""Request and response schemas for characterization REST endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.characterization.contracts.enums import CharacterizationStage, ExecutionStatus, G2Decision


class CharacterizationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_scenarios: int = Field(default=50, ge=1, le=200)
    enable_iterative_refinement: bool = True
    coverage_threshold: float = Field(default=60.0, ge=0.0, le=100.0)


class CharacterizationExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    job_id: str
    status: ExecutionStatus
    stage: CharacterizationStage
    stage_progress_pct: int
    summary: Optional[str] = None
    started_at: Optional[str] = None


class GateG2DecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: G2Decision
    rationale: str = Field(..., min_length=10)
    conditions: List[str] = Field(default_factory=list)


class GateG2StatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    ready: bool
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    latest_decision: Optional[Dict[str, Any]] = None

