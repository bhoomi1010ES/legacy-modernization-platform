"""Production authentication endpoints with server-validated session lifecycle."""

from typing import List, Optional, Tuple
from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_and_permissions
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest, UserResponse
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
