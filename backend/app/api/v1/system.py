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
    profiles = []
    profile_status = "unavailable"
    controller_available = False
    controller_worker = False
    images_match = False
    try:
        from app.services.verification_profiles import available_profiles
        from app.services.sandbox_client import health
        profiles = available_profiles()
        profile_status = "configured" if profiles else "profile_missing"
        controller = await health()
        controller_available = True
        approved_images = set(controller.get("images", []))
        controller_worker = controller.get("worker_alive") is True
        images_match = bool(profiles) and all(
            profile["image"] in approved_images for profile in profiles
        )
    except Exception:
        # Missing controller/profile/runtime is an unavailable component, never ready.
        if not controller_available:
            profile_status = "unavailable"
    sandbox_healthy = bool(profiles) and controller_worker and images_match
    if controller_available and not profiles:
        profile_status = "profile_missing"
    elif controller_available and profiles and not images_match:
        profile_status = "image_unapproved"
    elif controller_available and sandbox_healthy:
        profile_status = "ready"
    if not db_healthy or not sandbox_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        ready=db_healthy and sandbox_healthy,
        components={
            "database": "healthy" if db_healthy else "unhealthy",
            "storage": "healthy",
            "agent_workers": "healthy" if controller_worker else "unavailable",
            "sandboxes": "ready" if sandbox_healthy else profile_status,
        },
    )
