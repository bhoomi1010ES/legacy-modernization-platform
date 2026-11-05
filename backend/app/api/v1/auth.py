"""Production authentication endpoints with server-validated session lifecycle."""

from typing import List, Optional, Tuple
import uuid
from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_permissions
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ForbiddenException, NotFoundException, ValidationException
from app.domain.state_machine import RBACPolicy
from app.models.audit import AuditEvent
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    RoleAssignmentRequest,
    UserResponse,
)
from app.schemas.system import SuccessResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new enterprise user account and initialize session",
    operation_id="auth_register",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    correlation_id = getattr(request.state, "correlation_id", None)

    user, session_id, permissions = await AuthService.register_user(
        db=db,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        role=payload.role or "DEVELOPER",
        ip_address=ip,
        user_agent=user_agent,
        correlation_id=correlation_id,
        allow_privileged=False,
    )

    # Set secure HttpOnly session cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        path="/",
    )

    return UserResponse(
        user_id=str(user.user_id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        permissions=permissions,
        created_at=user.created_at.isoformat(),
    )


@router.post(
    "/login",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and set secure session cookie",
    operation_id="auth_login",
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    correlation_id = getattr(request.state, "correlation_id", None)

    user, session_id, permissions = await AuthService.authenticate_user(
        db=db,
        email=payload.email,
        password=payload.password,
        ip_address=ip,
        user_agent=user_agent,
        correlation_id=correlation_id,
    )

    # Set secure HttpOnly session cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        path="/",
    )

    return UserResponse(
        user_id=str(user.user_id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        permissions=permissions,
        created_at=user.created_at.isoformat(),
    )


@router.post(
    "/logout",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Invalidate active session and clear cookie",
    operation_id="auth_logout",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    rebase_session_id: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> SuccessResponse:
    raw_token = rebase_session_id
    if not raw_token and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            raw_token = parts[1]

    correlation_id = getattr(request.state, "correlation_id", None)
    await AuthService.logout(db, raw_token, correlation_id=correlation_id)

    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )
    return SuccessResponse(message="Successfully signed out.")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user identity and capabilities",
    operation_id="auth_me",
)
async def get_me(
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_and_permissions),
) -> UserResponse:
    user, permissions = auth_data
    return UserResponse(
        user_id=str(user.user_id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        permissions=permissions,
        created_at=user.created_at.isoformat(),
    )


@router.post(
    "/users/{user_id}/role",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign or update a user workspace role (Admin only)",
    operation_id="auth_assign_user_role",
)
async def assign_user_role(
    user_id: str,
    payload: RoleAssignmentRequest,
    request: Request,
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_and_permissions),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    current_user, permissions = auth_data
    if current_user.role not in ("ADMIN", "SUPER_ADMIN") and not RBACPolicy.has_permission(current_user.role, "user:manage"):
        raise ForbiddenException("Only administrators can assign user roles.")

    valid_roles = {"SUPER_ADMIN", "ADMIN", "PROJECT_MANAGER", "REVIEWER", "APPROVER", "DEVELOPER", "VIEWER"}
    normalized_role = payload.role.strip().upper()
    if normalized_role not in valid_roles:
        raise ValidationException(f"Invalid role '{payload.role}' specified.")

    try:
        target_uuid = uuid.UUID(user_id)
    except ValueError:
        raise NotFoundException("User", user_id)

    target_user = await db.get(User, target_uuid)
    if not target_user:
        raise NotFoundException("User", user_id)

    old_role = target_user.role
    target_user.role = normalized_role

    correlation_id = getattr(request.state, "correlation_id", None)
    audit = AuditEvent(
        event_type="USER_ROLE_ASSIGNED",
        actor_type="USER",
        actor_id=str(current_user.user_id),
        correlation_id=correlation_id,
        payload={
            "target_user_id": str(target_user.user_id),
            "target_email": target_user.email,
            "old_role": old_role,
            "new_role": normalized_role,
            "reason": payload.reason,
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(target_user)

    target_permissions = RBACPolicy.permissions_for(target_user.role)
    return UserResponse(
        user_id=str(target_user.user_id),
        email=target_user.email,
        full_name=target_user.full_name,
        role=target_user.role,
        status=target_user.status,
        permissions=target_permissions,
        created_at=target_user.created_at.isoformat(),
    )
