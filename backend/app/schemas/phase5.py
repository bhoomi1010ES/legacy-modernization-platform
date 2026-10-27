"""Versioned characterization and disposable migration input contracts."""

from typing import Any, Literal
import logging
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NormalizationRule(StrictInput):
    path: str = Field(pattern=r"^(?:/(?:[A-Za-z0-9_-]|~[01])+)+$")
    kind: Literal["timestamp", "random_id", "unordered"]
    justification: str = Field(min_length=10, max_length=1000)
    contract_allows: bool = False

    @field_validator("justification")
    @classmethod
    def nonblank_justification(cls, value: str) -> str:
        try:
            if len(value.strip()) < 10:
                raise ValueError("Normalization requires an explanatory justification")
            return value.strip()
        except Exception:
            logger.exception("phase5.nonblank_justification failed")
            raise


class Scenario(StrictInput):
    name: str = Field(min_length=1, max_length=200)
    module: str = Field(min_length=1, max_length=200)
    interface: str = Field(min_length=1, max_length=200)
    behavior: str = Field(min_length=1, max_length=500)
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected: Any = None
    normalization: list[NormalizationRule] = Field(default_factory=list, max_length=50)
    known_bug: str | None = Field(default=None, max_length=2000)


class Column(StrictInput):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
    type: Literal["INTEGER", "REAL", "TEXT", "BLOB"] = "TEXT"
    nullable: bool = True
    primary_key: bool = False
    unique: bool = False
    max_length: int | None = Field(default=None, ge=1, le=1000000)
    references_table: str | None = Field(
        default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,62}$"
    )
    references_column: str | None = Field(
        default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,62}$"
    )


class Table(StrictInput):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
    columns: list[Column] = Field(min_length=1, max_length=100)


class CaptureRequest(StrictInput):
    idempotency_key: str = Field(min_length=1, max_length=100)
    scenarios: list[Scenario] = Field(default_factory=list, max_length=200)
    tables: list[Table] = Field(default_factory=list, max_length=100)
    target_tables: list[Table] = Field(default_factory=list, max_length=100)
    environment: dict[str, str] = Field(
        default_factory=dict,
        description="Replay notes only; never injected into a process",
    )

    @model_validator(mode="after")
    def controlled_inputs(self):
        try:
            for scenario in self.scenarios:
                reject_unsafe_inputs(scenario.inputs)
            reject_unsafe_inputs(self.environment)
            return self
        except Exception:
            logger.exception("phase5.controlled_inputs failed")
            raise


def reject_unsafe_inputs(value: Any) -> None:
    """Accept test fixtures, never process controls or production connection material."""
    try:
        from app.services.secret_redactor import get_secret_redactor

        if isinstance(value, dict):
            for key, item in value.items():
                name = str(key).lower().replace("-", "_")
                if name in {
                    "command",
                    "shell",
                    "argv",
                    "adapter_command",
                    "mounts",
                    "host_mount",
                    "database_url",
                    "connection_url",
                    "dsn",
                    "observations",
                    "execution_results",
                }:
                    raise ValueError(
                        "Process controls, connections and supplied observations are prohibited"
                    )
                if any(
                    word in name
                    for word in ("password", "credential", "secret", "token", "api_key")
                ) and not (
                    isinstance(item, str)
                    and item.startswith(("fixture-", "test-", "dummy-"))
                ):
                    raise ValueError("Only synthetic test credentials are permitted")
                reject_unsafe_inputs(item)
        elif isinstance(value, list):
            for item in value:
                reject_unsafe_inputs(item)
        elif isinstance(value, str):
            if (
                re.search(
                    r"(?i)(?:postgres(?:ql)?(?:\+\w+)?|mysql|mssql|mongodb(?:\+srv)?|redis|sqlite)://",
                    value,
                )
                or get_secret_redactor().redact_text(value) != value
            ):
                raise ValueError("Production connections and secrets are prohibited")
    except Exception:
        logger.exception("phase5.reject_unsafe_inputs failed")
        raise


class FreezeRequest(StrictInput):
    suite_id: str
    content_hash: str


class SampleTable(StrictInput):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)


class ValidationRequest(StrictInput):
    scope: Literal["disposable"] = "disposable"
    tables: list[SampleTable] = Field(default_factory=list, max_length=100)


class CaseEvidence(StrictInput):
    test_case_id: str
    name: str
    module: str
    interface: str
    behavior: str
    fixtures: dict[str, Any]
    expected: Any
    actual: Any
    outcome: Literal["PASSED", "FAILED", "UNAVAILABLE", "NON_REPRODUCIBLE"]
    normalization: list[NormalizationRule]
    known_bug: str | None
    side_effects: Any
    limitation: str | None
    evidence_status: Literal["OBSERVED", "UNOBSERVED"] = "UNOBSERVED"
    observed_candidate: bool = False


class CoverageEntry(StrictInput):
    name: str
    covered: bool
    status: str = "UNTESTED"
    observed: bool = False


class CoverageReport(StrictInput):
    modules: list[CoverageEntry]
    interfaces: list[CoverageEntry]
    behaviors: list[CoverageEntry]
    untested_paths: list[str]
    percent: float = Field(ge=0, le=100)
    limitations: list[str]
    executed_behaviors: list[str] = Field(default_factory=list)


class SuiteArtifact(StrictInput):
    schema_version: Literal["5.1"]
    cases: list[CaseEvidence]
    runtime_available: bool
    coverage: CoverageReport
    known_bugs: list[str]
    normalization: list[NormalizationRule]
    environment: dict[str, Any]
    discovered_tests: list[str]
    discovery_evidence: list[dict[str, Any]] = Field(default_factory=list)
    schema_artifact_id: str
    schema_hash: str
    g2_readiness: dict[str, Any] | None = None
    candidate_scenarios: list[dict[str, Any]] = Field(default_factory=list)
