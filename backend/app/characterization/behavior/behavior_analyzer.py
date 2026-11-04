"""Empirical Behavior Synthesizer and Contradiction Detection Engine."""

from typing import Dict, List
import uuid

from app.characterization.contracts.behavior import (
    BehaviorRule,
    BehaviorSpecification,
    StateTransition,
)
from app.characterization.contracts.enums import FindingClassification
from app.characterization.contracts.observations import ExecutionObservation
from app.characterization.contracts.scenarios import ExecutionResult, ScenarioCatalog


class BehaviorAnalyzer:
    """Extracts empirical behavior rules, state transitions, and flags logical contradictions."""

    def analyze(
        self,
        scenario_catalog: ScenarioCatalog,
        execution_results: List[ExecutionResult],
        observations: List[ExecutionObservation],
    ) -> BehaviorSpecification:
        """Synthesize rules and cross-reference for contradictions."""
        rules: List[BehaviorRule] = []
        transitions: List[StateTransition] = []
        contradictions: List[str] = []

        scenario_map = {s.scenario_id: s for s in scenario_catalog.scenarios}
        obs_map = {o.scenario_id: o for o in observations}

        # Index outcomes by workflow and normalized input signature
        workflow_outcomes: Dict[str, Dict[str, List[ExecutionResult]]] = {}

        for res in execution_results:
            scen = scenario_map.get(res.scenario_id)
            if not scen:
                continue

            wf_id = res.workflow_id
            obs = obs_map.get(res.scenario_id)

            # Rule derivation
            rule_id = f"rule_{uuid.uuid4().hex[:8]}"
            if res.passed:
                condition = f"When workflow '{wf_id}' is invoked with {scen.scenario_type.value} input payload"
                consequence = f"Execution succeeds with exit code {res.exit_code} and valid normalized output"
                classification = FindingClassification.OBSERVED_FACT
                confidence = 0.95
            else:
                condition = f"When workflow '{wf_id}' encounters {scen.scenario_type.value} condition"
                consequence = f"Execution rejects or fails with exit code {res.exit_code}: {res.error_message or 'error encountered'}"
                classification = FindingClassification.OBSERVED_FACT if res.exit_code != 0 else FindingClassification.INFERENCE
                confidence = 0.90

            rules.append(
                BehaviorRule(
                    rule_id=rule_id,
                    workflow_id=wf_id,
                    scenario_id=scen.scenario_id,
                    condition=condition,
                    consequence=consequence,
                    classification=classification,
                    confidence=confidence,
                )
            )

            # State transition derivation from observations
            if obs and obs.state_changes:
                transitions.append(
                    StateTransition(
                        transition_id=f"trans_{uuid.uuid4().hex[:8]}",
                        workflow_id=wf_id,
                        from_state="PRE_EXECUTION",
                        to_state="POST_EXECUTION_MUTATED",
                        trigger_action=f"Execute {scen.name}",
                        observed_mutations=[sc.target for sc in obs.state_changes],
                    )
                )

            # Group for contradiction detection
            input_key = str(scen.inputs)
            if wf_id not in workflow_outcomes:
                workflow_outcomes[wf_id] = {}
            if input_key not in workflow_outcomes[wf_id]:
                workflow_outcomes[wf_id][input_key] = []
            workflow_outcomes[wf_id][input_key].append(res)

        # Cross-reference for contradictions
        for wf_id, input_dict in workflow_outcomes.items():
            for input_sig, results in input_dict.items():
                if len(results) > 1:
                    codes = {r.exit_code for r in results}
                    statuses = {r.passed for r in results}
                    if len(codes) > 1 or len(statuses) > 1:
                        c_desc = f"Contradiction in workflow {wf_id}: Identical input '{input_sig}' yielded conflicting outcomes: codes={codes}, passed={statuses}"
                        contradictions.append(c_desc)

        return BehaviorSpecification(
            total_rules=len(rules),
            rules=rules,
            state_transitions=transitions,
            contradictions_count=len(contradictions),
            contradictions=contradictions,
        )

