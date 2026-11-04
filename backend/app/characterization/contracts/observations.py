"""Contracts for empirical execution observation and side-effects."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class StateChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    change_type: str = Field(..., description="FILE_CREATED, FILE_MODIFIED, FILE_DELETED, DB_MUTATION, NETWORK_CALL")
    target: str
    details: Dict[str, Any] = Field(default_factory=dict)
    before_hash: Optional[str] = None
    after_hash: Optional[str] = None


class SideEffectInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    created_files: List[str] = Field(default_factory=list)
    modified_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)
    outbound_calls: List[str] = Field(default_factory=list)
    storage_mutations: int = Field(default=0, ge=0)


class ExecutionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str
    scenario_id: str
    workflow_id: str
    execution_mode: str = Field(..., description="DOCKER_CONTAINER, HOST_PROCESS_FALLBACK, IN_MEMORY_DOUBLE")
    duration_ms: float
    exit_code: int
    raw_output: Any = None
    normalized_output: Any = None
    side_effects: SideEffectInventory
    state_changes: List[StateChange] = Field(default_factory=list)
    reproducibility: str = Field(default="DETERMINISTIC", description="DETERMINISTIC, NON_DETERMINISTIC, FAILED, UNAVAILABLE")
    captured_at: str

