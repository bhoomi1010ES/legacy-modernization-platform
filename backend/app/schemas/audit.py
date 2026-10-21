"""Audit trail event schemas."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class AuditEventResponse(BaseModel):
    event_id: str
    job_id: Optional[str] = None
    event_type: str
    actor_type: str = Field("USER", description="USER, SYSTEM, or AGENT")
    actor_id: str
    action: Optional[str] = None
    correlation_id: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    created_at: str


class AuditListResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int
    offset: int
    limit: int
