"""Phase 6 work/evidence only. Workflow transitions belong exclusively to Supervisor."""

import asyncio
import logging
import json
import uuid
from decimal import Decimal
from pathlib import PurePosixPath
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.config import settings
from app.core.errors import ConflictException, NotFoundException
from app.models.agent import AgentRun
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.budget import BudgetUsage
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.phase4 import (
    RepositorySnapshotModel,
    TargetBlueprintModel,
    ConversionPlanModel,
    ConversionPlanModuleModel,
)
from app.models.test_case import TestResult
from app.schemas.phase6 import ChangeSet
from app.services.artifact_service import ArtifactService
from app.services import phase6_workspace as workspace
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


async def publish(db, job, module, attempt, kind, data, lineage):
    try:
        # Serialize version allocation with all other Phase 6 publishers for this job.
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
            canonical(data),
            (
                "Verifier"
                if kind == "VERIFICATION_REPORT"
                else "Reviewer" if kind == "REVIEW_REPORT" else "CodeWriter"
            ),
            module_id=module.module_id,
            derived_from=lineage,
            extra_metadata={"phase": 6, "attempt_id": str(attempt.attempt_id)},
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
            if artifact.artifact_type == "CONVERTED_MODULE":
                evidence = {
                    **payload,
                    "code_artifact_id": str(artifact.artifact_id),
                    "code_hash": artifact.content_hash,
                }
            elif artifact.artifact_type == "VERIFICATION_REPORT":
                evidence.update(
                    verification=payload,
                    checks=payload.get("checks", []),
                    results=payload.get("cases", []),
                    verification_hash=artifact.content_hash,
                )
            elif artifact.artifact_type == "REVIEW_REPORT":
                evidence.update(review=payload, review_hash=artifact.content_hash)
        if "failure_signature" in (run.output_payload or {}):
            evidence["failure_signature"] = run.output_payload["failure_signature"]
        if attempt.status == "VERIFIED" and not all(
            k in evidence for k in ("code_hash", "verification_hash", "review_hash")
        ):
            raise ConflictException(
                "Verified status without immutable independent evidence is not valid"
            )
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
        maximum = min(5, 1 + job.max_repair_attempts)
        if last and last.attempt_number >= maximum:
            raise ConflictException(
                "Repair attempt limit exhausted; human escalation required"
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
                previous.status not in {"REPAIR_REQUIRED", "BLOCKED", "REJECTED"}
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
        run = AgentRun(
            run_id=uuid.uuid4(),
            job_id=job.job_id,
            agent_name="CodeWriter",
            task_id=f"p6-{uuid.uuid4().hex}",
            correlation_id=f"p6-{uuid.uuid4().hex[:16]}",
            model_provider=settings.PHASE6_MODEL_PROVIDER or "unconfigured",
            model_identifier=settings.PHASE6_MODEL_IDENTIFIER or "unconfigured",
            status="QUEUED",
            task_payload=get_secret_redactor().redact_object(context),
            trace_payload={"events": ["QUEUED"]},
        )
        run.task_payload = {
            **run.task_payload,
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
            attempt_number=number,
            status="QUEUED",
            git_branch=f"job/{job.job_id}/module/{module.module_id}/attempt/{number}",
            lease_generation=module.lease_generation,
        )
        db.add(attempt)
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
                )
                visited[identity] = reference["content_hash"]
            except Exception:
                logger.exception("phase6.hydrate_dependency failed")
                raise

        for reference in references:
            await visit(reference, set())
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
        repo = workspace.repository_for(str(job.job_id))
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
        await hydrate_dependencies(
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
        source_slice = {
            p: v
            for p, v in sources.items()
            if any(
                PurePosixPath(p) == scope or scope in PurePosixPath(p).parents
                for scope in scopes
            )
        }
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
        if isinstance(output, dict) and "content" in output:
            from app.services.phase5_engine import (
                strict_adapter_object,
                reject_json_constant,
            )

            output = json.loads(
                output["content"],
                object_pairs_hook=strict_adapter_object,
                parse_constant=reject_json_constant,
            )
        changes = ChangeSet.model_validate(output)
        applied = await workspace.apply_changes(
            worktree, changes.files, context["allowed_targets"]
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
        await db.commit()
        # ALL frozen cases, not only an optimistic module slice, run after every change.
        verification = await verifier_service.execute(
            snapshot, context["cases"], context["baseline_hash"]
        )
        verification["unobserved_cases"] = [
            {k: c.get(k) for k in ("test_case_id", "name", "outcome")}
            for c in context.get("unobserved_cases", [])
        ]
        verification["baseline_hash"] = context["baseline_hash"]
        verification["source_commit"] = applied["commit"]
        verification["verifier_version"] = "phase6-verifier-v1"
        reviewer = review(
            changes.files,
            context["public_contracts"],
            code.content_hash,
            design_notes=changes.design_notes,
            execution=verification,
        )
        verification_artifact = await publish(
            db,
            job,
            module,
            attempt,
            "VERIFICATION_REPORT",
            verification,
            [str(code.artifact_id), context["baseline_id"]],
        )
        review_artifact = await publish(
            db,
            job,
            module,
            attempt,
            "REVIEW_REPORT",
            reviewer,
            [str(code.artifact_id), str(verification_artifact.artifact_id)],
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
        for item in verification.get("cases", []):
            case = next(
                c for c in context["cases"] if c["test_case_id"] == item["test_case_id"]
            )
            db.add(
                TestResult(
                    test_case_id=uuid.UUID(item["test_case_id"]),
                    attempt_id=attempt.attempt_id,
                    outcome="PASSED" if item["status"] == "PASS" else "FAILED",
                    difference_classification=(
                        "NONE" if item["status"] == "PASS" else "REGRESSION"
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
                5, 1 + job.max_repair_attempts
            ):
                status, reason = (
                    "ESCALATED",
                    "Repeated failure or repair limit exhausted; human review required",
                )
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
                reason = (
                    "Conversion blocked: "
                    + (str(exc.message) if hasattr(exc, "message") else str(exc))[:500]
                )
                reason = get_secret_redactor().redact_text(reason)
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
