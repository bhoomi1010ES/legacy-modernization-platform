"""Phase 6 typed tasks and agent outputs; API callers cannot submit commands or results."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class QueueConversion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=80)


class RepairRequest(QueueConversion):
    rationale: str = Field(min_length=10, max_length=2000)


class WaiverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: str = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=10, max_length=2000)


class ChangeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    files: dict[str, str] = Field(min_length=1, max_length=100)
    design_notes: str = Field(min_length=1, max_length=10000)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    test_commands: list[list[str]] = Field(default_factory=list, max_length=20)


class CheckSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["build", "unit", "static", "security"]
    command: list[str] = Field(min_length=1, max_length=32)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    category: str
    message: str
    path: str | None = None
    line: int | None = None
    evidence_ref: str
