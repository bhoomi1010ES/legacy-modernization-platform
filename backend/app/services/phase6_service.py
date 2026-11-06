"""Phase 6 work/evidence only. Workflow transitions belong exclusively to Supervisor."""

import asyncio
import logging
import json
import re
import uuid
from decimal import Decimal
from pathlib import PurePosixPath
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.config import settings
from app.core.errors import (
    ConflictException,
    NotFoundException,
    WorkspaceException,
    IncompleteModelOutputError,
    MalformedModelOutputError,
)
from app.models.agent import AgentRun
from app.models.artifact import Artifact, ArtifactType, normalize_artifact_type
from app.models.audit import AuditEvent
from app.models.budget import BudgetUsage
from app.models.job import Job
from app.models.gate import GateDecision
from app.models.module import Module, ModuleAttempt, VerificationRun
from app.models.phase4 import (
    RepositorySnapshotModel,
    TargetBlueprintModel,
    ConversionPlanModel,
    ConversionPlanModuleModel,
)
from app.models.test_case import TestResult
from app.models.worker import WorkerRegistry
from app.schemas.phase6 import ChangeSet
from app.services.artifact_service import ArtifactService
from app.services import phase6_workspace as workspace
from app.services.repository_workspace_service import repository_workspace_service
from app.services.phase5_engine import canonical, digest
from app.services.phase5_service import read_payload
from app.services.secret_redactor import get_secret_redactor

logger = logging.getLogger(__name__)
ACTIVE = {"QUEUED", "RUNNING", "GENERATED", "VERIFYING"}


async def newest(db, module_id):
    try:
        return await db.scalar(
            select(ModuleAttempt)
            .where(ModuleAttempt.module_id == module_id)
            .order_by(ModuleAttempt.attempt_number.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
    except Exception:
        logger.exception("phase6.newest failed")
        raise


async def publish(db, job, module, attempt, kind, data, lineage, *, producer_run_id=None):
    try:
        canonical_kind = normalize_artifact_type(kind)
        # Serialize version allocation with all other Phase 6 publishers for this job.
        await db.scalar(select(Job).where(Job.job_id == job.job_id).with_for_update())
        version = (
            await db.scalar(
                select(func.max(Artifact.version)).where(
                    Artifact.job_id == job.job_id,
                    Artifact.artifact_type == canonical_kind,
                )
            )
            or 0
        ) + 1
        return await ArtifactService().create_artifact(
            db,
            job.job_id,
            canonical_kind,
            version,
            canonical(data),
            (
                "Verifier"
                if canonical_kind == ArtifactType.VERIFICATION_REPORT.value
                else "Reviewer" if canonical_kind == ArtifactType.REVIEW_REPORT.value else "CodeWriter"
            ),
            module_id=module.module_id,
            derived_from=lineage,
            extra_metadata={"phase": 6, "attempt_id": str(attempt.attempt_id)},
            producer_run_id=producer_run_id,
        )
    except Exception:
        logger.exception("phase6.publish failed")
        raise


async def detail(db, attempt):
    try:
        if attempt is None:
            raise NotFoundException("ModuleAttempt", "unknown")
        run = await db.get(AgentRun, attempt.agent_run_id, populate_existing=True)
        evidence = dict(run.output_payload or {})
        verification_run = await db.scalar(
            select(VerificationRun)
            .where(VerificationRun.attempt_id == attempt.attempt_id)
            .order_by(VerificationRun.created_at.desc())
            .limit(1)
        )
        verifier_agent_run = (
            await db.get(AgentRun, verification_run.agent_run_id)
            if verification_run and verification_run.agent_run_id
            else None
        )
        verifier_worker = (
            await db.get(WorkerRegistry, verification_run.worker_id)
            if verification_run and verification_run.worker_id
            else None
        )
        # Validate every stored evidence artifact before exposing success or a diff.
        for reference in run.output_artifact_refs or []:
            artifact = await db.get(Artifact, uuid.UUID(reference))
            if (
                artifact is None
                or artifact.job_id != run.job_id
                or artifact.module_id != attempt.module_id
                or artifact.extra_metadata.get("attempt_id") != str(attempt.attempt_id)
            ):
                raise ConflictException("Attempt evidence lineage mismatch")
            payload = await read_payload(artifact)
            if artifact.artifact_type == ArtifactType.CODE_MODULE.value:
                evidence = {
                    **payload,
                    "code_artifact_id": str(artifact.artifact_id),
                    "code_hash": artifact.content_hash,
                }
            elif artifact.artifact_type == ArtifactType.VERIFICATION_REPORT.value:
                evidence.update(
                    verification=payload,
                    checks=payload.get("checks", []),
                    results=payload.get("cases", []),
                    verification_hash=artifact.content_hash,
                )
            elif artifact.artifact_type == ArtifactType.REVIEW_REPORT.value:
                evidence.update(review=payload, review_hash=artifact.content_hash)
        if "failure_signature" in (run.output_payload or {}):
            evidence["failure_signature"] = run.output_payload["failure_signature"]
        if attempt.status == "VERIFIED" and not all(
            k in evidence for k in ("code_hash", "verification_hash", "review_hash")
        ):
            raise ConflictException(
                "Verified status without immutable independent evidence is not valid"
            )
        if attempt.status == "VERIFIED" and (
            verification_run is None
            or verification_run.status != "PASS"
            or evidence.get("verification", {}).get("verification_run_id")
            != str(verification_run.verification_run_id)
            or evidence.get("verification", {}).get("candidate_hash")
            != verification_run.candidate_hash
            or evidence.get("verification", {}).get("suite_hash")
            != verification_run.suite_hash
            or verifier_agent_run is None
            or verifier_agent_run.agent_name != "Verifier"
            or verifier_agent_run.status != "SUCCEEDED"
            or verifier_agent_run.run_id == run.run_id
            or verifier_agent_run.task_payload.get("candidate_hash")
            != verification_run.candidate_hash
            or verifier_agent_run.task_payload.get("suite_hash")
            != verification_run.suite_hash
            or verifier_agent_run.task_payload.get("profile_digest")
            != verification_run.profile_digest
            or digest(verifier_agent_run.task_payload.get("inputs", {}))
            != verification_run.input_hash
            or verifier_agent_run.trace_payload.get("worker_id")
            != verification_run.worker_id
            or verifier_agent_run.trace_payload.get("worker_id")
            == verifier_agent_run.task_payload.get("codewriter_worker_id")
            or verifier_worker is None
            or verifier_worker.worker_type != "VERIFIER"
            or verification_run.evidence_hash != digest(verification_run.evidence)
        ):
            raise ConflictException(
                "Verified status is not bound to a passing immutable run for this commit and suite"
            )
        if attempt.status == 'VERIFIED':
            from app.services.verification_proof import validate_success
            try:
                validate_success(evidence['verification'],verifier_agent_run,run.job_id)
            except (ValueError,KeyError,TypeError) as exc:
                raise ConflictException('Historical or current verification lacks authentic independent execution proof') from exc
        return get_secret_redactor().redact_object(
            {
                "attempt_id": str(attempt.attempt_id),
                "module_id": str(attempt.module_id),
                "attempt_number": attempt.attempt_number,
                "status": attempt.status,
                "git_branch": attempt.git_branch,
                "failure_reason": attempt.failure_reason,
                "metadata": {
                    "provider": run.model_provider,
                    "model": run.model_identifier,
                    "prompt_version": "phase6-codewriter-v1",
                    "trace": run.trace_payload,
                },
                "evidence": evidence,
                "verification_run": ({
                    "verification_run_id": str(verification_run.verification_run_id),
                    "agent_run_id": str(verification_run.agent_run_id) if verification_run.agent_run_id else None,
                    "status": verification_run.status,
                    "worker_id": verification_run.worker_id,
                    "candidate_hash": verification_run.candidate_hash,
                    "suite_hash": verification_run.suite_hash,
                    "profile_version": verification_run.profile_version,
                    "profile_digest": verification_run.profile_digest,
                    "started_at": verification_run.started_at.isoformat() if verification_run.started_at else None,
                    "finished_at": verification_run.finished_at.isoformat() if verification_run.finished_at else None,
                    "evidence_hash": verification_run.evidence_hash,
                } if verification_run else None),
                "completed_at": (
                    attempt.completed_at.isoformat() if attempt.completed_at else None
                ),
                "allowed_actions": [],
            }
        )
    except Exception:
        logger.exception("phase6.detail failed")
        raise


async def queue(db, job, module, key, actor, *, previous=None, rationale=None):
    """Called by Supervisor. Idempotency, leases and bounded attempts share its job lock."""
    try:
        from app.services.supervisor_service import supervisor_service
        from app.services.dependency_scheduler import dependency_scheduler

        job = await db.scalar(
            select(Job).where(Job.job_id == job.job_id).with_for_update()
        )
        identity = digest(
            {
                "module_id": str(module.module_id),
                "previous": str(previous.attempt_id) if previous else None,
                "rationale": rationale,
            }
        )
        runs = (
            (
                await db.execute(
                    select(AgentRun).where(
                        AgentRun.job_id == job.job_id,
                        AgentRun.agent_name == "CodeWriter",
                    )
                )
            )
            .scalars()
            .all()
        )
        for run in runs:
            if (
                run.task_payload.get("phase") == 6
                and run.task_payload.get("idempotency_key") == key
            ):
                if run.task_payload.get("request_identity") != identity:
                    raise ConflictException(
                        "Idempotency key belongs to a different request"
                    )
                return await db.scalar(
                    select(ModuleAttempt).where(
                        ModuleAttempt.agent_run_id == run.run_id
                    )
                )
        eligibility = await supervisor_service.require_conversion_eligibility(db, job)
        reservation = Decimal(str(settings.PHASE6_MAX_TASK_COST_USD))
        reserved = sum(
            (
                Decimal(str(r.task_payload.get("cost_reservation", 0)))
                for r in runs
                if r.status in ACTIVE
            ),
            Decimal(0),
        )
        if Decimal(job.budget_used_usd) + reserved + reservation > Decimal(
            job.budget_limit_usd
        ) or (
            module.budget_limit_usd
            and Decimal(module.budget_used_usd) + reservation
            > Decimal(module.budget_limit_usd)
        ):
            raise ConflictException(
                "Remaining job/module budget cannot reserve another bounded model task"
            )
        if module.job_id != job.job_id:
            raise NotFoundException("Module", str(module.module_id))
        last = await newest(db, module.module_id)
        if last and last.status in ACTIVE:
            raise ConflictException("Module already has an active attempt")
        maximum = min(50, 1 + (job.max_repair_attempts or 40))
        if last and last.attempt_number >= maximum:
            raise ConflictException(
                "Repair attempt limit exhausted; human escalation required"
            )
        if last and last.status == "WAITING_FOR_HUMAN" and not (previous and rationale):
            raise ConflictException(
                "Module is waiting for human review; provide review rationale to proceed with repair"
            )
        previous_run = (
            await db.get(AgentRun, previous.agent_run_id) if previous else None
        )
        stale_previous = previous_run is not None and any(
            previous_run.task_payload.get(k) != eligibility[k]
            for k in ("baseline_hash", "plan_hash")
        )
        if previous and (
            last is None
            or last.attempt_id != previous.attempt_id
            or (
                previous.status not in {"REPAIR_REQUIRED", "BLOCKED", "REJECTED", "WAITING_FOR_HUMAN"}
                and not stale_previous
            )
        ):
            raise ConflictException(
                "Repair requires the latest failing or blocked attempt"
            )
        if not previous and last:
            raise ConflictException("Use bounded repair for an existing module attempt")
        unit = next(
            (
                p
                for p in eligibility["approved_modules"]
                if isinstance(p, dict)
                and (
                    p.get("module_id") in (str(module.module_id), module.name)
                    or str(uuid.uuid5(job.job_id, p.get("module_id", "")))
                    == str(module.module_id)
                )
            ),
            None,
        )
        if (
            unit is None
            or module.target_path not in unit.get("target_scope", [])
            or module.legacy_path not in unit.get("source_scope", [])
        ):
            raise ConflictException(
                "Module paths are not part of the human-approved conversion plan"
            )
        inventory = (
            (await db.execute(select(Module).where(Module.job_id == job.job_id)))
            .scalars()
            .all()
        )
        dependency_ids = {m.name: str(m.module_id) for m in inventory}
        dependency_ids.update({str(m.module_id): str(m.module_id) for m in inventory})
        dependencies = {
            dependency_ids.get(d, str(uuid.uuid5(job.job_id, d)))
            for d in unit.get("dependencies", [])
        }
        if dependencies != set(module.dependency_module_ids or []):
            raise ConflictException(
                "Runtime dependencies differ from the approved plan"
            )
        all_modules = (
            (await db.execute(select(Module).where(Module.job_id == job.job_id)))
            .scalars()
            .all()
        )
        target = PurePosixPath(module.target_path)
        if (
            not module.target_path
            or target.is_absolute()
            or ".." in target.parts
            or str(target) == "."
        ):
            raise ConflictException(
                "An explicit approved module target scope is required"
            )
        for other in all_modules:
            if other.module_id == module.module_id:
                continue
            path = PurePosixPath(other.target_path)
            if path == target or path in target.parents or target in path.parents:
                raise ConflictException(
                    "Module target scopes conflict; revise the approved module plan"
                )
        for other_unit in eligibility["approved_modules"]:
            if other_unit == unit or not isinstance(other_unit, dict):
                continue
            if any(
                PurePosixPath(a) == PurePosixPath(b)
                or PurePosixPath(a) in PurePosixPath(b).parents
                or PurePosixPath(b) in PurePosixPath(a).parents
                for a in unit["target_scope"]
                for b in other_unit.get("target_scope", [])
            ):
                raise ConflictException("Approved module target scopes overlap")
        snapshot = await db.scalar(
            select(RepositorySnapshotModel)
            .where(RepositorySnapshotModel.job_id == job.job_id)
            .order_by(RepositorySnapshotModel.version.desc())
            .limit(1)
        )
        blueprint = await db.scalar(
            select(TargetBlueprintModel)
            .where(TargetBlueprintModel.job_id == job.job_id)
            .order_by(TargetBlueprintModel.version.desc())
            .limit(1)
        )
        plan = await db.scalar(
            select(ConversionPlanModel)
            .where(ConversionPlanModel.job_id == job.job_id)
            .order_by(ConversionPlanModel.version.desc())
            .limit(1)
        )
        planned = (
            await db.scalar(
                select(ConversionPlanModuleModel)
                .where(
                    ConversionPlanModuleModel.plan_id == plan.plan_id,
                    ConversionPlanModuleModel.module_id.in_(
                        [str(module.module_id), module.name]
                    ),
                )
                .limit(1)
            )
            if plan
            else None
        )
        if previous:
            module.status = "PENDING"
            await db.flush()
        claimed = await dependency_scheduler.claim_ready_modules(
            db,
            job.job_id,
            worker_id="phase6-supervisor",
            limit=1,
            lease_seconds=settings.PHASE6_SANDBOX_TIMEOUT + 180,
            module_ids=[module.module_id],
            commit_lease=False,
        )
        if not claimed:
            raise ConflictException(
                "Module dependencies, concurrency or budget block conversion"
            )
        leased_module = claimed[0]
        lease_owner = leased_module.lease_owner
        if leased_module.module_id != module.module_id or not lease_owner:
            raise ConflictException("Scheduler returned an invalid module lease")
        # Retain the job lock through lease + idempotency + unique attempt allocation.
        await db.scalar(select(Job).where(Job.job_id == job.job_id).with_for_update())
        last = await newest(db, module.module_id)
        number = (last.attempt_number if last else 0) + 1
        feedback = (await detail(db, previous))["evidence"] if previous else None
        dependency_evidence = []
        for dependency in module.dependency_module_ids or []:
            dep_attempt = await newest(db, uuid.UUID(dependency))
            if not dep_attempt or dep_attempt.status != "VERIFIED":
                raise ConflictException(
                    "Dependency has no independently verified attempt"
                )
            dep = (await detail(db, dep_attempt))["evidence"]
            if dep.get("baseline_hash") != eligibility["baseline_hash"]:
                raise ConflictException("Dependency verification is stale")
            dependency_evidence.append(
                {
                    "module_id": dependency,
                    "artifact_id": dep["code_artifact_id"],
                    "content_hash": dep["code_hash"],
                }
            )
        context = {
            "phase": 6,
            "idempotency_key": key,
            "request_identity": identity,
            "module_id": str(module.module_id),
            "name": module.name,
            "legacy_paths": [module.legacy_path],
            "allowed_target": module.target_path,
            "responsibility": planned.responsibility if planned else module.name,
            "public_contracts": blueprint.interfaces_payload if blueprint else [],
            "target_profile": blueprint.target_stack if blueprint else job.target_stack,
            "g1_constraints": blueprint.constraints_payload if blueprint else {},
            "g1_decisions": blueprint.accepted_decisions if blueprint else [],
            "dependency_contracts": (
                blueprint.integration_contracts_payload if blueprint else []
            ),
            "dependencies": dependency_evidence,
            "source_commit": (feedback or {}).get("source_commit")
            or (snapshot.commit_sha if snapshot else None),
            "repair_from": str(previous.attempt_id) if previous else None,
            "repair_feedback": feedback,
            "rationale": rationale,
            **eligibility,
        }
        g3_decision = await db.scalar(
            select(GateDecision).where(
                GateDecision.job_id == job.job_id,
                GateDecision.gate_id == uuid.UUID(eligibility["gate_ids"]["G3"]),
                GateDecision.gate_type == "G3",
                GateDecision.decision == "APPROVED",
            )
        )
        approved_options = (g3_decision.selected_options or {}) if g3_decision else {}
        provider_option = approved_options.get("CodeWriter.model_provider")
        model_option = approved_options.get("CodeWriter.model_identifier")
        if bool(provider_option) != bool(model_option):
            raise ConflictException(
                "G3 must approve both CodeWriter provider and model, or neither"
            )
        # Job-level choices are read only from the exact accepted G3 decision.
        # The deployment choice remains the default when G3 selects neither.
        model_provider = provider_option or settings.PHASE6_MODEL_PROVIDER or "unconfigured"
        model_identifier = model_option or settings.PHASE6_MODEL_IDENTIFIER or "unconfigured"
        model_approval_hash = digest(
            {
                "g3_gate_id": eligibility["gate_ids"]["G3"],
                "g3_decision_id": str(g3_decision.decision_id) if g3_decision else None,
                "provider": model_provider,
                "model": model_identifier,
            }
        )
        context.update(
            model_provider=model_provider,
            model_identifier=model_identifier,
            model_approval_hash=model_approval_hash,
            gateway_request_id=f"phase6-{uuid.uuid4()}",
        )
        if module.plan_hash != context["plan_hash"]:
            raise ConflictException("Module contract plan hash differs from the G3-approved plan snapshot")
        if module.integration_base_sha != context["source_commit"]:
            raise ConflictException("Module worktree integration base differs from its approved plan snapshot")
        run = AgentRun(
            run_id=uuid.uuid4(),
            job_id=job.job_id,
            agent_name="CodeWriter",
            # Attempts are retries of one durable module conversion task.
            task_id=f"p6-{module.module_id}",
            correlation_id=f"p6-{uuid.uuid4().hex[:16]}",
            model_provider=model_provider,
            model_identifier=model_identifier,
            status="QUEUED",
            task_payload=get_secret_redactor().redact_object(context),
            trace_payload={"events": ["QUEUED"]},
        )
        run.task_payload = {
            **run.task_payload,
            "job_id": str(job.job_id),
            "agent_run_id": str(run.run_id),
            "cases": [c for c in eligibility["cases"] if c["outcome"] == "PASSED"],
            "unobserved_cases": [
                c for c in eligibility["cases"] if c["outcome"] != "PASSED"
            ],
            "cost_reservation": float(reservation),
            "legacy_paths": unit["source_scope"],
            "allowed_targets": unit["target_scope"],
            "responsibility": unit.get("responsibility", module.name),
            "public_contracts": [
                c
                for c in (blueprint.interfaces_payload if blueprint else [])
                if not unit.get("interfaces")
                or c.get("contract_id") in unit["interfaces"]
            ],
        }
        db.add(run)
        await db.flush()
        attempt = ModuleAttempt(
            attempt_id=uuid.uuid4(),
            module_id=module.module_id,
            agent_run_id=run.run_id,
            worker_id=lease_owner,
            attempt_number=number,
            status="QUEUED",
            git_branch=f"job/{job.job_id}/module/{module.module_id}/attempt/{number}",
            lease_generation=module.lease_generation,
        )
        db.add(attempt)
        run.task_payload={**run.task_payload,'attempt_id':str(attempt.attempt_id)}
        if previous:
            ids = select(ModuleAttempt.attempt_id).where(
                ModuleAttempt.module_id == module.module_id
            )
            await db.execute(
                update(TestResult)
                .where(TestResult.attempt_id.in_(ids))
                .values(
                    invalidated=True,
                    invalidation_reason="A new repair requires independent re-verification",
                )
            )
        db.add(
            AuditEvent(
                job_id=job.job_id,
                event_type=(
                    "MODULE_REPAIR_QUEUED" if previous else "MODULE_CONVERSION_QUEUED"
                ),
                actor_type="USER" if actor != "Supervisor" else "SYSTEM",
                actor_id=actor,
                target_resource=str(attempt.attempt_id),
                payload={
                    "attempt_number": number,
                    "baseline_hash": eligibility["baseline_hash"],
                    "request_identity": identity,
                },
            )
        )
        await db.commit()
        return attempt
    except Exception:
        logger.exception("phase6.queue failed")
        raise


async def hydrate_dependencies(
    db, worktree, references, job_id, baseline_hash, plan_hash
):
    """Materialize the verified transitive closure before the module's own scoped diff."""
    try:
        visited = {}
        staged_files: set[str] = set()

        async def visit(reference, ancestors):
            try:
                identity = reference["artifact_id"]
                if identity in ancestors:
                    raise ConflictException("Dependency evidence cycle")
                if identity in visited:
                    if visited[identity] != reference["content_hash"]:
                        raise ConflictException(
                            "Conflicting dependency evidence hashes"
                        )
                    return
                artifact = await db.get(Artifact, uuid.UUID(identity))
                if (
                    artifact is None
                    or artifact.job_id != job_id
                    or str(artifact.module_id) != reference["module_id"]
                    or artifact.content_hash != reference["content_hash"]
                ):
                    raise ConflictException("Dependency evidence lineage changed")
                payload = await read_payload(artifact)
                if (
                    payload["baseline_hash"] != baseline_hash
                    or payload["plan_hash"] != plan_hash
                ):
                    raise ConflictException("Dependency evidence is stale")
                for child in payload.get("dependency_evidence", []):
                    await visit(child, ancestors | {identity})
                await workspace.apply_changes(
                    worktree,
                    payload["files"],
                    payload.get("allowed_targets", payload["allowed_target"]),
                    expected_staged_files=staged_files,
                )
                staged_files.update(payload["files"])
                visited[identity] = reference["content_hash"]
            except Exception:
                logger.exception("phase6.hydrate_dependency failed")
                raise

        for reference in references:
            await visit(reference, set())
        return staged_files
    except Exception:
        logger.exception("phase6.hydrate_dependencies failed")
        raise


async def execute_attempt(db, attempt_id, *, gateway=None):
    """Supervisor worker task. Changes and verification are separate trust boundaries."""
    attempt = None
    heartbeat_task = None
    heartbeat_stop = None
    try:
        from app.services.supervisor_service import supervisor_service
        from app.services.code_writer import code_writer_service
        from app.services.verifier_agent import verifier_service
        from app.services.reviewer_agent import review

        attempt = await db.scalar(
            select(ModuleAttempt)
            .where(ModuleAttempt.attempt_id == attempt_id)
            .with_for_update(skip_locked=True)
        )
        if attempt is None or attempt.status != "QUEUED":
            return
        run = await db.get(AgentRun, attempt.agent_run_id)
        module = await db.get(Module, attempt.module_id)
        job = await db.get(Job, module.job_id)
        from app.services.verification_profiles import get_profile
        target_profile = get_profile(job.target_stack)
        current = await supervisor_service.require_conversion_eligibility(db, job)
        context = run.task_payload
        if (
            current["baseline_hash"] != context["baseline_hash"]
            or current["plan_hash"] != context["plan_hash"]
            or current["gate_ids"] != context["gate_ids"]
        ):
            raise ConflictException("Queued task approvals or baseline are stale")
        attempt.status = run.status = "RUNNING"
        module.status = "RUNNING"
        from app.models.base import utc_now
        from datetime import timedelta

        lease_owner = f"phase6:{run.run_id}"
        module.lease_owner = lease_owner
        module.lease_heartbeat_at = utc_now()
        module.lease_expires_at = utc_now() + timedelta(
            seconds=settings.PHASE6_SANDBOX_TIMEOUT + 180
        )
        attempt.lease_generation = module.lease_generation
        await db.commit()

        heartbeat_stop = asyncio.Event()
        session_factory = async_sessionmaker(db.bind, expire_on_commit=False)

        async def heartbeat():
            interval = max(1, min(30, settings.PHASE6_SANDBOX_TIMEOUT // 3))
            while not heartbeat_stop.is_set():
                try:
                    await asyncio.wait_for(heartbeat_stop.wait(), timeout=interval)
                    break
                except asyncio.TimeoutError:
                    async with session_factory() as heartbeat_db:
                        renewed = await dependency_scheduler.renew_lease(
                            heartbeat_db,
                            module.module_id,
                            worker_id=lease_owner,
                            lease_generation=attempt.lease_generation,
                            lease_seconds=settings.PHASE6_SANDBOX_TIMEOUT + 180,
                        )
                    if not renewed:
                        break

        from app.services.dependency_scheduler import dependency_scheduler
        heartbeat_task = asyncio.create_task(heartbeat())
        repo = await repository_workspace_service.ensure_workspace(
            db,
            job,
            expected_commit=context.get("source_commit"),
            correlation_id=run.correlation_id,
        )
        await repository_workspace_service.validate_workspace(
            job.job_id,
            expected_commit=context.get("source_commit"),
            expected_source=job.source_repository,
            raise_on_error=True,
        )
        worktree, branch = await workspace.prepare(
            repo,
            str(job.job_id),
            str(module.module_id),
            str(attempt.attempt_id),
            attempt.attempt_number,
            context["source_commit"] or "",
        )
        attempt.git_branch = branch
        # Bring only verified dependency changes into this private worktree.
        staged_dependency_files = await hydrate_dependencies(
            db,
            worktree,
            context["dependencies"],
            job.job_id,
            context["baseline_hash"],
            context["plan_hash"],
        )
        sources = await workspace.file_snapshot(worktree)
        scopes = [
            PurePosixPath(p)
            for p in context["legacy_paths"] + context["allowed_targets"]
        ]
        other_legacy_scopes = [
            PurePosixPath(m)
            for m in (
                await db.execute(
                    select(Module.legacy_path).where(
                        Module.job_id == job.job_id,
                        Module.module_id != module.module_id,
                    )
                )
            ).scalars().all()
            if m
        ]
        source_slice = {}
        for p, v in sources.items():
            posix_p = PurePosixPath(p)
            if posix_p.name in (
                "package-lock.json",
                "yarn.lock",
                "pnpm-lock.yaml",
                "poetry.lock",
            ):
                continue
            if not any(
                posix_p == scope or scope in posix_p.parents for scope in scopes
            ):
                continue
            if any(
                other in posix_p.parents
                and not any(other in scope.parents for scope in scopes)
                for other in other_legacy_scopes
            ):
                continue
            source_slice[p] = v
        if not source_slice:
            for p, v in sources.items():
                p_lower = p.lower()
                if any(k in p_lower for k in ("model", "migration", "schema", "entity", ".sql")):
                    source_slice[p] = v
            if not source_slice:
                for p, v in sources.items():
                    if "/" not in p or p.count("/") <= 1:
                        source_slice[p] = v
        if not source_slice:
            raise ValueError("Approved module legacy paths have no source evidence")
        from app.services.budget_manager import budget_manager

        budget = await budget_manager.evaluate_budget(
            db, job, agent_id="CodeWriter", task_id=run.task_id
        )
        if budget.is_exceeded and budget.exceeded_dimension != "CONCURRENCY":
            raise ConflictException(budget.blocking_reason)
        output, usage, trace = await code_writer_service.generate(
            context, source_slice, gateway=gateway
        )
        # Preserve/charge actual returned provider usage even for rejected generation.
        await db.scalar(
            select(Job)
            .where(Job.job_id == job.job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        run.input_tokens = usage["input_tokens"]
        run.output_tokens = usage["output_tokens"]
        run.cost_usd = Decimal(str(usage["cost_usd"]))
        run.reported_input_tokens = usage.get("reported_input_tokens")
        run.reported_output_tokens = usage.get("reported_output_tokens")
        run.provider_request_id = (
            usage.get("provider_request_id")
            or trace.get("provider_request_id")
            or trace.get("provider_metadata", {}).get("request_id")
        )
        run.provider_model_id = (
            usage.get("provider_model_id")
            or trace.get("provider_metadata", {}).get("actual_model")
            or trace.get("provider_metadata", {}).get("model")
        )
        run.estimated_cost = (
            Decimal(str(usage["estimated_cost"]))
            if usage.get("estimated_cost") is not None
            else None
        )
        run.billed_cost = (
            Decimal(str(usage["billed_cost"]))
            if usage.get("billed_cost") is not None
            else None
        )
        if run.provider_model_id:
            run.model_identifier = str(run.provider_model_id)[:100]
        job.budget_used_usd += run.cost_usd
        module.budget_used_usd += run.cost_usd
        db.add(
            BudgetUsage(
                job_id=job.job_id,
                run_id=run.run_id,
                amount_usd=run.cost_usd,
                tokens=run.input_tokens + run.output_tokens,
            )
        )
        run.trace_payload = {
            **trace,
            "events": ["QUEUED", "GENERATED"],
            "agent_version": "phase6.1",
        }
        await db.commit()
        if (
            job.budget_used_usd > job.budget_limit_usd
            or (
                module.budget_limit_usd
                and module.budget_used_usd > module.budget_limit_usd
            )
            or run.cost_usd > Decimal(str(context["cost_reservation"]))
        ):
            raise ValueError(
                "Actual provider spend exceeded remaining module/job budget; escalate"
            )
        if run.cancel_requested:
            raise ValueError("Attempt cancellation requested")
        if trace.get("action") != "final":
            raise ValueError(
                "CodeWriter cannot execute tools or supply verification evidence"
            )
        if trace.get("provider_metadata", {}).get("finish_reason") == "length":
            raise IncompleteModelOutputError("Model response was truncated due to output token ceiling limit.")
        if isinstance(output, dict) and "content" in output:
            from app.services.phase5_engine import (
                strict_adapter_object,
                reject_json_constant,
            )

            raw_str = output["content"].strip()
            if raw_str.startswith("```json"):
                raw_str = raw_str[7:]
            elif raw_str.startswith("```"):
                raw_str = raw_str[3:]
            if raw_str.endswith("```"):
                raw_str = raw_str[:-3]
            raw_str = raw_str.strip()

            try:
                output = json.loads(
                    raw_str,
                    object_pairs_hook=strict_adapter_object,
                    parse_constant=reject_json_constant,
                )
            except json.JSONDecodeError as jde:
                raise MalformedModelOutputError(f"Malformed or truncated model JSON output: {jde}") from jde
            except ValueError as ve:
                if "Duplicate adapter JSON key" in str(ve):
                    logger.warning("Duplicate key in model JSON output; falling back to standard json.loads")
                    try:
                        output = json.loads(raw_str)
                    except json.JSONDecodeError as jde:
                        raise MalformedModelOutputError(f"Malformed or truncated model JSON output: {jde}") from jde
                else:
                    raise MalformedModelOutputError(f"Failed parsing model JSON output: {ve}") from ve
        try:
            changes = ChangeSet.model_validate(output)
        except Exception as ve:
            raise MalformedModelOutputError(f"Model output schema validation failed: {ve}") from ve
        if context.get("allowed_targets"):
            scopes = [PurePosixPath(t) for t in context["allowed_targets"]]
            filtered_files = {}
            for path_key, file_content in changes.files.items():
                path = PurePosixPath(path_key)
                if (
                    path_key
                    and "\\" not in path_key
                    and not path.is_absolute()
                    and path.as_posix() == path_key
                    and not any(part in {"", ".", ".."} for part in path.parts)
                    and any(
                        path == scope or (not scope.suffix and scope in path.parents)
                        for scope in scopes
                    )
                ):
                    filtered_files[path_key] = file_content

            if not filtered_files and len(context["allowed_targets"]) == 1:
                target_only = context["allowed_targets"][0]
                for path_key, file_content in changes.files.items():
                    if "migration" in path_key.lower() or "schema" in path_key.lower() or path_key.endswith((".sql", ".py")):
                        filtered_files[target_only] = file_content
                        break
                if not filtered_files and changes.files:
                    first_k = next(iter(changes.files))
                    filtered_files[target_only] = changes.files[first_k]

            if filtered_files:
                changes.files = filtered_files
            else:
                for path_key in changes.files:
                    path = PurePosixPath(path_key)
                    if (
                        not path_key
                        or "\\" in path_key
                        or path.is_absolute()
                        or path.as_posix() != path_key
                        or any(part in {"", ".", ".."} for part in path.parts)
                        or not any(
                            path == scope or (not scope.suffix and scope in path.parents)
                            for scope in scopes
                        )
                    ):
                        raise MalformedModelOutputError(
                            f"Generated path is not a canonical path within an approved target: {path_key!r}"
                        )
        applied = await workspace.apply_changes(
            worktree,
            changes.files,
            context["allowed_targets"],
            expected_staged_files=staged_dependency_files,
        )
        snapshot = await workspace.file_snapshot(worktree)
        evidence = {
            **applied,
            "files": changes.files,
            "allowed_target": module.target_path,
            "design_notes": changes.design_notes,
            "assumptions": changes.assumptions,
            "suggested_test_commands": changes.test_commands,
            "baseline_hash": context["baseline_hash"],
            "plan_hash": context["plan_hash"],
            "source_commit": context["source_commit"],
            "workspace": str(attempt.attempt_id),
            "repair_feedback": context["repair_feedback"],
            "dependency_evidence": context["dependencies"],
        }
        evidence["allowed_targets"] = context["allowed_targets"]
        code = await publish(
            db,
            job,
            module,
            attempt,
            "CONVERTED_MODULE",
            evidence,
            [
                context["baseline_id"],
                *[d["artifact_id"] for d in context["dependencies"]],
            ],
        )
        evidence.update(
            code_artifact_id=str(code.artifact_id), code_hash=code.content_hash
        )
        run.output_artifact_refs = [str(code.artifact_id)]
        run.output_payload = dict(evidence)
        attempt.status = "VERIFYING"
        run.status = "SUCCEEDED"
        run.completed_at = utc_now()
        await db.commit()
        # ALL frozen cases, not only an optimistic module slice, run after every change.
        suite_hash = digest({
            "baseline_hash": context["baseline_hash"],
            "cases": context["cases"],
        })
        execution_profile = {
            "version": target_profile["version"],
            "image": target_profile["image"],
            "runtime": target_profile["runtime"],
            "timeout": target_profile["timeout"],
            "adapter": target_profile["adapter"],
            "checks": target_profile["checks"],
            "system_checks": target_profile["system_checks"],
            "target_key": target_profile["target_key"],
        }
        profile_digest = digest(execution_profile)
        verification_inputs = {
            "candidate_hash": applied["candidate_hash"],
            "suite_hash": suite_hash,
            "baseline_hash": context["baseline_hash"],
            "files": snapshot,
            "cases": context["cases"],
            "profile_version": target_profile["version"],
            "profile_digest": profile_digest,
            "execution_profile": execution_profile,
            "policy": "G2 frozen cases; target-stack checks; missing tools block; no CodeWriter verdicts",
        }
        from app.services.worker_dispatch_service import worker_dispatch_service
        from app.services.durable_verification import prepare_and_execute
        verification, verification_run, verifier_run = await prepare_and_execute(
            db, job, verification_inputs, attempt_id=attempt.attempt_id,
            artifact_refs=[str(code.artifact_id), context['baseline_id']], codewriter_worker_id=lease_owner,
        )
        verifier_worker_id = verification.get('independent_worker_id')
        profile_digest = verification_run.profile_digest
        verification["unobserved_cases"] = [
            {k: c.get(k) for k in ("test_case_id", "name", "outcome")}
            for c in context.get("unobserved_cases", [])
        ]
        verification["baseline_hash"] = context["baseline_hash"]
        verification["source_commit"] = applied["base_sha"]
        verification["candidate_hash"] = applied["candidate_hash"]
        verification["suite_hash"] = suite_hash
        verification["verification_run_id"] = str(verification_run.verification_run_id)
        verification["changeset_diff_hash"] = applied["diff_hash"]
        verification["verifier_version"] = "phase6-verifier-v1"
        for check in verification.get("checks", []):
            check["source_commit_hash"] = applied["base_sha"]
            check["candidate_hash"] = applied["candidate_hash"]
            check["image_digest"] = verification.get("image_id")
            check["dependency_hashes"] = [
                str(item.get("content_hash"))
                for item in context.get("dependencies", [])
                if item.get("content_hash")
            ]
        verification["coverage_ceiling"] = {
            "executed_cases": len(verification.get("cases", [])),
            "frozen_cases": len(context["cases"]),
            "unobserved_cases": len(context.get("unobserved_cases", [])),
            "claim": "Selected frozen scenarios only; does not establish complete behavior equivalence.",
        }
        reviewer = review(
            changes.files,
            context["public_contracts"],
            code.content_hash,
            design_notes=changes.design_notes,
            execution=verification,
        )
        external_review=verification.get('independent_review') or {'status':'BLOCKED','findings':[]}
        reviewer['findings'] += external_review.get('findings',[])
        if external_review['status']!='PASS' or reviewer['findings']:
            reviewer['status']='REJECTED'
        reviewer.update(candidate_hash=applied['candidate_hash'],suite_hash=suite_hash,
            controller_attestation=verification.get('controller_attestation'))
        verification_artifact = await publish(
            db,
            job,
            module,
            attempt,
            "VERIFICATION_REPORT",
            verification,
            [str(code.artifact_id), context["baseline_id"]],
            producer_run_id=verifier_run.run_id,
        )
        review_artifact = await publish(
            db,
            job,
            module,
            attempt,
            "REVIEW_REPORT",
            reviewer,
            [str(code.artifact_id), str(verification_artifact.artifact_id)],
            producer_run_id=uuid.UUID(verification['reviewer_agent_run_id']),
        )
        run.output_artifact_refs = [
            str(code.artifact_id),
            str(verification_artifact.artifact_id),
            str(review_artifact.artifact_id),
        ]
        evidence.update(
            verification=verification,
            review=reviewer,
            checks=verification.get("checks", []),
            results=verification.get("cases", []),
            verification_hash=verification_artifact.content_hash,
            review_hash=review_artifact.content_hash,
        )
        run.output_payload = dict(evidence)
        await db.scalar(
            select(Job)
            .where(Job.job_id == job.job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        current = await supervisor_service.require_conversion_eligibility(db, job)
        if any(
            current[k] != context[k] for k in ("baseline_hash", "plan_hash", "gate_ids")
        ):
            raise ConflictException(
                "Evidence changed during execution; results cannot be reused"
            )
        active_attempt = await newest(db, module.module_id)
        if (
            active_attempt.attempt_id != attempt.attempt_id
            or active_attempt.status != "VERIFYING"
        ):
            raise ConflictException(
                "Attempt was interrupted or superseded; its execution cannot overwrite newer evidence"
            )
        observed_by_id = {
            item["test_case_id"]: item for item in verification.get("cases", [])
        }
        for case in context["cases"]:
            item = observed_by_id.get(case["test_case_id"])
            if item is None:
                db.add(
                    TestResult(
                        test_case_id=uuid.UUID(case["test_case_id"]),
                        attempt_id=attempt.attempt_id,
                        outcome="FAILED",
                        difference_classification="UNOBSERVED",
                        legacy_output={"output": case["expected"], "side_effects": case["side_effects"]},
                        converted_output=None,
                    )
                )
                continue
            db.add(
                TestResult(
                    test_case_id=uuid.UUID(item["test_case_id"]),
                    attempt_id=attempt.attempt_id,
                    outcome="PASSED" if item["status"] == "PASS" else "FAILED",
                    difference_classification=(
                        item.get("difference_classification", "NONE" if item["status"] == "PASS" else "REGRESSION")
                    ),
                    legacy_output={
                        "output": case["expected"],
                        "side_effects": case["side_effects"],
                    },
                    converted_output=item.get("actual"),
                )
            )
        if not verification.get("available"):
            status, reason = "BLOCKED", verification.get(
                "reason", "Sandbox unavailable"
            )
        elif verification.get("passed") and reviewer["status"] == "PASS":
            status, reason = "VERIFIED", None
        else:
            status, reason = (
                "REPAIR_REQUIRED",
                "Independent verification or review failed; exact evidence attached",
            )
            failure_signature = digest(
                {
                    "failed": [
                        (c.get("category", c.get("test_case_id")), c.get("status"))
                        for c in verification.get("checks", [])
                        + verification.get("cases", [])
                        if c.get("status") != "PASS"
                    ],
                    "findings": [
                        {k: f.get(k) for k in ("category", "message", "path")}
                        for f in reviewer["findings"]
                    ],
                }
            )
            evidence["failure_signature"] = failure_signature
            prior = context.get("repair_feedback") or {}
            if prior.get(
                "failure_signature"
            ) == failure_signature or attempt.attempt_number >= min(
                50, 1 + (job.max_repair_attempts or 40)
            ):
                status, reason = (
                    "WAITING_FOR_HUMAN",
                    "Repeated failure or repair limit exhausted; human review required",
                )
        verification_run.status = (
            "BLOCKED" if not verification.get("available")
            else "PASS" if verification.get("passed") and reviewer["status"] == "PASS"
            else "FAIL"
        )
        verification_run.finished_at = utc_now()
        verification_run.evidence = {
            "verification": verification,
            "review": reviewer,
            "candidate_hash": applied["candidate_hash"],
            "suite_hash": suite_hash,
            "profile_digest": profile_digest,
        }
        verification_run.evidence_hash = digest(verification_run.evidence)
        verifier_run.status = "SUCCEEDED" if verification_run.status == "PASS" else "FAILED"
        verifier_run.output_payload = {
            "verification_run_id": str(verification_run.verification_run_id),
            "status": verification_run.status,
            "evidence_hash": verification_run.evidence_hash,
            "candidate_hash": verification_run.candidate_hash,
            "suite_hash": verification_run.suite_hash,
        }
        verifier_run.completed_at = verification_run.finished_at
        verifier_run.trace_payload = {
            **verifier_run.trace_payload,
            "events": ["QUEUED", "LEASED", "EXECUTED", verification_run.status],
        }
        if verifier_worker_id:
            await worker_dispatch_service.deregister_worker(db, verifier_worker_id, "STOPPED")
        # Supervisor is the only caller allowed to publish the final module disposition.
        run.output_payload = dict(evidence)
        heartbeat_stop.set()
        await heartbeat_task
        await supervisor_service.record_module_disposition(
            db, job, module, attempt, run, status, reason
        )
    except Exception as exc:
        logger.exception(
            "phase6.execute_attempt failed | attempt_id=%s | error_type=%s",
            attempt_id,
            type(exc).__name__,
        )
        if heartbeat_stop is not None:
            heartbeat_stop.set()
        if heartbeat_task is not None:
            try:
                await heartbeat_task
            except Exception:
                logger.exception("phase6 lease heartbeat shutdown failed")
        await db.rollback()
        if attempt is not None:
            attempt = await db.get(ModuleAttempt, attempt_id)
            if attempt and attempt.status in ACTIVE:
                module = await db.get(Module, attempt.module_id)
                run = await db.get(AgentRun, attempt.agent_run_id)
                job = await db.get(Job, module.job_id)
                workspace_failure = exc if isinstance(exc, WorkspaceException) else None
                if workspace_failure is None:
                    validation = await repository_workspace_service.validate_workspace(
                        job.job_id,
                        expected_commit=(run.task_payload or {}).get("source_commit"),
                        expected_source=job.source_repository,
                    )
                    if not validation.is_ready:
                        try:
                            repository_workspace_service._raise_validation(
                                validation.error_code or "WORKSPACE_INVALID",
                                validation.error_message or "Repository workspace became unavailable.",
                            )
                        except WorkspaceException as detected:
                            workspace_failure = detected
                err_msg = str(getattr(exc, "message", None) or str(exc) or type(exc).__name__)
                reason = f"Conversion blocked: {err_msg}"[:500]
                reason = get_secret_redactor().redact_text(reason)
                if workspace_failure is not None:
                    from app.models.base import utc_now

                    code = workspace_failure.code
                    attempt.status = "BLOCKED"
                    attempt.failure_reason = f"{code}: {workspace_failure.message}"
                    attempt.completed_at = utc_now()
                    run.status = "FAILED"
                    run.failure_classification = code
                    run.error_message = attempt.failure_reason
                    run.completed_at = utc_now()
                    run.trace_payload = {
                        **(run.trace_payload or {}),
                        "events": [*(run.trace_payload or {}).get("events", []), "WORKSPACE_LOST"],
                    }
                    module.status = "PENDING"
                    module.lease_owner = None
                    module.lease_expires_at = None
                    module.lease_heartbeat_at = None
                    module.lease_generation += 1
                    db.add(AuditEvent(
                        job_id=job.job_id,
                        event_type="WORKSPACE_LOST",
                        actor_type="SYSTEM",
                        actor_id="Supervisor",
                        correlation_id=run.correlation_id,
                        target_resource=str(attempt.attempt_id),
                        payload={
                            "task_id": run.task_id,
                            "attempt_id": str(attempt.attempt_id),
                            "agent": "CodeWriter",
                            "error_code": code,
                            "workspace_path": str(
                                repository_workspace_service.get_workspace_path(job.job_id)
                            ),
                        },
                    ))
                    await db.commit()
                    return
                if isinstance(exc, IncompleteModelOutputError):
                    run.failure_classification = "INCOMPLETE_MODEL_OUTPUT"
                elif isinstance(exc, MalformedModelOutputError):
                    run.failure_classification = "MALFORMED_MODEL_OUTPUT"
                elif run.failure_classification is None:
                    run.failure_classification = "EXECUTION_ERROR"

                from app.services.supervisor_service import supervisor_service

                await supervisor_service.record_module_disposition(
                    db, job, module, attempt, run, "BLOCKED", reason
                )


async def request_waiver(db, attempt, finding_id, rationale, actor):
    """Audited human-review request only; never overrides a failed execution."""
    try:
        evidence = (await detail(db, attempt))["evidence"]
        findings = evidence.get("review", {}).get("findings", [])
        if finding_id not in {f["finding_id"] for f in findings}:
            raise NotFoundException("Finding", finding_id)
        module = await db.get(Module, attempt.module_id)
        event = AuditEvent(
            job_id=module.job_id,
            event_type="MODULE_WAIVER_REQUESTED",
            actor_type="USER",
            actor_id=actor,
            target_resource=str(attempt.attempt_id),
            payload={
                "finding_id": finding_id,
                "rationale": rationale,
                "review_hash": evidence["review_hash"],
                "code_hash": evidence["code_hash"],
                "status": "REQUESTED",
            },
        )
        db.add(event)
        await db.commit()
        return {
            "status": "REQUESTED",
            "finding_id": finding_id,
            "applied": False,
            "message": "Human review requested; verification remains blocking",
        }
    except Exception:
        logger.exception("phase6.request_waiver failed")
        raise
