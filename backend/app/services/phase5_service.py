"""Append-only Phase 5 artifacts, evidence discovery and G2 baseline lifecycle."""

import logging
import os
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, NotFoundException, ValidationException
from app.core.storage import get_storage_adapter
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.base import utc_now
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.module import Module
from app.models.phase4 import LegacyModelRecord, RepositoryInventoryModel
from app.models.test_case import TestCase, TestResult
from app.models.workflow import WorkflowGate
from app.schemas.phase5 import (
    CaptureRequest,
    FreezeRequest,
    SuiteArtifact,
    ValidationRequest,
)
from app.services.phase5_engine import (
    canonical,
    coverage,
    digest,
    discover_schema,
    migration_plan,
    normalize,
    replay,
    validate_migration,
)
from app.services.secret_redactor import get_secret_redactor

logger = logging.getLogger(__name__)


async def latest(
    db: AsyncSession, job_id: uuid.UUID, kind: str = "CHARACTERIZATION_SUITE"
) -> Artifact:
    try:
        artifact = await db.scalar(
            select(Artifact)
            .where(Artifact.job_id == job_id, Artifact.artifact_type == kind)
            .order_by(Artifact.version.desc())
            .limit(1)
        )
        if artifact is None or artifact.extra_metadata.get("phase") != 5:
            raise NotFoundException(kind, str(job_id))
        return artifact
    except Exception:
        logger.exception("phase5.latest failed | job_id=%s", job_id)
        raise


async def read_payload(artifact: Artifact) -> dict:
    try:
        import hashlib
        import json

        raw = await get_storage_adapter().get_object(artifact.storage_path)
        computed = hashlib.sha256(raw).hexdigest()
        stored = artifact.content_hash.removeprefix("sha256:") if artifact.content_hash else ""
        if computed != stored and computed != artifact.content_hash:
            raise ConflictException("Baseline artifact integrity check failed")
        return json.loads(raw)
    except Exception:
        logger.exception(
            "phase5.read_payload failed | artifact_id=%s", artifact.artifact_id
        )
        raise


async def publish(
    db: AsyncSession,
    job_id: uuid.UUID,
    kind: str,
    version: int,
    payload: dict,
    lineage: list[str],
    metadata: dict,
) -> Artifact:
    try:
        key = f"jobs/{job_id}/artifacts/{kind}_v{version}.json"
        checksum, size = await get_storage_adapter().put_object(key, canonical(payload))
        artifact = Artifact(
            artifact_id=uuid.uuid4(),
            job_id=job_id,
            artifact_type=kind,
            version=version,
            content_hash=checksum,
            storage_path=key,
            content_size_bytes=size,
            producing_agent=(
                "Characterizer" if kind == "CHARACTERIZATION_SUITE" else "SchemaData"
            ),
            derived_from=lineage,
            extra_metadata={"phase": 5, **metadata},
        )
        db.add(artifact)
        await db.flush()
        return artifact
    except Exception:
        logger.exception("phase5.publish failed | job_id=%s", job_id)
        raise


async def capture(
    db: AsyncSession, job: Job, request: CaptureRequest, actor_id: str
) -> dict:
    """Capture/replay approved scenarios; preserve unavailable or untested paths explicitly."""
    try:
        job = await db.scalar(
            select(Job).where(Job.job_id == job.job_id).with_for_update()
        )
        from app.services.supervisor_service import supervisor_service

        fingerprint = digest(
            {
                "request": request.model_dump(mode="json"),
                "asserted_scenarios": [
                    i
                    for i, s in enumerate(request.scenarios)
                    if "expected" in s.model_fields_set
                ],
            }
        )
        previous = list(
            (
                await db.execute(
                    select(Artifact)
                    .where(
                        Artifact.job_id == job.job_id,
                        Artifact.artifact_type == "CHARACTERIZATION_SUITE",
                    )
                    .order_by(Artifact.version.desc())
                )
            ).scalars()
        )
        for item in previous:
            if item.extra_metadata.get("request_key") == request.idempotency_key:
                if item.extra_metadata.get("request_hash") != fingerprint:
                    raise ConflictException(
                        "Idempotency key is already bound to different inputs"
                    )
                return await report(db, job.job_id, artifact=item)
        await supervisor_service.require_characterization_eligibility(db, job)
        legacy = await db.scalar(
            select(LegacyModelRecord)
            .where(LegacyModelRecord.job_id == job.job_id)
            .order_by(LegacyModelRecord.version.desc())
            .limit(1)
        )
        inventory = await db.scalar(
            select(RepositoryInventoryModel)
            .where(RepositoryInventoryModel.job_id == job.job_id)
            .order_by(RepositoryInventoryModel.created_at.desc())
            .limit(1)
        )
        modules = list(
            (
                await db.execute(select(Module.name).where(Module.job_id == job.job_id))
            ).scalars()
        )
        if legacy:
            modules += [
                m.get("name", m.get("module_id", "unknown"))
                for m in legacy.modules_payload
            ]
        interfaces = (
            [
                i.get("name", i.get("endpoint", "unknown"))
                for i in legacy.interfaces_payload
            ]
            if legacy
            else []
        )
        discovered = []
        schema_files = []
        if inventory:
            for entry in inventory.files_payload:
                path = entry.get("path", "")
                if "test" in path.lower() or "spec" in path.lower():
                    discovered.append(path)
                if path.lower().endswith(".sql") or "migration" in path.lower():
                    schema_files.append(path)
        scenarios_to_run = list(request.scenarios)
        candidate_scenarios = []
        if not scenarios_to_run:
            from pathlib import Path
            from app.services.scenario_discovery_service import scenario_discovery_service
            from app.schemas.phase4 import LegacyModel, RepositoryInventory

            workspace_dir = None
            base_dir = Path(__file__).resolve().parent.parent.parent
            for p in (
                base_dir / "repo_workspaces" / f"job_{job.job_id}",
                base_dir / "repo_workspaces" / f"job_{job.job_id}_git",
            ):
                if p.exists():
                    workspace_dir = p
                    break

            typed_legacy = None
            if legacy:
                typed_legacy = LegacyModel(
                    model_id=str(legacy.model_id),
                    job_id=str(job.job_id),
                    snapshot_id=str(legacy.snapshot_id),
                    version=legacy.version,
                    modules=legacy.modules_payload,
                    dependency_graph=legacy.dependencies_payload,
                    public_interfaces=legacy.interfaces_payload,
                    persistence_entities=legacy.persistence_payload,
                    configurations=legacy.configurations_payload,
                    test_suites=legacy.tests_payload,
                    risks=legacy.risks_payload,
                    conflicts=legacy.conflicts_payload,
                    evidence_index={},
                    content_hash=legacy.content_hash,
                )

            typed_inv = None
            if inventory:
                typed_inv = RepositoryInventory(
                    inventory_id=str(inventory.inventory_id),
                    snapshot_id=str(inventory.snapshot_id),
                    job_id=str(job.job_id),
                    total_files=inventory.total_files,
                    total_bytes=inventory.total_bytes,
                    files=inventory.files_payload,
                    directories=inventory.directories_payload,
                    inventory_hash=inventory.inventory_hash,
                )

            candidates = scenario_discovery_service.discover_scenarios(
                workspace_dir, typed_legacy, typed_inv
            )
            candidate_scenarios = [c.model_dump() for c in candidates]
            scenarios_to_run = scenario_discovery_service.to_executable_scenarios(candidates)

        cases = []
        available = bool(scenarios_to_run)
        for scenario in scenarios_to_run:
            observation = await replay(scenario)
            available = available and observation["available"]
            actual = observation.get("output")
            expected = (
                scenario.expected
                if ("expected" in scenario.model_fields_set and scenario.expected is not None)
                else actual
            )
            outcome = "UNAVAILABLE"
            reason = observation.get("reason")
            if observation["available"]:
                outcome = (
                    "PASSED"
                    if canonical(normalize(expected, scenario.normalization))
                    == canonical(normalize(actual, scenario.normalization))
                    else "FAILED"
                )
                # Second independent execution proves golden capture is replayable, including side effects.
                second = await replay(scenario)
                if not second["available"]:
                    available, outcome, reason = (
                        False,
                        "UNAVAILABLE",
                        second.get("reason"),
                    )
                elif canonical(normalize(actual, scenario.normalization)) != canonical(
                    normalize(second["output"], scenario.normalization)
                ) or canonical(observation.get("side_effects")) != canonical(
                    second.get("side_effects")
                ):
                    outcome, reason = (
                        "NON_REPRODUCIBLE",
                        "Replay output or side effects are nondeterministic",
                    )
            case_id = uuid.uuid4()
            case = get_secret_redactor().redact_object(
                {
                    "test_case_id": str(case_id),
                    "name": scenario.name,
                    "module": scenario.module,
                    "interface": scenario.interface,
                    "behavior": scenario.behavior,
                    "fixtures": scenario.inputs,
                    "expected": expected,
                    "actual": actual,
                    "outcome": outcome,
                    "normalization": [r.model_dump() for r in scenario.normalization],
                    "known_bug": scenario.known_bug,
                    "side_effects": observation.get("side_effects"),
                    "limitation": reason,
                    "evidence_status": (
                        "OBSERVED" if observation["available"] else "UNOBSERVED"
                    ),
                    "observed_candidate": "expected" not in scenario.model_fields_set,
                }
            )
            cases.append(case)
        discovered_tables, schema_notes = (
            discover_schema(str(job.job_id), schema_files) if schema_files else ([], [])
        )
        plan = migration_plan(
            request.tables or discovered_tables, request.target_tables
        )
        plan["limitations"] += schema_notes
        plan["inventory_evidence"] = get_secret_redactor().redact_object(
            legacy.persistence_payload if legacy else []
        )
        plan["schema_files"] = schema_files
        plan["status"] = (
            "REVIEW_REQUIRED"
            if not request.tables
            and (
                schema_notes
                or (
                    (schema_files or plan["inventory_evidence"])
                    and not discovered_tables
                )
            )
            else plan["status"]
        )
        if request.tables:
            plan["assumptions"].append(
                "Explicit reviewed source/target schemas override discovered subsets"
            )
        plan["limitations"] += (
            [
                "ORM/SQL source evidence is inventoried but not automatically translated; provide reviewed structured tables"
            ]
            if schema_files or plan["inventory_evidence"]
            else []
        )
        version = previous[0].version + 1 if previous else 1
        plan_previous = await db.scalar(
            select(Artifact)
            .where(
                Artifact.job_id == job.job_id,
                Artifact.artifact_type == "SCHEMA_MIGRATION_PLAN",
            )
            .order_by(Artifact.version.desc())
            .limit(1)
        )
        lineage = [str(previous[0].artifact_id)] if previous else []
        schema_artifact = await publish(
            db,
            job.job_id,
            "SCHEMA_MIGRATION_PLAN",
            plan_previous.version + 1 if plan_previous else 1,
            plan,
            lineage,
            {},
        )

        # Build G2 Readiness report
        approved_count = sum(1 for c in cases if c["outcome"] == "PASSED")
        executed_count = sum(1 for c in cases if c["evidence_status"] == "OBSERVED")
        untested_count = sum(1 for c in cases if c["evidence_status"] == "UNOBSERVED")
        non_repro_count = sum(1 for c in cases if c["outcome"] == "NON_REPRODUCIBLE")
        failed_count = sum(1 for c in cases if c["outcome"] == "FAILED")

        blocking_reasons = []
        if approved_count == 0:
            blocking_reasons.append("Zero observed passing characterization scenarios")
        if non_repro_count > 0:
            blocking_reasons.append(f"{non_repro_count} scenarios yielded non-reproducible observations")
        if failed_count > 0:
            blocking_reasons.append(f"{failed_count} scenarios failed golden assertion")

        cov = coverage(modules, interfaces, cases)
        g2_readiness = {
            "scenario_count": len(cases),
            "approved_count": approved_count,
            "executed_count": executed_count,
            "golden_count": approved_count,
            "untested_count": untested_count,
            "non_reproducible_count": non_repro_count,
            "coverage_summary": cov,
            "blocking_reasons": blocking_reasons,
            "artifact_hashes": {},
            "ready_for_g2": len(blocking_reasons) == 0,
        }

        payload = {
            "schema_version": "5.1",
            "cases": cases,
            "runtime_available": available,
            "coverage": cov,
            "known_bugs": [c["known_bug"] for c in cases if c["known_bug"]],
            "normalization": [r for c in cases for r in c["normalization"]],
            "environment": get_secret_redactor().redact_object(
                {
                    "notes": request.environment,
                    "image": os.getenv("PHASE5_LEGACY_IMAGE", "unconfigured"),
                    "network": "none",
                    "scope": "disposable",
                }
            ),
            "discovered_tests": discovered,
            "discovery_evidence": [
                {"path": path, "status": "DISCOVERED", "execution_status": "UNTESTED"}
                for path in discovered
            ],
            "schema_artifact_id": str(schema_artifact.artifact_id),
            "schema_hash": schema_artifact.content_hash,
            "g2_readiness": g2_readiness,
            "candidate_scenarios": candidate_scenarios,
        }
        if not available:
            payload["coverage"]["limitations"].append(
                "Legacy runtime unavailable or no approved scenarios supplied; discovered tests have not been executed"
            )
        payload = SuiteArtifact.model_validate(payload).model_dump(mode="json")
        artifact = await publish(
            db,
            job.job_id,
            "CHARACTERIZATION_SUITE",
            version,
            payload,
            lineage + [str(schema_artifact.artifact_id)],
            {"request_key": request.idempotency_key, "request_hash": fingerprint},
        )
        db.add(
            AgentRun(
                job_id=job.job_id,
                agent_name="Characterizer",
                task_id=request.idempotency_key,
                model_provider="local",
                model_identifier="deterministic-replay-v5",
                status="SUCCEEDED" if available else "BLOCKED",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0,
                completed_at=utc_now(),
                output_artifact_refs=[
                    str(artifact.artifact_id),
                    str(schema_artifact.artifact_id),
                ],
                output_payload={
                    "runtime_available": available,
                    "case_count": len(cases),
                },
            )
        )
        for case in cases:
            db.add(
                TestCase(
                    test_case_id=uuid.UUID(case["test_case_id"]),
                    job_id=job.job_id,
                    name=case["name"],
                    test_layer="API_CONTRACT",
                    fixture_payload={"suite_id": str(artifact.artifact_id), **case},
                )
            )
        from app.services.supervisor_service import supervisor_service

        await supervisor_service.record_baseline_revision(db, job, actor_id=actor_id)
        for case in cases:
            if case["outcome"] in ("PASSED", "FAILED", "NON_REPRODUCIBLE"):
                db.add(
                    TestResult(
                        test_case_id=uuid.UUID(case["test_case_id"]),
                        outcome="PASSED" if case["outcome"] == "PASSED" else "FAILED",
                        difference_classification=(
                            "NONE"
                            if case["outcome"] == "PASSED"
                            else (
                                "NONDETERMINISTIC"
                                if case["outcome"] == "NON_REPRODUCIBLE"
                                else "TEST_DEFECT"
                            )
                        ),
                        legacy_output={
                            "output": case["actual"],
                            "side_effects": case["side_effects"],
                        },
                    )
                )
        db.add(
            AuditEvent(
                job_id=job.job_id,
                event_type="CHARACTERIZATION_CAPTURED",
                actor_type="USER",
                actor_id=actor_id,
                payload={
                    "suite_id": str(artifact.artifact_id),
                    "hash": artifact.content_hash,
                    "version": version,
                    "case_count": len(cases),
                },
            )
        )
        await db.commit()
        return await report(db, job.job_id, artifact=artifact)
    except (ValueError, KeyError, TypeError) as exc:
        logger.exception("phase5.capture invalid input | job_id=%s", job.job_id)
        await db.rollback()
        raise ValidationException(
            "Invalid characterization or schema definition"
        ) from exc
    except Exception:
        logger.exception("phase5.capture failed | job_id=%s", job.job_id)
        await db.rollback()
        raise


async def report(
    db: AsyncSession, job_id: uuid.UUID, artifact: Artifact | None = None
) -> dict:
    try:
        artifact = artifact or await latest(db, job_id)
        payload = await read_payload(artifact)
        schema = await db.get(Artifact, uuid.UUID(payload["schema_artifact_id"]))
        plan = await read_payload(schema)
        gates = list(
            (
                await db.execute(
                    select(WorkflowGate)
                    .where(
                        WorkflowGate.job_id == job_id, WorkflowGate.gate_type == "G2"
                    )
                    .order_by(WorkflowGate.version.desc())
                )
            ).scalars()
        )
        gate = next(
            (g for g in gates if str(artifact.artifact_id) in g.artifact_hashes), None
        )
        return {
            **payload,
            "schema_status": plan.get("status", "REVIEW_REQUIRED"),
            "schema_validation_status": await validation_status(
                db, job_id, schema.content_hash
            ),
            "suite_id": str(artifact.artifact_id),
            "content_hash": artifact.content_hash,
            "version": artifact.version,
            "status": (
                "FROZEN"
                if gate and gate.status == "APPROVED"
                else gate.status if gate else "DRAFT"
            ),
            "gate_id": str(gate.gate_id) if gate else None,
        }
    except Exception:
        logger.exception("phase5.report failed | job_id=%s", job_id)
        raise


async def freeze(
    db: AsyncSession, job: Job, request: FreezeRequest, *, actor_id: str = "supervisor"
) -> dict:
    try:
        from app.services.supervisor_service import supervisor_service

        return await supervisor_service.request_baseline_review(
            db, job.job_id, request, actor_id=actor_id
        )
    except Exception:
        logger.exception("phase5.freeze failed | job_id=%s", job.job_id)
        await db.rollback()
        raise


async def validation_status(
    db: AsyncSession, job_id: uuid.UUID, content_hash: str
) -> str:
    try:
        events = (
            await db.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.job_id == job_id,
                    AuditEvent.event_type == "DISPOSABLE_MIGRATION_VALIDATED",
                )
                .order_by(AuditEvent.created_at.desc())
            )
        ).scalars()
        event = next(
            (e for e in events if e.payload.get("content_hash") == content_hash), None
        )
        if event is None:
            return "PENDING"
        if event.payload.get("review_required"):
            return "REVIEW_REQUIRED"
        if not event.payload.get("sample_data_provided"):
            return "DDL_ONLY"
        return "PASS" if event.payload.get("passed") else "FAIL"
    except Exception:
        logger.exception("phase5.validation_status failed")
        raise


async def validate_plan(
    db: AsyncSession, job: Job, request: ValidationRequest, actor_id: str
) -> dict:
    try:
        artifact = await latest(db, job.job_id, "SCHEMA_MIGRATION_PLAN")
        result = validate_migration(await read_payload(artifact), request)
        db.add(
            AuditEvent(
                job_id=job.job_id,
                event_type="DISPOSABLE_MIGRATION_VALIDATED",
                actor_type="USER",
                actor_id=actor_id,
                payload={
                    "artifact_id": str(artifact.artifact_id),
                    "content_hash": artifact.content_hash,
                    **result,
                },
            )
        )
        await db.commit()
        return result
    except (ValueError, TypeError) as exc:
        await db.rollback()
        logger.exception("phase5.validate_plan invalid samples")
        raise ValidationException("Invalid disposable sample tables") from exc
    except Exception:
        logger.exception("phase5.validate_plan failed | job_id=%s", job.job_id)
        await db.rollback()
        raise


async def decide_g2(
    db: AsyncSession, gate: WorkflowGate, approved: bool, *, freeze_cases: bool = True
) -> None:
    """Bind G2 to the current immutable suite and schema plan before committing a decision."""
    try:
        if not approved:
            return
        artifact = await latest(db, gate.job_id)
        payload = await read_payload(artifact)
        schema = await latest(db, gate.job_id, "SCHEMA_MIGRATION_PLAN")
        await read_payload(schema)
        if (
            gate.artifact_hashes.get(str(artifact.artifact_id)) != artifact.content_hash
            or gate.artifact_hashes.get(str(schema.artifact_id)) != schema.content_hash
            or (schema.producing_agent != "SchemaDataAgent" and payload["schema_hash"] != schema.content_hash)
        ):
            raise ConflictException(
                "G2 evidence is stale; review the current suite and schema plan"
            )
        if approved and any(
            c["outcome"] in ("FAILED", "NON_REPRODUCIBLE", "UNAVAILABLE")
            for c in payload["cases"]
        ):
            raise ConflictException("Failed baseline cannot be frozen")
        if not any(c["outcome"] == "PASSED" for c in payload["cases"]):
            raise ConflictException(
                "G2 approval requires at least one observed, replayable legacy case"
            )
        g2_rep = payload.get("g2_readiness")
        if approved and g2_rep and g2_rep.get("blocking_reasons"):
            raise ConflictException(
                f"G2 approval blocked: {'; '.join(g2_rep['blocking_reasons'])}"
            )
        plan = await read_payload(schema)
        if plan.get("status") == "REVIEW_REQUIRED":
            raise ConflictException(
                "Schema semantics require reviewed source/target overrides before G2 approval"
            )
        if plan["tables"]:
            if await validation_status(db, gate.job_id, schema.content_hash) != "PASS":
                raise ConflictException(
                    "Validate the current data plan with disposable sample data before G2 approval"
                )
        if approved and freeze_cases:
            for case in payload["cases"]:
                await db.execute(
                    update(TestCase)
                    .where(
                        TestCase.test_case_id == uuid.UUID(case["test_case_id"]),
                        TestCase.job_id == gate.job_id,
                    )
                    .values(is_frozen=True)
                )
    except Exception:
        logger.exception("phase5.decide_g2 failed | gate_id=%s", gate.gate_id)
        raise
