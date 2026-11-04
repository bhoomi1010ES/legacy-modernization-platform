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
from app.api.v1.agent_runs import router as agent_runs_router
from app.api.v1.workflow import router as workflow_router
from app.api.v1.phase4 import router as phase4_router
from app.api.v1.phase5 import router as phase5_router
from app.api.v1.phase6 import router as phase6_router
from app.api.v1.phase7 import router as phase7_router
from app.characterization.api.router import router as characterization_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(artifacts_router)
api_v1_router.include_router(gates_router)
api_v1_router.include_router(agents_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(system_router)
api_v1_router.include_router(agent_runs_router)
api_v1_router.include_router(workflow_router)
api_v1_router.include_router(phase4_router)
api_v1_router.include_router(phase5_router)
api_v1_router.include_router(phase6_router)
api_v1_router.include_router(phase7_router)
api_v1_router.include_router(characterization_router)

__all__ = ["api_v1_router"]
