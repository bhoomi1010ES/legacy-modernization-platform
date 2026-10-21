"""API v1 router composition."""

from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.artifacts import router as artifacts_router
from app.api.v1.gates import router as gates_router
from app.api.v1.agents import router as agents_router
from app.api.v1.audit import router as audit_router
from app.api.v1.reports import router as reports_router
from app.api.v1.system import router as system_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(artifacts_router)
api_v1_router.include_router(gates_router)
api_v1_router.include_router(agents_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(system_router)

__all__ = ["api_v1_router"]
