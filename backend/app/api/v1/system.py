"""Health and Kubernetes readiness probe endpoints."""

from fastapi import APIRouter, Response, status
from app.core.config import settings
from app.core.database import ping_database
from app.schemas.system import HealthResponse, ReadinessResponse

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check probe",
    operation_id="system_health",
)
async def get_health() -> HealthResponse:
    db_healthy = await ping_database()
    return HealthResponse(
        status="ok" if db_healthy else "degraded",
        version=settings.VERSION,
        database="connected" if db_healthy else "disconnected",
    )


@router.get(
    "/readiness",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness probe for traffic routing",
    operation_id="system_readiness",
)
@router.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_readiness(response: Response) -> ReadinessResponse:
    db_healthy = await ping_database()
    if not db_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        ready=db_healthy,
        components={
            "database": "healthy" if db_healthy else "unhealthy",
            "storage": "healthy",
            "agent_workers": "healthy",
            "sandboxes": "ready",
        },
    )
