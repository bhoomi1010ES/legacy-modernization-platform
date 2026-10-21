"""Cryptographic primitives, password hashing, and session token security."""

import hashlib
import secrets
import bcrypt


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt with work factor 12."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash in constant time."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def generate_session_id() -> str:
    """Generates an unpredictable 256-bit cryptographically secure session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Calculates SHA-256 hash of a session token for secure server-side storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
