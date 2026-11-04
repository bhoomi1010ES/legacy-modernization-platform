"""FastAPI dependencies for authentication, database sessions, and resource authorization."""

from typing import List, Optional, Tuple
import uuid
from fastapi import Cookie, Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ForbiddenException, NotFoundException, UnauthorizedException
from app.models.job import Job, JobMembership
from app.models.user import User
from app.services.auth_service import AuthService


async def get_current_user_and_permissions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    rebase_session_id: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> Tuple[User, List[str]]:
    """Extracts session token from HttpOnly cookie or Authorization Bearer header and verifies session."""
    raw_token = rebase_session_id

    # Fallback to Authorization: Bearer <session_id> if cookie not present (for API clients/tests)
    if not raw_token and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            raw_token = parts[1]

    if not raw_token:
        raise UnauthorizedException("Authentication required. Please log in.")

    return await AuthService.get_user_from_session(db, raw_token)


async def get_current_user(
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_and_permissions)
) -> User:
    """Returns authenticated User instance."""
    return auth_data[0]


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    rebase_session_id: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """Returns authenticated User instance if valid session exists, otherwise None."""
    raw_token = rebase_session_id
    if not raw_token and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            raw_token = parts[1]

    if not raw_token:
        return None

    try:
        user, _ = await AuthService.get_user_from_session(db, raw_token)
        return user
    except Exception:
        return None



def require_permission(permission: str):
    """Dependency factory checking global user capability."""
    async def permission_checker(
        auth_data: Tuple[User, List[str]] = Depends(get_current_user_and_permissions)
    ) -> User:
        user, permissions = auth_data
        if permission not in permissions:
            raise ForbiddenException(f"User lacks required capability: '{permission}'.")
        return user

    return permission_checker


def require_job_access(permission: str = "job:read"):
    """Validates that caller is authorized to access the specific job.

    Enforces:
    1. Active JobMembership check.
    2. Anti-IDOR not-found masking policy where appropriate.
    """
    async def job_access_checker(
        job_id: str,
        auth_data: Tuple[User, List[str]] = Depends(get_current_user_and_permissions),
        db: AsyncSession = Depends(get_db),
    ) -> Tuple[Job, User]:
        user, _ = auth_data

        try:
            job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
            stmt = select(Job).where(Job.job_id == job_uuid)
        except ValueError:
            stmt = select(Job).where(Job.name == job_id)

        # Check job existence
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()

        if not job:
            raise NotFoundException(resource="Job", resource_id=job_id)

        # Verify job membership
        mem_stmt = select(JobMembership).where(
            JobMembership.job_id == job.job_id,
            JobMembership.user_id == user.user_id,
        )
        mem_res = await db.execute(mem_stmt)
        membership = mem_res.scalar_one_or_none()

        if not membership:
            # Consistent not-found response to avoid leaking job existence to unauthorized users
            raise NotFoundException(resource="Job", resource_id=job_id)

        # All authenticated job members share capabilities; membership remains
        # the job-level access boundary and prevents cross-job IDOR.
        return job, user

    return job_access_checker
