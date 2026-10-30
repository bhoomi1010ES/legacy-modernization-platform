"""Versioned integration/evidence work. Supervisor and GateService own all transitions."""

import json
import logging
from time import monotonic
import uuid

from sqlalchemy import func, select

from app.core.errors import ConflictException, NotFoundException
from app.models.agent import AgentRun
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.base import utc_now
from app.models.gate import GateDecision
from app.models.job import Job
from app.models.module import Module
from app.models.test_case import TestResult
from app.models.workflow import WorkflowGate, WorkflowOutbox
from app.schemas.phase7 import JobReport
from app.services import (
    phase6_service,
    phase6_workspace as workspace,
    phase6_sandbox as sandbox,
)
from app.services import phase7_engine as engine
from app.services.artifact_service import ArtifactService
from app.services.phase5_engine import canonical, digest
from app.services.phase5_service import latest, read_payload
from app.services.reviewer_agent import review

logger = logging.getLogger(__name__)


async def publish(
    db, job, run, kind: str, payload: dict, lineage: list[str]
) -> Artifact:
    try:
        await db.scalar(select(Job).where(Job.job_id == job.job_id).with_for_update())
        version = (
            await db.scalar(
                select(func.max(Artifact.version)).where(
                    Artifact.job_id == job.job_id, Artifact.artifact_type == kind
                )
            )
            or 0
        ) + 1
        return await ArtifactService().create_artifact(
            db,
            job.job_id,
            kind,
            version,
            canonical(payload),
            "Integrator",
            derived_from=lineage,
            extra_metadata={"phase": 7, "run_id": str(run.run_id)},
        )
    except Exception:
        logger.exception("phase7.publish failed | kind=%s", kind)
        raise


async def artifact_view(db, job_id, kind: str, version: int | None = None) -> dict:
    try:
        query = select(Artifact).where(
            Artifact.job_id == job_id, Artifact.artifact_type == kind
        )
        if version is not None:
            query = query.where(Artifact.version == version)
        artifact = await db.scalar(query.order_by(Artifact.version.desc()).limit(1))
        if artifact is None or artifact.extra_metadata.get("phase") != 7:
            raise NotFoundException(kind, str(job_id))
        payload = await read_payload(artifact)
        return {
            "artifact_id": str(artifact.artifact_id),
            "version": artifact.version,
            "content_hash": artifact.content_hash,
            "download_url": f"/api/v1/jobs/{job_id}/artifacts/{artifact.artifact_id}/download",
            "content": payload,
        }
    except Exception:
        logger.exception(
            "phase7.artifact_view failed | job_id=%s kind=%s", job_id, kind
        )
        raise


async def bindings_for(db, job) -> tuple[dict, list[dict]]:
    """Revalidate real Phase 6 artifacts/results, then bind the approved DAG exactly."""
    try:
        from app.services.supervisor_service import supervisor_service

        current = await supervisor_service.require_integration_eligibility(db, job)
        if not current["cases"] or any(
            case["outcome"] != "PASSED" for case in current["cases"]
        ):
            raise ConflictException(
                "Required frozen scenarios remain unobserved or failing"
            )
        modules = list(
            (
                await db.execute(select(Module).where(Module.job_id == job.job_id))
            ).scalars()
        )
        ordered = engine.dependency_order(current["approved_modules"], modules)
        bindings = []
        expected_ids = {case["test_case_id"] for case in current["cases"]}
        for module in ordered:
            attempt = await phase6_service.newest(db, module.module_id)
            info = await phase6_service.detail(db, attempt)
            evidence = info["evidence"]
            verification = evidence.get("verification", {})
            checks, cases = verification.get("checks", []), verification.get(
                "cases", []
            )
            if (
                verification.get("available") is not True
                or not {"build", "unit", "static", "security"}
                <= {item.get("category") for item in checks}
                or any(
                    item.get("status") != "PASS"
                    or type(item.get("exit_code")) is not int
                    or item["exit_code"] != 0
                    for item in checks + cases
                )
                or {item.get("test_case_id") for item in cases} != expected_ids
                or len(cases) != len(expected_ids)
                or verification.get("unobserved_cases")
            ):
                raise ConflictException(
                    "Integration requires complete independently executed module evidence"
                )
            rows = list(
                (
                    await db.execute(
                        select(TestResult).where(
                            TestResult.attempt_id == attempt.attempt_id
                        )
                    )
                ).scalars()
            )
            if (
                len(rows) != len(expected_ids)
                or {str(row.test_case_id) for row in rows} != expected_ids
                or any(row.invalidated or row.outcome != "PASSED" for row in rows)
            ):
                raise ConflictException(
                    "Module verification results are absent, invalidated or inconsistent"
                )
            unit = next(
                unit
                for unit in current["approved_modules"]
                if unit["module_id"] in (module.name, str(module.module_id))
            )
            if (
                module.target_path not in unit["target_scope"]
                or module.legacy_path not in unit["source_scope"]
            ):
                raise ConflictException("Module scope changed after approval")
            for path in evidence["files"]:
                if not any(
                    path == scope or path.startswith(scope.rstrip("/") + "/")
                    for scope in unit["target_scope"]
                ):
                    raise ConflictException(
                        "Verified changes escaped the approved target scope"
                    )
            bindings.append(
                {
                    "module_id": str(module.module_id),
                    "name": module.name,
                    "status": module.status,
                    "attempt_id": str(attempt.attempt_id),
                    "attempt_number": attempt.attempt_number,
                    "branch": attempt.git_branch,
                    "commit": evidence["commit"],
                    "source_commit": evidence["source_commit"],
                    "code_hash": evidence["code_hash"],
                    "code_artifact_id": evidence["code_artifact_id"],
                    "verification_hash": evidence["verification_hash"],
                    "review_hash": evidence["review_hash"],
                    "files": evidence["files"],
                    "changed_files": evidence["changed_files"],
                    "diff": evidence["diff"],
                    "findings": evidence["review"]["findings"],
                }
            )
        if len({binding["source_commit"] for binding in bindings}) != 1:
            raise ConflictException(
                "Module attempts do not share the pinned source snapshot"
            )
        return current, bindings
    except Exception:
        logger.exception("phase7.bindings_for failed | job_id=%s", job.job_id)
        raise


def identity(current: dict, bindings: list[dict]) -> str:
    try:
        return digest(
            {
                "baseline_hash": current["baseline_hash"],
                "plan_hash": current["plan_hash"],
                "gate_ids": current["gate_ids"],
                "modules": [
                    {
                        key: binding[key]
                        for key in (
                            "module_id",
                            "attempt_id",
                            "commit",
                            "code_hash",
                            "verification_hash",
                            "review_hash",
                        )
                    }
                    for binding in bindings
                ],
            }
        )
    except Exception:
        logger.exception("phase7.identity failed")
        raise


async def queue_integration(db, job, key: str, actor: str) -> AgentRun:
    """Called by Supervisor after its eligibility/transition guard."""
    try:
        job = await db.scalar(
            select(Job).where(Job.job_id == job.job_id).with_for_update()
        )
        if job.status != "INTEGRATING":
            raise ConflictException(
                "Integration requires the canonical integration state"
            )
        runs = list(
            (
                await db.execute(
                    select(AgentRun)
                    .where(
                        AgentRun.job_id == job.job_id,
                        AgentRun.agent_name == "Integrator",
                    )
                    .order_by(AgentRun.started_at.desc())
                )
            ).scalars()
        )
        for run in runs:
            if (
                run.task_payload.get("phase") == 7
                and run.task_payload.get("request_key") == key
                and (run.status in ("QUEUED", "RUNNING") or (run.output_payload or {}).get("status") == "READY_FOR_REVIEW")
            ):
                return run
        if any(run.status in ("QUEUED", "RUNNING") for run in runs):
            raise ConflictException("Integration already has an active run")
        current, bindings = await bindings_for(db, job)
        run = AgentRun(
            job_id=job.job_id,
            agent_name="Integrator",
            model_provider="deterministic",
            model_identifier="phase7-integrator-v1",
            status="QUEUED",
            task_id="integration",
            task_payload={
                "phase": 7,
                "request_key": key,
                "identity": identity(current, bindings),
                "current": current,
                "bindings": bindings,
            },
            trace_payload={"events": ["QUEUED"]},
        )
        db.add(run)
        await db.flush()
        db.add(
            AuditEvent(
                job_id=job.job_id,
                event_type="INTEGRATION_QUEUED",
                actor_type="USER",
                actor_id=actor,
                target_resource=str(run.run_id),
                payload={"identity": run.task_payload["identity"]},
            )
        )
        await db.commit()
        return run
    except Exception:
        logger.exception("phase7.queue_integration failed")
        raise


async def execute_integration(db, run_id) -> dict:
    """Fresh Git candidate + real sandbox. No production migration, deployment or gate approval."""
    start = monotonic()
    run = None
    try:
        run = await db.scalar(
            select(AgentRun)
            .where(AgentRun.run_id == run_id)
            .with_for_update(skip_locked=True)
        )
        if run is None:
            raise ConflictException("Integration run is leased by another worker")
        if run.status != "QUEUED":
            return run.output_payload or {"run_id": str(run_id), "status": run.status}
        job = await db.get(Job, run.job_id)
        if job.status != "INTEGRATING":
            raise ConflictException(
                "Integration is paused, stale or no longer eligible"
            )
        current, bindings = await bindings_for(db, job)
        if identity(current, bindings) != run.task_payload["identity"]:
            raise ConflictException("Queued integration inputs changed")
        run.status = "RUNNING"
        await db.commit()
        from app.services.repository_workspace_service import repository_workspace_service

        repo = await repository_workspace_service.ensure_workspace(
            db,
            job,
            expected_commit=bindings[0]["source_commit"],
            correlation_id=run.correlation_id,
        )
        merged = await engine.merge_verified(
            repo,
            str(job.job_id),
            str(run.run_id),
            bindings[0]["source_commit"],
            bindings,
        )
        files = merged.pop("files", {})
        verification = {
            "available": False,
            "passed": False,
            "checks": [],
            "cases": [],
            "reason": "Merge conflict; verification not executed",
        }
        suite = await read_payload(await latest(db, job.job_id))
        schema = await read_payload(
            await latest(db, job.job_id, "SCHEMA_MIGRATION_PLAN")
        )
        if merged["status"] == "MERGED":
            try:
                profile = engine.system_profile(bool(schema["tables"]))
            except (ValueError, TypeError):
                verification["reason"] = (
                    "Administrator full-system check profile unavailable"
                )
            else:
                verification = await sandbox.execute(
                    files,
                    current["cases"],
                    current["baseline_hash"],
                    system_checks=profile,
                )
        verification.update(
            run_id=str(run.run_id),
            integrated_commit=merged["commit"],
            baseline_hash=current["baseline_hash"],
        )
        verification_artifact = await publish(
            db,
            job,
            run,
            "SYSTEM_VERIFICATION",
            verification,
            [binding["code_artifact_id"] for binding in bindings],
        )
        sbom = engine.sbom_evidence(verification, files)
        sbom_artifact = await publish(
            db,
            job,
            run,
            "SBOM",
            {**sbom, "integrated_commit": merged["commit"]},
            [str(verification_artifact.artifact_id)],
        )
        review_report = review(
            files, [], verification_artifact.content_hash, execution=verification
        )
        rows = []
        definitions = {case["test_case_id"]: case for case in current["cases"]}
        for case in verification.get("cases", []):
            if type(case.get("exit_code")) is not int:
                continue
            record = TestResult(
                test_case_id=uuid.UUID(case["test_case_id"]),
                outcome="PASSED" if case["status"] == "PASS" else "FAILED",
                difference_classification=(
                    "NONE" if case["status"] == "PASS" else "REGRESSION"
                ),
                legacy_output={"output": definitions[case["test_case_id"]]["expected"]},
                converted_output={
                    "integration_run_id": str(run.run_id),
                    "actual": case["actual"],
                    "verification_hash": verification_artifact.content_hash,
                },
            )
            db.add(record)
            rows.append(record)
        await db.flush()
        counts = {
            "total": len(definitions),
            "executed": len(rows),
            "passed": sum(row.outcome == "PASSED" for row in rows),
            "failed": sum(row.outcome == "FAILED" for row in rows),
            "unobserved": len(definitions) - len(rows),
        }
        current_now, bindings_now = await bindings_for(db, job)
        await db.refresh(job)
        if (
            job.status != "INTEGRATING"
            or identity(current_now, bindings_now) != run.task_payload["identity"]
        ):
            raise ConflictException(
                "Workflow or module evidence changed during system verification"
            )
        ready = (
            merged["status"] == "MERGED"
            and verification.get("available") is True
            and verification.get("passed") is True
            and review_report["status"] == "PASS"
            and sbom["status"] == "GENERATED"
            and counts["unobserved"] == 0
        )
        status = (
            "READY_FOR_REVIEW"
            if ready
            else "CONFLICT" if merged["status"] == "CONFLICT" else "BLOCKED"
        )
        integration_payload = {
            **merged,
            "run_id": str(run.run_id),
            "status": status,
            "identity": run.task_payload["identity"],
            "verification_artifact_id": str(verification_artifact.artifact_id),
            "verification_hash": verification_artifact.content_hash,
            "sbom_artifact_id": str(sbom_artifact.artifact_id),
            "sbom_hash": sbom_artifact.content_hash,
            "test_result_ids": [str(row.result_id) for row in rows],
            "counts": counts,
            "schema_status": (
                "CHECKED_IN_SANDBOX"
                if schema["tables"] and verification.get("passed")
                else "NOT_APPLICABLE" if not schema["tables"] else "UNVERIFIED"
            ),
            "review": review_report,
        }
        integration_artifact = await publish(
            db,
            job,
            run,
            "INTEGRATION_REPORT",
            integration_payload,
            [str(verification_artifact.artifact_id), str(sbom_artifact.artifact_id)],
        )
        decisions = list(
            (
                await db.execute(
                    select(GateDecision).where(GateDecision.job_id == job.job_id)
                )
            ).scalars()
        )
        agent_runs = list(
            (
                await db.execute(select(AgentRun).where(AgentRun.job_id == job.job_id))
            ).scalars()
        )
        limitations = (
            list(suite["coverage"].get("limitations", []))
            + list(sbom.get("limitations", []))
            + review_report["limitations"]
        )
        if sbom["status"] != "GENERATED":
            limitations.append(
                "SBOM not generated: " + sbom.get("reason", sbom["status"])
            )
        limitations += [
            "Equivalence covers executed frozen scenarios only, not line/branch coverage.",
            "PR publishing requires deliberate provider configuration; no production cutover is included.",
        ]
        report = JobReport(
            job_id=str(job.job_id),
            run_id=str(run.run_id),
            status=status,
            source_stack=job.source_stack,
            target_stack=job.target_stack,
            source_commit=bindings[0]["source_commit"],
            integrated_commit=merged["commit"],
            branch=merged["branch"],
            baseline_hash=current["baseline_hash"],
            plan_hash=current["plan_hash"],
            gate_ids=current["gate_ids"],
            modules=[
                {key: value for key, value in binding.items() if key != "files"}
                for binding in bindings
            ],
            decisions=[
                {
                    "gate_id": str(decision.gate_id),
                    "type": decision.gate_type,
                    "decision": decision.decision,
                    "rationale": decision.rationale,
                    "artifact_hashes": decision.artifact_hashes,
                }
                for decision in decisions
            ],
            counts=counts,
            coverage={**suite["coverage"], "known_legacy_bugs": [case["known_bug"] for case in suite["cases"] if case.get("known_bug")], "normalization": [{"test_case_id": case["test_case_id"], "rules": case["normalization"]} for case in suite["cases"]]},
            findings=review_report["findings"]
            + [finding for binding in bindings for finding in binding["findings"]],
            waivers=[
                waiver for decision in decisions for waiver in decision.waivers or []
            ],
            costs={
                "recorded_job_total": str(job.budget_used_usd),
                "agent_run_total": str(sum(item.cost_usd for item in agent_runs)),
                "integration_llm_cost": "0",
                "note": "No model inference occurs in integration; existing ledger totals are not an external invoice",
            },
            duration_ms=(monotonic() - start) * 1000,
            limitations=limitations,
            evidence={
                "integration": {
                    "artifact_id": str(integration_artifact.artifact_id),
                    "hash": integration_artifact.content_hash,
                    "conflicts": merged["conflicts"],
                    "diff": merged.get("diff", ""),
                    "merge_history": merged["merge_history"],
                },
                "verification": {
                    "artifact_id": str(verification_artifact.artifact_id),
                    "hash": verification_artifact.content_hash,
                    "checks": verification.get("checks", []),
                    "image_id": verification.get("image_id"),
                    "container_name": verification.get("container_name"),
                    "reason": verification.get("reason"),
                },
                "sbom": {
                    "artifact_id": str(sbom_artifact.artifact_id),
                    "hash": sbom_artifact.content_hash,
                    "status": sbom["status"],
                    "tool": sbom.get("tool"),
                    "tool_version": sbom.get("tool_version"),
                    "format": sbom.get("format"),
                },
            },
        )
        report_artifact = await publish(
            db,
            job,
            run,
            "JOB_REPORT",
            report.model_dump(mode="json"),
            [
                str(integration_artifact.artifact_id),
                str(sbom_artifact.artifact_id),
                current["baseline_id"],
            ],
        )
        run.status = "SUCCEEDED" if ready else "FAILED"
        run.completed_at = utc_now()
        run.output_payload = {
            "run_id": str(run.run_id),
            "status": status,
            "report_artifact_id": str(report_artifact.artifact_id),
            "report_hash": report_artifact.content_hash,
            "report_version": report_artifact.version,
            "commit": merged["commit"],
            "branch": merged["branch"],
        }
        run.output_artifact_refs = [
            str(item.artifact_id)
            for item in (
                verification_artifact,
                sbom_artifact,
                integration_artifact,
                report_artifact,
            )
        ]
        run.trace_payload = {
            "events": ["QUEUED", "RUNNING", status],
            "agent_version": "phase7-integrator-v1",
        }
        # Supervisor owns disposition; do not change module states or approve/open G4 here.
        from app.services.supervisor_service import supervisor_service

        await supervisor_service.record_integration_disposition(db, job, run)
        return run.output_payload
    except Exception:
        logger.exception("phase7.execute_integration failed | run_id=%s", run_id)
        await db.rollback()
        if run is not None:
            run = await db.get(AgentRun, run_id)
            if run is not None and run.status in ("QUEUED", "RUNNING"):
                run.status, run.completed_at = "FAILED", utc_now()
                run.error_message = "Integration stopped: invalid/stale inputs, Git failure or evidence persistence failure; no G4 approval"
                run.output_payload = {
                    "run_id": str(run_id),
                    "status": "BLOCKED",
                    "reason": run.error_message,
                }
                db.add(
                    AuditEvent(
                        job_id=run.job_id,
                        event_type="INTEGRATION_BLOCKED",
                        actor_type="SYSTEM",
                        actor_id="Supervisor",
                        target_resource=str(run_id),
                        payload=run.output_payload,
                    )
                )
                await db.commit()
                return run.output_payload
        raise


async def validate_package(db, job, report_hash: str, *, gate=None) -> dict:
    """G4/PR readiness is computed from exact current bytes, commits and persisted results."""
    try:
        report = await artifact_view(db, job.job_id, "JOB_REPORT")
        content = report["content"]
        if (
            report["content_hash"] != report_hash
            or content["status"] != "READY_FOR_REVIEW"
        ):
            raise ConflictException(
                "Current final report is stale or not ready for review"
            )
        current, bindings = await bindings_for(db, job)
        run = await db.get(AgentRun, uuid.UUID(content["run_id"]))
        if (
            run is None
            or run.status != "SUCCEEDED"
            or identity(current, bindings) != run.task_payload.get("identity")
        ):
            raise ConflictException(
                "Final report no longer matches verified modules/gates"
            )
        integration = await artifact_view(db, job.job_id, "INTEGRATION_REPORT")
        verification = await artifact_view(db, job.job_id, "SYSTEM_VERIFICATION")
        sbom = await artifact_view(db, job.job_id, "SBOM")
        for name, view in (
            ("integration", integration),
            ("verification", verification),
            ("sbom", sbom),
        ):
            if (
                content["evidence"][name]["artifact_id"] != view["artifact_id"]
                or content["evidence"][name]["hash"] != view["content_hash"]
            ):
                raise ConflictException(
                    "Final package references a stale evidence version"
                )
            if (
                view["content"].get("integrated_commit", view["content"].get("commit"))
                != content["integrated_commit"]
            ):
                raise ConflictException("Final package commit identity mismatch")
        if (
            sbom["content"]["status"] != "GENERATED"
            or verification["content"].get("passed") is not True
            or not verification["content"].get("available")
        ):
            raise ConflictException(
                "Final package lacks successful full verification/SBOM"
            )
        rows = list(
            (
                await db.execute(
                    select(TestResult).where(
                        TestResult.result_id.in_(
                            [
                                uuid.UUID(key)
                                for key in integration["content"]["test_result_ids"]
                            ]
                        )
                    )
                )
            ).scalars()
        )
        if (
            len(rows) != content["counts"]["total"]
            or any(
                row.invalidated
                or row.outcome != "PASSED"
                or row.converted_output.get("integration_run_id") != content["run_id"]
                for row in rows
            )
            or {str(row.test_case_id) for row in rows}
            != {case["test_case_id"] for case in current["cases"]}
        ):
            raise ConflictException(
                "Final persisted results are missing, invalidated or inconsistent"
            )
        repo = workspace.repository_for(str(job.job_id))
        if (
            await workspace.git(repo, "rev-parse", content["branch"])
            != content["integrated_commit"]
        ):
            raise ConflictException(
                "Integration branch changed since final verification"
            )
        if gate is not None:
            for view in (report, integration, verification, sbom):
                if (
                    gate.artifact_hashes.get(view["artifact_id"])
                    != view["content_hash"]
                ):
                    raise ConflictException(
                        "G4 is not bound to the current evidence package"
                    )
        return report
    except Exception:
        logger.exception("phase7.validate_package failed | job_id=%s", job.job_id)
        raise


async def decide_g4(db, job, gate, payload) -> None:
    """Called only by canonical GateService, including compatibility gate URLs."""
    try:
        if payload.decision.value == "APPROVED":
            report = await artifact_view(db, job.job_id, "JOB_REPORT")
            await validate_package(db, job, report["content_hash"], gate=gate)
            # A signed waiver must reference recorded intended-difference evidence;
            # it cannot invent a case or override mandatory full-system checks.
            rows = list(
                (
                    await db.execute(
                        select(TestResult).where(
                            TestResult.result_id.in_(
                                [
                                    uuid.UUID(key)
                                    for key in (
                                        await artifact_view(
                                            db, job.job_id, "INTEGRATION_REPORT"
                                        )
                                    )["content"]["test_result_ids"]
                                ]
                            )
                        )
                    )
                ).scalars()
            )
            waivable = {
                str(row.test_case_id)
                for row in rows
                if row.difference_classification == "INTENDED_DIFFERENCE"
                and not row.invalidated
            }
            if len({waiver.test_id for waiver in payload.waivers}) != len(
                payload.waivers
            ) or any(
                waiver.test_id not in waivable
                or waiver.difference_type != "INTENDED_DIFFERENCE"
                or len(waiver.waiver_rationale.strip()) < 10
                for waiver in payload.waivers
            ):
                raise ConflictException(
                    "Waivers require exact recorded intended-difference evidence; mandatory failing checks cannot be waived"
                )
        else:
            try:
                integration = await artifact_view(db, job.job_id, "INTEGRATION_REPORT")
            except NotFoundException:
                return
            rows = list(
                (
                    await db.execute(
                        select(TestResult).where(
                            TestResult.result_id.in_(
                                [
                                    uuid.UUID(key)
                                    for key in integration["content"].get(
                                        "test_result_ids", []
                                    )
                                ]
                            )
                        )
                    )
                ).scalars()
            )
            for row in rows:
                row.invalidated, row.invalidation_reason = (
                    True,
                    "G4 rejected; fresh integration verification required",
                )
    except Exception:
        logger.exception("phase7.decide_g4 failed | gate_id=%s", gate.gate_id)
        raise


async def record_delivery(db, job, gate, decision) -> None:
    """Stage an immutable delivery record in GateService's approval transaction."""
    try:
        report = await artifact_view(db, job.job_id, "JOB_REPORT")
        await db.flush()
        payload = {
            "job_id": str(job.job_id),
            "branch": report["content"]["branch"],
            "commit": report["content"]["integrated_commit"],
            "report_id": report["artifact_id"],
            "report_hash": report["content_hash"],
            "report_version": report["version"],
            "sbom_hash": report["content"]["evidence"]["sbom"]["hash"],
            "gate_id": str(gate.gate_id),
            "decision_id": str(decision.decision_id),
            "reviewer_user_id": str(decision.reviewer_user_id),
            "rationale": decision.rationale,
            "waivers": decision.waivers,
            "delivered_at": decision.decided_at.isoformat(),
            "production_cutover_included": False,
        }
        try:
            pr = await artifact_view(db, job.job_id, "PULL_REQUEST_RECORD")
        except NotFoundException:
            payload["pull_request"] = {"status": "MANUAL_REQUIRED"}
        else:
            payload["pull_request"] = (
                pr["content"]
                if pr["content"].get("report_hash") == report["content_hash"]
                else {"status": "MANUAL_REQUIRED"}
            )
        version = (
            await db.scalar(
                select(func.max(Artifact.version)).where(
                    Artifact.job_id == job.job_id,
                    Artifact.artifact_type == "DELIVERY_RECORD",
                )
            )
            or 0
        ) + 1
        await ArtifactService().create_artifact(
            db,
            job.job_id,
            "DELIVERY_RECORD",
            version,
            canonical(payload),
            "Supervisor",
            derived_from=[
                report["artifact_id"],
                report["content"]["evidence"]["sbom"]["artifact_id"],
            ],
            extra_metadata={"phase": 7},
            commit=False,
        )
    except Exception:
        logger.exception("phase7.record_delivery failed")
        raise


async def pull_request(db, job, request, actor: str, *, provider=None) -> dict:
    """Idempotent explicit publishing action; manual handoff is not PR creation."""
    try:
        report = await validate_package(db, job, request.report_hash)
        content = report["content"]
        key = f"phase7-pr:{job.job_id}:{request.idempotency_key}"
        existing = await db.scalar(
            select(WorkflowOutbox).where(WorkflowOutbox.idempotency_key == key)
        )
        if existing:
            if existing.payload.get("report_hash") != request.report_hash:
                raise ConflictException("PR idempotency key belongs to another report")
            return existing.payload.get(
                "result",
                {
                    "status": "UNKNOWN",
                    "reason": "Prior external request is unresolved; inspect remote before retrying",
                },
            )
        event = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=key,
            event_type="PHASE7_PULL_REQUEST",
            status="PROCESSING",
            attempts=1,
            payload={"report_hash": request.report_hash},
        )
        db.add(event)
        await db.commit()
        manual = {
            "status": "MANUAL_REQUIRED",
            "branch": content["branch"],
            "commit": content["integrated_commit"],
            "report_hash": report["content_hash"],
            "summary": f"Modernization review: {job.name}; report v{report['version']}; commit {content['integrated_commit']}; {content['counts']['passed']}/{content['counts']['total']} frozen cases passed. Review limitations/waivers and the SBOM before G4 approval.",
            "instructions": [
                "Review the exact candidate commit, versioned JobReport, SBOM and uncovered behavior.",
                "Push this candidate branch using your approved Git credential workflow.",
                "Create a draft pull request against the reviewed base branch; do not merge/deploy automatically.",
            ],
        }
        if provider is None:
            from app.services.git_provider import configured_provider

            provider = configured_provider()
        result = (
            manual
            if provider is None
            else {
                **manual,
                **(
                    await provider.create(
                        branch=content["branch"],
                        commit=content["integrated_commit"],
                        title=f"Modernization review: {job.name}",
                        body=manual["summary"],
                    )
                ),
            }
        )
        await publish(
            db,
            job,
            await db.get(AgentRun, uuid.UUID(content["run_id"])),
            "PULL_REQUEST_RECORD",
            result,
            [report["artifact_id"]],
        )
        event.status, event.processed_at = "PROCESSED", utc_now()
        event.payload = {"report_hash": request.report_hash, "result": result}
        db.add(
            AuditEvent(
                job_id=job.job_id,
                event_type="PULL_REQUEST_" + result["status"],
                actor_type="USER",
                actor_id=actor,
                target_resource=report["artifact_id"],
                payload={
                    key: result.get(key)
                    for key in ("status", "url", "branch", "commit", "report_hash")
                },
            )
        )
        await db.commit()
        return result
    except Exception:
        logger.exception("phase7.pull_request failed")
        raise


async def delivery(db, job) -> dict:
    try:
        result = {
            "job_id": str(job.job_id),
            "job_status": job.status,
            "delivery_ready": False,
            "production_cutover_included": False,
            "report": None,
            "gate": None,
            "pull_request": {"status": "MANUAL_REQUIRED", "url": None},
            "delivery_record": None,
            "limitations": [],
        }
        try:
            report = await artifact_view(db, job.job_id, "JOB_REPORT")
        except NotFoundException:
            result["limitations"] = [
                "No final integration package exists; module evidence is not final delivery evidence"
            ]
            return result
        result["report"] = report
        try:
            await validate_package(db, job, report["content_hash"])
            result["package_current"] = True
        except (ConflictException, NotFoundException):
            result["package_current"] = False
            result["limitations"].append(
                "Current report is blocked, stale, rejected or has missing execution/SBOM evidence"
            )
        gate = await db.scalar(
            select(WorkflowGate)
            .where(WorkflowGate.job_id == job.job_id, WorkflowGate.gate_type == "G4")
            .order_by(WorkflowGate.version.desc())
            .limit(1)
        )
        if gate:
            result["gate"] = {
                "gate_id": str(gate.gate_id),
                "status": gate.status,
                "version": gate.version,
                "artifact_hashes": gate.artifact_hashes,
            }
        try:
            pr = await artifact_view(db, job.job_id, "PULL_REQUEST_RECORD")
        except NotFoundException:
            logger.debug("phase7.delivery optional PR absent | job_id=%s", job.job_id)
        else:
            if pr["content"].get("report_hash") == report["content_hash"]:
                result["pull_request"] = pr["content"]
        if (
            job.status == "COMPLETED"
            and gate
            and gate.status == "APPROVED"
            and result.get("package_current")
        ):
            await validate_package(db, job, report["content_hash"], gate=gate)
            record = await artifact_view(db, job.job_id, "DELIVERY_RECORD")
            if record["content"]["report_hash"] == report["content_hash"] and record[
                "content"
            ]["gate_id"] == str(gate.gate_id):
                result["delivery_ready"], result["delivery_record"] = True, record
        return result
    except Exception:
        logger.exception("phase7.delivery failed")
        raise
