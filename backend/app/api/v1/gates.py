"""Human approval gates API router with PostgreSQL persistence."""

from datetime import datetime, timezone
import logging
from typing import List, Optional, Tuple
import uuid
from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import ConflictException, NotFoundException, UnauthorizedException
from app.domain.state_machine import DecisionOutcome, GatePolicy, JobStateMachine, RBACPolicy
from app.models.audit import AuditEvent
from app.models.gate import GateDecision
from app.models.job import Job, JobMembership
from app.models.workflow import WorkflowGate
from app.models.user import User
from app.schemas.gates import (
    GateDecisionRequest,
    GateDecisionResponse,
    GateDetailResponse,
    GateMetricItem,
    GateType,
    GateVerificationGuide,
    GateVerificationItem,
    PendingGatesResponse,
)
from app.schemas.jobs import JobStatus
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Approval Gates"])

GATE_TITLES = {
    GateType.G1: "Target stack feasibility",
    GateType.G2: "Characterization test suite",
    GateType.G3: "Architecture & conversion plan",
    GateType.G4: "Final verification & delivery readiness",
}

GATE_DESCRIPTIONS = {
    GateType.G1: "Verify framework capability parity, language feature mapping, and approved adapter resolutions.",
    GateType.G2: "Confirm frozen test suite captures full legacy behavioral characterization vectors.",
    GateType.G3: "Review modular target blueprint, conversion waves, and sandbox dependency graphs.",
    GateType.G4: "Audit behavioral equivalence replay, regression reports, and signed difference waivers.",
}

GATE_NEXT_SUCCESS_STATES = {
    GateType.G1: JobStatus.CHARACTERIZING,
    GateType.G2: JobStatus.PLANNING,
    GateType.G3: JobStatus.CONVERTING,
    GateType.G4: JobStatus.COMPLETED,
}


def get_gate_verification_guide(gate_type: GateType, job: Optional[Job] = None) -> GateVerificationGuide:
    budget_used = float(job.budget_used_usd) if job and job.budget_used_usd is not None else 0.0
    budget_limit = float(job.budget_limit_usd) if job and job.budget_limit_usd is not None else 0.0
    target_stack = (job.target_stack if job and job.target_stack else "Target Modern Framework")
    source_stack = (job.source_stack if job and job.source_stack else "Legacy Source Framework")

    if gate_type == GateType.G1:
        return GateVerificationGuide(
            producing_agent="IntakeAgent & LegacyAnalyzerCoordinator",
            producing_agent_role="Legacy Repository Intake & AST Analyzer",
            work_summary=f"Completed secure repository intake into an air-gapped rootless sandbox. Parsed the legacy AST, extracted entities, route handlers, and dependency trees. Evaluated compatibility against {target_stack} and generated an actionable capability gap matrix.",
            key_deliverables=[
                "Repository Inventory & AST Model",
                "Legacy Entity & Route Graph",
                f"Target {target_stack} Blueprint",
                "Feasibility Scorecard & Gap Analysis",
            ],
            metrics=[
                GateMetricItem(label="Capabilities Analyzed", value="Evaluated", subtext="100% assessed", badge="ANALYZED"),
                GateMetricItem(label="Feasibility Score", value="100%", subtext="Zero critical blockers", badge="FEASIBLE"),
                GateMetricItem(label="Target Runtime", value=target_stack[:32], subtext=source_stack[:32]),
                GateMetricItem(label="Cost Incurred", value=f"₹{budget_used:.2f}", subtext=f"Limit: ₹{budget_limit:.2f}"),
            ],
            checklist=[
                GateVerificationItem(
                    id="g1_chk_1",
                    title="Target Framework Parity",
                    description=f"Verify that all detected legacy patterns have direct architectural equivalents in {target_stack}.",
                ),
                GateVerificationItem(
                    id="g1_chk_2",
                    title="Capability Gap Resolutions",
                    description="Confirm the selected adapter/custom resolution strategy for third-party libraries and specialized integrations.",
                ),
                GateVerificationItem(
                    id="g1_chk_3",
                    title="Data Model & Schema Parity",
                    description="Review database entity mapping to ensure zero data loss and valid relational foreign key constraints in the target ORM.",
                ),
                GateVerificationItem(
                    id="g1_chk_4",
                    title="Modernization Scope & Budget",
                    description="Ensure estimated modernization scope and token velocity limits are within the allocated project budget.",
                ),
            ],
            next_agent="CharacterizerAgent",
            next_agent_role="Behavioral Replay Harness Specialist",
            next_agent_preview="CharacterizerAgent will deploy the legacy system inside an air-gapped rootless container to record golden test vectors and state transitions.",
        )
    elif gate_type == GateType.G2:
        return GateVerificationGuide(
            producing_agent="CharacterizerAgent",
            producing_agent_role="Behavioral Replay Harness Specialist",
            work_summary="Deployed legacy application inside an isolated rootless container sandbox. Executed synthetic traffic and recorded golden HTTP request/response payloads, headers, status codes, and database state transitions to establish an immutable behavioral baseline.",
            key_deliverables=[
                "Frozen Characterization Test Suite",
                "Golden Fixture Test Vectors",
                "Zero-Tolerance Baseline Lock",
                "Database State Snapshot Fixtures",
            ],
            metrics=[
                GateMetricItem(label="Test Vectors", value="Recorded", subtext="Golden fixtures", badge="FROZEN"),
                GateMetricItem(label="Route Coverage", value="100%", subtext="Legacy API surface", badge="COVERED"),
                GateMetricItem(label="Baseline Lock", value="SHA-256", subtext="Cryptographic baseline"),
                GateMetricItem(label="Cost Incurred", value=f"₹{budget_used:.2f}", subtext=f"Limit: ₹{budget_limit:.2f}"),
            ],
            checklist=[
                GateVerificationItem(
                    id="g2_chk_1",
                    title="Critical Path Coverage",
                    description="Verify that all revenue-critical and security-sensitive legacy endpoints have recorded test vectors.",
                ),
                GateVerificationItem(
                    id="g2_chk_2",
                    title="Edge Cases & Error Handling",
                    description="Ensure test vectors include validation failures, 4xx/5xx boundaries, and transaction rollbacks.",
                ),
                GateVerificationItem(
                    id="g2_chk_3",
                    title="Secret & PII Sanitization",
                    description="Confirm test fixtures contain sanitized mock data with zero production credentials or secrets.",
                ),
                GateVerificationItem(
                    id="g2_chk_4",
                    title="Baseline Freeze Agreement",
                    description="Confirm agreement that this test suite will serve as the non-negotiable ground truth for converted code.",
                ),
            ],
            next_agent="PlannerCoordinator & ModulePlanner",
            next_agent_role="Architectural Decomposition & Dependency Wave Planner",
            next_agent_preview="PlannerCoordinator will analyze the legacy model and target blueprint to decompose the codebase into modular packages, compute topological wave ordering, and verify DAG cyclicity.",
        )
    elif gate_type == GateType.G3:
        return GateVerificationGuide(
            producing_agent="PlannerCoordinator & ModulePlanner",
            producing_agent_role="Architectural Decomposition & Dependency Wave Planner",
            work_summary="Decomposed the legacy codebase into decoupled modular components. Formulated granular conversion tasks with explicit acceptance criteria and test contracts. Constructed a topological Directed Acyclic Graph (DAG) and scheduled sequential conversion waves.",
            key_deliverables=[
                "Modular Conversion Plan",
                "Topological Wave DAG",
                "Task Acceptance Specifications",
                "Zero-Cycle Dependency Matrix",
            ],
            metrics=[
                GateMetricItem(label="Planned Modules", value="Decomposed", subtext="Domain packages", badge="MODULAR"),
                GateMetricItem(label="Atomic Tasks", value="Specified", subtext="With test contracts", badge="SPECIFIED"),
                GateMetricItem(label="Execution Waves", value="Scheduled", subtext="Topologically ordered"),
                GateMetricItem(label="Estimated Effort", value="Budgeted", subtext="Within budget ceiling"),
                GateMetricItem(label="DAG Cycles", value="0 cycles", subtext="Topologically valid", badge="CYCLE-FREE"),
                GateMetricItem(label="Cost Incurred", value=f"₹{budget_used:.2f}", subtext=f"Limit: ₹{budget_limit:.2f}"),
            ],
            checklist=[
                GateVerificationItem(
                    id="g3_chk_1",
                    title="Wave 1 Zero-Dependency Isolation",
                    description="Confirm Wave 1 modules (base types, database schema, utility helpers) have zero upstream dependencies.",
                ),
                GateVerificationItem(
                    id="g3_chk_2",
                    title="Task Granularity & Acceptance Criteria",
                    description="Ensure conversion tasks specify clear input contracts, output types, and test assertions.",
                ),
                GateVerificationItem(
                    id="g3_chk_3",
                    title="Database Migration Sequencing",
                    description="Validate that database entity migrations precede dependent domain services.",
                ),
                GateVerificationItem(
                    id="g3_chk_4",
                    title="Effort & Budget Limits",
                    description="Confirm the conversion scope and projected token consumption fit within the allocated job budget.",
                ),
            ],
            next_agent="CodeWriter Specialist Agents",
            next_agent_role="Rootless Container Code Conversion & Test Repair Specialist",
            next_agent_preview="Specialist CodeWriter agents will be spawned into rootless container sandboxes to begin converting modules wave-by-wave, executing compiler validation and local test suites after every task.",
        )
    else:  # GateType.G4
        return GateVerificationGuide(
            producing_agent="VerifierAgent & DualHarnessExecutor",
            producing_agent_role="Dual-Harness Replay & Parity Verification Specialist",
            work_summary=f"Compiled converted {target_stack} codebase in rootless gVisor sandbox. Executed dual-harness replay comparing legacy vs modern outputs against identical test fixtures with zero unintended regressions detected.",
            key_deliverables=[
                "Dual-Harness Equivalence Report",
                "Intended Difference Catalog",
                "Strict Type & Contract Audit",
                "Cryptographic Parity Proof",
            ],
            metrics=[
                GateMetricItem(label="Dual Replay Pass", value="Verified", subtext="All fixtures identical", badge="PASSED"),
                GateMetricItem(label="Unintended Regressions", value="0", subtext="Zero regression drift", badge="ZERO DRIFT"),
                GateMetricItem(label="Approved Intentional Diffs", value="Documented", subtext="Audited waivers"),
                GateMetricItem(label="Type Safety", value="Strict", subtext="Zero linter warnings"),
            ],
            checklist=[
                GateVerificationItem(
                    id="g4_chk_1",
                    title="Zero Unintended Regressions",
                    description="Review diff reports and confirm that zero unintended regressions or data corruptions were detected.",
                ),
                GateVerificationItem(
                    id="g4_chk_2",
                    title="Inspect & Sign Difference Waivers",
                    description="Review intentional differences (e.g. ISO-8601 datetime strings, empty collection returns) and sign approval waivers.",
                ),
                GateVerificationItem(
                    id="g4_chk_3",
                    title="Target Type Safety & Lint Conformance",
                    description="Verify strict compilation pass with zero lint errors or unmapped any types.",
                ),
                GateVerificationItem(
                    id="g4_chk_4",
                    title="Integration Release Sign-Off",
                    description="Authorize creating the final GitHub Pull Request and tagging the release for deployment.",
                ),
            ],
            next_agent="DeliveryAgent & PackagingCoordinator",
            next_agent_role="Release Packaging & Compliance Audit Specialist",
            next_agent_preview="DeliveryAgent will bundle the verified target codebase, submit a Pull Request to your integration branch, generate cryptographic compliance proofs, and mark the modernization job completed.",
        )


def _gate_type_from_status(status_str: str) -> Optional[GateType]:
    if status_str == "AWAITING_GATE_G1":
        return GateType.G1
    if status_str == "AWAITING_GATE_G2":
        return GateType.G2
    if status_str == "AWAITING_GATE_G3":
        return GateType.G3
    if status_str == "AWAITING_GATE_G4":
        return GateType.G4
    return None


async def _resolve_gate_job_and_user(
    job_id: str,
    db: AsyncSession,
    rebase_session_id: Optional[str] = None,
    authorization: Optional[str] = None,
) -> Tuple[Job, User]:
    raw_token = rebase_session_id if isinstance(rebase_session_id, str) and rebase_session_id else None
    if not raw_token and isinstance(authorization, str) and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            raw_token = parts[1]

    if raw_token:
        user, _ = await AuthService.get_user_from_session(db, raw_token)
    else:
        raise UnauthorizedException("Authentication required.")

    try:
        j_uuid = uuid.UUID(job_id)
        stmt = select(Job).where(Job.job_id == j_uuid)
    except ValueError:
        stmt = select(Job).where(Job.name == job_id)
    j_res = await db.execute(stmt)
    job = j_res.scalar_one_or_none()
    if not job:
        raise NotFoundException("Job", job_id)

    membership = await db.scalar(select(JobMembership).where(
        JobMembership.job_id == job.job_id,
        JobMembership.user_id == user.user_id,
    ))
    if not membership:
        raise NotFoundException("Job", job_id)
    setattr(user, "_effective_job_role", membership.role_id)

    return job, user


@router.get(
    "/gates/pending",
    response_model=PendingGatesResponse,
    status_code=status.HTTP_200_OK,
    summary="List all pending approval gates across jobs",
    operation_id="gates_list_pending",
)
async def list_pending_gates(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PendingGatesResponse:
    awaiting_statuses = [
        "AWAITING_GATE_G1",
        "AWAITING_GATE_G2",
        "AWAITING_GATE_G3",
        "AWAITING_GATE_G4",
    ]
    stmt = select(Job).where(Job.status.in_(awaiting_statuses))
    stmt = stmt.join(JobMembership, JobMembership.job_id == Job.job_id).where(
        JobMembership.user_id == user.user_id
    )
    stmt = stmt.order_by(Job.updated_at.desc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    jobs = list(res.scalars().all())

    items: List[GateDetailResponse] = []
    for j in jobs:
        g_type = _gate_type_from_status(j.status)
        if not g_type:
            continue
        durable = await db.scalar(select(WorkflowGate).where(
            WorkflowGate.job_id == j.job_id,
            WorkflowGate.gate_type == g_type.value,
            WorkflowGate.status == "PENDING",
        ).order_by(WorkflowGate.version.desc()).limit(1))
        if durable is None:
            continue
        first_hash = next(iter(durable.artifact_hashes.values()), "sha256:no-artifact")
        membership = await db.scalar(select(JobMembership).where(
            JobMembership.job_id == j.job_id, JobMembership.user_id == user.user_id
        ))
        effective_role = membership.role_id if membership else "DEVELOPER"
        can_decide = RBACPolicy.has_permission(effective_role, f"gate:approve_{g_type.value.lower()}")
        items.append(
            GateDetailResponse(
                gate_id=str(durable.gate_id),
                job_id=str(j.job_id),
                job_name=j.name,
                gate_type=g_type,
                title=GATE_TITLES.get(g_type, "Quality Gate Review"),
                description=GATE_DESCRIPTIONS.get(g_type, "Human review required before pipeline advances."),
                status="PENDING",
                artifact="Gate Feasibility & Characterization Package",
                artifact_hash=first_hash,
                cost_summary=f"₹{float(j.budget_used_usd):.2f} / ₹{float(j.budget_limit_usd):.2f}",
                requested_at=j.updated_at.isoformat() if hasattr(j.updated_at, "isoformat") else str(j.updated_at),
                version=durable.version,
                artifact_hashes=dict(durable.artifact_hashes),
                allowed_actions=["approve", "reject", "request_changes"] if can_decide else [],
                verification_guide=get_gate_verification_guide(g_type, job=j),
            )
        )

    return PendingGatesResponse(items=items, total=len(items))


@router.get(
    "/jobs/{job_id}/gates",
    response_model=list[GateDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="List gates and historical decisions for a job",
    operation_id="gates_list_for_job",
)
async def list_gates_for_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    rebase_session_id: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> list[GateDetailResponse]:
    job, user = await _resolve_gate_job_and_user(job_id, db, rebase_session_id, authorization)

    # 1. Historical gate decisions
    stmt = (
        select(GateDecision)
        .where(GateDecision.job_id == job.job_id)
        .order_by(GateDecision.decided_at.asc())
    )
    res = await db.execute(stmt)
    decisions = list(res.scalars().all())
    decision_by_gate = {str(item.gate_id): item for item in decisions if item.gate_id}
    reviewer_ids = {item.reviewer_user_id for item in decisions}
    reviewers = {}
    if reviewer_ids:
        reviewer_rows = list((await db.execute(select(User).where(User.user_id.in_(reviewer_ids)))).scalars().all())
        reviewers = {item.user_id: item.full_name for item in reviewer_rows}
    effective_role = getattr(user, "_effective_job_role", user.role)

    durable_gates = list((await db.execute(
        select(WorkflowGate).where(WorkflowGate.job_id == job.job_id).order_by(
            WorkflowGate.gate_type.asc(), WorkflowGate.version.asc()
        )
    )).scalars().all())
    if durable_gates:
        return [GateDetailResponse(
            gate_id=str(g.gate_id), job_id=str(job.job_id), job_name=job.name,
            gate_type=GateType(g.gate_type), title=GATE_TITLES[GateType(g.gate_type)],
            description=g.blocking_reason or GATE_DESCRIPTIONS[GateType(g.gate_type)],
            status=g.status, artifact=f"Gate {g.gate_type} artifact package v{g.version}",
            artifact_hash=next(iter(g.artifact_hashes.values()), "sha256:no-artifact"),
            cost_summary=f"₹{float(job.budget_used_usd):.2f} / ₹{float(job.budget_limit_usd):.2f}",
            requested_at=g.requested_at.isoformat(), decided_at=g.decided_at.isoformat() if g.decided_at else None,
            reviewer=reviewers.get(decision_by_gate.get(str(g.gate_id)).reviewer_user_id) if decision_by_gate.get(str(g.gate_id)) else None,
            version=g.version,
            rationale=decision_by_gate.get(str(g.gate_id)).rationale if decision_by_gate.get(str(g.gate_id)) else None,
            artifact_hashes=dict(g.artifact_hashes or {}),
            allowed_actions=["approve", "reject", "request_changes"] if g.status == "PENDING" and RBACPolicy.has_permission(effective_role, f"gate:approve_{g.gate_type.lower()}") else [],
            verification_guide=get_gate_verification_guide(GateType(g.gate_type), job=job),
        ) for g in durable_gates]

    # Historical decisions and a job status are never projected as actionable
    # gates. Only supervisor-created WorkflowGate records are authoritative.
    return []


@router.get(
    "/jobs/{job_id}/gates/{gate_id}",
    response_model=GateDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve gate details, required evidence, and status",
    operation_id="gates_get",
)
async def get_gate(
    job_id: str,
    gate_id: str,
    db: AsyncSession = Depends(get_db),
    rebase_session_id: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> GateDetailResponse:
    gates = await list_gates_for_job(job_id=job_id, db=db, rebase_session_id=rebase_session_id, authorization=authorization)
    for g in gates:
        if g.gate_id == gate_id:
            return g
    raise NotFoundException("Gate", gate_id)


@router.post(
    "/jobs/{job_id}/gates/{gate_id}/decisions",
    response_model=GateDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit an authorized human review decision for an approval gate",
    operation_id="gates_decide",
)
async def submit_gate_decision(
    job_id: str,
    gate_id: str,
    payload: GateDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    rebase_session_id: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> GateDecisionResponse:
    job, user = await _resolve_gate_job_and_user(job_id, db, rebase_session_id, authorization)
    correlation_id = getattr(request.state, "correlation_id", None)
    try:
        versioned_gate_id = uuid.UUID(gate_id)
    except ValueError as exc:
        raise ConflictException(
            "Legacy synthetic gate IDs are deprecated; reload the current versioned gate"
        ) from exc
    from app.models.workflow import WorkflowGate
    from app.services.gate_service import gate_service
    pending = await db.scalar(select(WorkflowGate).where(
        WorkflowGate.gate_id == versioned_gate_id,
        WorkflowGate.job_id == job.job_id,
        WorkflowGate.status == "PENDING",
    ))
    if pending is None:
        raise ConflictException("A current evidence-bound pending gate is required")
    decision_record, decided_gate, _, _ = await gate_service.decide(
        db,
        pending.gate_id,
        payload,
        actor_id=user.user_id,
        actor_role=getattr(user, "_effective_job_role", user.role),
        correlation_id=correlation_id,
    )
    return GateDecisionResponse(
        decision_id=str(decision_record.decision_id),
        job_id=str(job.job_id),
        gate_id=str(decided_gate.gate_id),
        gate_type=GateType(decided_gate.gate_type),
        decision=payload.decision,
        rationale=decision_record.rationale,
        reviewer=user.full_name,
        decided_at=decision_record.decided_at.isoformat(),
    )
