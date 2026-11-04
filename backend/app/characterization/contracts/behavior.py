"""Contracts for empirical behavior synthesis and contradictions."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.characterization.contracts.enums import FindingClassification


class StateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    transition_id: str
    workflow_id: str
    from_state: str
    to_state: str
    trigger_action: str
    observed_mutations: List[str] = Field(default_factory=list)


class BehaviorRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    workflow_id: str
    scenario_id: Optional[str] = None
    condition: str
    consequence: str
    classification: FindingClassification
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    is_contradictory: bool = False
    contradiction_details: Optional[str] = None


class BehaviorSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_rules: int = Field(default=0, ge=0)
    rules: List[BehaviorRule] = Field(default_factory=list)
    state_transitions: List[StateTransition] = Field(default_factory=list)
    contradictions_count: int = Field(default=0, ge=0)
    contradictions: List[str] = Field(default_factory=list)

