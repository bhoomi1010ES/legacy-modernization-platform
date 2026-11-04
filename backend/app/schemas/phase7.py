"""Phase 7 inputs contain identities, never commands, patches or execution results."""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class IntegrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8, max_length=100)


class PackageRequest(IntegrationRequest):
    report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class SystemCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal[
        "build", "unit", "integration", "static", "security", "schema", "sbom",
        "dependency", "license", "runtime", "api_compatibility"
    ]
    command: list[str] = Field(min_length=1, max_length=32)


class JobReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "phase7-job-report-v1"
    job_id: str
    run_id: str
    status: str
    source_stack: str
    target_stack: str
    source_commit: str
    integrated_commit: str | None = None
    branch: str = ""
    candidate_hash: str
    baseline_hash: str
    plan_hash: str
    gate_ids: dict[str, str]
    modules: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    counts: dict[str, int]
    coverage: dict[str, Any]
    findings: list[dict[str, Any]]
    waivers: list[dict[str, Any]]
    costs: dict[str, Any]
    duration_ms: float
    limitations: list[str]
    evidence: dict[str, Any]
