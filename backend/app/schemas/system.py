"""System status, readiness probe, and generic success schemas."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field("ok", description="Overall service status.")
    version: str = Field(..., description="API version.")
    database: str = Field("connected", description="Database connection health.")


class ReadinessResponse(BaseModel):
    ready: bool = Field(True, description="Readiness for incoming traffic.")
    components: dict[str, str] = Field(..., description="Subsystem health status map.")


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = "Operation completed successfully."
