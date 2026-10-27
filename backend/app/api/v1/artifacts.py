"""Artifact deliverables router with cryptographic integrity validation and lineage tracking."""

import json
import logging
from fastapi.responses import Response
from typing import Any, Dict, Optional, Tuple
import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_job_access
from app.core.errors import NotFoundException, ForbiddenException
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.user import User
from app.schemas.artifacts import (
    ArtifactContentResponse,
    ArtifactListResponse,
    ArtifactResponse,
)
from app.services.artifact_service import ArtifactService

router = APIRouter(prefix="/jobs/{job_id}/artifacts", tags=["Artifacts"])
artifact_service = ArtifactService()
logger = logging.getLogger(__name__)


class CreateArtifactPayload(BaseModel):
    artifact_type: str = Field(..., description="Deliverable type name.")
    version: int = Field(1, ge=1, description="Version integer.")
    content: dict[str, Any] = Field(..., description="JSON content payload.")
    producing_agent: str = Field("ModernizationAgent", description="Authoring agent name.")
    derived_from: list[str] = Field(default_factory=list, description="Predecessor hashes.")


@router.get("/{artifact_id}/download", operation_id="artifacts_download")
async def download_artifact(artifact_id: uuid.UUID, access=Depends(require_job_access("artifact:download")), db=Depends(get_db)):
    try:
        artifact, raw = await artifact_service.get_artifact_content(db, access[0].job_id, artifact_id)
        return Response(content=raw, media_type=artifact.media_type, headers={"Content-Disposition": f'attachment; filename="{artifact.artifact_id}.json"', "X-Content-SHA256": artifact.content_hash, "X-Content-Type-Options": "nosniff"})
    except Exception:
        logger.exception("artifacts.download_artifact failed")
        raise


def _artifact_to_response(art: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        artifact_id=str(art.artifact_id),
        job_id=str(art.job_id),
        artifact_type=art.artifact_type,
        version=art.version,
        content_hash=art.content_hash,
        storage_path=art.storage_path,
        producing_agent=art.producing_agent,
        derived_from=art.derived_from or [],
        size_bytes=art.content_size_bytes,
        created_at=art.created_at.isoformat() if hasattr(art.created_at, "isoformat") else str(art.created_at),
    )


@router.get(
    "",
    response_model=ArtifactListResponse,
    status_code=status.HTTP_200_OK,
    summary="List versioned deliverables for a job",
    operation_id="artifacts_list",
)
async def list_artifacts(
    job_id: str,
    artifact_type: Optional[str] = Query(None),
    access: Tuple[Job, User] = Depends(require_job_access(permission="artifact:read")),
    db: AsyncSession = Depends(get_db),
) -> ArtifactListResponse:
    job, user = access
    db_items = await artifact_service.list_artifacts(db, job.job_id, artifact_type=artifact_type)
    items = [_artifact_to_response(a) for a in db_items]
    return ArtifactListResponse(items=items, total=len(items))


@router.post(
    "",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish an immutable artifact version with SHA-256 validation",
    operation_id="artifacts_create",
)
async def create_artifact(
    job_id: str,
    payload: CreateArtifactPayload,
    request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="artifact:publish_diagnostic")),
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    job, user = access
    correlation_id = getattr(request.state, "correlation_id", None)
    normalized_type = "".join(ch for ch in payload.artifact_type.upper() if ch.isalnum())
    workflow_owned = {
        "REPOSITORYSNAPSHOT", "REPOSITORYINVENTORY", "LEGACYMODEL",
        "TARGETBLUEPRINT", "FEASIBILITYREPORT", "CHARACTERIZATIONSUITE",
        "SCHEMAMIGRATIONPLAN", "CONVERSIONPLAN", "CHANGESET",
        "VERIFICATIONREPORT", "SYSTEMVERIFICATION", "SYSTEMVERIFICATIONREPORT",
        "INTEGRATEDWORKSPACE", "INTEGRATIONREPORT", "JOBREPORT", "SBOM",
        "DELIVERYRECORD", "PULLREQUESTRECORD",
    }
    if normalized_type in workflow_owned:
        raise ForbiddenException("Workflow-owned evidence can only be published by a supervisor-dispatched agent")
    if not normalized_type.startswith(("DIAGNOSTIC", "USERNOTE", "ATTACHMENT")):
        raise ForbiddenException("API callers may publish only diagnostic, user-note, or attachment artifacts")
    content_bytes = json.dumps(payload.content, sort_keys=True).encode("utf-8")

    art = await artifact_service.create_artifact(
        db=db,
        job_id=job.job_id,
        artifact_type=payload.artifact_type,
        version=payload.version,
        content_bytes=content_bytes,
        producing_agent=f"API_USER:{user.user_id}",
        derived_from=payload.derived_from,
        user=user,
        correlation_id=correlation_id,
    )
    return _artifact_to_response(art)


@router.get(
    "/{artifact_id}",
    response_model=ArtifactResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve artifact metadata and lineage",
    operation_id="artifacts_get",
)
async def get_artifact(
    job_id: str,
    artifact_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="artifact:read")),
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    job, user = access
    try:
        art_uuid = uuid.UUID(artifact_id)
    except ValueError:
        raise NotFoundException("Artifact", artifact_id)
    db_art = await artifact_service.get_artifact(db, job.job_id, art_uuid)
    return _artifact_to_response(db_art)


@router.get(
    "/{artifact_id}/content",
    response_model=ArtifactContentResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve parsed artifact content JSON with SHA-256 verification",
    operation_id="artifacts_get_content",
)
async def get_artifact_content(
    job_id: str,
    artifact_id: str,
    access: Tuple[Job, User] = Depends(require_job_access(permission="artifact:download")),
    db: AsyncSession = Depends(get_db),
) -> ArtifactContentResponse:
    job, user = access
    try:
        art_uuid = uuid.UUID(artifact_id)
    except ValueError:
        raise NotFoundException("Artifact", artifact_id)
    artifact, content_bytes = await artifact_service.get_artifact_content(db, job.job_id, art_uuid)
    try:
        parsed_json = json.loads(content_bytes.decode("utf-8"))
    except Exception:
        parsed_json = {"raw": content_bytes.decode("utf-8", errors="replace")}
    return ArtifactContentResponse(
        artifact_id=str(artifact.artifact_id),
        artifact_type=artifact.artifact_type,
        version=artifact.version,
        content_hash=artifact.content_hash,
        content=parsed_json,
    )
