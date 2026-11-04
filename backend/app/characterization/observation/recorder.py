"""Empirical execution recorder synthesizing observations and side-effects."""

from datetime import datetime, timezone
import uuid
from typing import Any, List

from app.characterization.contracts.observations import (
    ExecutionObservation,
    SideEffectInventory,
    StateChange,
)
from app.characterization.contracts.scenarios import ExecutionResult
from app.characterization.observation.normalizer import ObservationNormalizer


class ObservationRecorder:
    """Builds structured ExecutionObservation records with normalization."""

    def __init__(self):
        self.normalizer = ObservationNormalizer()

    def record(
        self,
        execution_result: ExecutionResult,
        execution_mode: str,
        created_files: List[str],
        modified_files: List[str],
        deleted_files: List[str],
        state_changes: List[StateChange],
        reproducibility: str = "DETERMINISTIC",
    ) -> ExecutionObservation:
        """Construct comprehensive observation from execution result and filesystem mutations."""
        side_effects = SideEffectInventory(
            created_files=created_files,
            modified_files=modified_files,
            deleted_files=deleted_files,
            outbound_calls=[],
            storage_mutations=len(created_files) + len(modified_files) + len(deleted_files),
        )

        raw_output = {
            "stdout": execution_result.stdout,
            "stderr": execution_result.stderr,
            "exit_code": execution_result.exit_code,
        }
        normalized_output = self.normalizer.normalize_data(raw_output)

        return ExecutionObservation(
            observation_id=f"obs_{uuid.uuid4().hex[:10]}",
            scenario_id=execution_result.scenario_id,
            workflow_id=execution_result.workflow_id,
            execution_mode=execution_mode,
            duration_ms=execution_result.duration_ms,
            exit_code=execution_result.exit_code,
            raw_output=raw_output,
            normalized_output=normalized_output,
            side_effects=side_effects,
            state_changes=state_changes,
            reproducibility=reproducibility,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )

