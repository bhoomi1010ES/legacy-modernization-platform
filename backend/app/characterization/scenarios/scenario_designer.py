"""Multidimensional Scenario Designer (Positive, Boundary, Invalid Input, Error Path)."""

import hashlib
from typing import Dict, List

from app.characterization.contracts.enums import ScenarioType
from app.characterization.contracts.scenarios import ScenarioCatalog, ScenarioDefinition
from app.characterization.contracts.workflows import WorkflowDefinition, WorkflowInventory


class MultidimensionalScenarioDesigner:
    """Generates 4-quadrant behavioral scenario suites for discovered workflows."""

    def design_catalog(
        self,
        workflow_inventory: WorkflowInventory,
        max_scenarios: int = 50,
    ) -> ScenarioCatalog:
        """Design positive, boundary, invalid input, and error scenarios for each workflow."""
        scenarios: List[ScenarioDefinition] = []
        by_type: Dict[str, int] = {st.value: 0 for st in ScenarioType}
        by_workflow: Dict[str, int] = {}

        for wf in workflow_inventory.workflows:
            wf_scenarios = self._design_for_workflow(wf)
            by_workflow[wf.workflow_id] = 0

            for sc in wf_scenarios:
                if len(scenarios) >= max_scenarios:
                    break
                scenarios.append(sc)
                by_type[sc.scenario_type.value] = by_type.get(sc.scenario_type.value, 0) + 1
                by_workflow[wf.workflow_id] += 1

            if len(scenarios) >= max_scenarios:
                break

        return ScenarioCatalog(
            total_scenarios=len(scenarios),
            scenarios=scenarios,
            by_type=by_type,
            by_workflow=by_workflow,
        )

    design = design_catalog

    def _design_for_workflow(self, wf: WorkflowDefinition) -> List[ScenarioDefinition]:
        """Generate 4-quadrant scenarios for a single workflow."""
        results: List[ScenarioDefinition] = []
        domain = wf.domain
        primary_ep = wf.entrypoints[0] if wf.entrypoints else None
        target_path = primary_ep.path if primary_ep else f"/{domain}"

        # 1. POSITIVE: Happy path with nominal inputs
        pos_id = self._deterministic_id(wf.workflow_id, ScenarioType.POSITIVE, 1)
        results.append(
            ScenarioDefinition(
                scenario_id=pos_id,
                workflow_id=wf.workflow_id,
                scenario_type=ScenarioType.POSITIVE,
                name=f"{domain.capitalize()} Nominal Execution",
                objective=f"Verify nominal successful execution of {wf.name} on path '{target_path}'.",
                inputs={
                    "path": target_path,
                    "method": primary_ep.method if primary_ep else "GET",
                    "payload": {"id": 101, "name": f"test_{domain}", "active": True},
                },
                expected_status_code=200,
                expected_outcome="SUCCESS",
            )
        )

        # 2. BOUNDARY: Extreme values and limits
        bnd_id = self._deterministic_id(wf.workflow_id, ScenarioType.BOUNDARY, 2)
        results.append(
            ScenarioDefinition(
                scenario_id=bnd_id,
                workflow_id=wf.workflow_id,
                scenario_type=ScenarioType.BOUNDARY,
                name=f"{domain.capitalize()} Boundary Values",
                objective=f"Verify behavior under boundary conditions (zero, max length, extreme bounds) for {wf.name}.",
                inputs={
                    "path": target_path,
                    "method": primary_ep.method if primary_ep else "GET",
                    "payload": {"id": 0, "name": "X" * 1024, "count": 2147483647},
                },
                expected_status_code=200,
                expected_outcome="BOUNDARY_ACCEPTED",
            )
        )

        # 3. INVALID_INPUT: Malformed or missing required schema keys
        inv_id = self._deterministic_id(wf.workflow_id, ScenarioType.INVALID_INPUT, 3)
        results.append(
            ScenarioDefinition(
                scenario_id=inv_id,
                workflow_id=wf.workflow_id,
                scenario_type=ScenarioType.INVALID_INPUT,
                name=f"{domain.capitalize()} Malformed Schema Rejection",
                objective=f"Verify schema validation cleanly rejects malformed or missing fields for {wf.name}.",
                inputs={
                    "path": target_path,
                    "method": primary_ep.method if primary_ep else "POST",
                    "payload": {"invalid_key_null": None, "type_mismatch": 999999999},
                },
                expected_status_code=400,
                expected_outcome="VALIDATION_REJECTION",
            )
        )

        # 4. ERROR_PATH: Missing entity ID / unauthorized access
        err_id = self._deterministic_id(wf.workflow_id, ScenarioType.ERROR_PATH, 4)
        results.append(
            ScenarioDefinition(
                scenario_id=err_id,
                workflow_id=wf.workflow_id,
                scenario_type=ScenarioType.ERROR_PATH,
                name=f"{domain.capitalize()} Missing Entity Not Found",
                objective=f"Verify 404 / error recovery when querying non-existent entity in {wf.name}.",
                inputs={
                    "path": f"{target_path.rstrip('/')}/non_existent_99999",
                    "method": "GET",
                    "payload": {},
                },
                expected_status_code=404,
                expected_outcome="NOT_FOUND_RECOVERY",
            )
        )

        return results

    def _deterministic_id(self, wf_id: str, st: ScenarioType, idx: int) -> str:
        h = hashlib.sha256(f"{wf_id}:{st.value}:{idx}".encode("utf-8")).hexdigest()[:10]
        return f"scen_{h}"
