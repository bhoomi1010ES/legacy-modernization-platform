"""Truthful workflow projection service deriving UI state strictly from persisted database records."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ForbiddenException, NotFoundException
from app.models.agent import AgentRun
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.gate import GateDecision
from app.models.job import Job, JobMembership
from app.models.module import Module, ModuleAttempt, VerificationRun
from app.models.user import User
from app.models.workflow import WorkflowCheckpoint, WorkflowGate
from app.schemas.workflow_projection import (
    AuditEventProjection,
    CostSummaryProjection,
    GateProjection,
    ModuleItemProjection,
    StageProjection,
    VerificationSummaryProjection,
    WorkflowProjectionResponse,
)
from app.services.artifact_service import ArtifactService


class WorkflowProjectionService:
    def __init__(self, artifact_service: Optional[ArtifactService] = None):
        self.artifact_service = artifact_service or ArtifactService()

    async def get_projection(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        user: User,
        since_seq: int = 0,
    ) -> WorkflowProjectionResponse:
        # 1. Fetch Job and verify authorization
        job_stmt = select(Job).where(Job.job_id == job_id)
        job_res = await db.execute(job_stmt)
        job = job_res.scalar_one_or_none()
        if not job:
            raise NotFoundException("Job", str(job_id))

        if job.owner_user_id != user.user_id and getattr(user, "role_id", getattr(user, "role", None)) != "ADMIN":
            mem_stmt = select(JobMembership).where(
                JobMembership.job_id == job.job_id,
                JobMembership.user_id == user.user_id,
            )
            mem_res = await db.execute(mem_stmt)
            if not mem_res.scalar_one_or_none():
                raise ForbiddenException("User is not authorized for this job.")

        # 2. Fetch all AgentRuns for this job
        runs_stmt = (
            select(AgentRun)
            .where(AgentRun.job_id == job_id)
            .order_by(AgentRun.started_at.asc())
        )
        runs_res = await db.execute(runs_stmt)
        agent_runs = runs_res.scalars().all()

        runs_by_name: Dict[str, List[AgentRun]] = {}
        for r in agent_runs:
            key = r.agent_name.strip().lower()
            runs_by_name.setdefault(key, []).append(r)

        # 3. Fetch all Modules and attempts for this job
        modules_stmt = (
            select(Module)
            .where(Module.job_id == job_id)
            .order_by(Module.wave_number.asc(), Module.name.asc())
            .options(
                selectinload(Module.attempts).selectinload(ModuleAttempt.verification_runs)
            )
        )
        modules_res = await db.execute(modules_stmt)
        modules = modules_res.scalars().all()

        # 4. Fetch all Gates and Decisions
        gates_stmt = (
            select(WorkflowGate)
            .where(WorkflowGate.job_id == job_id)
            .order_by(WorkflowGate.gate_type.asc(), WorkflowGate.version.desc())
            .options(
                selectinload(WorkflowGate.decisions).selectinload(GateDecision.reviewer)
            )
        )
        gates_res = await db.execute(gates_stmt)
        workflow_gates = gates_res.scalars().all()

        # 5. Fetch Artifacts for existence & hash checks
        artifacts_stmt = (
            select(Artifact)
            .where(Artifact.job_id == job_id)
            .order_by(Artifact.created_at.desc())
        )
        artifacts_res = await db.execute(artifacts_stmt)
        all_artifacts = artifacts_res.scalars().all()
        artifacts_by_type: Dict[str, Artifact] = {}
        for art in all_artifacts:
            art_type = (art.artifact_type or "").upper()
            if art_type not in artifacts_by_type:
                artifacts_by_type[art_type] = art

        # 6. Fetch AuditEvents
        audit_stmt = (
            select(AuditEvent)
            .where(AuditEvent.job_id == job_id)
            .order_by(AuditEvent.created_at.asc(), AuditEvent.event_id.asc())
        )
        audit_res = await db.execute(audit_stmt)
        audit_events = audit_res.scalars().all()

        # Build Stage Projections
        stages = self._build_stage_projections(job, runs_by_name, artifacts_by_type, workflow_gates)

        # Build Module Projections
        module_projections, verified_count, failed_count = self._build_module_projections(modules)

        # Build Gate Projections
        gate_projections = self._build_gate_projections(workflow_gates)

        # Build Verification Summary
        verification_summary = self._build_verification_summary(
            modules, all_artifacts, artifacts_by_type, verified_count, failed_count
        )

        # Calculate truthful progress
        total_modules = len(modules)
        is_indeterminate = total_modules == 0 and job.status not in ("COMPLETED", "FAILED", "CANCELLED")
        progress: Optional[int]
        if job.status == "COMPLETED":
            progress = 100
        elif is_indeterminate:
            progress = None
        else:
            progress = int((verified_count / total_modules) * 100) if total_modules > 0 else 0

        # Build Cost Summary
        cost_summary = self._build_cost_summary(job, agent_runs)

        # Build Audit Events with monotonic sequence
        event_projections = []
        latest_seq = 0
        for idx, evt in enumerate(audit_events, start=1):
            latest_seq = idx
            if idx > since_seq:
                event_projections.append(
                    AuditEventProjection(
                        event_id=str(evt.event_id),
                        sequence=idx,
                        event_type=evt.event_type,
                        actor_type=evt.actor_type,
                        actor_id=evt.actor_id,
                        payload=evt.payload or {},
                        created_at=evt.created_at,
                    )
                )

        return WorkflowProjectionResponse(
            projection_version="v1",
            job_id=str(job.job_id),
            job_name=job.name,
            status=job.status,
            progress=progress,
            is_progress_indeterminate=is_indeterminate,
            total_modules=total_modules,
            stages=stages,
            modules=module_projections,
            gates=gate_projections,
            verification_summary=verification_summary,
            cost=cost_summary,
            events=event_projections,
            latest_sequence=latest_seq,
        )

    def _build_stage_projections(
        self,
        job: Job,
        runs_by_name: Dict[str, List[AgentRun]],
        artifacts_by_type: Dict[str, Artifact],
        workflow_gates: List[WorkflowGate],
    ) -> List[StageProjection]:
        stages: List[StageProjection] = []

        def get_latest_run(*names: str) -> Optional[AgentRun]:
            for n in names:
                runs = runs_by_name.get(n.lower(), [])
                if runs:
                    return runs[-1]
            return None

        # 1. Intake Stage
        intake_run = get_latest_run("intakeworker", "intakeagent", "intake")
        intake_status = self._map_run_status(intake_run, default="RUNNING" if job.status == "INTAKE" else "NOT_STARTED")
        stages.append(
            self._create_stage(
                stage_id="intake",
                name="Repository Intake",
                status=intake_status,
                run=intake_run,
                artifact=artifacts_by_type.get("SOURCE_INVENTORY"),
                tool_name="git-adapter",
            )
        )

        # 2. Analysis Workers
        worker_specs = [
            ("structure_worker", "Structure Worker", ["structureworker", "structure_worker"], "SOURCE_LAYOUT"),
            ("dependency_worker", "Dependency Worker", ["dependencyworker", "dependency_worker"], "DEPENDENCY_GRAPH"),
            ("interface_worker", "Interface Worker", ["interfaceworker", "interface_worker"], "INTERFACE_SURFACE"),
            ("data_worker", "Data Worker", ["dataworker", "data_worker"], "SCHEMA_DATA"),
            ("test_worker", "Test Worker", ["testworker", "test_worker"], "TEST_INVENTORY"),
            ("integration_worker", "Integration Worker", ["integrationworker", "integration_worker"], "INTEGRATION_BOUNDARY"),
            ("risk_worker", "Risk Worker", ["riskworker", "risk_worker"], "RISK_ASSESSMENT"),
        ]
        for stage_id, name, run_keys, art_key in worker_specs:
            run = get_latest_run(*run_keys)
            status = self._map_run_status(run, default="NOT_STARTED")
            stages.append(
                self._create_stage(
                    stage_id=stage_id,
                    name=name,
                    status=status,
                    run=run,
                    artifact=artifacts_by_type.get(art_key),
                    tool_name="analyzer-specialist",
                )
            )

        # 3. Legacy Model Aggregation
        legacy_art = artifacts_by_type.get("LEGACY_MODEL") or artifacts_by_type.get("LEGACYMODEL")
        legacy_run = get_latest_run("analyzercoordinator", "legacy_model_aggregator")
        legacy_status = "VERIFIED" if legacy_art else self._map_run_status(legacy_run, default="NOT_STARTED")
        stages.append(
            self._create_stage(
                stage_id="legacy_model",
                name="Legacy Domain Model",
                status=legacy_status,
                run=legacy_run,
                artifact=legacy_art,
                tool_name="plan-aggregator",
            )
        )

        # 4. Target Architecture Blueprint
        arch_run = get_latest_run("architectagent", "architect")
        arch_art = artifacts_by_type.get("TARGET_BLUEPRINT") or artifacts_by_type.get("TARGETBLUEPRINT")
        arch_status = self._map_run_status(arch_run, default="NOT_STARTED")
        stages.append(
            self._create_stage(
                stage_id="architect",
                name="Target Architecture Blueprint",
                status=arch_status,
                run=arch_run,
                artifact=arch_art,
                tool_name="architect-engine",
            )
        )

        # 5. Feasibility Assessment
        feas_run = get_latest_run("feasibilityagent", "feasibility")
        feas_art = artifacts_by_type.get("FEASIBILITY_REPORT") or artifacts_by_type.get("FEASIBILITYREPORT")
        feas_status = self._map_run_status(feas_run, default="NOT_STARTED")
        stages.append(
            self._create_stage(
                stage_id="feasibility",
                name="Migration Feasibility Assessment",
                status=feas_status,
                run=feas_run,
                artifact=feas_art,
                tool_name="feasibility-prober",
            )
        )

        # 6. Gate G1
        g1_gate = next((g for g in workflow_gates if g.gate_type == "G1"), None)
        stages.append(self._create_gate_stage("gate_g1", "Architecture Review (Gate G1)", g1_gate, job))

        # 7. Characterizer (Phase 5)
        char_run = get_latest_run("characterizeragent", "characterizer")
        char_art = artifacts_by_type.get("CHARACTERIZATION_SUITE") or artifacts_by_type.get("CHARACTERIZATIONSUITE")
        char_status = self._map_run_status(char_run, default="RUNNING" if job.status == "CHARACTERIZING" else "NOT_STARTED")
        stages.append(
            self._create_stage(
                stage_id="characterizer",
                name="Legacy Characterization & Baseline Fixtures",
                status=char_status,
                run=char_run,
                artifact=char_art,
                tool_name="phase5-sandbox-characterizer",
            )
        )

        # 8. Schema Data Migration
        schema_run = get_latest_run("schemadataagent", "schema_data")
        schema_art = artifacts_by_type.get("SCHEMA_MIGRATION_PLAN") or artifacts_by_type.get("SCHEMAMIGRATIONPLAN")
        schema_status = self._map_run_status(schema_run, default="NOT_STARTED")
        stages.append(
            self._create_stage(
                stage_id="schema_data",
                name="Schema & Data Contract Migration",
                status=schema_status,
                run=schema_run,
                artifact=schema_art,
                tool_name="schema-data-engine",
            )
        )

        # 9. Gate G2
        g2_gate = next((g for g in workflow_gates if g.gate_type == "G2"), None)
        stages.append(self._create_gate_stage("gate_g2", "Characterization & Baseline Sign-Off (Gate G2)", g2_gate, job))

        # 10. Planner Coordinator
        plan_run = get_latest_run("plannercoordinator", "planneragent", "planner")
        plan_art = artifacts_by_type.get("CONVERSION_PLAN") or artifacts_by_type.get("CONVERSIONPLAN")
        plan_status = self._map_run_status(plan_run, default="RUNNING" if job.status == "PLANNING" else "NOT_STARTED")
        stages.append(
            self._create_stage(
                stage_id="planner",
                name="Topological DAG & Wave Plan",
                status=plan_status,
                run=plan_run,
                artifact=plan_art,
                tool_name="planner-dag-engine",
            )
        )

        # 11. Gate G3
        g3_gate = next((g for g in workflow_gates if g.gate_type == "G3"), None)
        stages.append(self._create_gate_stage("gate_g3", "Modular Wave Plan Approval (Gate G3)", g3_gate, job))

        # 12. Code Conversion Execution (CodeWriter)
        code_run = get_latest_run("codewriteragent", "codewriter", "code_writer")
        code_status = self._map_run_status(code_run, default="RUNNING" if job.status == "CONVERTING" else "NOT_STARTED")
        # Ensure SUCCEEDED CodeWriter is NOT mapped to VERIFIED!
        if code_status == "VERIFIED":
            code_status = "SUCCEEDED"
        stages.append(
            self._create_stage(
                stage_id="code_writer",
                name="CodeWriter Sandboxed Conversion",
                status=code_status,
                run=code_run,
                artifact=None,
                tool_name="e2b-sandbox-writer",
            )
        )

        # 13. Independent Durable Verifier
        verifier_run = get_latest_run("verifieragent", "independent_verifier", "durable_verifier")
        verifier_status = "NOT_RUN"
        if verifier_run:
            if verifier_run.status == "SUCCEEDED":
                verifier_status = "VERIFIED"
            elif verifier_run.status in ("FAILED", "BLOCKED"):
                verifier_status = verifier_run.status
            elif verifier_run.status in ("RUNNING", "QUEUED"):
                verifier_status = verifier_run.status
        stages.append(
            self._create_stage(
                stage_id="verifier",
                name="Independent Target Stack Verifier",
                status=verifier_status,
                run=verifier_run,
                artifact=artifacts_by_type.get("VERIFICATION_REPORT"),
                tool_name="target-stack-verifier",
            )
        )

        # 14. Architecture Reviewer
        rev_run = get_latest_run("revieweragent", "reviewer")
        rev_status = self._map_run_status(rev_run, default="NOT_STARTED")
        stages.append(
            self._create_stage(
                stage_id="reviewer",
                name="Security & Architecture Reviewer",
                status=rev_status,
                run=rev_run,
                artifact=artifacts_by_type.get("REVIEW_REPORT"),
                tool_name="reviewer-agent",
            )
        )

        # 15. Integration & Delivery (Phase 7)
        int_run = get_latest_run("integratoragent", "phase7_integrator", "integrator")
        int_art = artifacts_by_type.get("JOB_REPORT") or artifacts_by_type.get("EQUIVALENCE_REPORT")
        int_status = self._map_run_status(int_run, default="RUNNING" if job.status == "INTEGRATING" else "NOT_STARTED")
        stages.append(
            self._create_stage(
                stage_id="integrator",
                name="Full Target Integration & Delivery",
                status=int_status,
                run=int_run,
                artifact=int_art,
                tool_name="syft-phase7-integrator",
            )
        )

        # 16. Gate G4
        g4_gate = next((g for g in workflow_gates if g.gate_type == "G4"), None)
        stages.append(self._create_gate_stage("gate_g4", "Final Delivery & Parity Sign-Off (Gate G4)", g4_gate, job))

        return stages

    def _map_run_status(self, run: Optional[AgentRun], default: str = "NOT_STARTED") -> str:
        if not run:
            return default
        st = run.status.upper()
        if st in ("SUCCEEDED", "COMPLETED"):
            return "VERIFIED"
        if st in ("FAILED", "BLOCKED", "RUNNING", "QUEUED"):
            return st
        return default

    def _create_stage(
        self,
        stage_id: str,
        name: str,
        status: str,
        run: Optional[AgentRun],
        artifact: Optional[Artifact],
        tool_name: str,
    ) -> StageProjection:
        run_id = str(run.run_id) if run else None
        worker_id = (run.trace_payload.get("worker_id") if run and isinstance(run.trace_payload, dict) else None)
        art_id = str(artifact.artifact_id) if artifact else None
        art_hash = artifact.content_hash if artifact else None
        evidence_available = artifact is not None and bool(artifact.content_hash)
        evidence_url = f"/api/v1/artifacts/{art_id}" if art_id else None
        err = run.error_message if run else None

        return StageProjection(
            stage_id=stage_id,
            name=name,
            status=status,
            agent_name=run.agent_name if run else None,
            agent_run_id=run_id,
            worker_id=worker_id,
            artifact_id=art_id,
            artifact_hash=art_hash,
            tool_name=tool_name,
            tool_version="1.0.0",
            commit_sha=None,
            evidence_url=evidence_url,
            evidence_available=evidence_available,
            error_message=err,
            started_at=run.started_at if run else None,
            completed_at=run.completed_at if run else None,
        )

    def _create_gate_stage(
        self,
        stage_id: str,
        name: str,
        gate: Optional[WorkflowGate],
        job: Job,
    ) -> StageProjection:
        if not gate:
            return StageProjection(
                stage_id=stage_id,
                name=name,
                status="NOT_STARTED",
                tool_name="workflow-gatekeeper",
                evidence_available=False,
            )

        st = gate.status.upper()
        stage_status: str
        if st == "APPROVED":
            stage_status = "VERIFIED"
        elif st in ("REJECTED", "INVALIDATED"):
            stage_status = "FAILED"
        elif st == "PENDING":
            stage_status = "WAITING_FOR_HUMAN"
        elif st == "TIMED_OUT":
            stage_status = "BLOCKED"
        else:
            stage_status = st

        hashes = gate.artifact_hashes or {}
        first_hash = next(iter(hashes.values())) if hashes else None

        return StageProjection(
            stage_id=stage_id,
            name=name,
            status=stage_status,
            artifact_hash=first_hash,
            tool_name="workflow-gatekeeper",
            evidence_available=bool(first_hash),
            error_message=gate.blocking_reason,
            started_at=gate.requested_at,
            completed_at=gate.decided_at,
        )

    def _build_module_projections(
        self, modules: List[Module]
    ) -> Tuple[List[ModuleItemProjection], int, int]:
        projections: List[ModuleItemProjection] = []
        verified_count = 0
        failed_count = 0

        for m in modules:
            attempts = sorted(m.attempts or [], key=lambda a: a.attempt_number)
            latest_attempt = attempts[-1] if attempts else None
            attempt_count = len(attempts)

            v_run = None
            if latest_attempt and latest_attempt.verification_runs:
                sorted_v = sorted(
                    latest_attempt.verification_runs,
                    key=lambda v: v.created_at,
                )
                v_run = sorted_v[-1]

            verification_status = "NOT_RUN"
            cand_hash = None
            if v_run:
                cand_hash = v_run.candidate_hash
                if v_run.status == "PASS":
                    verification_status = "PASS"
                elif v_run.status == "FAIL":
                    verification_status = "FAIL"
                elif v_run.status in ("RUNNING", "QUEUED", "BLOCKED"):
                    verification_status = v_run.status

            if verification_status == "PASS":
                verified_count += 1
            elif m.status in ("FAILED", "BLOCKED") or verification_status == "FAIL":
                failed_count += 1

            projections.append(
                ModuleItemProjection(
                    module_id=str(m.module_id),
                    name=m.name,
                    legacy_path=m.legacy_path,
                    target_path=m.target_path,
                    status=m.status,
                    risk_level=m.risk_level,
                    wave_number=m.wave_number,
                    attempt_count=attempt_count,
                    latest_attempt_id=str(latest_attempt.attempt_id) if latest_attempt else None,
                    verification_status=verification_status,
                    verification_run_id=str(v_run.verification_run_id) if v_run else None,
                    candidate_hash=cand_hash,
                    error_message=latest_attempt.failure_reason if latest_attempt else None,
                )
            )

        return projections, verified_count, failed_count

    def _build_gate_projections(
        self, workflow_gates: List[WorkflowGate]
    ) -> List[GateProjection]:
        projections: List[GateProjection] = []
        for g in workflow_gates:
            decisions = sorted(g.decisions or [], key=lambda d: d.decided_at)
            latest_decision = decisions[-1] if decisions else None
            reviewer_id = str(latest_decision.reviewer_user_id) if latest_decision else None
            reviewer_name = (
                latest_decision.reviewer.full_name
                if latest_decision and latest_decision.reviewer
                else None
            )

            is_stale = g.status == "INVALIDATED" or bool(
                g.blocking_reason and "stale" in g.blocking_reason.lower()
            )

            projections.append(
                GateProjection(
                    gate_id=str(g.gate_id),
                    gate_type=g.gate_type,
                    version=g.version,
                    status=g.status,
                    artifact_hashes=g.artifact_hashes or {},
                    is_stale=is_stale,
                    blocking_reason=g.blocking_reason,
                    reviewer_user_id=reviewer_id,
                    reviewer_name=reviewer_name,
                    decided_at=g.decided_at,
                    waivers=latest_decision.waivers if latest_decision else [],
                    selected_options=latest_decision.selected_options if latest_decision else {},
                )
            )
        return projections

    def _build_verification_summary(
        self,
        modules: List[Module],
        all_artifacts: List[Artifact],
        artifacts_by_type: Dict[str, Artifact],
        verified_modules: int,
        failed_modules: int,
    ) -> VerificationSummaryProjection:
        # Check if Equivalence Report or Job Report exists
        report_art = artifacts_by_type.get("JOB_REPORT") or artifacts_by_type.get("EQUIVALENCE_REPORT")
        executed = 0
        passed = 0
        failed = 0
        unobserved = 0
        unintended_regressions = 0
        waivers_count = 0
        parity_verified = False
        latest_run_id = None

        if report_art and isinstance(report_art.metadata_payload, dict):
            meta = report_art.metadata_payload
            executed = meta.get("executed_cases", 0)
            passed = meta.get("passed_cases", 0)
            failed = meta.get("failed_cases", 0)
            unobserved = meta.get("unobserved_cases", 0)
            unintended_regressions = meta.get("unintended_regressions_count", 0)
            waivers_count = meta.get("approved_waivers_count", 0)
            parity_verified = meta.get("parity_verified", False)
        else:
            # Aggregate from module verification runs
            for m in modules:
                for att in m.attempts or []:
                    for vr in att.verification_runs or []:
                        latest_run_id = str(vr.verification_run_id)
                        ev = vr.evidence or {}
                        if isinstance(ev, dict):
                            executed += ev.get("executed", 1 if vr.status in ("PASS", "FAIL") else 0)
                            if vr.status == "PASS":
                                passed += 1
                            elif vr.status == "FAIL":
                                failed += 1
                                unintended_regressions += 1
                            elif vr.status == "BLOCKED":
                                unobserved += 1

            parity_verified = len(modules) > 0 and verified_modules == len(modules) and failed_modules == 0

        total_cases = executed + unobserved
        has_unwaived = unintended_regressions > 0

        return VerificationSummaryProjection(
            total_cases=total_cases,
            executed_cases=executed,
            passed_cases=passed,
            failed_cases=failed,
            unobserved_cases=unobserved,
            parity_verified=parity_verified,
            has_unwaived_regressions=has_unwaived,
            unintended_regressions_count=unintended_regressions,
            approved_waivers_count=waivers_count,
            latest_verification_run_id=latest_run_id,
        )

    def _build_cost_summary(
        self, job: Job, agent_runs: List[AgentRun]
    ) -> CostSummaryProjection:
        input_tokens = sum(r.input_tokens or 0 for r in agent_runs)
        output_tokens = sum(r.output_tokens or 0 for r in agent_runs)
        pricing_ver = next(
            (r.pricing_table_version for r in reversed(agent_runs) if r.pricing_table_version),
            None,
        )

        return CostSummaryProjection(
            budget_limit_usd=float(job.budget_limit_usd),
            budget_used_usd=float(job.budget_used_usd),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pricing_version=pricing_ver,
        )
