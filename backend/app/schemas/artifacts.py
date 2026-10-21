"""Artifact and deliverable schemas."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ArtifactResponse(BaseModel):
    artifact_id: str = Field(..., description="Unique artifact identifier.")
    job_id: str = Field(..., description="Associated modernization job.")
    artifact_type: str = Field(..., description="Artifact type (e.g. RepoInventory, FeasibilityReport, CharacterizationSuite).")
    version: int = Field(..., ge=1, description="Sequential version integer.")
    content_hash: str = Field(..., description="Cryptographic SHA-256 hash of the artifact content.")
    storage_path: str = Field(..., description="Internal storage object URI.")
    producing_agent: str = Field(..., description="Specialist agent that authored the deliverable.")
    derived_from: list[str] = Field(default_factory=list, description="Array of predecessor artifact hashes establishing lineage.")
    size_bytes: int = Field(..., description="Payload size in bytes.")
    created_at: str = Field(..., description="ISO 8601 creation timestamp.")


class ArtifactListResponse(BaseModel):
    items: list[ArtifactResponse]
    total: int


class ArtifactContentResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    version: int
    content_hash: str
    content: dict[str, Any]
