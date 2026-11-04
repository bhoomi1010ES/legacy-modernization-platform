"""Contracts for the top-level immutable CharacterizationSuite artifact."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.characterization.contracts.behavior import BehaviorSpecification
from app.characterization.contracts.coverage import CoverageReport
from app.characterization.contracts.observations import ExecutionObservation
from app.characterization.contracts.scenarios import ExecutionResult, ScenarioCatalog
from app.characterization.contracts.test_inventory import TestInventory
from app.characterization.contracts.uncertainty import UncertaintyReport
from app.characterization.contracts.workflows import WorkflowInventory


class CharacterizationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    workspace_path: str
    source_commit_sha: Optional[str] = None
    target_stack: Optional[str] = None
    execution_timeout_seconds: int = 180


class CharacterizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    max_scenarios: int = Field(default=50, ge=1, le=200)
    enable_iterative_refinement: bool = True
    coverage_threshold: float = Field(default=60.0, ge=0.0, le=100.0)


class CharacterizationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_id: str
    job_id: str
    version: int = 1
    content_hash: str = ""
    test_inventory: TestInventory
    workflow_inventory: WorkflowInventory
    scenario_catalog: ScenarioCatalog
    execution_results: List[ExecutionResult] = Field(default_factory=list)
    observations: List[ExecutionObservation] = Field(default_factory=list)
    behavior_specification: BehaviorSpecification
    coverage_report: CoverageReport
    uncertainty_report: UncertaintyReport
    is_partial: bool = False
    is_frozen: bool = False
    frozen_at: Optional[str] = None
    created_at: str

