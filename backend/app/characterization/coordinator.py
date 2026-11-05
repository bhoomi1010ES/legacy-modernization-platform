"""Characterization Coordinator orchestrating the 9-stage Phase 5A execution pipeline."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.characterization.behavior.behavior_analyzer import BehaviorAnalyzer
from app.characterization.contracts.enums import CharacterizationStage, ExecutionStatus
from app.characterization.contracts.observations import ExecutionObservation
from app.characterization.contracts.scenarios import ExecutionResult
from app.characterization.contracts.suite import CharacterizationRequest, CharacterizationSuite
from app.characterization.contracts.uncertainty import UncertaintyRecord, UncertaintyReport
from app.characterization.coverage.coverage_calculator import CoverageCalculator
from app.characterization.discovery.test_discovery import UniversalTestDiscoveryEngine
from app.characterization.discovery.workflow_discovery import UniversalWorkflowDiscoveryEngine
from app.characterization.execution.sandbox import IsolatedExecutionSandbox
from app.characterization.gate_g2 import GateG2Manager
from app.characterization.models import (
    CharacterizationEventModel,
    CharacterizationExecutionModel,
    CharacterizationScenarioModel,
    CharacterizationSuiteModel,
)
from app.characterization.observation.filesystem_diff import FilesystemDiffer
from app.characterization.observation.recorder import ObservationRecorder
from app.characterization.persistence.repository import CharacterizationRepository
from app.characterization.scenarios.scenario_designer import MultidimensionalScenarioDesigner
from app.characterization.suite_aggregator import SuiteAggregator
from app.services.artifact_service import artifact_service


class CharacterizationCoordinator:
    """Drives the 9-stage empirical characterization pipeline from 0% to 100%."""

    def __init__(
        self,
        db: Optional[AsyncSession] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        repo: Optional[CharacterizationRepository] = None,
    ):
        self.db = db
        self.repo = repo or CharacterizationRepository(db)
        self.event_callback = event_callback
        self.seq_num = 0

        # Sub-engines
        self.test_engine = UniversalTestDiscoveryEngine()
        self.workflow_engine = UniversalWorkflowDiscoveryEngine()
        self.designer = MultidimensionalScenarioDesigner()
        self.sandbox = IsolatedExecutionSandbox()
        self.fs_differ = FilesystemDiffer()
        self.recorder = ObservationRecorder()
        self.analyzer = BehaviorAnalyzer()
        self.coverage_calc = CoverageCalculator()
        self.aggregator = SuiteAggregator()
        self.g2_manager = GateG2Manager()

    async def _emit_event(
        self,
        execution_id: str,
        stage: CharacterizationStage,
        event_type: str,
        message: str,
        payload: Dict[str, Any],
    ) -> None:
        """Persist event to database and notify broadcast subscribers."""
        self.seq_num += 1
        event = CharacterizationEventModel(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            execution_id=execution_id,
            sequence_number=self.seq_num,
            stage=stage.value,
            event_type=event_type,
            message=message,
            payload=payload,
        )
        await self.repo.save_event(event)

        if self.event_callback:
            event_dict = {
                "sequence_number": self.seq_num,
                "stage": stage.value,
                "event_type": event_type,
                "message": message,
                "payload": payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if asyncio.iscoroutinefunction(self.event_callback):
                await self.event_callback(event_dict)
            else:
                self.event_callback(event_dict)

    async def run(
        self,
        execution_id: str,
        job_id_str: str,
        workspace_path: Path,
        request: CharacterizationRequest,
    ) -> CharacterizationSuite:
        """Execute the authoritative 9-stage characterization lifecycle."""
        t0 = time.monotonic()
        job_uuid = uuid.UUID(job_id_str)

        try:
            existing = await self.repo.get_execution(execution_id)
            if not existing:
                execution = CharacterizationExecutionModel(
                    execution_id=execution_id,
                    job_id=job_uuid,
                    status=ExecutionStatus.PENDING.value,
                    stage=CharacterizationStage.TEST_INVENTORY_DISCOVERY.value,
                    stage_progress_pct=0,
                    summary=f"Executing 9-stage characterization pipeline for job {job_id_str}.",
                    started_at=datetime.now(timezone.utc),
                )
                await self.repo.create_execution(execution)
                if self.db is not None:
                    await self.db.flush()

            # -------------------------------------------------------------
            # Stage 1: TEST_INVENTORY_DISCOVERY (10%)
            # -------------------------------------------------------------
            await self.repo.update_execution_stage(
                execution_id, CharacterizationStage.TEST_INVENTORY_DISCOVERY.value, 10
            )
            test_inventory = self.test_engine.discover(workspace_path)
            await self._emit_event(
                execution_id,
                CharacterizationStage.TEST_INVENTORY_DISCOVERY,
                "TEST_INVENTORY_DISCOVERED",
                f"Discovered {test_inventory.total_test_files} test files with {test_inventory.total_test_cases} test cases.",
                test_inventory.model_dump(),
            )

            # -------------------------------------------------------------
            # Stage 2: WORKFLOW_MAPPING (20%)
            # -------------------------------------------------------------
            await self.repo.update_execution_stage(
                execution_id, CharacterizationStage.WORKFLOW_MAPPING.value, 20
            )
            workflow_inventory = self.workflow_engine.discover(workspace_path)
            await self._emit_event(
                execution_id,
                CharacterizationStage.WORKFLOW_MAPPING,
                "WORKFLOWS_MAPPED",
                f"Mapped {workflow_inventory.total_workflows} workflows ({workflow_inventory.critical_workflows_count} critical) across {len(workflow_inventory.domains_discovered)} domains.",
                workflow_inventory.model_dump(),
            )

            # -------------------------------------------------------------
            # Stage 3: SCENARIO_DESIGN (35%)
            # -------------------------------------------------------------
            await self.repo.update_execution_stage(
                execution_id, CharacterizationStage.SCENARIO_DESIGN.value, 35
            )
            scenario_catalog = self.designer.design_catalog(
                workflow_inventory, max_scenarios=request.max_scenarios
            )
            await self._emit_event(
                execution_id,
                CharacterizationStage.SCENARIO_DESIGN,
                "SCENARIOS_DESIGNED",
                f"Designed {scenario_catalog.total_scenarios} multidimensional scenarios across {len(scenario_catalog.by_workflow)} workflows.",
                scenario_catalog.model_dump(),
            )

            # -------------------------------------------------------------
            # Stage 4: ISOLATED_EXECUTION (60%)
            # -------------------------------------------------------------
            await self.repo.update_execution_stage(
                execution_id, CharacterizationStage.ISOLATED_EXECUTION.value, 40
            )
            execution_results: List[ExecutionResult] = []
            observations: List[ExecutionObservation] = []
            db_scenarios: List[CharacterizationScenarioModel] = []

            with tempfile.TemporaryDirectory(prefix="rebase_char_sandbox_") as tmp_dir:
                sandbox_dir = Path(tmp_dir)

                for idx, scen in enumerate(scenario_catalog.scenarios):
                    # Pre-execution snapshot
                    before_snap = self.fs_differ.capture_snapshot(sandbox_dir)

                    # Isolated Execution Run 1
                    exec_res, exec_mode = self.sandbox.execute_scenario(
                        scenario=scen,
                        workspace_dir=workspace_path,
                        sandbox_dir=sandbox_dir,
                    )

                    # Post-execution snapshot
                    after_snap = self.fs_differ.capture_snapshot(sandbox_dir)
                    created, modified, deleted, changes = self.fs_differ.diff(before_snap, after_snap)

                    # Second run for deterministic golden comparison
                    exec_res_2, _ = self.sandbox.execute_scenario(
                        scenario=scen,
                        workspace_dir=workspace_path,
                        sandbox_dir=sandbox_dir,
                    )
                    reproducibility = (
                        "DETERMINISTIC" if exec_res.stdout == exec_res_2.stdout and exec_res.exit_code == exec_res_2.exit_code
                        else "NON_DETERMINISTIC"
                    )

                    obs = self.recorder.record(
                        execution_result=exec_res,
                        execution_mode=exec_mode,
                        created_files=created,
                        modified_files=modified,
                        deleted_files=deleted,
                        state_changes=changes,
                        reproducibility=reproducibility,
                    )

                    execution_results.append(exec_res)
                    observations.append(obs)

                    db_scenarios.append(
                        CharacterizationScenarioModel(
                            scenario_id=scen.scenario_id,
                            execution_id=execution_id,
                            workflow_id=scen.workflow_id,
                            scenario_type=scen.scenario_type.value,
                            objective=scen.objective,
                            status=exec_res.status.value,
                            exit_code=exec_res.exit_code,
                            passed=exec_res.passed,
                            duration_ms=exec_res.duration_ms,
                            scenario_data=scen.model_dump(),
                        )
                    )

                await self.repo.save_scenarios(db_scenarios)

            await self._emit_event(
                execution_id,
                CharacterizationStage.ISOLATED_EXECUTION,
                "SCENARIOS_EXECUTED",
                f"Executed {len(execution_results)} scenarios ({sum(1 for r in execution_results if r.passed)} passed).",
                {"total": len(execution_results), "passed": sum(1 for r in execution_results if r.passed)},
            )

            # -------------------------------------------------------------
            # Stage 5: BEHAVIOR_ANALYSIS (75%)
            # -------------------------------------------------------------
            await self.repo.update_execution_stage(
                execution_id, CharacterizationStage.BEHAVIOR_ANALYSIS.value, 75
            )
            behavior_spec = self.analyzer.analyze(
                scenario_catalog=scenario_catalog,
                execution_results=execution_results,
                observations=observations,
            )
            await self._emit_event(
                execution_id,
                CharacterizationStage.BEHAVIOR_ANALYSIS,
                "BEHAVIOR_ANALYZED",
                f"Synthesized {behavior_spec.total_rules} empirical rules with {behavior_spec.contradictions_count} contradictions.",
                behavior_spec.model_dump(),
            )

            # -------------------------------------------------------------
            # Stage 6: COVERAGE_EVALUATION (85%)
            # -------------------------------------------------------------
            await self.repo.update_execution_stage(
                execution_id, CharacterizationStage.COVERAGE_EVALUATION.value, 85
            )
            coverage_report = self.coverage_calc.calculate(
                workflow_inventory=workflow_inventory,
                scenario_catalog=scenario_catalog,
                execution_results=execution_results,
                observations=observations,
                behavior_spec=behavior_spec,
                g2_threshold_pct=request.coverage_threshold,
            )
            await self._emit_event(
                execution_id,
                CharacterizationStage.COVERAGE_EVALUATION,
                "COVERAGE_EVALUATED",
                f"Calculated 9-dimension coverage: {coverage_report.aggregate_percentage}% aggregate.",
                coverage_report.model_dump(),
            )

            # -------------------------------------------------------------
            # Stage 7: ITERATIVE_REFINEMENT (90%)
            # -------------------------------------------------------------
            await self.repo.update_execution_stage(
                execution_id, CharacterizationStage.ITERATIVE_REFINEMENT.value, 90
            )
            uncertainties: List[UncertaintyRecord] = []
            if coverage_report.coverage_gaps:
                for gap in coverage_report.coverage_gaps[:5]:
                    uncertainties.append(
                        UncertaintyRecord(
                            uncertainty_id=f"unc_{uuid.uuid4().hex[:8]}",
                            target_workflow="general",
                            nature="COVERAGE_GAP",
                            impact=gap,
                            recommended_mitigation="Review and expand nominal scenario catalog before G2 freeze.",
                        )
                    )

            uncertainty_report = UncertaintyReport(
                total_uncertainties=len(uncertainties),
                records=uncertainties,
                risk_level="MEDIUM" if uncertainties else "LOW",
            )
            await self._emit_event(
                execution_id,
                CharacterizationStage.ITERATIVE_REFINEMENT,
                "REFINEMENT_EVALUATED",
                f"Iterative refinement completed with {uncertainty_report.total_uncertainties} uncertainties identified.",
                uncertainty_report.model_dump(),
            )

            # -------------------------------------------------------------
            # Stage 8: SUITE_AGGREGATION (95%)
            # -------------------------------------------------------------
            await self.repo.update_execution_stage(
                execution_id, CharacterizationStage.SUITE_AGGREGATION.value, 95
            )
            prev_suite = await self.repo.get_latest_suite(job_uuid)
            version = (prev_suite.version + 1) if prev_suite else 1
            suite_id = f"suite_{job_id_str[:8]}_v{version}_{uuid.uuid4().hex[:6]}"
            now_iso = datetime.now(timezone.utc).isoformat()

            suite = self.aggregator.aggregate(
                suite_id=suite_id,
                job_id=job_id_str,
                version=version,
                test_inventory=test_inventory,
                workflow_inventory=workflow_inventory,
                scenario_catalog=scenario_catalog,
                execution_results=execution_results,
                observations=observations,
                behavior_spec=behavior_spec,
                coverage_report=coverage_report,
                uncertainty_report=uncertainty_report,
                created_at=now_iso,
            )

            suite_model = CharacterizationSuiteModel(
                suite_id=suite.suite_id,
                job_id=job_uuid,
                execution_id=execution_id,
                version=suite.version,
                content_hash=suite.content_hash,
                suite_data=suite.model_dump(),
                is_partial=False,
                is_frozen=False,
                frozen_at=None,
            )
            await self.repo.save_suite(suite_model)

            # Register as official CHARACTERIZATION_SUITE artifact in REBASE artifact ledger
            cases_payload = []
            for r, obs in zip(execution_results, observations):
                cases_payload.append({
                    "test_case_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, r.scenario_id)),
                    "name": r.scenario_id,
                    "outcome": "PASSED" if r.passed else "FAILED",
                    "actual": r.stdout,
                    "side_effects": [
                        {"type": "FILE_CREATED", "target": p} for p in obs.created_files
                    ] + [
                        {"type": "FILE_MODIFIED", "target": p} for p in obs.modified_files
                    ] + [
                        {"type": "FILE_DELETED", "target": p} for p in obs.deleted_files
                    ],
                })

            readiness = self.g2_manager.evaluate_gate_readiness(
                suite=suite, coverage_threshold_pct=request.coverage_threshold
            )

            suite_payload = suite.model_dump()
            suite_payload["cases"] = cases_payload
            suite_payload["g2_readiness"] = readiness
            suite_payload["schema_hash"] = suite.content_hash
            suite_payload["runtime_available"] = any(r.passed for r in execution_results) if execution_results else False

            content_bytes = json.dumps(suite_payload, sort_keys=True).encode("utf-8")
            if self.db is not None:
                await artifact_service.publish_artifact(
                    db=self.db,
                    job_id=job_uuid,
                    artifact_type="CHARACTERIZATION_SUITE",
                    version=version,
                    content_bytes=content_bytes,
                    producing_agent="CharacterizerAgent",
                    derived_from=[],
                    extra_metadata={"phase": 5, "source": "Phase5ACoordinator"},
                    commit=False,
                )

            await self._emit_event(
                execution_id,
                CharacterizationStage.SUITE_AGGREGATION,
                "SUITE_AGGREGATED",
                f"Synthesized CharacterizationSuite v{version} with SHA-256 {suite.content_hash[:16]}...",
                {"suite_id": suite.suite_id, "content_hash": suite.content_hash, "version": suite.version},
            )

            # -------------------------------------------------------------
            # Stage 9: GATE_G2_READINESS (100%)
            # -------------------------------------------------------------
            await self.repo.update_execution_stage(
                execution_id, CharacterizationStage.GATE_G2_READINESS.value, 100
            )
            readiness = self.g2_manager.evaluate_gate_readiness(
                suite=suite, coverage_threshold_pct=request.coverage_threshold
            )
            await self._emit_event(
                execution_id,
                CharacterizationStage.GATE_G2_READINESS,
                "GATE_G2_READINESS_EVALUATED",
                f"Gate G2 readiness evaluated: {'READY' if readiness['ready'] else 'BLOCKED'} (Coverage: {readiness['metrics']['aggregate_coverage']}%).",
                readiness,
            )

            duration_ms = (time.monotonic() - t0) * 1000
            await self.repo.complete_execution(
                execution_id=execution_id,
                status=ExecutionStatus.COMPLETED.value,
                total_scenarios=len(execution_results),
                total_workflows=workflow_inventory.total_workflows,
                duration_ms=duration_ms,
            )

            await self.db.commit()
            return suite

        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            await self.repo.complete_execution(
                execution_id=execution_id,
                status=ExecutionStatus.FAILED.value,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            await self.db.commit()
            raise
