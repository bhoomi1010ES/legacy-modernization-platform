"""Contracts for multi-paradigm route and workflow discovery."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class EntryPointDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entrypoint_id: str
    entrypoint_type: str = Field(..., description="REST_ENDPOINT, CLI_COMMAND, EVENT_HANDLER, HTML_FORM, WEB_ROUTE")
    path: str
    method: Optional[str] = None
    source_file: str
    line_number: Optional[int] = None
    signature: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_id: str
    name: str
    domain: str
    description: str
    entrypoints: List[EntryPointDefinition] = Field(default_factory=list)
    is_critical: bool = Field(default=False, description="Flagged for auth, payment, data mutation, or core transactions")
    dependencies: List[str] = Field(default_factory=list)
    declared_side_effects: List[str] = Field(default_factory=list)


class WorkflowInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_workflows: int = Field(default=0, ge=0)
    critical_workflows_count: int = Field(default=0, ge=0)
    workflows: List[WorkflowDefinition] = Field(default_factory=list)
    entrypoints: List[EntryPointDefinition] = Field(default_factory=list)
    domains_discovered: List[str] = Field(default_factory=list)

