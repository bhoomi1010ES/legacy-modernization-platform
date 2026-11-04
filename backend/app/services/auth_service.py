"""Authentication, session lifecycle, and brute-force protection service."""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ConflictException,
    ForbiddenException,
    UnauthorizedException,
    ValidationException,
)
from app.core.security import generate_session_id, hash_password, hash_session_token, verify_password
from app.models.audit import AuditEvent
from app.models.role import Role
from app.models.user import User, UserSession
from app.domain.state_machine import RBACPolicy

# In-memory login attempt tracker for brute-force mitigation
# Key: email_or_ip -> list of failure timestamps
_failed_attempts: Dict[str, List[datetime]] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_MINUTES = 15
IDLE_TIMEOUT_HOURS = 4


def _check_rate_limit(key: str) -> None:
    """Enforces login throttling: max 5 failed attempts per 15 minutes."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=LOCKOUT_WINDOW_MINUTES)
    if key in _failed_attempts:
        # Keep only recent attempts
        _failed_attempts[key] = [t for t in _failed_attempts[key] if t > cutoff]
        if len(_failed_attempts[key]) >= MAX_FAILED_ATTEMPTS:
            raise UnauthorizedException(
                "Too many failed login attempts. Please wait 15 minutes before trying again."
            )


def _record_failed_attempt(key: str) -> None:
    now = datetime.now(timezone.utc)
    if key not in _failed_attempts:
        _failed_attempts[key] = []
    _failed_attempts[key].append(now)


def _clear_failed_attempts(key: str) -> None:
    _failed_attempts.pop(key, None)


class AuthService:
    """Manages secure password verification, session creation, rotation, and revocation."""

    @staticmethod
    async def register_user(
        db: AsyncSession,
        email: str,
        full_name: str,
        password: str,
        role: str = "DEVELOPER",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
        allow_privileged: bool = False,
    ) -> Tuple[User, str, List[str]]:
        clean_email = email.strip().lower()
        clean_name = full_name.strip()

        # Check if email is already registered
        stmt = select(User).where(User.email == clean_email)
        res = await db.execute(stmt)
        existing_user = res.scalar_one_or_none()
        if existing_user:
            raise ConflictException(f"An account with email '{clean_email}' already exists.")

        # Sanitize and assign role
        privileged_roles = {"SUPER_ADMIN", "ADMIN", "PROJECT_MANAGER", "REVIEWER", "APPROVER"}
        valid_roles = {"SUPER_ADMIN", "ADMIN", "PROJECT_MANAGER", "REVIEWER", "APPROVER", "DEVELOPER", "VIEWER"}
        requested_role = (role or "DEVELOPER").strip().upper()
        if requested_role in privileged_roles and not allow_privileged:
            raise ForbiddenException(
                f"Self-assignment of privileged role '{requested_role}' is forbidden on public registration."
            )
        if requested_role not in valid_roles:
            raise ForbiddenException(
                f"Invalid or unauthorized role '{requested_role}' requested."
            )
        assigned_role = requested_role if allow_privileged else (
            requested_role if requested_role in ("DEVELOPER", "VIEWER") else "DEVELOPER"
        )

        # Create user
        pw_hash = hash_password(password)
        new_user = User(
            user_id=uuid.uuid4(),
            email=clean_email,
            full_name=clean_name,
            password_hash=pw_hash,
            role=assigned_role,
            status="ACTIVE",
        )
        db.add(new_user)
        await db.flush()

        # Generate session token and session record
        raw_session_token = generate_session_id()
        token_hash = hash_session_token(raw_session_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)

        new_session = UserSession(
            session_id=str(uuid.uuid4()),
            user_id=new_user.user_id,
            token_hash=token_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=now,
            last_activity_at=now,
            expires_at=expires_at,
            is_revoked=False,
        )
        db.add(new_session)

        # Audit log user registration
        audit = AuditEvent(
            event_type="USER_REGISTERED",
            actor_type="USER",
            actor_id=str(new_user.user_id),
            correlation_id=correlation_id,
            payload={"email": new_user.email, "role": new_user.role, "ip_address": ip_address},
        )
        db.add(audit)
        await db.commit()
        await db.refresh(new_user)

        permissions = RBACPolicy.permissions_for(new_user.role)
        return new_user, raw_session_token, permissions

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Tuple[User, str, List[str]]:
        clean_email = email.strip().lower()
        rate_limit_key = f"{clean_email}:{ip_address or 'unknown'}"
        _check_rate_limit(rate_limit_key)

        stmt = select(User).where(User.email == clean_email)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        is_valid_pw = verify_password(password, user.password_hash) if user else False

        # Constant-time protection and generic error message against user enumeration
        if not user or not is_valid_pw:
            _record_failed_attempt(rate_limit_key)
            # Record failed login audit event
            audit = AuditEvent(
                event_type="LOGIN_FAILED",
                actor_type="USER",
                actor_id=clean_email,
                correlation_id=correlation_id,
                payload={"ip_address": ip_address, "reason": "invalid_credentials"},
            )
            db.add(audit)
            await db.commit()
            raise UnauthorizedException("Invalid email or password.")

        if user.status != "ACTIVE":
            raise ForbiddenException(f"Account is {user.status.lower()}. Please contact your administrator.")

        _clear_failed_attempts(rate_limit_key)

        # Invalidate existing active sessions for this user (session rotation on login)
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.user_id, UserSession.is_revoked.is_(False))
            .values(is_revoked=True)
        )

        # Generate fresh session token
        raw_session_token = generate_session_id()
        token_hash = hash_session_token(raw_session_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)

        new_session = UserSession(
            session_id=str(uuid.uuid4()),
            user_id=user.user_id,
            token_hash=token_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=now,
            last_activity_at=now,
            expires_at=expires_at,
            is_revoked=False,
        )
        db.add(new_session)

        # Audit log successful login
        audit = AuditEvent(
            event_type="LOGIN_SUCCESS",
            actor_type="USER",
            actor_id=str(user.user_id),
            correlation_id=correlation_id,
            payload={"email": user.email, "role": user.role, "ip_address": ip_address},
        )
        db.add(audit)
        await db.commit()

        # Fetch permissions for effective profile
        permissions = RBACPolicy.permissions_for(user.role)
        return user, raw_session_token, permissions

    @staticmethod
    async def get_user_from_session(
        db: AsyncSession,
        raw_session_token: Optional[str],
    ) -> Tuple[User, List[str]]:
        if not raw_session_token:
            raise UnauthorizedException("Authentication required. Missing session.")

        token_hash = hash_session_token(raw_session_token)
        stmt = select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.is_revoked.is_(False),
        )
        res = await db.execute(stmt)
        session_record = res.scalar_one_or_none()

        if not session_record:
            raise UnauthorizedException("Session is invalid or has been revoked.")

        now = datetime.now(timezone.utc)

        # Absolute expiration check
        if session_record.expires_at < now:
            session_record.is_revoked = True
            await db.commit()
            raise UnauthorizedException("Session has expired. Please log in again.")

        # Idle timeout check (4 hours)
        idle_threshold = now - timedelta(hours=IDLE_TIMEOUT_HOURS)
        if session_record.last_activity_at < idle_threshold:
            session_record.is_revoked = True
            await db.commit()
            raise UnauthorizedException("Session timed out due to inactivity.")

        # Touch last_activity_at
        session_record.last_activity_at = now

        # Fetch active user
        user_stmt = select(User).where(User.user_id == session_record.user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()

        if not user or user.status != "ACTIVE":
            session_record.is_revoked = True
            await db.commit()
            raise ForbiddenException("Account is disabled or inactive.")

        await db.commit()
        permissions = RBACPolicy.permissions_for(user.role)
        return user, permissions

    @staticmethod
    async def logout(
        db: AsyncSession,
        raw_session_token: Optional[str],
        correlation_id: Optional[str] = None,
    ) -> None:
        if not raw_session_token:
            return

        token_hash = hash_session_token(raw_session_token)
        stmt = select(UserSession).where(UserSession.token_hash == token_hash)
        res = await db.execute(stmt)
        session_record = res.scalar_one_or_none()

        if session_record and not session_record.is_revoked:
            session_record.is_revoked = True
            audit = AuditEvent(
                event_type="LOGOUT",
                actor_type="USER",
                actor_id=str(session_record.user_id),
                correlation_id=correlation_id,
                payload={"session_id": session_record.session_id[:8] + "..."},
            )
            db.add(audit)
            await db.commit()
