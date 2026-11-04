"""FastAPI router for Phase 5A Characterization and Gate G2."""

from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Path as FastPath, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.characterization.api.events import sse_event_stream
from app.characterization.api.schemas import (
    CharacterizationExecutionResponse,
    CharacterizationRunRequest,
    GateG2DecisionPayload,
    GateG2StatusResponse,
)
from app.characterization.contracts.approval import GateG2Request
from app.characterization.contracts.enums import CharacterizationStage, ExecutionStatus
from app.characterization.contracts.suite import CharacterizationRequest, CharacterizationSuite
from app.characterization.persistence.repository import CharacterizationRepository
from app.characterization.service import characterization_service
from app.models.user import User

router = APIRouter(tags=["Characterization & Gate G2"])


@router.post(
    "/{job_id}/characterization/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CharacterizationExecutionResponse,
)
async def start_characterization_run(
    job_id: str = FastPath(..., description="Job or project ID"),
    payload: Optional[CharacterizationRunRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start asynchronous 9-stage characterization pipeline in background."""
    req_payload = payload or CharacterizationRunRequest()
    char_req = CharacterizationRequest(
        job_id=job_id,
        max_scenarios=req_payload.max_scenarios,
        enable_iterative_refinement=req_payload.enable_iterative_refinement,
        coverage_threshold=req_payload.coverage_threshold,
    )

    execution_id = await characterization_service.start_characterization(
        db=db, job_id=job_id, request=char_req
    )

    return CharacterizationExecutionResponse(
        execution_id=execution_id,
        job_id=job_id,
        status=ExecutionStatus.PENDING,
        stage=CharacterizationStage.INITIALIZING,
        stage_progress_pct=0,
        summary=f"Dispatched characterization pipeline for job {job_id}.",
    )


@router.get(
    "/{job_id}/characterization/executions/{execution_id}",
    response_model=CharacterizationExecutionResponse,
)
async def get_characterization_execution(
    job_id: str = FastPath(...),
    execution_id: str = FastPath(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Poll execution lifecycle status and stage progression."""
    exec_model = await characterization_service.get_execution(db, execution_id)
    if not exec_model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution '{execution_id}' not found.",
        )

    return CharacterizationExecutionResponse(
        execution_id=exec_model.execution_id,
        job_id=str(exec_model.job_id),
        status=ExecutionStatus(exec_model.status),
        stage=CharacterizationStage(exec_model.stage) if exec_model.stage in CharacterizationStage.__members__ else CharacterizationStage.INITIALIZING,
        stage_progress_pct=exec_model.stage_progress_pct,
        summary=exec_model.summary,
        started_at=exec_model.started_at.isoformat() if exec_model.started_at else None,
    )


@router.get(
    "/{job_id}/characterization/events/{execution_id}",
    response_class=StreamingResponse,
)
async def stream_characterization_events(
    job_id: str = FastPath(...),
    execution_id: str = FastPath(...),
    current_user: User = Depends(get_current_user),
):
    """Stream real-time stage progress events via Server-Sent Events (SSE)."""
    generator = characterization_service.subscribe_events(execution_id)
    return StreamingResponse(
        sse_event_stream(generator),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{job_id}/characterization/suite",
    response_model=CharacterizationSuite,
)
async def get_latest_suite(
    job_id: str = FastPath(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the latest complete synthesized CharacterizationSuite artifact."""
    suite = await characterization_service.get_latest_suite(db, job_id)
    if not suite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No characterization suite found for job '{job_id}'.",
        )
    return suite


@router.get(
    "/{job_id}/characterization/suite/version/{version}",
    response_model=CharacterizationSuite,
)
async def get_suite_version(
    job_id: str = FastPath(...),
    version: int = FastPath(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a specific historical version of the characterization suite."""
    suite = await characterization_service.get_suite_by_version(db, job_id, version)
    if not suite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suite version {version} not found for job '{job_id}'.",
        )
    return suite


@router.get(
    "/{job_id}/characterization/gate-g2/status",
    response_model=GateG2StatusResponse,
)
async def get_gate_g2_status(
    job_id: str = FastPath(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check Gate G2 readiness, coverage metrics, contradictions, and latest decision."""
    suite = await characterization_service.get_latest_suite(db, job_id)
    if not suite:
        return GateG2StatusResponse(
            job_id=job_id,
            ready=False,
            blocking_reasons=["No characterization suite has been executed yet."],
            warnings=[],
            metrics={},
            latest_decision=None,
        )

    readiness = characterization_service.g2_manager.evaluate_gate_readiness(suite)
    repo = CharacterizationRepository(db)
    latest_appr = await repo.get_latest_g2_approval(uuid.UUID(job_id))

    return GateG2StatusResponse(
        job_id=job_id,
        ready=readiness["ready"],
        blocking_reasons=readiness["blocking_reasons"],
        warnings=readiness["warnings"],
        metrics=readiness["metrics"],
        latest_decision={
            "approval_id": latest_appr.approval_id,
            "decision": latest_appr.decision,
            "decided_by": latest_appr.decided_by,
            "decided_at": latest_appr.decided_at.isoformat(),
        } if latest_appr else None,
    )


@router.post(
    "/{job_id}/characterization/gate-g2/decision",
)
async def submit_gate_g2_decision(
    job_id: str = FastPath(...),
    payload: GateG2DecisionPayload = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit human review decision (APPROVE, REJECT, etc.) and freeze golden baseline."""
    req = GateG2Request(
        decision=payload.decision,
        rationale=payload.rationale,
        conditions=payload.conditions,
    )
    decided_by = current_user.email or current_user.full_name or str(current_user.user_id)

    try:
        decision_record, updated_suite = await characterization_service.submit_gate_g2_decision(
            db=db,
            job_id=job_id,
            request=req,
            decided_by=decided_by,
        )
        return {
            "status": "DECISION_RECORDED",
            "decision_record": decision_record.model_dump(),
            "is_frozen": updated_suite.is_frozen,
            "frozen_at": updated_suite.frozen_at,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

