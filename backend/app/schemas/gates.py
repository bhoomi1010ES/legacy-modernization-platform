"""Approval gate request, decision, and detail schemas."""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class GateType(str, Enum):
    G1 = "G1"  # Feasibility Decision
    G2 = "G2"  # Characterization Freeze
    G3 = "G3"  # Blueprint & Conversion Plan
    G4 = "G4"  # Final Equivalence & Delivery


class DecisionOutcome(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_CHANGES = "NEEDS_CHANGES"


class WaiverItem(BaseModel):
    test_id: str
    difference_type: str
    waiver_rationale: str = Field(..., min_length=10)


class GateDecisionRequest(BaseModel):
    decision: DecisionOutcome = Field(..., description="Approval or rejection decision.")
    rationale: str = Field(..., min_length=10, description="Mandatory written rationale explaining the review decision (minimum 10 characters).")
    waivers: list[WaiverItem] = Field(default_factory=list, description="Signed waivers for intended differences at Gate G4.")
    options: Optional[dict[str, str]] = Field(default_factory=dict, description="Chosen gap resolutions for Gate G1 (e.g. adapter selection).")
    artifact_hashes: dict[str, str] = Field(default_factory=dict, description="Artifact hashes observed by the reviewer.")
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=255)


class GateDecisionResponse(BaseModel):
    decision_id: str
    job_id: str
    gate_id: str
    gate_type: GateType
    decision: DecisionOutcome
    rationale: str
    reviewer: str
    decided_at: str


class GateVerificationItem(BaseModel):
    id: str
    title: str
    description: str
    mandatory: bool = True


class GateMetricItem(BaseModel):
    label: str
    value: str
    subtext: Optional[str] = None
    badge: Optional[str] = None


class GateVerificationGuide(BaseModel):
    producing_agent: str
    producing_agent_role: str
    work_summary: str
    key_deliverables: list[str] = Field(default_factory=list)
    metrics: list[GateMetricItem] = Field(default_factory=list)
    checklist: list[GateVerificationItem] = Field(default_factory=list)
    next_agent: str
    next_agent_role: str
    next_agent_preview: str


class GateDetailResponse(BaseModel):
    gate_id: str
    job_id: str
    job_name: str
    gate_type: GateType
    title: str
    description: str
    status: str
    artifact: str
    artifact_hash: str
    cost_summary: str
    requested_at: str
    decided_at: Optional[str] = None
    reviewer: Optional[str] = None
    version: int = 1
    rationale: Optional[str] = None
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    allowed_actions: list[str] = Field(default_factory=list)
    verification_guide: Optional[GateVerificationGuide] = None


class PendingGatesResponse(BaseModel):
    items: list[GateDetailResponse]
    total: int
