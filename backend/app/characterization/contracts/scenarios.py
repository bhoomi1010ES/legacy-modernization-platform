"""Contracts for multidimensional scenario design and execution results."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.characterization.contracts.enums import ScenarioStatus, ScenarioType


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    workflow_id: str
    scenario_type: ScenarioType
    name: str
    objective: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_status_code: Optional[int] = None
    expected_outcome: Optional[str] = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    prerequisites: List[str] = Field(default_factory=list)


class ScenarioCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_scenarios: int = Field(default=0, ge=0)
    scenarios: List[ScenarioDefinition] = Field(default_factory=list)
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_workflow: Dict[str, int] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    workflow_id: str
    status: ScenarioStatus
    passed: bool
    exit_code: int
    duration_ms: float
    stdout: str = ""
    stderr: str = ""
    error_message: Optional[str] = None

