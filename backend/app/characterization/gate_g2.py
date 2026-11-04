"""Gate G2 Readiness Evaluation and Baseline Freeze Logic."""

from datetime import datetime, timezone
from typing import Any, Dict, Tuple
import uuid

from app.characterization.contracts.approval import G2ApprovalDecisionRecord, GateG2Request
from app.characterization.contracts.enums import G2Decision
from app.characterization.contracts.suite import CharacterizationSuite


class GateG2Manager:
    """Evaluates readiness for Gate G2 and freezes the golden characterization baseline."""

    def evaluate_gate_readiness(
        self,
        suite: CharacterizationSuite,
        coverage_threshold_pct: float = 60.0,
    ) -> Dict[str, Any]:
        """Verify preconditions required for human architectural sign-off."""
        blocking_reasons = []
        warnings = []

        # 1. Critical workflows check
        crit_metric = suite.coverage_report.dimensions.get("CRITICAL_BEHAVIOR_COVERAGE")
        if crit_metric and crit_metric.percentage < 100.0:
            blocking_reasons.append(
                f"Critical workflows are not fully characterized ({crit_metric.percentage}% < 100.0%)"
            )

        # 2. Contradiction check
        if suite.behavior_specification.contradictions_count > 0:
            blocking_reasons.append(
                f"Behavioral contradictions detected ({suite.behavior_specification.contradictions_count} conflicting observations)"
            )

        # 3. Overall coverage threshold check
        if suite.coverage_report.aggregate_percentage < coverage_threshold_pct:
            blocking_reasons.append(
                f"Aggregate empirical coverage ({suite.coverage_report.aggregate_percentage}%) is below minimum threshold ({coverage_threshold_pct}%)"
            )

        # 4. Partial execution warning
        if suite.is_partial:
            warnings.append("Characterization suite was generated from partial/truncated execution.")

        ready = (len(blocking_reasons) == 0)
        return {
            "ready": ready,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "metrics": {
                "aggregate_coverage": suite.coverage_report.aggregate_percentage,
                "total_workflows": suite.workflow_inventory.total_workflows,
                "total_scenarios_executed": len(suite.execution_results),
                "contradictions_count": suite.behavior_specification.contradictions_count,
            },
        }

    def process_g2_decision(
        self,
        suite: CharacterizationSuite,
        request: GateG2Request,
        decided_by: str,
    ) -> Tuple[G2ApprovalDecisionRecord, CharacterizationSuite]:
        """Apply human review decision and freeze baseline if approved."""
        now_iso = datetime.now(timezone.utc).isoformat()
        approval_id = f"g2_appr_{suite.job_id[:8]}_{uuid.uuid4().hex[:8]}"

        should_freeze = request.decision in (G2Decision.APPROVE, G2Decision.APPROVE_WITH_CONDITIONS)

        updated_suite = CharacterizationSuite(
            suite_id=suite.suite_id,
            job_id=suite.job_id,
            version=suite.version,
            content_hash=suite.content_hash,
            test_inventory=suite.test_inventory,
            workflow_inventory=suite.workflow_inventory,
            scenario_catalog=suite.scenario_catalog,
            execution_results=suite.execution_results,
            observations=suite.observations,
            behavior_specification=suite.behavior_specification,
            coverage_report=suite.coverage_report,
            uncertainty_report=suite.uncertainty_report,
            is_partial=suite.is_partial,
            is_frozen=should_freeze,
            frozen_at=now_iso if should_freeze else None,
            created_at=suite.created_at,
        )

        decision_record = G2ApprovalDecisionRecord(
            approval_id=approval_id,
            job_id=suite.job_id,
            suite_id=suite.suite_id,
            suite_version=suite.version,
            suite_content_hash=suite.content_hash,
            decision=request.decision,
            decided_by=decided_by,
            rationale=request.rationale,
            conditions=request.conditions,
            is_valid=True,
            invalidation_reason=None,
            decided_at=now_iso,
        )

        return decision_record, updated_suite

