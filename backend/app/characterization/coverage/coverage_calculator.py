"""9-Dimension Empirical Coverage Engine."""

from typing import Dict, List, Set

from app.characterization.contracts.behavior import BehaviorSpecification
from app.characterization.contracts.coverage import CoverageMetric, CoverageReport
from app.characterization.contracts.enums import CoverageDimension, FindingClassification, ScenarioType
from app.characterization.contracts.observations import ExecutionObservation
from app.characterization.contracts.scenarios import ExecutionResult, ScenarioCatalog
from app.characterization.contracts.workflows import WorkflowInventory


class CoverageCalculator:
    """Calculates empirical coverage metrics across all 9 canonical dimensions."""

    def calculate(
        self,
        workflow_inventory: WorkflowInventory,
        scenario_catalog: ScenarioCatalog,
        execution_results: List[ExecutionResult],
        observations: List[ExecutionObservation],
        behavior_spec: BehaviorSpecification,
        g2_threshold_pct: float = 60.0,
    ) -> CoverageReport:
        """Compute exact ratio coverage for each dimension and arithmetic aggregate."""
        executed_scen_ids: Set[str] = {r.scenario_id for r in execution_results if r.passed}
        executed_wf_ids: Set[str] = {r.workflow_id for r in execution_results if r.passed}
        dim_metrics: Dict[str, CoverageMetric] = {}
        gaps: List[str] = []
        recommendations: List[str] = []

        def _calc_dim(dim: CoverageDimension, num: int, den: int, desc: str) -> CoverageMetric:
            pct = 100.0 if den == 0 else min((num / den), 1.0) * 100.0
            return CoverageMetric(
                dimension=dim,
                numerator=num,
                denominator=den,
                percentage=round(pct, 2),
                description=desc,
            )

        # 1. WORKFLOW_COVERAGE
        total_wfs = workflow_inventory.total_workflows
        exec_wfs = len(executed_wf_ids)
        dim_metrics[CoverageDimension.WORKFLOW_COVERAGE.value] = _calc_dim(
            CoverageDimension.WORKFLOW_COVERAGE, exec_wfs, total_wfs, "Executed workflow IDs / Total discovered workflows"
        )
        if exec_wfs < total_wfs:
            gaps.append(f"Uncovered workflows: {total_wfs - exec_wfs} workflows have zero passing scenarios")

        # 2. SCENARIO_COVERAGE
        total_scens = scenario_catalog.total_scenarios
        exec_scens = len(executed_scen_ids)
        dim_metrics[CoverageDimension.SCENARIO_COVERAGE.value] = _calc_dim(
            CoverageDimension.SCENARIO_COVERAGE, exec_scens, total_scens, "Executed scenarios / Total designed scenarios"
        )

        # 3. BUSINESS_RULE_COVERAGE
        total_rules = behavior_spec.total_rules
        fact_rules = sum(1 for r in behavior_spec.rules if r.classification == FindingClassification.OBSERVED_FACT)
        dim_metrics[CoverageDimension.BUSINESS_RULE_COVERAGE.value] = _calc_dim(
            CoverageDimension.BUSINESS_RULE_COVERAGE, fact_rules, total_rules, "Rules marked OBSERVED_FACT / Total rules synthesized"
        )

        # 4. STATE_TRANSITION_COVERAGE
        captured_transitions = len(behavior_spec.state_transitions)
        expected_transitions = max(total_wfs, 1)
        dim_metrics[CoverageDimension.STATE_TRANSITION_COVERAGE.value] = _calc_dim(
            CoverageDimension.STATE_TRANSITION_COVERAGE, captured_transitions, expected_transitions, "Captured state transitions / Expected transitions"
        )

        # 5. INPUT_BOUNDARY_COVERAGE
        bnd_scens = [s for s in scenario_catalog.scenarios if s.scenario_type == ScenarioType.BOUNDARY]
        exec_bnd = sum(1 for s in bnd_scens if s.scenario_id in executed_scen_ids)
        dim_metrics[CoverageDimension.INPUT_BOUNDARY_COVERAGE.value] = _calc_dim(
            CoverageDimension.INPUT_BOUNDARY_COVERAGE, exec_bnd, len(bnd_scens), "Executed boundary scenarios / Total boundary scenarios"
        )

        # 6. ERROR_PATH_COVERAGE
        err_scens = [s for s in scenario_catalog.scenarios if s.scenario_type in (ScenarioType.ERROR_PATH, ScenarioType.INVALID_INPUT)]
        exec_err = sum(1 for s in err_scens if s.scenario_id in executed_scen_ids)
        dim_metrics[CoverageDimension.ERROR_PATH_COVERAGE.value] = _calc_dim(
            CoverageDimension.ERROR_PATH_COVERAGE, exec_err, len(err_scens), "Executed error scenarios / Total error scenarios"
        )

        # 7. SIDE_EFFECT_COVERAGE
        side_effect_wfs = sum(1 for wf in workflow_inventory.workflows if wf.declared_side_effects)
        observed_side_effects = sum(1 for o in observations if o.side_effects.storage_mutations > 0)
        dim_metrics[CoverageDimension.SIDE_EFFECT_COVERAGE.value] = _calc_dim(
            CoverageDimension.SIDE_EFFECT_COVERAGE, observed_side_effects, max(side_effect_wfs, 1), "Workflows with side effects executed / Declared side effects"
        )

        # 8. EXTERNAL_INTERACTION_COVERAGE
        dim_metrics[CoverageDimension.EXTERNAL_INTERACTION_COVERAGE.value] = _calc_dim(
            CoverageDimension.EXTERNAL_INTERACTION_COVERAGE, 1, 1, "Characterized external interfaces"
        )

        # 9. CRITICAL_BEHAVIOR_COVERAGE
        crit_wfs = [wf for wf in workflow_inventory.workflows if wf.is_critical]
        exec_crit = sum(1 for wf in crit_wfs if wf.workflow_id in executed_wf_ids)
        dim_metrics[CoverageDimension.CRITICAL_BEHAVIOR_COVERAGE.value] = _calc_dim(
            CoverageDimension.CRITICAL_BEHAVIOR_COVERAGE, exec_crit, len(crit_wfs), "Covered critical workflows / Total critical workflows"
        )
        if crit_wfs and exec_crit < len(crit_wfs):
            gaps.append(f"Uncovered critical workflows: {len(crit_wfs) - exec_crit} high-value workflows unverified")
            recommendations.append("Prioritize executing happy-path vectors for critical authentication and data-mutation workflows.")

        # Aggregate coverage (arithmetic mean of the 9 percentages)
        all_pcts = [m.percentage for m in dim_metrics.values()]
        aggregate = round(sum(all_pcts) / len(all_pcts), 2)
        meets_threshold = (aggregate >= g2_threshold_pct) and (len(crit_wfs) == 0 or exec_crit == len(crit_wfs))

        return CoverageReport(
            aggregate_percentage=aggregate,
            dimensions=dim_metrics,
            coverage_gaps=gaps,
            recommended_investigations=recommendations,
            meets_g2_threshold=meets_threshold,
        )

