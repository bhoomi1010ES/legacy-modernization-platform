"""FastAPI dependencies for authentication, database sessions, and resource authorization."""

from typing import List, Optional, Tuple
import uuid
from fastapi import Cookie, Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ForbiddenException, NotFoundException, UnauthorizedException
from app.domain.state_machine import RBACPolicy
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


def require_permission(permission: str = None):
    """Dependency ensuring caller is an authenticated user (RBAC removed)."""
    async def permission_checker(
        auth_data: Tuple[User, List[str]] = Depends(get_current_user_and_permissions)
    ) -> User:
        user, _ = auth_data
        return user

    return permission_checker


def require_job_access(permission: str = None):
    """Validates that caller is authenticated and the requested job exists.
    RBAC removed: all authenticated users accessing a valid job are authorized.
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

        # Retain job membership check for anti-IDOR isolation where configured
        mem_stmt = select(JobMembership).where(
            JobMembership.job_id == job.job_id,
            JobMembership.user_id == user.user_id,
        )
        mem_res = await db.execute(mem_stmt)
        membership = mem_res.scalar_one_or_none()

        # If job has explicit memberships and caller is neither member nor owner, mask with 404
        if not membership and job.owner_user_id != user.user_id:
            # Check if job has ANY memberships
            any_mem = (await db.execute(select(JobMembership.membership_id).where(JobMembership.job_id == job.job_id).limit(1))).scalar()
            if any_mem:
                raise NotFoundException(resource="Job", resource_id=job_id)

        return job, user

    return job_access_checker
