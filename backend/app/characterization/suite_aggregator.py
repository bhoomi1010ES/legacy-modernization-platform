"""Deterministic Suite Hashing and Aggregation Engine."""

import hashlib
import json
from typing import Any, Dict

from app.characterization.contracts.behavior import BehaviorSpecification
from app.characterization.contracts.coverage import CoverageReport
from app.characterization.contracts.observations import ExecutionObservation
from app.characterization.contracts.scenarios import ExecutionResult, ScenarioCatalog
from app.characterization.contracts.suite import CharacterizationSuite
from app.characterization.contracts.test_inventory import TestInventory
from app.characterization.contracts.uncertainty import UncertaintyReport
from app.characterization.contracts.workflows import WorkflowInventory


class SuiteAggregator:
    """Assembles all characterization sub-inventories and computes deterministic content hash."""

    VOLATILE_FIELDS = {"content_hash", "created_at", "frozen_at", "is_frozen"}

    def compute_suite_hash(self, suite_data: Dict[str, Any]) -> str:
        """Serialize canonical JSON payload stripping non-semantic timestamps and flags."""
        clean_data = {
            k: v for k, v in suite_data.items()
            if k not in self.VOLATILE_FIELDS
        }
        canonical_json = json.dumps(
            clean_data,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def aggregate(
        self,
        suite_id: str,
        job_id: str,
        version: int,
        test_inventory: TestInventory,
        workflow_inventory: WorkflowInventory,
        scenario_catalog: ScenarioCatalog,
        execution_results: list[ExecutionResult],
        observations: list[ExecutionObservation],
        behavior_spec: BehaviorSpecification,
        coverage_report: CoverageReport,
        uncertainty_report: UncertaintyReport,
        created_at: str,
        is_partial: bool = False,
    ) -> CharacterizationSuite:
        """Assemble domain models into a final hash-bound CharacterizationSuite."""
        preliminary_suite = CharacterizationSuite(
            suite_id=suite_id,
            job_id=job_id,
            version=version,
            content_hash="",
            test_inventory=test_inventory,
            workflow_inventory=workflow_inventory,
            scenario_catalog=scenario_catalog,
            execution_results=execution_results,
            observations=observations,
            behavior_specification=behavior_spec,
            coverage_report=coverage_report,
            uncertainty_report=uncertainty_report,
            is_partial=is_partial,
            is_frozen=False,
            frozen_at=None,
            created_at=created_at,
        )

        content_hash = self.compute_suite_hash(preliminary_suite.model_dump())

        return CharacterizationSuite(
            suite_id=suite_id,
            job_id=job_id,
            version=version,
            content_hash=content_hash,
            test_inventory=test_inventory,
            workflow_inventory=workflow_inventory,
            scenario_catalog=scenario_catalog,
            execution_results=execution_results,
            observations=observations,
            behavior_specification=behavior_spec,
            coverage_report=coverage_report,
            uncertainty_report=uncertainty_report,
            is_partial=is_partial,
            is_frozen=False,
            frozen_at=None,
            created_at=created_at,
        )

